"""Operations supported by the Waydroid multi-instance command line."""

import asyncio
import ipaddress
import re
from dataclasses import dataclass
from gettext import gettext as _

from waydroid_helper.controller.app.emulator_display import device_command
from waydroid_helper.controller.app.embedded_session import session_status
from waydroid_helper.waydroid_instance import DEFAULT_INSTANCE, instance_name, waydroid_output


@dataclass(frozen=True)
class Device:
    ident: str
    running: bool


class InstanceService:
    async def list_devices(self):
        # The installed list includes stopped devices. The session list only
        # describes currently running instances and may include a starting one.
        installed, running = await asyncio.gather(
            waydroid_output("instance", "list"), waydroid_output("session", "list")
        )
        active = set(running.splitlines())
        names = {instance_name(name) for name in installed.splitlines()}
        return [Device(name, name in active) for name in sorted(names, key=lambda n: (n != DEFAULT_INSTANCE, n))]

    async def create(self, name):
        await waydroid_output("instance", "create", self._named_instance(name))

    async def remove(self, name):
        # The service checks again under its lifecycle lock so another client
        # cannot race deletion by starting the same device.
        await waydroid_output("instance", "remove", self._named_instance(name))

    async def stop(self, name):
        await waydroid_output("session", "stop", instance=name)

    async def android_version(self, name):
        release = await waydroid_output("prop", "get", "ro.build.version.release", instance=name)
        return release if re.fullmatch(r"[0-9][A-Za-z0-9._-]{0,31}", release) else ""

    async def clear_cache(self, name):
        status = await session_status(name)
        try:
            address = ipaddress.IPv4Address(status.get("IP address"))
        except ipaddress.AddressValueError as error:
            raise RuntimeError(_("Android input is not connected.")) from error
        # Android's package manager trims app caches and leaves app data and
        # installed packages intact. Target only the selected instance's ADB.
        await waydroid_output("adb", "connect", instance=name)
        await device_command(f"{address}:5555", "shell", "pm", "trim-caches", "999G", timeout=180)

    @staticmethod
    def _named_instance(name):
        if instance_name(name) == DEFAULT_INSTANCE:
            raise ValueError(_("Waydroid reserves the default device."))
        return name
