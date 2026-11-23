"""Native profile library for the foreground Android application."""

import asyncio
import json
from gettext import gettext as _

from gi.repository import Adw, Gio, GLib, Gtk

from waydroid_helper.compat_widget import MessageDialog
from waydroid_helper.controller.app.emulator_preferences import (
    EmulatorPreferences,
    add_hint_opacity,
)
from waydroid_helper.controller.app.mapping_profiles import layout_for_input
from waydroid_helper.util.log import logger


def ask_profile_text(parent, title, initial, callback, field=None):
    sheet = EmulatorPreferences(parent, title, height=250)
    group = Adw.PreferencesGroup()
    sheet.page.add(group)
    if hasattr(Adw, "EntryRow"):
        entry = Adw.EntryRow(title=field or _("Profile name"))
        group.add(entry)
    else:
        row = Adw.ActionRow(title=field or _("Profile name"))
        entry = Gtk.Entry(valign=Gtk.Align.CENTER)
        row.add_suffix(entry)
        group.add(row)
    entry.set_text(initial)
    ok = Gtk.Button(label=_("Save"), halign=Gtk.Align.END, margin_top=12)
    ok.add_css_class("suggested-action")
    group.add(ok)

    def submit(*_):
        if entry.get_text().strip() or field:
            if callback(entry.get_text().strip()) is not False:
                sheet.close()

    ok.connect("clicked", submit)
    entry.connect(
        (
            "entry-activated"
            if isinstance(entry, getattr(Adw, "EntryRow", ()))
            else "activate"
        ),
        submit,
    )
    sheet.present()
    entry.grab_focus()


class MappingProfilesDialog(EmulatorPreferences):
    def __init__(self, window, kind):
        super().__init__(window, _("Mapping profiles"), height=560)
        self.workspace = window.profiles
        self.package = self.workspace.package
        self.group = Adw.PreferencesGroup(
            title=_("Android Home") if self.package == "home" else self.package
        )
        self.page.add(self.group)
        self.kind = kind
        self.status = Adw.ActionRow(title=_("Connected gamepads"))
        self.group.add(self.status)
        add_hint_opacity(self.group, _("Hint opacity"), window.preferences)
        self.list_group = Adw.PreferencesGroup(title=_("Saved profiles"))
        reload_button = Gtk.Button(
            icon_name="view-refresh-symbolic", tooltip_text=_("Refresh")
        )
        reload_button.add_css_class("flat")
        reload_button.connect("clicked", lambda *_: self.refresh())
        self.list_group.set_header_suffix(reload_button)
        self.page.add(self.list_group)
        self.profile_rows = []
        self.controls = Adw.PreferencesGroup()
        self.page.add(self.controls)
        self.action(self.controls, _("New profile"), "list-add-symbolic", self.new)
        self.action(
            self.controls,
            _("Save current controls as…"),
            "document-save-as-symbolic",
            self.save_as,
        )
        self.action(
            self.controls,
            _("Import layout…"),
            "document-open-symbolic",
            self.import_layout,
        )
        self.monitor_handlers = []
        monitor = window.gamepad.monitor
        if monitor:
            for signal in ("device-connected", "device-disconnected"):
                self.monitor_handlers.append(
                    monitor.connect_after(signal, lambda *_: self.devices_changed())
                )

        def disconnect_monitor(*_):
            for handler in self.monitor_handlers:
                monitor.disconnect(handler)

        self.on_dismissed(disconnect_monitor)
        self.refresh()

    def devices_changed(self):
        names = [d.get_name() for d in self.parent_window.gamepad.devices]
        subtitle = ", ".join(names) or _("No gamepad connected")
        if self.parent_window.gamepad.monitor is None:
            subtitle = _("Gamepad bindings require libmanette 0.2")
        self.status.set_subtitle(subtitle)
        self.status.set_visible(self.kind == "gamepad")

    def action(self, group, title, icon, callback):
        row = Adw.ActionRow(title=title, activatable=True)
        row.add_prefix(Gtk.Image(icon_name=icon))
        row.connect("activated", lambda *_: self.run(callback))
        group.add(row)

    def run(self, callback):
        try:
            callback()
            return True
        except (OSError, ValueError, KeyError, TypeError, GLib.Error) as error:
            logger.exception("Mapping profile action failed for %s", self.package)
            self.alert(_("Could not update mapping profile"), str(error))
            return False

    def alert(self, title, message):
        dialog = MessageDialog(heading=title, body=message, parent=self.parent_window)
        dialog.add_response(Gtk.ResponseType.CLOSE, _("Close"))
        dialog.present()

    def refresh(self):
        if self.workspace.package != self.package:
            return
        self.devices_changed()
        for row in self.profile_rows:
            self.list_group.remove(row)
        self.profile_rows.clear()
        lib = self.workspace.library(self.kind)
        entries = lib.entries()
        if not entries:
            empty = Adw.ActionRow(title=_("No saved profiles"))
            self.list_group.add(empty)
            self.profile_rows.append(empty)
            return
        active = lib.active()
        for ident, name, pinned in entries:
            row = Adw.ExpanderRow(title=GLib.markup_escape_text(name))
            if pinned:
                row.add_prefix(Gtk.Image(icon_name="view-pin-symbolic"))
            if ident == active:
                row.set_subtitle(_("In use"))
            self.list_group.add(row)
            self.profile_rows.append(row)

            def option(title, icon, callback, key=ident):
                action = Adw.ActionRow(title=title, activatable=True)
                action.add_prefix(Gtk.Image(icon_name=icon))
                action.connect("activated", lambda *_: self.run(lambda: callback(key)))
                row.add_row(action)

            option(_("Apply"), "object-select-symbolic", self.apply)
            option(
                _("Edit controls"),
                "document-edit-symbolic",
                lambda key: self.apply(key, edit=True),
            )
            option(_("Profile notes"), "text-x-generic-symbolic", self.notes)
            option(_("Rename"), "insert-text-symbolic", self.rename)
            option(_("Duplicate"), "edit-copy-symbolic", self.duplicate)
            option(_("Unpin") if pinned else _("Pin"), "view-pin-symbolic", self.pin)
            option(_("Export layout…"), "document-send-symbolic", self.export_layout)
            option(
                _("Open file location"),
                "folder-open-symbolic",
                lambda key: Gio.AppInfo.launch_default_for_uri(
                    lib.folder.as_uri(), None
                ),
            )
            option(_("Delete"), "user-trash-symbolic", self.delete)

    def ask_name(self, title, initial, callback, field=None):
        def save(value):
            if (
                self.workspace.package == self.package
                and self.workspace.kind == self.kind
            ):
                return self.run(lambda: callback(value))

        ask_profile_text(self, title, initial, save, field)

    def new(self):
        self.close()
        self.parent_window.edit_profile(new=True)

    def save_as(self):
        lib = self.workspace.library()

        def save(name):
            ident = lib.save(name, self.workspace.capture())
            lib.select(ident)
            self.refresh()

        self.ask_name(_("Save current controls as…"), "", save)

    def apply(self, ident, edit=False):
        if edit:
            self.close()
            self.parent_window.edit_profile(ident=ident)
        else:
            self.workspace.apply(ident)
            self.close()

    def rename(self, ident):
        lib = self.workspace.library()
        data = lib.read(ident)

        def save(name):
            lib.save(name, data, ident, data["profile"].get("pinned"))
            self.refresh()

        self.ask_name(_("Rename profile"), data["profile"]["name"], save)

    def notes(self, ident):
        lib = self.workspace.library()
        data = lib.read(ident)
        info = data["profile"]

        def save(value):
            info["notes"] = value
            lib.save(info["name"], data, ident, info.get("pinned", False))

        self.ask_name(_("Profile notes"), info.get("notes", ""), save, field=_("Notes"))

    def duplicate(self, ident):
        lib = self.workspace.library()
        data = lib.read(ident)

        def save(name):
            lib.save(name, data)
            self.refresh()

        self.ask_name(
            _("Duplicate profile"), _("%s (copy)") % data["profile"]["name"], save
        )

    def pin(self, ident):
        lib = self.workspace.library()
        data = lib.read(ident)
        lib.save(
            data["profile"]["name"], data, ident, not data["profile"].get("pinned")
        )
        self.refresh()

    def delete(self, ident):
        lib = self.workspace.library()
        name = lib.read(ident)["profile"]["name"]
        confirm = MessageDialog(
            heading=_("Delete mapping profile?"), body=name, parent=self.parent_window
        )
        confirm.add_response(Gtk.ResponseType.CANCEL, _("Cancel"))
        confirm.add_response(Gtk.ResponseType.OK, _("Delete"))
        confirm.set_default_response(Gtk.ResponseType.CANCEL)
        confirm.set_response_appearance(Gtk.ResponseType.OK, "destructive-action")

        def response(_dialog, choice):
            if choice in (Gtk.ResponseType.OK, Gtk.ResponseType.OK.value_nick):

                def remove():
                    active = lib.active() == ident
                    Gio.File.new_for_path(str(lib.path(ident))).trash(None)
                    if active and (self.package, self.kind) == (
                        self.workspace.package,
                        self.workspace.kind,
                    ):
                        self.workspace.restore({"widgets": []})
                    self.refresh()

                self.run(remove)

        confirm.connect("response", response)
        confirm.present()

    def import_layout(self):
        lib = self.workspace.library()

        async def read(path):
            data = await asyncio.to_thread(
                lambda: json.loads(path.read_text(encoding="utf-8"))
            )
            data = layout_for_input(data, lib.kind)
            known = self.parent_window.widget_factory.get_available_types()
            if any(item["type"] not in known for item in data["widgets"]):
                raise ValueError(_("Unknown control in layout"))
            lib.save(path.stem, data)
            self.refresh()

        self.parent_window.tools.pick_file(_("Import layout…"), "*.json", read)

    def export_layout(self, ident):
        lib = self.workspace.library()
        data = lib.read(ident)

        async def save(path):
            await asyncio.to_thread(lib.write, path, data)

        self.parent_window.tools.pick_file(
            _("Export layout…"), "*.json", save, "layout.json"
        )
