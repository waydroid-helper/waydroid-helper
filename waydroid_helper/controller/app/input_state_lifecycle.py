#!/usr/bin/env python3
"""ADB lifecycle for the Android input-state companion service."""

from __future__ import annotations

import asyncio
import os

from waydroid_helper.controller.core.input_state_server import (
    ANDROID_INPUT_STATE_PORT,
    AndroidInputStateServer,
)
from waydroid_helper.util import AdbHelper, logger


INPUT_STATE_PORT = ANDROID_INPUT_STATE_PORT
INPUT_STATE_DEVICE_PORT = INPUT_STATE_PORT
COMPANION_PACKAGE = "com.jaoushingan.waydroidhelper.accessibilitybridge"
COMPANION_SERVICE = (
    f"{COMPANION_PACKAGE}/"
    f"{COMPANION_PACKAGE}.TextInputAccessibilityService"
)


def _get_companion_apk_path() -> str:
    override_path = os.environ.get("WAYDROID_HELPER_INPUT_STATE_APK")
    if override_path:
        return override_path

    pkgdatadir = os.environ.get("PKGDATADIR")
    if pkgdatadir:
        return os.path.join(
            pkgdatadir,
            "waydroid_helper/android/text-input-accessibility-bridge/app-debug.apk",
        )

    return os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "../../../android/text-input-accessibility-bridge/app/build/outputs/apk/debug/app-debug.apk",
    )


class AndroidInputStateLifecycleService:
    """Starts the host socket and keeps the Android companion pointed at it."""

    def __init__(
        self,
        server: AndroidInputStateServer,
        adb_helper: AdbHelper,
    ) -> None:
        self.server = server
        self.adb_helper = adb_helper
        self.setup_task: asyncio.Task[None] = asyncio.create_task(self.setup())

    async def setup(self) -> None:
        await self.server.wait_started()
        try:
            if not await self.adb_helper.connect():
                logger.warning("Cannot set up Android input-state bridge: ADB connect failed")
                return

            if not await self.adb_helper.reverse_tcp_tunnel(
                INPUT_STATE_DEVICE_PORT,
                self.server.port,
            ):
                logger.warning("Cannot set up Android input-state bridge: adb reverse failed")
                return
            logger.info(
                "Android input-state reverse tunnel ready: tcp:%s -> tcp:%s",
                INPUT_STATE_DEVICE_PORT,
                self.server.port,
            )
            await self._install_companion_if_available()
            await self._enable_accessibility_service_if_allowed()
        except asyncio.CancelledError:
            return
        except Exception:
            logger.exception("Failed to set up Android input-state bridge")

    async def cleanup(self) -> None:
        if not self.setup_task.done():
            self.setup_task.cancel()
        await self.server.close()
        await self.adb_helper.remove_reverse_tunnel(f"tcp:{INPUT_STATE_DEVICE_PORT}")

    async def _install_companion_if_available(self) -> None:
        apk_path = _get_companion_apk_path()
        if not os.path.exists(apk_path):
            logger.info(
                "Android input-state companion APK not found at %s; "
                "skip automatic install",
                apk_path,
            )
            return

        await self.adb_helper.install_apk(apk_path)

    async def _enable_accessibility_service_if_allowed(self) -> None:
        if await self.adb_helper.enable_accessibility_service(COMPANION_SERVICE):
            logger.info("Requested Android accessibility service enable: %s", COMPANION_SERVICE)
