# pyright: reportUnknownArgumentType=false, reportUnknownParameterType=false, reportMissingParameterType=false
import asyncio
from dataclasses import dataclass, field
from collections import deque
import os
import shlex
from typing import Deque, TypedDict


class SubprocessResult(TypedDict):
    command: str
    key: str 
    returncode: int
    stdout: str
    stderr: str
    process: asyncio.subprocess.Process | None

class SubprocessError(Exception):
    def __init__(self, returncode: int, stderr: bytes):
        self.returncode: int = returncode
        self.stderr: bytes = stderr
        super().__init__(
            f"Command failed with return code {returncode}: {stderr.decode()}"
        )


@dataclass
class SubprocessHandle:
    command: str
    key: str
    process: asyncio.subprocess.Process
    _stdout_buf: deque[bytes] = field(default_factory=lambda: deque(maxlen=200))
    _stderr_buf: deque[bytes] = field(default_factory=lambda: deque(maxlen=200))
    _stdout_task: asyncio.Task[None] | None = None
    _stderr_task: asyncio.Task[None] | None = None

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
        buf: Deque[bytes],
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

    async def wait(self, timeout: float | None = None) -> SubprocessResult:
        if timeout is None:
            await self.process.wait()
        else:
            await asyncio.wait_for(self.process.wait(), timeout=timeout)

        # 确保把尾部输出读完
        for t in (self._stdout_task, self._stderr_task):
            if t is not None:
                try:
                    await t
                except Exception:
                    pass

        return {
            "command": self.command,
            "key": self.key,
            "returncode": self.process.returncode if self.process.returncode is not None else 1,
            "stdout": self.stdout_text(),
            "stderr": self.stderr_text(),
            "process": None,
        }


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

    async def run_async(
        self,
        command: str,
        flag: bool = False,
        key: str | None = None,
        env: dict[str, str] | None = None,
        shell: bool = False,
    ) -> SubprocessHandle:
        """
        异步启动子进程并持续捕获 stdout/stderr。
        用于 wait=False 但调用方仍需要拿到 stderr（比如秒退原因）的场景。
        """
        if self._semaphore is None:
            raise RuntimeError("Semaphore is not initialized")

        env = env or {}
        async with self._semaphore:
            env_vars = {
                **os.environ.copy(),
                **env,
                "PATH": f"/usr/bin:/bin:{os.environ['PATH']}",
                "LD_LIBRARY_PATH": "",
                "PYTHONPATH": "",
                "PYTHONHOME": "",
            }
            if shell:
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env_vars,
                    preexec_fn=os.setsid if flag else None,
                )
            else:
                command_list = shlex.split(command)
                process = await asyncio.create_subprocess_exec(
                    *command_list,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env_vars,
                    preexec_fn=os.setsid if flag else None,
                )

        handle = SubprocessHandle(
            command=command,
            key=key if key else command,
            process=process,
        )
        handle.start_capture()
        return handle

    async def run(
        self,
        command: str,
        flag: bool = False,
        key: str | None = None,
        env: dict[str, str] | None = None,
        wait: bool = True,
        timeout: float | None = None,
        shell: bool = False,
    )->SubprocessResult:
        if self._semaphore is None:
            raise RuntimeError("Semaphore is not initialized")
        
        env = env or {}  # Initialize empty dict if env is None
        async with self._semaphore:
            # command_list = command.split(" ")
            # if self.is_running_in_flatpak():
            #     if (
            #         "pkexec" == command_list[0]
            #         or "waydroid" == command_list[0]
            #         or "waydroid" == command_list[1]
            #     ):
            #         command = f'flatpak-spawn --host bash -c "{command}"'
            env_vars = {
                **os.environ.copy(),
                **env,
                "PATH": f"/usr/bin:/bin:{os.environ['PATH']}",
                "LD_LIBRARY_PATH": "",
                "PYTHONPATH": "",
                "PYTHONHOME": "",
            }
            if shell:
                process = await asyncio.create_subprocess_shell(
                    command,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env_vars,
                    preexec_fn=os.setsid if flag else None,
                )
            else:
                command_list = shlex.split(command)
                process = await asyncio.create_subprocess_exec(
                    *command_list,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                    env=env_vars,
                    preexec_fn=os.setsid if flag else None,
                )

            if wait:
                if timeout:
                    try:
                        await asyncio.wait_for(process.wait(), timeout=timeout)
                    except asyncio.TimeoutError:
                        process.kill()  # 超时强杀
                        await process.wait()
                stdout, stderr = await process.communicate()
            else:
                # 兼容旧接口：仍返回 process，但不再假装 returncode=0。
                # 若调用方需要 stderr/stdout，请使用 run_async()。
                return {
                    "command": command,
                    "key": key if key else command,
                    "returncode": -1,  # 表示“未等待，不确定”
                    "stdout": "",
                    "stderr": "",
                    "process": process,  # 返回进程对象以便跟踪
                }

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
                raise SubprocessError(result["returncode"], stderr)

            return result
