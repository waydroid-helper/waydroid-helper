"""Android display settings exposed by the embedded emulator."""

import asyncio
import re
from dataclasses import dataclass
from gettext import gettext as _

import gi

gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from waydroid_helper.controller.app.embedded_session import waydroid_output
from waydroid_helper.controller.app.emulator_preferences import add_spin, add_switch
from waydroid_helper.util.log import logger


@dataclass(frozen=True)
class DisplayMode:
    width: int
    height: int
    dpi: int


PRESETS = (
    (
        _("Tablet"),
        ((3840, 2160, 540), (2560, 1440, 360), (1920, 1080, 280), (1600, 900, 240)),
    ),
    (
        _("Phone"),
        ((2160, 3840, 960), (1440, 2560, 640), (1080, 1920, 480), (900, 1600, 320)),
    ),
    (
        _("Ultrawide"),
        ((3440, 1440, 480), (2560, 1080, 360), (1920, 864, 240), (1680, 720, 240)),
    ),
)


async def device_command(serial, *args, timeout=30):
    """Run on the instance owned by this window, including on multi-device hosts."""
    proc = await asyncio.create_subprocess_exec(
        "adb",
        "-s",
        serial,
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        out, err = await asyncio.wait_for(proc.communicate(), timeout)
    finally:
        if proc.returncode is None:
            proc.kill()
            await proc.wait()
    if proc.returncode:
        raise RuntimeError(
            err.decode(errors="replace").strip() or out.decode(errors="replace").strip()
        )
    return out


async def read_mode(serial):
    size, density = await asyncio.gather(
        device_command(serial, "shell", "wm", "size"),
        device_command(serial, "shell", "wm", "density"),
    )
    sizes = re.findall(rb"(?:Physical|Override) size:\s*(\d+)x(\d+)", size)
    densities = re.findall(rb"(?:Physical|Override) density:\s*(\d+)", density)
    if not sizes or not densities:
        raise RuntimeError(_("Android display information is unavailable."))
    return DisplayMode(*map(int, sizes[-1]), int(densities[-1]))


async def stage_mode(mode, scale, remember):
    """Stage native dimensions without disturbing running Android apps.

    Waydroid reads these properties at HWC initialization. They are logical
    Wayland dimensions, while the settings dialog and Android use pixels.
    Commit all three requested values together after both native properties
    are written. A failed write must leave the previous selection usable.
    """
    names = ("persist.waydroid.width", "persist.waydroid.height")
    previous = await asyncio.gather(
        *(waydroid_output("prop", "get", name) for name in names)
    )
    changed = []
    try:
        for name, pixels, old in zip(names, (mode.width, mode.height), previous):
            logical = str(max(1, round(pixels / scale)))
            if logical != old:
                await waydroid_output("prop", "set", name, logical)
                changed.append((name, old))
        if not remember():
            raise RuntimeError(_("Could not save display settings."))
    except BaseException:
        for name, old in reversed(changed):
            await waydroid_output("prop", "set", name, old)
        raise


async def apply_android_mode(serial, mode):
    """Apply pixel-exact overrides after Android has booted on the new output.

    Prefer the native mode whenever it matches. An explicit size override is
    only necessary for earlier Android overrides or rounding at fractional
    desktop scale. Read both values back before enabling input.
    """
    for key, desired in (
        ("size", f"{mode.width}x{mode.height}"),
        ("density", str(mode.dpi)),
    ):
        reply = (await device_command(serial, "shell", "wm", key)).decode().splitlines()
        values = [
            line.partition(":")[2].strip()
            for line in reply
            if line.startswith(("Physical ", "Override "))
        ]
        if not values:
            raise RuntimeError(_("Android display information is unavailable."))
        if values[-1] != desired:
            await device_command(
                serial, "shell", "wm", key, "reset" if values[0] == desired else desired
            )
    actual = await read_mode(serial)
    if actual != mode:
        raise RuntimeError(_("Android did not accept the selected display mode."))


class DisplaySettingsPage(Adw.Bin):
    def __init__(self, dialog, active_mode, saved_mode):
        from waydroid_helper.compat_widget import Banner, ToolbarView

        super().__init__()
        self.dialog = dialog
        self.active_mode = active_mode
        self.saved_mode = saved_mode
        self._save_task = None
        self._save_failed = False

        self.banner = Banner()
        self.banner.connect("button-clicked", self._banner_clicked)
        page = Adw.PreferencesPage()
        toolbar = ToolbarView()
        toolbar.add_top_bar(self.banner)
        toolbar.set_content(page)
        self.set_child(toolbar)

        display = Adw.PreferencesGroup()
        page.add(display)
        self.modes = [DisplayMode(*values) for _, group in PRESETS for values in group]
        labels = [
            f"{w} × {h}, {dpi} DPI ({name})"
            for name, group in PRESETS
            for w, h, dpi in group
        ]
        self.combo = Adw.ComboRow(
            title=_("Resolution"),
            use_subtitle=True,
            model=Gtk.StringList.new([*labels, _("Custom")]),
        )
        self.combo.set_selected(
            self.modes.index(saved_mode) if saved_mode in self.modes else len(labels)
        )
        display.add(self.combo)
        self.fields = [
            add_spin(display, title, value, low, high)
            for title, value, low, high in (
                (_("Width"), saved_mode.width, 200, 8192),
                (_("Height"), saved_mode.height, 200, 8192),
                ("DPI", saved_mode.dpi, 72, 1200),
            )
        ]
        self._sync_fields()
        self.combo.connect("notify::selected", self._selection_changed)
        for field in self.fields:
            field.connect("notify::value", self._custom_value_changed)

        window = Adw.PreferencesGroup(title=_("Window management"))
        page.add(window)
        preferences = dialog.parent_window.preferences
        add_switch(
            window, _("Fix window size"), preferences, "emulator-lock-size"
        )
        add_switch(
            window,
            _("Remember window size"),
            preferences,
            "emulator-remember-size",
        )
        self._update_banner()

    def _sync_fields(self):
        index = self.combo.get_selected()
        for field in self.fields:
            row = (
                field
                if isinstance(field, Adw.PreferencesRow)
                else field.get_ancestor(Adw.PreferencesRow)
            )
            row.set_visible(index == len(self.modes))
        if index < len(self.modes):
            mode = self.modes[index]
            for field, value in zip(self.fields, (mode.width, mode.height, mode.dpi)):
                field.set_value(value)

    def _selection_changed(self, *_):
        self._sync_fields()
        self._queue_save()

    def _custom_value_changed(self, *_):
        if self.combo.get_selected() == len(self.modes):
            self._queue_save()

    def _chosen_mode(self):
        index = self.combo.get_selected()
        if index < len(self.modes):
            return self.modes[index]
        return DisplayMode(*(round(field.get_value()) for field in self.fields))

    def _queue_save(self):
        if self._save_task is not None:
            return
        self._save_failed = False
        if self._chosen_mode() == self.saved_mode:
            self._update_banner()
            return
        self.banner.set_sensitive(False)
        self.dialog.set_busy(True)
        self._save_task = asyncio.create_task(self._save())

    async def _save(self):
        try:
            # Native width and height are written in a single transaction.
            # Serialize writes and pick up the latest choice after each one,
            # so a preset change or repeated spin cannot interleave writes.
            while (mode := self._chosen_mode()) != self.saved_mode:
                try:
                    await self.dialog.parent_window.apply_display_mode(mode)
                except Exception:
                    logger.exception("Failed to stage Android display mode %s", mode)
                    if mode == self._chosen_mode():
                        self._save_failed = True
                        return
                else:
                    self.saved_mode = mode
        finally:
            self._save_task = None
            self.dialog.set_busy(False)
            self._update_banner()
            self.banner.set_sensitive(True)

    def _update_banner(self):
        if self._save_failed:
            self.banner.set_title(_("Could not save display settings."))
            self.banner.set_button_label(_("Retry"))
        elif self.saved_mode != self.active_mode:
            self.banner.set_title(_("Restart Android to apply the new resolution and DPI."))
            self.banner.set_button_label(_("Restart Now"))
        self.banner.set_revealed(self._save_failed or self.saved_mode != self.active_mode)

    def _banner_clicked(self, *_):
        if self._save_task is not None:
            return
        if self._save_failed:
            self._queue_save()
        elif self.saved_mode != self.active_mode:
            if self.dialog.parent_window.restart_now():
                self.dialog.close()
