#!/usr/bin/env python3
"""ADB and scrcpy-server lifecycle orchestration."""

from __future__ import annotations

import asyncio

from waydroid_helper.controller.core.runtime import ScreenGeometry
from waydroid_helper.controller.core.server import Server
from waydroid_helper.util import AdbHelper, logger


MAX_RETRY_ATTEMPTS = 5
RETRY_DELAY_SECONDS = 3


class ScrcpyLifecycleService:
    """Owns startup and cleanup side effects for one controller window."""

    def __init__(
        self,
        server: Server,
        adb_helper: AdbHelper,
        screen_geometry: ScreenGeometry,
    ) -> None:
        self.server = server
        self.adb_helper = adb_helper
        self.screen_geometry = screen_geometry
        self.setup_task: asyncio.Task[None] = asyncio.create_task(self.setup())

    async def setup(self) -> None:
        """Push scrcpy-server and start it on the device, with retry logic."""
        await self.server.wait_started()

        if not self.server.server:
            return

        for attempt in range(MAX_RETRY_ATTEMPTS):
            try:
                if not await self.adb_helper.connect():
                    await asyncio.sleep(RETRY_DELAY_SECONDS)
                    continue

                screen_resolution = await self.adb_helper.get_screen_resolution()
                if screen_resolution:
                    self.screen_geometry.set_resolution(*screen_resolution)

                if not await self.adb_helper.push_scrcpy_server():
                    await asyncio.sleep(RETRY_DELAY_SECONDS)
                    continue

                scid, socket_name = self.adb_helper.generate_scid()
                if not await self.adb_helper.reverse_tunnel(
                    socket_name, self.server.port
                ):
                    await asyncio.sleep(RETRY_DELAY_SECONDS)
                    continue

                if not await self.adb_helper.start_scrcpy_server(scid):
                    await asyncio.sleep(RETRY_DELAY_SECONDS)
                    continue

                return

            except asyncio.CancelledError:
                return
            except Exception:
                logger.exception("Failed to set up scrcpy on attempt %s", attempt + 1)
                await asyncio.sleep(RETRY_DELAY_SECONDS)

    async def close_server(self) -> None:
        await self.server.close()

    async def cleanup(self) -> None:
        if not self.setup_task.done():
            self.setup_task.cancel()
        await self.adb_helper.remove_reverse_tunnel()
