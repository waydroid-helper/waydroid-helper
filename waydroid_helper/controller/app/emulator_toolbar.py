"""Header controls for the embedded Android display."""

import re
from gettext import gettext as _

from gi.repository import Gio, GLib, Gtk

from waydroid_helper.controller.android.keycodes import AKeyCode
from waydroid_helper.controller.app.emulator_display import device_command


def icon_button(icon, label, action):
    button = Gtk.Button(icon_name=icon, tooltip_text=label, focus_on_click=False)
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


class EmulatorToolbar(Gtk.HeaderBar):
    def __init__(self, window):
        super().__init__(show_title_buttons=True)
        self.window = window
        self.add_css_class("emulator-header")
        self.set_title_widget(Gtk.Box())
        brand = Gtk.Box(spacing=7)
        brand.append(Gtk.Image(icon_name="phone-symbolic"))
        title = Gtk.Label(label="Waydroid")
        title.add_css_class("heading")
        brand.append(title)
        self.pack_start(brand)

        self.more = self._menu("view-more-horizontal-symbolic", _("More"))
        self.pack_end(
            icon_button(
                "view-fullscreen-symbolic",
                _("Fullscreen (F11)"),
                window.toggle_fullscreen,
            )
        )
        self.pack_end(self.more)
        self.back = icon_button(
            "go-previous-symbolic",
            _("Android Back"),
            lambda: window.send_key(AKeyCode.AKEYCODE_BACK),
        )
        self.pack_end(self.back)

        self.volume = self._menu("audio-volume-high-symbolic", _("Volume"))
        self.pack_end(self.volume)
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
        self.pack_end(self.mapping)
        self.mode = self._row(
            self.mapping,
            "document-edit-symbolic",
            _("Edit controls"),
            window.toggle_mapping,
            "F1",
        )
        self._row(
            self.mapping,
            "input-gaming-symbolic",
            _("Gamepad mappings"),
            window.gamepad.edit,
        )
        mapping_pages = self._build_control_picker()
        self.visibility = self._row(
            self.mapping,
            "view-conceal-symbolic",
            _("Hide controls"),
            window.toggle_all_widgets_transparency,
            "F12",
        )
        self.mapping.items.append(Gtk.Separator())
        self._build_layout_picker(mapping_pages)
        self._row(
            self.mapping,
            "document-save-symbolic",
            _("Save layout"),
            window.menu_manager.save_layout,
        )
        self.mapping.get_popover().connect("show", lambda *_: self.sync_mode())
        self._build_more_menu()
        self.sync_mode()

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

    def _build_control_picker(self):
        menu = self.mapping
        popover = menu.get_popover()
        stack = Gtk.Stack(
            transition_type=Gtk.StackTransitionType.SLIDE_LEFT_RIGHT, vhomogeneous=False
        )
        popover.set_child(None)
        stack.add_named(menu.items, "mapping")
        picker = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        stack.add_named(picker, "controls")
        popover.set_child(stack)
        menu.items.append(
            MenuRow(
                "list-add-symbolic",
                _("Add control"),
                lambda: stack.set_visible_child_name("controls"),
            )
        )
        picker.append(
            MenuRow(
                "go-previous-symbolic",
                _("Key mapping"),
                lambda: stack.set_visible_child_name("mapping"),
            )
        )
        picker.append(Gtk.Separator())
        factory = self.window.widget_factory
        for kind in sorted(factory.get_available_types()):
            if not getattr(
                factory.widget_classes[kind], "ALLOW_CONTEXT_MENU_CREATION", True
            ):
                continue
            metadata = factory.get_widget_metadata(kind)
            option = Gtk.Button(
                label=metadata["name"], tooltip_text=metadata["description"]
            )
            option.add_css_class("flat")
            option.get_child().set_xalign(0)

            def choose(_button, control=kind):
                menu.popdown()
                self.window.begin_placement(control)

            option.connect("clicked", choose)
            picker.append(option)
        popover.connect("closed", lambda *_: stack.set_visible_child_name("mapping"))
        return stack

    def _build_layout_picker(self, pages):
        page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        pages.add_named(page, "layouts")
        page.append(
            MenuRow(
                "go-previous-symbolic",
                _("Saved layouts"),
                lambda: pages.set_visible_child_name("mapping"),
            )
        )
        page.append(Gtk.Separator())
        scroller = Gtk.ScrolledWindow(
            max_content_height=220,
            propagate_natural_height=True,
            hscrollbar_policy=Gtk.PolicyType.NEVER,
        )
        page.append(scroller)

        def show_files():
            # Read on demand so a scheme saved in a file picker (or another
            # helper window) immediately appears on the next visit.
            choices = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
            for path in self.window.layout_file_actions.saved_layouts():

                def select(file=path):
                    self.mapping.popdown()
                    self.window.menu_manager.open_layout(
                        str(file), self.window.widget_factory
                    )

                choices.append(
                    MenuRow("document-properties-symbolic", path.stem, select)
                )
            scroller.set_child(choices)
            pages.set_visible_child_name("layouts")

        def browse():
            self.mapping.popdown()
            self.window.menu_manager.load_layout(self.window.widget_factory)

        page.append(MenuRow("document-open-symbolic", _("Open file…"), browse))
        self.mapping.items.append(
            MenuRow("document-open-recent-symbolic", _("Saved layouts"), show_files)
        )

    def sync_mode(self):
        edit = self.window.current_mode == self.window.EDIT_MODE
        self.mode.caption.set_label(_("Finish editing") if edit else _("Edit controls"))
        self.visibility.set_sensitive(not edit)
        hidden = self.window.widget_transparency_controller.is_transparent
        self.visibility.caption.set_label(
            _("Show controls") if hidden else _("Hide controls")
        )
        if edit:
            self.mapping.add_css_class("editing")
        else:
            self.mapping.remove_css_class("editing")

    def _menu(self, icon, label):
        button = Gtk.MenuButton(icon_name=icon, tooltip_text=label)
        popover = Gtk.Popover()
        popover.add_css_class("menu")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        box.set_size_request(205, -1)
        # Popovers live outside the game input subtree. Hand focus back when
        # they close so the first mapped key after using a menu reaches Android.
        popover.connect("closed", lambda *_: self.window.canvas.grab_focus())
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
