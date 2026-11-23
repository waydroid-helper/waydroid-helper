"""Provision the released Android IME and manage explicit opt-in per emulator session."""

import asyncio
import hashlib
import os
import shlex
import tempfile
from gettext import gettext as _
from pathlib import Path

import httpx
from gi.repository import Gtk

from waydroid_helper.controller.app.emulator_display import device_command
from waydroid_helper.util.log import logger


PACKAGE = "org.waydroid.helper.desktopime"
LEGACY_PACKAGE = "org.waydroid.helper.hostime"
PREFERENCE = "emulator-desktop-ime-enabled"
APK_URL = ("https://github.com/waydroid-helper/waydroid-desktop-ime/releases/download/"
           "v0.1.0/waydroid-desktop-ime.apk")
APK_SHA256 = "3d3785e967c172c9e507be32db457f72128a0b9444c4b836aea76aa3c8e7ba89"


async def _android_user(serial):
    user = (await device_command(serial, "shell", "am", "get-current-user")).decode().strip()
    if not user.isdecimal():
        raise RuntimeError(_("Could not identify the current Android user."))
    return user


async def installed_release(serial, user):
    # Match the exact package and the bytes in its installed base APK. Android
    # paths can contain '=' as part of their randomized installation directory.
    listing = await device_command(serial, "shell", "pm", "list", "packages", "-f",
                                   "--user", user, PACKAGE)
    for line in listing.decode().splitlines():
        path, sep, name = line.removeprefix("package:").rpartition("=")
        if sep and name == PACKAGE and path.startswith("/"):
            digest = await device_command(serial, "shell", "sha256sum", shlex.quote(path))
            return digest.split(maxsplit=1)[:1] == [APK_SHA256.encode()]
    return False


async def install_release(serial, user):
    if await installed_release(serial, user):
        return
    # Each attempt owns its directory. Only pass completed, verified bytes to
    # PackageManager; cancellation or a partial download never installs an APK.
    with tempfile.TemporaryDirectory(prefix="waydroid-desktop-ime-") as folder:
        apk = Path(folder) / "waydroid-desktop-ime.apk"
        digest = hashlib.sha256()
        try:
            async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
                async with client.stream("GET", APK_URL) as response:
                    response.raise_for_status()
                    with apk.open("wb") as output:
                        async for chunk in response.aiter_bytes():
                            digest.update(chunk)
                            output.write(chunk)
        except httpx.HTTPError as error:
            raise RuntimeError(_("Could not download the input method. Check your connection and try again.")) from error
        if digest.hexdigest() != APK_SHA256:
            raise ValueError(_("The input method download failed its integrity check."))
        await device_command(serial, "install", "-r", "--user", user, str(apk), timeout=90)
        if not await installed_release(serial, user):
            raise RuntimeError(_("Android could not verify the installed input method."))


class DesktopImeSetup:
    def __init__(self, window, bridge):
        self.window = window
        self.bridge = bridge
        self.serial = None
        self.dialog = None
        self.operation = None
        self.monitor = None
        self.package = None

    def attach(self, serial):
        self.serial = serial
        if self.window.preferences.get_boolean(PREFERENCE):
            self.operation = asyncio.create_task(self._enable(install=False))
        elif os.environ.get("WAYDROID_HELPER_HOST_IME") == "1":
            # Keep existing prototype launches usable until the user opts into
            # the independently signed release. The two packages can coexist.
            self.operation = asyncio.create_task(self._enable(install=False, legacy=True))

    async def detach(self):
        self.serial = None
        if self.dialog:
            self.dialog.close()
            self.dialog = None
        if self.operation:
            self.operation.cancel()
            await asyncio.gather(self.operation, return_exceptions=True)
        await self._stop_monitor()

    async def _stop_monitor(self):
        if self.monitor:
            self.monitor.cancel()
            await asyncio.gather(self.monitor, return_exceptions=True)
            self.monitor = None
        self.package = None

    def configure(self):
        from waydroid_helper.compat_widget import MessageDialog

        if self.dialog:
            self.dialog.present()
            return
        if not self.serial:
            self.window.show_notification(_("Android input is not connected."))
            return
        if self.operation and not self.operation.done():
            self.window.show_notification(_("Setting up the desktop input method…"))
            return
        disable = self.window.preferences.get_boolean(PREFERENCE) and self.package == PACKAGE
        if disable:
            title = _("Turn off the desktop input method?")
            body = _("Android text fields will stop using your computer’s input method.")
            accept = _("Turn off")
        else:
            title = _("Use your computer’s input method?")
            body = _("When you enter an Android text field, key mappings pause so you can type "
                     "and choose candidates with your computer’s input method. When you finish "
                     "entering text, key mappings resume automatically.\n\n"
                     "On first use, Waydroid Helper downloads the input method from its GitHub "
                     "release and installs it in Waydroid.")
            accept = _("Install and enable")
        dialog = self.dialog = MessageDialog(heading=title, body=body, parent=self.window)
        dialog.add_response(Gtk.ResponseType.CANCEL, _("Cancel"))
        dialog.add_response(Gtk.ResponseType.OK, accept)
        dialog.set_response_appearance(Gtk.ResponseType.OK, "suggested-action")
        dialog.set_default_response(Gtk.ResponseType.CANCEL)

        def respond(_dialog, response):
            self.dialog = None
            if response not in (Gtk.ResponseType.OK, Gtk.ResponseType.OK.value_nick):
                return
            if self.serial and not (self.operation and not self.operation.done()):
                self.operation = asyncio.create_task(self._disable() if disable else self._enable(install=True))

        dialog.connect("response", respond)
        dialog.present()

    async def _disable(self):
        if not self.window.preferences.set_boolean(PREFERENCE, False):
            self.window.show_notification(_("Could not save the input method setting."))
            return
        await self._stop_monitor()
        self.window.show_notification(_("Desktop input method turned off."))

    async def _enable(self, *, install, legacy=False):
        package = LEGACY_PACKAGE if legacy else PACKAGE
        try:
            user = await _android_user(self.serial)
            if install:
                self.window.show_notification(_("Setting up the desktop input method…"))
                await install_release(self.serial, user)
            elif not legacy and not await installed_release(self.serial, user):
                raise RuntimeError(_("Choose “Set up desktop input method…” to install the compatible version."))
            await self._stop_monitor()
            ready = asyncio.get_running_loop().create_future()
            self.monitor = asyncio.create_task(self._watch(user, package, ready))
            try:
                await asyncio.wait_for(ready, 20)
                if install and not self.window.preferences.set_boolean(PREFERENCE, True):
                    raise RuntimeError(_("Could not save the input method setting."))
            except BaseException:
                await self._stop_monitor()
                raise
            if install:
                self.window.show_notification(_("Desktop input method enabled."))
        except Exception as error:
            logger.warning("Desktop IME setup on %s failed: %s", self.serial, error)
            detail = str(error) or _("Android did not respond.")
            self.window.show_notification(_("Could not enable the desktop input method: %s") % detail)

    async def _watch(self, user, package, ready):
        delay = 1

        def connected():
            nonlocal delay
            delay = 1
            self.package = package
            if not ready.done():
                ready.set_result(None)

        while self.serial:
            try:
                if user != await _android_user(self.serial):
                    message = _("The active Android user changed. Set up the input method again.")
                    if not ready.done():
                        ready.set_exception(RuntimeError(message))
                    else:
                        self.window.show_notification(message)
                    return
                if ready.done() and package == PACKAGE and not await installed_release(self.serial, user):
                    self.window.show_notification(_("Choose “Set up desktop input method…” to install the compatible version."))
                    return
                await self.bridge.serve(self.serial, user, package, connected, legacy=package == LEGACY_PACKAGE)
            except Exception as error:
                if not ready.done():
                    ready.set_exception(error)
                    return
                logger.warning("Desktop IME disconnected on %s: %s", self.serial, error)
            finally:
                self.package = None
            await asyncio.sleep(delay)
            delay = min(15, delay * 2)
