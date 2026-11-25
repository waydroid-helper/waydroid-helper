"""Android display settings exposed by the embedded emulator."""

import asyncio
import re
from dataclasses import dataclass
from gettext import gettext as _

import gi

gi.require_version("Adw", "1")
from gi.repository import Adw, GLib, Gtk

from waydroid_helper.controller.app.embedded_session import waydroid_output
from waydroid_helper.controller.app.emulator_preferences import add_spin, add_switch


@dataclass(frozen=True)
class DisplayMode:
    width: int
    height: int
    dpi: int

    def logical_size(self, scale):
        return max(1, round(self.width / scale)), max(1, round(self.height / scale))

    def label(self):
        return f"{self.width} × {self.height}, {self.dpi} DPI"


def load_display_mode(settings, key):
    values = settings.get_value(key).unpack()
    return DisplayMode(*values) if all(value > 0 for value in values) else None


def store_display_mode(settings, key, mode):
    return settings.set_value(key, GLib.Variant("(iii)", (mode.width, mode.height, mode.dpi)))


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


NATIVE_SIZE_PROPERTIES = ("persist.waydroid.width", "persist.waydroid.height")


async def read_native_size():
    return tuple(
        await asyncio.gather(
            *(waydroid_output("prop", "get", name) for name in NATIVE_SIZE_PROPERTIES)
        )
    )


async def clear_conflicting_native_size(previous, desired):
    """Remove fixed dimensions that prevent HWC from using the Wayland output."""
    if all(not old or old == str(size) for old, size in zip(previous, desired)):
        return False
    # Older emulator settings wrote persistent HWC overrides. Clear both axes
    # together so future starts can use the compositor size selected on the
    # host. Restore any cleared property if the second write fails.
    changed = []
    try:
        for name, old in zip(NATIVE_SIZE_PROPERTIES, previous):
            if old:
                changed.append((name, old))
                await waydroid_output("prop", "set", name, "")
        # Waydroid's CLI can log property errors while returning exit status 0.
        if any(await read_native_size()):
            raise RuntimeError(_("Could not clear the old Waydroid display size."))
    except BaseException:
        for name, old in reversed(changed):
            await waydroid_output("prop", "set", name, old)
        raise
    return True


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
    def __init__(self, dialog, saved_mode, default_mode):
        from waydroid_helper.compat_widget import Banner, ToolbarView

        super().__init__()
        self.dialog = dialog
        self.saved_mode = saved_mode
        self._save_failed = False
        self.active_mode = None
        self.connected = False
        self.measured_mode = None

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
            f"{DisplayMode(w, h, dpi).label()} ({name})"
            for name, group in PRESETS
            for w, h, dpi in group
        ]
        self.custom_index = len(labels)
        self.automatic_index = self.custom_index + 1
        labels.append(_("Custom"))
        if saved_mode is None:
            labels.append(_("Automatic"))
        self.combo = Adw.ComboRow(
            title=_("Resolution"),
            use_subtitle=True,
            model=Gtk.StringList.new(labels),
        )
        if saved_mode is None:
            self.combo.set_selected(self.automatic_index)
        elif saved_mode not in self.modes:
            self.combo.set_selected(self.custom_index)
        else:
            self.combo.set_selected(self.modes.index(saved_mode))
        display.add(self.combo)
        initial = saved_mode or default_mode
        self.fields = [
            add_spin(display, title, value, low, high)
            for title, value, low, high in (
                (_("Width"), initial.width, 200, 8192),
                (_("Height"), initial.height, 200, 8192),
                ("DPI", initial.dpi, 72, 1200),
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

    def set_runtime_mode(self, mode, connected, last_mode):
        self.active_mode = mode
        self.connected = connected
        self.measured_mode = mode or last_mode
        self._sync_fields()
        self._update_banner()

    def _sync_fields(self):
        index = self.combo.get_selected()
        for field in self.fields:
            row = (
                field
                if isinstance(field, Adw.PreferencesRow)
                else field.get_ancestor(Adw.PreferencesRow)
            )
            row.set_visible(index == self.custom_index)
        automatic = index == self.automatic_index
        self.combo.set_use_subtitle(not automatic)
        mode = None
        if automatic:
            mode = self.measured_mode
            self.combo.set_subtitle(mode.label() if mode else _("Automatic"))
        elif index < self.custom_index:
            mode = self.modes[index]
        if mode:
            for field, value in zip(self.fields, (mode.width, mode.height, mode.dpi)):
                field.set_value(value)

    def _selection_changed(self, *_):
        self._sync_fields()
        index = self.combo.get_selected()
        if index < self.custom_index:
            self._save()
        elif index == self.automatic_index:
            self._save_failed = False
            self._update_banner()

    def _custom_value_changed(self, *_):
        if self.combo.get_selected() == self.custom_index:
            self._save()

    def _chosen_mode(self):
        index = self.combo.get_selected()
        if index < self.custom_index:
            return self.modes[index]
        return DisplayMode(*(round(field.get_value()) for field in self.fields))

    def _save(self):
        mode = self._chosen_mode()
        saved = mode == self.saved_mode or self.dialog.parent_window.save_display_mode(mode)
        self._save_failed = not saved
        if saved:
            self.saved_mode = mode
            model = self.combo.get_model()
            # Automatic represents installations that have never chosen a
            # startup mode. Once one is saved, the available choices are the
            # presets and their editable custom dimensions.
            if model.get_n_items() > self.automatic_index:
                model.remove(self.automatic_index)
        self._update_banner()

    def _needs_restart(self):
        return (
            self.connected and self.saved_mode is not None and self.saved_mode != self.active_mode
        )

    def _update_banner(self):
        needs_restart = self._needs_restart()
        if self._save_failed:
            self.banner.set_title(_("Could not save display settings."))
            self.banner.set_button_label(_("Retry"))
        elif needs_restart:
            self.banner.set_title(_("Restart Android to apply the new resolution and DPI."))
            self.banner.set_button_label(_("Restart Now"))
        self.banner.set_revealed(self._save_failed or needs_restart)

    def _banner_clicked(self, *_):
        if self._save_failed:
            self._save()
        elif self._needs_restart():
            if self.dialog.parent_window.restart_now():
                self.dialog.close()
