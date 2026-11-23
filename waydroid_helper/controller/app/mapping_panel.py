"""Input-device tabs and the dedicated editing header for the embedded window."""

from gettext import gettext as _

from gi.repository import Adw, GObject, Gtk, Pango

from waydroid_helper.controller.app.emulator_preferences import (
    add_hint_opacity,
    add_switch_row,
)
from waydroid_helper.controller.app.mapping_profiles import ProfileLibrary


class MappingPanel:
    def __init__(self, window, button):
        self.window = window
        self.button = button
        self.popover = button.get_popover()
        root = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=8,
            margin_top=8,
            margin_bottom=8,
            margin_start=8,
            margin_end=8,
        )
        root.set_size_request(295, -1)
        self.popover.set_child(root)
        labels = (_("Keyboard and mouse"), _("Gamepad"))
        if hasattr(Adw, "ToggleGroup"):
            self.tabs = Adw.ToggleGroup(homogeneous=True)
            for kind, label in zip(ProfileLibrary.INPUTS, labels):
                self.tabs.add(Adw.Toggle(name=kind, label=label))
            self.tabs.connect(
                "notify::active-name",
                lambda tabs, _: self.select(tabs.get_active_name()),
            )
            root.append(self.tabs)
        else:
            self.tabs = Adw.ViewStack()
            for kind, label in zip(ProfileLibrary.INPUTS, labels):
                self.tabs.add_titled(Gtk.Box(), kind, label)
            root.append(
                Adw.ViewSwitcher(stack=self.tabs, policy=Adw.ViewSwitcherPolicy.WIDE)
            )
            root.append(self.tabs)
            self.tabs.connect(
                "notify::visible-child-name",
                lambda tabs, _: self.select(tabs.get_visible_child_name()),
            )
        self.pages = Gtk.Stack(vhomogeneous=False)
        root.append(self.pages)
        self.empty = Adw.StatusPage(icon_name="document-new-symbolic")
        self.empty.add_css_class("compact")
        create = Gtk.Button(label=_("New profile"), halign=Gtk.Align.CENTER)
        create.add_css_class("suggested-action")
        create.connect(
            "clicked", lambda *_: self.act(lambda: window.edit_profile(new=True))
        )
        self.empty.set_child(create)
        self.pages.add_named(self.empty, "empty")

        body = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        self.pages.add_named(body, "profiles")
        self.choices = Gtk.DropDown()
        self.choice_handler = self.choices.connect("notify::selected", self._choose)
        body.append(self.choices)
        buttons = Gtk.Box(homogeneous=True, spacing=6)
        for name, callback in [
            (_("New profile"), lambda: window.edit_profile(new=True)),
            (_("Edit controls"), window.edit_profile),
            (_("Manage profiles"), window.open_profiles),
        ]:
            action = Gtk.Button(label=name)
            action.connect("clicked", lambda _, f=callback: self.act(f))
            buttons.append(action)
        body.append(buttons)
        hint_group = Adw.PreferencesGroup()
        body.append(hint_group)
        self.hints = add_switch_row(hint_group, _("Show control hints (F12)"))
        self.hint_handler = self.hints.connect(
            "notify::active", lambda *_: window.toggle_all_widgets_transparency()
        )
        opacity = add_hint_opacity(hint_group, _("Opacity"), window.preferences)
        self.hints.bind_property(
            "active", opacity, "sensitive", GObject.BindingFlags.SYNC_CREATE
        )
        self.popover.connect("show", lambda *_: self.refresh())

    def act(self, callback):
        self.button.popdown()
        callback()

    def select(self, kind):
        if kind and kind != self.window.profiles.kind:
            self.window.select_input(kind)
        if hasattr(self, "pages"):
            self.refresh()

    def _choose(self, combo, _prop):
        index = combo.get_selected()
        if index < len(self.entries):
            try:
                self.window.profiles.apply(self.entries[index][0])
            except (ValueError, OSError) as error:
                self.window.show_notification(str(error))
                self.refresh()

    def refresh(self):
        workspace = self.window.profiles
        kind = workspace.kind
        if isinstance(self.tabs, Adw.ViewStack):
            self.tabs.set_visible_child_name(kind)
        else:
            self.tabs.set_active_name(kind)
        library = workspace.library()
        self.entries = library.entries()
        self.empty.set_title(
            _("No gamepad profiles")
            if kind == "gamepad"
            else _("No keyboard and mouse profiles")
        )
        self.pages.set_visible_child_name("profiles" if self.entries else "empty")
        with self.choices.handler_block(self.choice_handler):
            self.choices.set_model(
                Gtk.StringList.new([name for _, name, _ in self.entries])
            )
            active = library.active()
            self.choices.set_selected(
                next(
                    (i for i, e in enumerate(self.entries) if e[0] == active),
                    Gtk.INVALID_LIST_POSITION,
                )
            )
        with self.hints.handler_block(self.hint_handler):
            self.hints.set_active(
                not self.window.widget_transparency_controller.is_transparent
            )


class MappingEditorBar:
    def __init__(self, window):
        self.widget = Adw.HeaderBar(
            show_start_title_buttons=False, show_end_title_buttons=False
        )
        self.window = window
        self.widget.add_css_class("flat")
        if hasattr(self.widget, "set_show_title"):
            self.widget.set_show_title(False)
        else:
            self.widget.set_title_widget(Gtk.Box())
        actions = Gtk.Box(spacing=4)
        self.widget.pack_end(actions)
        self.title = Gtk.Label(
            xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END
        )
        self.widget.pack_start(self.title)
        self.tools = []
        for label, icon, callback in [
            (_("Tutorial"), "help-browser-symbolic", self.tutorial),
            (_("Rename"), "document-edit-symbolic", self.rename),
            (_("Clear"), "edit-clear-all-symbolic", self.clear),
        ]:
            button = Gtk.Button(tooltip_text=label)
            button.add_css_class("flat")
            content = Gtk.Box(spacing=4)
            content.append(Gtk.Image(icon_name=icon))
            text = Gtk.Label(label=label)
            content.append(text)
            button.set_child(content)
            self.tools.append(text)
            button.connect("clicked", lambda _, f=callback: f())
            actions.append(button)
        cancel = Gtk.Button(label=_("Cancel"))
        cancel.connect("clicked", lambda *_: window.finish_profile(False))
        actions.append(cancel)
        self.save = Gtk.Button(label=_("Save"))
        self.save.add_css_class("suggested-action")
        self.save.connect("clicked", lambda *_: window.finish_profile(True))
        actions.append(self.save)

    def sync(self):
        edit = self.window.profiles.edit
        if edit:
            self.title.set_text(_("Editing profile · %s") % edit.name)
            self.save.set_sensitive(self.window.profiles.dirty())

    def compact(self, value):
        for label in self.tools:
            label.set_visible(not value)

    def rename(self):
        from waydroid_helper.controller.app.mapping_profiles_dialog import (
            ask_profile_text,
        )

        workspace = self.window.profiles
        edit = workspace.edit

        def update(name):
            if workspace.edit is edit:
                edit.name = name
                self.sync()

        ask_profile_text(self.window, _("Rename profile"), edit.name, update)

    def clear(self):
        self.window.on_clear_widgets(None)
        self.sync()

    def tutorial(self):
        from waydroid_helper.controller.app.emulator_preferences import (
            EmulatorPreferences,
        )

        sheet = EmulatorPreferences(self.window, _("Tutorial"), height=330)
        group = Adw.PreferencesGroup()
        sheet.page.add(group)
        for title, tip in [
            (_("Add control"), _("Right-click the Android image to place a control.")),
            (
                _("Edit controls"),
                _(
                    "Click a key label and press the input to bind. Drag the control to move it. Open its settings to adjust it."
                ),
            ),
            (
                _("Save profile"),
                _("Save applies this profile. Cancel restores your previous controls."),
            ),
        ]:
            group.add(Adw.ActionRow(title=title, subtitle=tip))
        sheet.present()
