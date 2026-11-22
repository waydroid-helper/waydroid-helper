"""Android display settings exposed by the embedded emulator."""

import asyncio
import re
from dataclasses import dataclass
from gettext import gettext as _

import gi

gi.require_version("Adw", "1")
from gi.repository import Adw, Gtk

from waydroid_helper.controller.app.embedded_session import waydroid_output
from waydroid_helper.controller.app.emulator_preferences import (
    EmulatorPreferences,
    add_spin,
    add_switch,
)
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


class DisplaySettings(EmulatorPreferences):
    def __init__(self, parent, mode):
        super().__init__(parent, _("Device settings"), height=540)
        display = Adw.PreferencesGroup(title=_("Display"))
        self.page.add(display)
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
            self.modes.index(mode) if mode in self.modes else len(labels)
        )
        display.add(self.combo)
        self.fields = [
            add_spin(display, title, value, low, high)
            for title, value, low, high in (
                (_("Width"), mode.width, 200, 8192),
                (_("Height"), mode.height, 200, 8192),
                ("DPI", mode.dpi, 72, 1200),
            )
        ]
        self.combo.connect("notify::selected", self._selection)
        self._selection()
        window = Adw.PreferencesGroup()
        self.page.add(window)
        add_switch(
            window, _("Fix window size"), parent.preferences, "emulator-lock-size"
        )
        add_switch(
            window,
            _("Remember window size"),
            parent.preferences,
            "emulator-remember-size",
        )
        actions = Adw.PreferencesGroup()
        self.page.add(actions)
        self.message = Gtk.Label(xalign=0, wrap=True, visible=False)
        actions.add(self.message)
        self.apply_button = Gtk.Button(
            label=_("Apply display settings"), halign=Gtk.Align.END
        )
        self.apply_button.add_css_class("suggested-action")
        self.apply_button.connect("clicked", self._apply)
        actions.add(self.apply_button)

    def _selection(self, *_):
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

    def _apply(self, *_):
        mode = DisplayMode(*(round(s.get_value()) for s in self.fields))
        self.set_busy(True)
        asyncio.create_task(self._save(mode))

    async def _save(self, mode):
        try:
            await self.parent_window.apply_display_mode(mode)
        except Exception as error:
            logger.exception("Failed to stage Android display mode %s", mode)
            self.message.set_text(str(error))
            self.message.set_visible(True)
            return
        finally:
            self.set_busy(False)
        self.close()
        self.parent_window.request_restart(
            _("Display settings saved. Restart Android to use the new output mode.")
        )
