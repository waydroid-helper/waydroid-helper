# pyright: reportUnknownArgumentType=false, reportUnknownParameterType=false, reportMissingParameterType=false
import asyncio
from dataclasses import dataclass, field
from collections import deque
import os
import shlex
from typing import TypedDict


class SubprocessResult(TypedDict):
    command: str
    key: str
    returncode: int
    stdout: str
    stderr: str
    process: asyncio.subprocess.Process | None


class SubprocessError(Exception):
    def __init__(self, returncode: int, stderr: str | bytes):
        self.returncode: int = returncode
        self.stderr: str = (
            stderr.decode(errors="replace")
            if isinstance(stderr, bytes)
            else stderr
        )
        super().__init__(
            f"Command failed with return code {returncode}: {self.stderr}"
        )


@dataclass
class SubprocessJob:
    command: str
    key: str
    process: asyncio.subprocess.Process | None = None
    _stdout_buf: deque[bytes] = field(default_factory=lambda: deque(maxlen=200))
    _stderr_buf: deque[bytes] = field(default_factory=lambda: deque(maxlen=200))
    _stdout_task: asyncio.Task[None] | None = None
    _stderr_task: asyncio.Task[None] | None = None
    _result_task: asyncio.Task[SubprocessResult] | None = None

    def __await__(self):
        return self.get().__await__()

    def start_capture(self) -> None:
        if self.process.stdout is not None and self._stdout_task is None:
            self._stdout_task = asyncio.create_task(
                self._drain_stream(self.process.stdout, self._stdout_buf)
            )
        if self.process.stderr is not None and self._stderr_task is None:
            self._stderr_task = asyncio.create_task(
                self._drain_stream(self.process.stderr, self._stderr_buf)
            )

    async def _drain_stream(
        self,
        stream: asyncio.StreamReader,
        buf: deque[bytes],
    ) -> None:
        try:
            while True:
                chunk = await stream.readline()
                if not chunk:
                    break
                buf.append(chunk)
        except Exception:
            # 捕获输出不应影响主流程（例如进程提前退出/pipe 关闭）
            return

    def stdout_text(self) -> str:
        return b"".join(self._stdout_buf).decode(errors="replace")

    def stderr_text(self) -> str:
        return b"".join(self._stderr_buf).decode(errors="replace")

    async def _join_capture_tasks(self) -> None:
        for t in (self._stdout_task, self._stderr_task):
            if t is not None:
                try:
                    await t
                except Exception:
                    pass

    async def _wait_for_result(self) -> SubprocessResult:
        if self.process is None:
            raise RuntimeError("Process has not been started")

        await self.process.wait()
        await self._join_capture_tasks()

        return {
            "command": self.command,
            "key": self.key,
            "returncode": self.process.returncode if self.process.returncode is not None else 1,
            "stdout": self.stdout_text(),
            "stderr": self.stderr_text(),
            "process": None,
        }

    def _ensure_result_task(self) -> asyncio.Task[SubprocessResult]:
        if self._result_task is None:
            self._result_task = asyncio.create_task(self._wait_for_result())
        return self._result_task

    async def get(
        self,
        timeout: float | None = None,
        check: bool = False,
    ) -> SubprocessResult:
        task = self._ensure_result_task()
        if timeout is None:
            result = await task
        else:
            result = await asyncio.wait_for(asyncio.shield(task), timeout=timeout)
        if check and result["returncode"] != 0:
            raise SubprocessError(result["returncode"], result["stderr"])
        return result

    async def wait(
        self,
        timeout: float | None = None,
        check: bool = False,
    ) -> SubprocessResult:
        return await self.get(timeout=timeout, check=check)

    async def verify_started(self, timeout: float) -> None:
        try:
            await self.get(timeout=timeout, check=True)
        except asyncio.TimeoutError:
            return

    def done(self) -> bool:
        return self._result_task is not None and self._result_task.done()

    def cancel(self) -> bool:
        cancelled = False
        if self._result_task is not None:
            cancelled = self._result_task.cancel()
        if self.process is not None and self.process.returncode is None:
            self.process.kill()
            cancelled = True
        return cancelled

    def task(self) -> asyncio.Task[SubprocessResult]:
        return self._ensure_result_task()


class SubprocessManager:
    _instance = None # pyright: ignore[reportUnannotatedClassAttribute]
    _semaphore: asyncio.Semaphore | None = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(SubprocessManager, cls).__new__(cls, *args, **kwargs)
            cls._semaphore = asyncio.Semaphore(10)
        return cls._instance

    def is_running_in_flatpak(self):
        return "container" in os.environ

    def _build_env(self, env: dict[str, str] | None = None) -> dict[str, str]:
        return {
            **os.environ.copy(),
            **(env or {}),
            "PATH": f"/usr/bin:/bin:{os.environ['PATH']}",
            "LD_LIBRARY_PATH": "",
            "PYTHONPATH": "",
            "PYTHONHOME": "",
        }

    async def _spawn_process_unlocked(
        self,
        command: str,
        flag: bool = False,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> asyncio.subprocess.Process:
        if self._semaphore is None:
            raise RuntimeError("Semaphore is not initialized")

        env_vars = self._build_env(env)
        if shell:
            return await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                env=env_vars,
                preexec_fn=os.setsid if flag else None,
            )
        command_list = shlex.split(command)
        return await asyncio.create_subprocess_exec(
            *command_list,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env_vars,
            preexec_fn=os.setsid if flag else None,
        )

    async def _spawn_process(
        self,
        command: str,
        flag: bool = False,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> asyncio.subprocess.Process:
        if self._semaphore is None:
            raise RuntimeError("Semaphore is not initialized")

        async with self._semaphore:
            return await self._spawn_process_unlocked(
                command=command,
                flag=flag,
                env=env,
                shell=shell,
            )

    async def start(
        self,
        command: str,
        flag: bool = False,
        key: str | None = None,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> SubprocessJob:
        process = await self._spawn_process(
            command=command,
            flag=flag,
            env=env,
            shell=shell,
        )
        job = SubprocessJob(
            command=command,
            key=key if key else command,
            process=process,
        )
        job.start_capture()
        return job

    async def _run_and_collect(
        self,
        command: str,
        flag: bool = False,
        key: str | None = None,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
        shell: bool = False,
    ) -> SubprocessResult:
        if self._semaphore is None:
            raise RuntimeError("Semaphore is not initialized")

        async with self._semaphore:
            process = await self._spawn_process_unlocked(
                command=command,
                flag=flag,
                env=env,
                shell=shell,
            )
            try:
                if timeout is None:
                    stdout, stderr = await process.communicate()
                else:
                    stdout, stderr = await asyncio.wait_for(
                        process.communicate(),
                        timeout=timeout,
                    )
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
                raise

            result :SubprocessResult= {
                "command": command,
                "key": key if key else command,
                "returncode": process.returncode if process.returncode is not None else 1,
                "stdout": stdout.decode(),
                "stderr": stderr.decode(),
                "process": None,  # 进程已完成，不需要跟踪
            }
            # print(
            #     json.dumps(
            #         result,
            #         sort_keys=True,
            #         indent=4,
            #         separators=(", ", ": "),
            #         ensure_ascii=False,
            #     )
            # )
            if result["returncode"] != 0:
                raise SubprocessError(result["returncode"], result["stderr"])

            return result

    def submit(
        self,
        command: str,
        flag: bool = False,
        key: str | None = None,
        env: dict[str, str] | None = None,
        timeout: float | None = None,
        shell: bool = False,
    ) -> SubprocessJob:
        return SubprocessJob(
            command=command,
            key=key if key else command,
            _result_task=asyncio.create_task(
                self._run_and_collect(
                    command=command,
                    flag=flag,
                    key=key,
                    env=env,
                    timeout=timeout,
                    shell=shell,
                )
            ),
        )
