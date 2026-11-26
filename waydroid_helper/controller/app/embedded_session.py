"""Own one Waydroid session attached to the window's Wayland socket."""

import asyncio
import ipaddress
import os
import uuid
from gettext import gettext as _

import gi

from waydroid_helper.util.log import logger
from waydroid_helper.waydroid_instance import DEFAULT_INSTANCE, waydroid_command, waydroid_output


def compositor_type():
    try:
        gi.require_version("Casilda", "1.0")
        from gi.repository import Casilda

        return Casilda.Compositor
    except (ImportError, ValueError) as error:
        raise RuntimeError(
            _("The emulator window requires Casilda 1.0 and its GTK typelib.")
        ) from error


async def session_status(instance=DEFAULT_INSTANCE):
    output = await waydroid_output("status", instance=instance)
    fields = {}
    for line in output.splitlines():
        name, separator, value = line.partition(":")
        if separator:
            fields[name.strip()] = value.strip()
    return fields


async def stop_confirmed_session(previous_display, instance=DEFAULT_INSTANCE):
    # The GTK confirmation may have been open while another launcher acted.
    # Check the display again before stopping, and wait for D-Bus ownership
    # to disappear before allowing show-full-ui to create the replacement.
    status = await session_status(instance)
    if status.get("Session") == "STOPPED":
        return
    if not previous_display or status.get("Wayland display") != previous_display:
        raise RuntimeError(_("The active Waydroid session changed. Please try again."))
    await waydroid_output("session", "stop", instance=instance)
    async with asyncio.timeout(20):
        while True:
            status = await session_status(instance)
            if status.get("Session") == "STOPPED":
                return
            if status.get("Wayland display") not in (None, previous_display):
                raise RuntimeError(_("Another Waydroid session is running."))
            await asyncio.sleep(0.15)


class EmbeddedSession:
    def __init__(self, instance=DEFAULT_INSTANCE):
        self.instance = instance
        self.socket = f"wdh-{uuid.uuid4().hex}"
        self.launcher = None

    async def start(self, *, dpi=None):
        # Each instance owns a separate session and socket. show-full-ui can
        # silently reuse that instance's active display, so check ownership
        # again after any launcher confirmation.
        status = await session_status(self.instance)
        if status.get("Session") == "STOPPED":
            env = {**os.environ, "WAYLAND_DISPLAY": self.socket}
            # Waydroid's session launcher can set the boot density in units of
            # 20 DPI. Custom values are set exactly by Android's window manager.
            if dpi and dpi % 20 == 0:
                env["GRID_UNIT_PX"] = str(dpi // 20)
            self.launcher = await asyncio.create_subprocess_exec(
                *waydroid_command("show-full-ui", instance=self.instance),
                env=env,
            )
            logger.info(
                "Starting embedded Waydroid on %s (pid %s)", self.socket, self.launcher.pid
            )
        elif status.get("Wayland display") != self.socket or not self.launcher:
            raise RuntimeError(_("Another Waydroid session is running."))
        async with asyncio.timeout(100):
            while True:
                status = await session_status(self.instance)
                display = status.get("Wayland display")
                if display and display != self.socket:
                    raise RuntimeError(_("Another Waydroid session is running."))
                if display == self.socket and status.get("IP address") not in (None, "UNKNOWN"):
                    # The IP lease can predate Android's platform binder service.
                    # Its first property read may time out while Android boots.
                    try:
                        booted = await waydroid_output(
                            "prop", "get", "sys.boot_completed", instance=self.instance
                        )
                    except TimeoutError:
                        logger.info("Waiting for Android platform service on %s", display)
                        continue
                    if booted == "1":
                        return str(ipaddress.IPv4Address(status["IP address"]))
                if self.launcher.returncode is not None:
                    raise RuntimeError(
                        _("Waydroid exited during startup (status %s).")
                        % self.launcher.returncode
                    )
                await asyncio.sleep(0.5)

    async def close(self):
        if self.launcher is None:
            return
        # The launcher also holds the Waydroid user's session service during
        # startup. Terminate it if closed before it has advertised our socket.
        try:
            if (await session_status(self.instance)).get("Wayland display") == self.socket:
                await waydroid_output("session", "stop", instance=self.instance)
        finally:
            if self.launcher.returncode is None:
                self.launcher.terminate()
            try:
                await asyncio.wait_for(self.launcher.wait(), 8)
            except TimeoutError:
                self.launcher.kill()
                await self.launcher.wait()
