"""Observe and control the Android tasks belonging to one embedded display."""

import asyncio
import json
from contextlib import suppress
from gettext import gettext as _
from pathlib import Path

from waydroid_helper.util.log import logger


class AndroidTasks:

    def __init__(self, serial, update, notify, unavailable=None):
        self.serial = serial
        self.update = update
        self.notify = notify
        self.unavailable = unavailable or (lambda: self.update([], 0))
        self.writer = None
        self.retry_delay = 1

    def command(self, action, task_id):
        if self.writer and not self.writer.is_closing():
            logger.debug("Android tab %s task %s on %s", action, task_id, self.serial)
            self.writer.write(f"{action} {task_id}\n".encode("ascii"))

    async def observe(self):
        while True:
            try:
                await self._session()
            except Exception:
                logger.exception("Android task monitor disconnected on %s", self.serial)
                if self.retry_delay == 1:
                    self.notify(_("Application tabs disconnected. Reconnecting…"))
            self.unavailable()
            await asyncio.sleep(self.retry_delay)
            self.retry_delay = min(self.retry_delay * 2, 15)

    async def _session(self):
        dex = (
            Path(__file__).resolve().parents[1] / "android/task-monitor.dex"
        ).read_bytes()
        # A non-PTY shell carries the DEX followed by newline-delimited commands.
        # head consumes exactly the DEX bytes before app_process inherits stdin.
        # Each connection owns its temporary file, including on concurrent starts.
        script = (
            'dir=$(mktemp -d /data/local/tmp/wdh-tabs-XXXXXX) || exit 1; dex="$dir/tasks.dex"; '
            'trap \'rm -f "$dex"; rmdir "$dir"\' EXIT; '
            f'head -c {len(dex)} > "$dex" && chmod 444 "$dex" && '
            'CLASSPATH="$dex" app_process / org.waydroid.helper.TaskMonitor'
        )
        proc = await asyncio.create_subprocess_exec(
            "adb",
            "-s",
            self.serial,
            "shell",
            "-T",
            script,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        errors = asyncio.create_task(self._log_errors(proc.stderr))
        try:
            proc.stdin.write(dex)
            await proc.stdin.drain()
            line = await asyncio.wait_for(proc.stdout.readline(), timeout=12)
            while line:
                message = json.loads(line)
                if "error" in message:
                    self.notify(_("Could not change the Android task."))
                else:
                    self.retry_delay = 1
                    self.writer = proc.stdin
                    self.update(message["apps"], message["active"])
                line = await proc.stdout.readline()
            raise ConnectionError("Android task monitor closed its output")
        finally:
            self.writer = None
            proc.stdin.close()
            try:
                await asyncio.wait_for(proc.wait(), timeout=2)
            except TimeoutError:
                with suppress(ProcessLookupError):
                    proc.kill()
                await proc.wait()
            await errors

    async def _log_errors(self, stream):
        async for line in stream:
            logger.warning(
                "Android task monitor on %s: %s",
                self.serial,
                line.decode(errors="replace").rstrip(),
            )
