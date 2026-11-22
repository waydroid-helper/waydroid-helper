"""Device actions for the embedded window's Tools menu."""

import asyncio
import os
import re
import secrets
import tempfile
from gettext import gettext as _
from pathlib import Path

from gi.repository import Adw, Gio, GLib, Gtk

from waydroid_helper.compat_widget.file_dialog import FileDialog
from waydroid_helper.controller.app.emulator_display import device_command
from waydroid_helper.controller.app.emulator_preferences import (
    EmulatorPreferences,
    add_spin,
)
from waydroid_helper.util.log import logger


class EmulatorTools:
    def __init__(self, window):
        self.window = window
        self.mock_location = False
        self.previous_mock_permission = None
        self.record_task = None
        self.record_pid = None
        self.record_ready = asyncio.Event()

    @property
    def serial(self):
        return self.window.scrcpy_lifecycle.adb_helper.serial

    def pick_file(self, title, pattern, callback, suggested=None):
        chooser = FileDialog(parent=self.window, title=title, modal=True)
        filt = Gtk.FileFilter()
        filt.set_name(pattern)
        filt.add_pattern(pattern)

        def chosen(ok, path):
            if ok and path:
                self.window.run_device_action(lambda: callback(Path(path)))

        if suggested:
            chooser.save_file(chosen, suggested_name=suggested, file_filter=filt)
        else:
            chooser.open_file(chosen, file_filter=filt)

    def screenshot(self):
        self.pick_file(_("Screenshot"), "*.png", self._screenshot, "Waydroid.png")

    async def _screenshot(self, path):
        data = await device_command(self.serial, "exec-out", "screencap", "-p")
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            raise RuntimeError(_("Android returned an invalid screenshot."))
        # Replace the destination only after the full image was received.
        await asyncio.to_thread(
            Gio.File.new_for_path(str(path)).replace_contents,
            data,
            None,
            False,
            Gio.FileCreateFlags.NONE,
            None,
        )
        self.window.show_notification(_("Screenshot saved"))

    def install_apk(self):
        self.pick_file(_("Install APK"), "*.apk", self._install)

    async def _install(self, path):
        result = await device_command(
            self.serial, "install", "-r", str(path), timeout=180
        )
        if "Success" not in result.decode(errors="replace").splitlines():
            raise RuntimeError(
                result.decode(errors="replace").strip() or _("APK installation failed.")
            )
        self.window.show_notification(_("APK installed"))

    def toggle_record(self):
        if self.record_task:
            self.window.run_device_action(self.stop_recording)
        else:
            self.pick_file(_("Screen recording"), "*.mp4", self._record, "Waydroid.mp4")

    async def _record(self, path):
        if self.record_task:
            return
        self.record_task = asyncio.current_task()
        self.record_ready.clear()
        remote = f"/data/local/tmp/wdh-{secrets.token_hex(10)}.mp4"
        proc = None
        serial = self.serial
        try:
            # Capture only this Android display. The shell replaces itself with
            # screenrecord, so SIGINT targets this recording and finalizes MP4.
            proc = await asyncio.create_subprocess_exec(
                "adb",
                "-s",
                serial,
                "shell",
                f"echo $$; exec screenrecord {remote}",
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            line = await asyncio.wait_for(proc.stdout.readline(), 8)
            if not line.strip().isdigit():
                raise RuntimeError(_("Could not start screen recording."))
            self.record_pid = line.strip().decode()
            self.record_ready.set()
            self.window.show_notification(_("Recording started"))
            stdout, stderr = await asyncio.wait_for(proc.communicate(), 195)
            if proc.returncode not in (0, 130):
                raise RuntimeError(
                    (stderr or stdout).decode(errors="replace").strip()
                    or _("Recording failed.")
                )
            with tempfile.TemporaryDirectory(dir=path.parent) as directory:
                movie = Path(directory) / "recording.mp4"
                await device_command(serial, "pull", remote, str(movie), timeout=180)
                if not movie.stat().st_size:
                    raise RuntimeError(_("Android returned an empty recording."))
                os.replace(movie, path)
            self.window.show_notification(_("Recording saved"))
        finally:
            if proc and proc.returncode is None:
                proc.kill()
                await proc.wait()
            try:
                await device_command(serial, "shell", "rm", "-f", remote)
            finally:
                self.record_task = self.record_pid = None
                self.record_ready.set()

    async def stop_recording(self):
        task = self.record_task
        if task is None:
            return
        # The user may stop immediately after choosing the destination, before
        # adb has returned a PID. Wait for startup or failure, then finalize
        # this exact recording before the session is disconnected.
        await self.record_ready.wait()
        if self.record_pid and self.record_task is task:
            pid, self.record_pid = self.record_pid, None
            await device_command(self.serial, "shell", "kill", "-2", pid)
        await asyncio.shield(task)

    async def finish(self):
        for cleanup in (self.stop_recording, self.clear_location):
            try:
                await cleanup()
            except Exception:
                logger.exception("Android tool cleanup failed: %s", cleanup.__name__)

    async def rotate(self):
        current = (
            (await device_command(self.serial, "shell", "wm", "user-rotation"))
            .decode()
            .split()
        )
        orientation = int(current[-1]) if current and current[-1].isdigit() else 0
        await device_command(
            self.serial,
            "shell",
            "wm",
            "user-rotation",
            "lock",
            str((orientation + 1) % 4),
        )
        self.window._queue_resolution_refresh()

    def shared_folders(self, side):
        from urllib.parse import quote
        from waydroid_helper.shared_folder import SharedFoldersWidget

        dialog = EmulatorPreferences(self.window, _("Shared folders"))
        panel = SharedFoldersWidget()
        panel.connect("updated", lambda *_: panel.restart_service())
        if side == "settings":
            dialog.page.add(panel)
        else:
            choices = Adw.PreferencesGroup(title=_("Choose a shared folder"))
            dialog.page.add(choices)
            rows = []

            def update(*_args):
                for row in rows:
                    choices.remove(row)
                rows.clear()
                for folder in panel.list_store:
                    path = Path(
                        folder.source if side == "host" else folder.target
                    ).expanduser()
                    row = Adw.ActionRow(
                        title=GLib.markup_escape_text(str(path)), activatable=True
                    )
                    row.add_suffix(Gtk.Image(icon_name="go-next-symbolic"))

                    def open_folder(_button, selected=path):
                        if side == "host":
                            Gtk.show_uri(self.window, selected.absolute().as_uri(), 0)
                        else:
                            media = Path.home() / ".local/share/waydroid/data/media/0"
                            if not selected.is_relative_to(media):
                                self.window.show_notification(
                                    _("This folder is outside Android shared storage.")
                                )
                                return
                            uri = (
                                "content://com.android.externalstorage.documents/document/"
                                + quote(
                                    "primary:" + str(selected.relative_to(media)),
                                    safe="",
                                )
                            )
                            self.window.run_device_action(
                                lambda: device_command(
                                    self.serial,
                                    "shell",
                                    "am",
                                    "start",
                                    "-a",
                                    "android.intent.action.VIEW",
                                    "-d",
                                    uri,
                                    "-t",
                                    "vnd.android.document/directory",
                                )
                            )
                        dialog.close()

                    row.connect("activated", open_folder)
                    rows.append(row)
                    choices.add(row)
                choices.set_description(
                    None if rows else _("No shared folder configured.")
                )

            panel.list_store.connect("items-changed", update)
            update()
        dialog.present()

    def virtual_location(self):
        dialog = EmulatorPreferences(self.window, _("Virtual location"), height=370)
        location = Adw.PreferencesGroup(
            description=_(
                "Setting a location uses Android’s mock-location permission for this session."
            )
        )
        dialog.page.add(location)
        fields = [
            add_spin(location, label, 0, -limit, limit, 0.00001, 5)
            for label, limit in ((_("Latitude"), 90), (_("Longitude"), 180))
        ]
        actions = Adw.PreferencesGroup()
        dialog.page.add(actions)
        error = Gtk.Label(wrap=True, visible=False)
        actions.add(error)
        buttons = Gtk.Box(spacing=8, halign=Gtk.Align.END)
        apply = Gtk.Button(label=_("Set location"))
        apply.add_css_class("suggested-action")
        clear = Gtk.Button(label=_("Clear virtual location"))
        clear.set_sensitive(self.mock_location)
        buttons.append(clear)
        buttons.append(apply)
        actions.add(buttons)

        async def change(enable):
            dialog.set_busy(True)
            try:
                if enable:
                    if not self.mock_location:
                        await self._create_location_provider()
                    await device_command(
                        self.serial,
                        "shell",
                        "cmd",
                        "location",
                        "providers",
                        "set-test-provider-enabled",
                        "gps",
                        "true",
                    )
                    coords = ",".join(
                        format(spin.get_value(), ".5f") for spin in fields
                    )
                    await device_command(
                        self.serial,
                        "shell",
                        "cmd",
                        "location",
                        "providers",
                        "set-test-provider-location",
                        "gps",
                        "--location",
                        coords,
                    )
                else:
                    await self.clear_location()
            except Exception as exc:
                error.set_label(str(exc))
                error.set_visible(True)
                return
            finally:
                clear.set_sensitive(self.mock_location)
                dialog.set_busy(False)
            dialog.close()

        apply.connect(
            "clicked", lambda *_: self.window.run_device_action(lambda: change(True))
        )
        clear.connect(
            "clicked", lambda *_: self.window.run_device_action(lambda: change(False))
        )
        dialog.present()

    async def _create_location_provider(self):
        # Scope the shell app-op to an explicitly requested virtual location.
        # Clear restores the user's previous mode, including the implicit
        # Android default when this app-op had never been set.
        query = (
            await device_command(
                self.serial,
                "shell",
                "appops",
                "get",
                "com.android.shell",
                "android:mock_location",
            )
        ).decode()
        previous = re.search(
            r"(?im)^MOCK_LOCATION:\s*(allow|deny|ignore|foreground|default|errored)",
            query,
        )
        mode = previous[1].lower() if previous else "default"
        if mode != "allow":
            await device_command(
                self.serial,
                "shell",
                "appops",
                "set",
                "com.android.shell",
                "android:mock_location",
                "allow",
            )
            self.previous_mock_permission = mode
        try:
            await device_command(
                self.serial,
                "shell",
                "cmd",
                "location",
                "providers",
                "add-test-provider",
                "gps",
            )
            self.mock_location = True
        except BaseException:
            await self.clear_location()
            raise

    async def clear_location(self):
        if self.mock_location:
            await device_command(
                self.serial,
                "shell",
                "cmd",
                "location",
                "providers",
                "remove-test-provider",
                "gps",
            )
            self.mock_location = False
        if self.previous_mock_permission is not None:
            await device_command(
                self.serial,
                "shell",
                "appops",
                "set",
                "com.android.shell",
                "android:mock_location",
                self.previous_mock_permission,
            )
            self.previous_mock_permission = None

    async def diagnostics(self):
        from waydroid_helper.controller.app.emulator_display import read_mode

        mode, release = await asyncio.gather(
            read_mode(self.serial),
            device_command(self.serial, "shell", "getprop", "ro.build.version.release"),
        )
        info = (
            f"Android {release.decode().strip()}\n{mode.width} × {mode.height} · {mode.dpi} DPI"
            f"\nADB {self.serial}\nWayland {self.window.session.socket}"
        )
        dialog = EmulatorPreferences(self.window, _("Device diagnostics"), height=240)
        details = Adw.PreferencesGroup()
        details.add(Gtk.Label(label=info, selectable=True, wrap=True, xalign=0))
        dialog.page.add(details)
        dialog.present()
