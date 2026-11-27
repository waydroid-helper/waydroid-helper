"""Provision the optional vendor GNSS driver when the user opens the map."""

import asyncio
from contextlib import asynccontextmanager
from gettext import gettext as _
import os
from pathlib import Path
import shutil
import tempfile

import httpx
from gi.repository import Gtk

from waydroid_helper.controller.app.emulator_display import device_command
from waydroid_helper import gnss_install
from waydroid_helper.util.log import logger

RELEASE = f"https://github.com/ayasa520/waydroid_stuff/releases/download/{gnss_install.RELEASE_VERSION}"


async def guest_arch(serial):
    sdk, abis = await asyncio.gather(*(
        device_command(serial, "shell", "getprop", prop) for prop in
        ("ro.vendor.build.version.sdk", "ro.vendor.product.cpu.abilist64")
    ))
    # App ABI lists can include Houdini's translated ARM binaries. Select the
    # vendor ABI because init loads this service directly in the guest.
    arch = {"x86_64": "x86_64", "arm64-v8a": "arm64"}.get(abis.decode().strip().split(",")[0])
    if sdk.strip() != b"33" or not arch:
        raise RuntimeError(_("The GNSS driver is available for Android 13 on x86_64 and ARM64."))
    return arch


async def download(arch):
    package = bytearray()
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
            async with client.stream("GET", f"{RELEASE}/{arch}.zip") as response:
                response.raise_for_status()
                async for chunk in response.aiter_bytes():
                    package.extend(chunk)
                    if len(package) > gnss_install.MAX_BYTES:
                        raise ValueError
        gnss_install.verify(package, arch)
    except httpx.HTTPError as error:
        raise RuntimeError(_("Could not download the GNSS driver. Check your connection and try again.")) from error
    except ValueError as error:
        raise RuntimeError(_("The GNSS driver download failed its integrity check.")) from error
    return package


@asynccontextmanager
async def authorized_install(instance, arch, package):
    script = Path(gnss_install.__file__).with_suffix(".py")
    with tempfile.TemporaryDirectory(prefix="waydroid-gnss-") as temp:
        # An AppImage FUSE mount may be inaccessible to a different UID. Use
        # its packaged standalone script, in a private per-invocation directory.
        if os.environ.get("APPIMAGE") or not os.access(script, os.X_OK):
            script = Path(shutil.copyfile(script, Path(temp) / "gnss_install.py"))
            script.chmod(0o700)
        proc = await asyncio.create_subprocess_exec(
            "pkexec", "--disable-internal-agent", str(script), instance, arch,
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
        )

        async def check():
            diagnostic = (await proc.stderr.read()).decode(errors="replace").strip()
            if await proc.wait():
                if proc.returncode in (126, 127):
                    raise PermissionError(_("Administrator authorization was not granted."))
                raise RuntimeError(diagnostic or _("Could not install the GNSS driver."))

        async def install():
            proc.stdin.write(package)
            try:
                await proc.stdin.drain()
            finally:
                proc.stdin.close()
            await check()

        authorized = False
        try:
            if (await proc.stdout.readline()).strip() != b"READY":
                proc.stdin.close()
                await check()
                raise RuntimeError(_("Could not install the GNSS driver."))
            authorized = True
            yield install
        finally:
            # EOF before the package arrives tells the privileged worker to
            # exit without touching the overlay, including on window shutdown.
            proc.stdin.close()
            if not authorized and proc.returncode is None:
                try:
                    proc.terminate()
                except (PermissionError, ProcessLookupError):
                    pass
            # A polkit agent may still be prompting under a different UID.
            # Closing stdin is sufficient: the worker checks EOF before any
            # write. Do not block window teardown on a pending system dialog.
            if proc.returncode is None:
                asyncio.create_task(proc.wait())


class LocationSetup:
    def __init__(self, window, location, show_map):
        self.window = window
        self.location = location
        self.show_map = show_map
        self.operation = None
        self.dialog = None

    def open(self):
        if self.dialog:
            self.dialog.present()
        elif self.operation is None or self.operation.done():
            self.operation = asyncio.create_task(self._open())

    async def close(self):
        if self.operation and not self.operation.done():
            self.operation.cancel()
            await asyncio.gather(self.operation, return_exceptions=True)

    async def _confirm(self):
        from waydroid_helper.compat_widget import MessageDialog

        answer = asyncio.get_running_loop().create_future()
        upgrade = self.location.needs_driver_update
        dialog = self.dialog = MessageDialog(
            heading=_("Update the GNSS driver?") if upgrade else _("Install the GNSS driver?"),
            body=_("The installed GNSS driver reports incorrect dates. Updating it will restart "
                   "this Android device and close open Android apps.") if upgrade else
                 _("Virtual location needs a GNSS driver. Waydroid Helper will download it, "
                   "ask for administrator authorization, and restart this Android device to install it. "
                   "Open Android apps will close."),
            parent=self.window,
        )
        dialog.add_response(Gtk.ResponseType.CANCEL, _("Cancel"))
        dialog.add_response(Gtk.ResponseType.OK, _("Update and restart") if upgrade else _("Install and restart"))
        dialog.set_response_appearance(Gtk.ResponseType.OK, "suggested-action")
        dialog.set_default_response(Gtk.ResponseType.CANCEL)

        def respond(_dialog, response):
            if not answer.done():
                answer.set_result(response in (Gtk.ResponseType.OK, Gtk.ResponseType.OK.value_nick))

        dialog.connect("response", respond)
        dialog.present()
        try:
            return await answer
        finally:
            self.dialog = None
            if answer.cancelled():
                dialog.close()

    async def _open(self):
        try:
            if not await self.location.has_driver() or self.location.needs_driver_update:
                serial = self.location.serial
                arch = await guest_arch(serial)
                if not await self._confirm():
                    return
                self.window.show_notification(_("Downloading the GNSS driver…"))
                package = await download(arch)
                async with authorized_install(self.location.instance, arch, package) as install:
                    if self.location.serial != serial or not self.window.restart_now(while_stopped=install):
                        raise RuntimeError(_("The device session changed. Please try again."))
                    await self.window.start_restart

                # startup lives until disconnect; wait for this boot's ADB
                # attachment or a failed startup, whichever happens first.
                attached = asyncio.create_task(self.location.attached.wait())
                try:
                    await asyncio.wait((attached, self.window.startup), return_when=asyncio.FIRST_COMPLETED)
                    if (not self.location.attached.is_set() or not await self.location.has_driver()
                            or self.location.needs_driver_update):
                        raise RuntimeError(_("The GNSS driver did not start on this device."))
                finally:
                    attached.cancel()
            self.show_map()
        except Exception as error:
            logger.warning("Virtual location setup for %s: %s", self.location.instance, error, exc_info=True)
            self.window.show_notification(str(error))
