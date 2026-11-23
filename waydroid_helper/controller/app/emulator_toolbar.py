"""Header controls for the embedded Android display."""

import re
from gettext import gettext as _

from gi.repository import Adw, Gio, GLib, GObject, Gtk

from waydroid_helper.controller.android.keycodes import AKeyCode
from waydroid_helper.controller.app.emulator_display import device_command
from waydroid_helper.controller.app.emulator_tabs import EmulatorTabs
from waydroid_helper.controller.app.mapping_panel import MappingPanel, MappingEditorBar


def icon_button(icon, label, action):
    button = Gtk.Button(icon_name=icon, tooltip_text=label, focus_on_click=False)
    button.add_css_class("emulator-tool")
    button.connect("clicked", lambda *_: action())
    return button


class MenuRow(Gtk.Button):
    def __init__(self, icon, label, action, shortcut=None):
        super().__init__()
        self.add_css_class("flat")
        content = Gtk.Box(spacing=10)
        content.append(Gtk.Image(icon_name=icon))
        self.caption = Gtk.Label(label=label, xalign=0, hexpand=True)
        content.append(self.caption)
        if shortcut:
            hint = Gtk.Label(label=shortcut)
            hint.add_css_class("dim-label")
            content.append(hint)
        self.set_child(content)
        self.connect("clicked", lambda *_: action())


class EmulatorToolbar:
    def __init__(self, window):
        self.header = Adw.HeaderBar(show_start_title_buttons=False)
        self.widget = Gtk.WindowHandle()
        row = Gtk.Box()
        row.add_css_class("emulator-header")
        start_controls = Gtk.WindowControls(side=Gtk.PackType.START)
        start_controls.bind_property(
            "empty",
            start_controls,
            "visible",
            GObject.BindingFlags.INVERT_BOOLEAN | GObject.BindingFlags.SYNC_CREATE,
        )
        row.append(start_controls)
        self.window = window
        self.header.add_css_class("flat")
        self.tabs = EmulatorTabs(
            lambda: window.send_key(AKeyCode.AKEYCODE_HOME), window.task_action
        )
        if hasattr(self.header, "set_show_title"):
            self.header.set_show_title(False)
        else:
            self.header.set_title_widget(Gtk.Box())
        # AdwHeaderBar bounds its title and action groups to their natural
        # width. Give the scrolling tab bar the remaining space directly, and
        # keep native window dragging and decorations on both sides.
        row.append(self.tabs.bar)
        # With only end controls, HeaderBar reserves a matching empty start
        # group in its natural width. Clamp it to the controls' measured minimum.
        controls = Adw.Clamp(child=self.header, maximum_size=0, tightening_threshold=0)
        controls.set_halign(Gtk.Align.END)
        row.append(controls)

        self.more = self._menu("view-more-horizontal-symbolic", _("More"))
        self.fullscreen_button = icon_button(
            "view-fullscreen-symbolic", _("Fullscreen (F11)"), window.toggle_fullscreen
        )
        self.header.pack_end(self.fullscreen_button)
        self.header.pack_end(self.more)
        self.back = icon_button(
            "go-previous-symbolic",
            _("Android Back"),
            lambda: window.send_key(AKeyCode.AKEYCODE_BACK),
        )
        self.header.pack_end(self.back)

        self.volume = self._menu("audio-volume-high-symbolic", _("Volume"))
        self.header.pack_end(self.volume)
        self.volume_slider = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0, 15, 1
        )
        self.volume_slider.set_draw_value(True)
        self.volume_slider.set_digits(0)
        self.volume_slider.set_sensitive(False)
        self.volume.items.append(self.volume_slider)
        self.volume_handler = self.volume_slider.connect(
            "value-changed", self._set_volume
        )
        self.volume_timeout = 0
        self.volume.get_popover().connect(
            "show", lambda *_: window.run_device_action(self._read_volume)
        )
        for icon, label, code in (
            ("audio-volume-high-symbolic", _("Volume up"), AKeyCode.AKEYCODE_VOLUME_UP),
            (
                "audio-volume-low-symbolic",
                _("Volume down"),
                AKeyCode.AKEYCODE_VOLUME_DOWN,
            ),
            ("audio-volume-muted-symbolic", _("Mute"), AKeyCode.AKEYCODE_VOLUME_MUTE),
        ):
            self._row(self.volume, icon, label, lambda key=code: window.send_key(key))

        self.mapping = self._menu("input-keyboard-symbolic", _("Key mapping"))
        self.header.pack_end(self.mapping)
        self.mapping_panel = MappingPanel(window, self.mapping)
        self.editor = MappingEditorBar(window)
        self.chrome = Gtk.Stack(vhomogeneous=False, hhomogeneous=False)
        self.chrome.add_named(row, "normal")
        self.chrome.add_named(self.editor.widget, "edit")
        self.widget.set_child(self.chrome)
        self._build_more_menu()
        self.sync_mode()

    def set_compact(self, compact):
        self.editor.compact(compact)
        if self.tabs.compact == compact:
            return
        # Both actions remain in More. Give their space to the scrolling tab
        # strip and its picker so resizing never adds a row above Android.
        self.back.set_visible(not compact)
        self.fullscreen_button.set_visible(not compact)
        if compact:
            self.header.add_css_class("compact")
        else:
            self.header.remove_css_class("compact")
        self.tabs.set_compact(compact)

    async def _read_volume(self):
        data = await device_command(
            self.window.scrcpy_lifecycle.adb_helper.serial,
            "shell",
            "cmd",
            "media_session",
            "volume",
            "--stream",
            "3",
            "--get",
        )
        match = re.search(rb"volume is (\d+) in range \[(\d+)\.\.(\d+)\]", data)
        self.volume_slider.set_sensitive(bool(match))
        if match:
            current, lower, upper = map(int, match.groups())
            with self.volume_slider.handler_block(self.volume_handler):
                self.volume_slider.set_range(lower, upper)
                self.volume_slider.set_value(current)

    def _set_volume(self, slider):
        if self.volume_timeout:
            GLib.source_remove(self.volume_timeout)

        def change():
            self.volume_timeout = 0
            self.window.run_device_action(
                lambda: device_command(
                    self.window.scrcpy_lifecycle.adb_helper.serial,
                    "shell",
                    "cmd",
                    "media_session",
                    "volume",
                    "--stream",
                    "3",
                    "--set",
                    str(round(slider.get_value())),
                )
            )
            return GLib.SOURCE_REMOVE

        self.volume_timeout = GLib.timeout_add(100, change)

    def _build_more_menu(self):
        window = self.window
        tools = window.tools
        actions = Gio.SimpleActionGroup()
        window.insert_action_group("emulator", actions)
        model = Gio.Menu()

        def action(menu, name, title, callback):
            entry = Gio.SimpleAction.new(name, None)
            entry.connect("activate", lambda *_: callback())
            actions.add_action(entry)
            menu.append(title, "emulator." + name)

        navigation = Gio.Menu()
        for name, title, key in (
            ("back", _("Back"), AKeyCode.AKEYCODE_BACK),
            ("recent", _("Recent apps"), AKeyCode.AKEYCODE_APP_SWITCH),
            ("home", _("Android Home"), AKeyCode.AKEYCODE_HOME),
        ):
            action(navigation, name, title, lambda k=key: window.send_key(k))
        model.append_submenu(_("Android navigation"), navigation)

        management = Gio.Menu()
        action(
            management, "fullscreen", _("Fullscreen (F11)"), window.toggle_fullscreen
        )
        action(
            management,
            "system-menu",
            _("System window menu (Always on Top)"),
            self._system_window_menu,
        )
        action(management, "mini", _("Mini mode"), window.toggle_mini)
        action(
            management,
            "rotate",
            _("Rotate screen"),
            lambda: window.run_device_action(tools.rotate),
        )
        action(management, "restore", _("Restore window size"), window.restore_size)
        model.append_submenu(_("Window management"), management)
        action(model, "mapping", _("Key mapping"), self.mapping.popup)
        action(model, "profiles", _("Manage profiles"), window.open_profiles)

        recording = Gio.Menu()
        action(
            recording,
            "capture-input",
            _("Start or stop input recording"),
            window.recorder.toggle,
        )
        action(
            recording,
            "play-input",
            _("Play or stop recording"),
            lambda: window.run_device_action(window.recorder.play),
        )
        action(recording, "import-input", _("Import recording"), window.recorder.load)
        action(recording, "export-input", _("Export recording"), window.recorder.export)
        model.append_submenu(_("Input recording"), recording)
        action(model, "location", _("Virtual location"), tools.virtual_location)

        utilities = Gio.Menu()
        action(utilities, "screenshot", _("Screenshot"), tools.screenshot)
        action(
            utilities,
            "record",
            _("Start or stop screen recording"),
            tools.toggle_record,
        )
        action(utilities, "install", _("Install APK"), tools.install_apk)
        action(utilities, "volume", _("Volume"), self.volume.popup)
        sharing = Gio.Menu()
        for name, title in (
            ("host", _("Open computer shared folder")),
            ("android", _("Open Android shared folder")),
            ("settings", _("Change shared folders")),
        ):
            action(
                sharing,
                "shared-" + name,
                title,
                lambda side=name: tools.shared_folders(side),
            )
        utilities.append_submenu(_("Shared folders"), sharing)
        model.append_submenu(_("More tools"), utilities)
        action(model, "settings", _("Device settings"), window.open_display_settings)

        support = Gio.Menu()
        base = "https://github.com/waydroid-helper/waydroid-helper"
        action(
            support,
            "guide",
            _("User guide"),
            lambda: Gtk.show_uri(window, base + "#readme", 0),
        )
        action(
            support,
            "diagnostics",
            _("Device diagnostics"),
            lambda: window.run_device_action(tools.diagnostics),
        )
        action(
            support,
            "feedback",
            _("Report an issue"),
            lambda: Gtk.show_uri(window, base + "/issues", 0),
        )
        model.append_submenu(_("Help center"), support)
        action(model, "restart", _("Restart device"), window.request_restart)
        self.more.set_menu_model(model)
        popover = self.more.get_popover()
        popover.connect("closed", lambda *_: window.canvas.grab_focus())
        self.menu_event = None
        click = Gtk.GestureClick()
        click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        click.connect(
            "pressed",
            lambda gesture, *_: setattr(
                self, "menu_event", gesture.get_current_event()
            ),
        )
        popover.add_controller(click)

    def _system_window_menu(self):
        # xdg-shell lets the compositor decide and persist the stacking policy.
        # Pass the original user event so the native window menu gets a valid
        # seat serial. Its Always on Top choice also reflects the real state.
        if not self.menu_event or not self.window.get_surface().show_window_menu(
            self.menu_event
        ):
            self.window.show_notification(
                _("Open the title bar’s system menu to change window stacking.")
            )
        self.menu_event = None

    def sync_mode(self):
        editing = self.window.profiles.edit is not None
        self.widget.set_visible(editing or not self.window.is_fullscreen())
        self.chrome.set_visible_child_name("edit" if editing else "normal")
        self.window.edit_shade.set_visible(editing)
        if editing:
            self.editor.sync()
        elif self.mapping.get_popover().get_visible():
            self.mapping_panel.refresh()

    def _menu(self, icon, label):
        button = Gtk.MenuButton(icon_name=icon, tooltip_text=label)
        button.add_css_class("emulator-tool")
        popover = Gtk.Popover()
        popover.add_css_class("menu")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_size_request(205, -1)
        # Popovers live outside the game input subtree. Hand focus back when
        # they close so the first mapped key after using a menu reaches Android.
        def restore_canvas_focus():
            # GtkMenuButton restores its toggle's focus after the closed signal.
            # Wait until that transfer finishes. A dialog or an editor that
            # already took focus must retain it.
            focus = self.window.get_focus()
            if (not popover.get_mapped() and focus is not None
                    and (focus is button or focus.is_ancestor(button))):
                self.window.canvas.grab_focus()
            return GLib.SOURCE_REMOVE

        popover.connect("closed", lambda *_: GLib.idle_add(restore_canvas_focus))
        popover.set_child(box)
        button.set_popover(popover)
        button.items = box
        return button

    def _row(self, menu, icon, label, callback, shortcut=None):
        def activate():
            menu.popdown()
            self.window.canvas.grab_focus()
            callback()

        item = MenuRow(icon, label, activate, shortcut)
        menu.items.append(item)
        return item
