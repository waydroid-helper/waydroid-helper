"""Per-controller preferences and navigation to the physical input tester."""

from gettext import gettext as _

from gi.repository import Adw, Gio, Gtk

from waydroid_helper.compat_widget import ToolbarView
from waydroid_helper.controller.app.emulator_preferences import add_switch_row
from waydroid_helper.controller.app.gamepad_preview import GamepadPreview


class GamepadSettingsWindow(Adw.PreferencesWindow):
    def __init__(self, parent, pad):
        super().__init__(
            title=pad.name, transient_for=parent, modal=True, destroy_with_parent=True,
            search_enabled=False,
        )
        self.pad = pad
        page = Adw.PreferencesPage()
        self.add(page)
        identity = Adw.PreferencesGroup()
        page.add(identity)
        if hasattr(Adw, "EntryRow"):
            self.name_entry = Adw.EntryRow(title=_("Controller name"))
            identity.add(self.name_entry)
        else:
            self.name_entry = Gtk.Entry(valign=Gtk.Align.CENTER)
            row = Adw.ActionRow(title=_("Controller name"), activatable_widget=self.name_entry)
            row.add_suffix(self.name_entry)
            identity.add(row)
        self.name_entry.set_text(pad.name)
        self.name_entry.connect("changed", self._rename)

        advanced = Adw.PreferencesGroup(title=_("Advanced settings"))
        page.add(advanced)
        switch = add_switch_row(advanced, _("Use Nintendo button layout"))
        subtitle = _("Swap A with B and X with Y for mapping and key capture.")
        if isinstance(switch, Adw.ActionRow):
            switch.set_subtitle(subtitle)
        else:
            advanced.set_description(subtitle)
        pad.settings.bind("nintendo-layout", switch, "active", Gio.SettingsBindFlags.DEFAULT)

        test = Adw.ActionRow(title=_("Test device input"))
        start = Gtk.Button(label=_("Start test"), valign=Gtk.Align.CENTER)
        start.connect("clicked", lambda *_: self.start_test())
        test.add_suffix(start)
        test.set_activatable_widget(start)
        advanced.add(test)

    def _rename(self, entry):
        name = entry.get_text().strip()
        self.pad.settings.set_string("name", "" if name == self.pad.device.get_name() else name)
        self.set_title(self.pad.name)

    def start_test(self):
        title = _("Test device input")
        view = Adw.ToolbarView() if hasattr(Adw, "ToolbarView") else ToolbarView()
        header = Adw.HeaderBar()
        header.set_title_widget(Adw.WindowTitle(title=title, subtitle=self.pad.name))
        view.add_top_bar(header)
        view.set_content(GamepadPreview(self.pad.device))
        if hasattr(self, "push_subpage"):
            self.push_subpage(Adw.NavigationPage.new(view, title))
        else:
            back = Gtk.Button(icon_name="go-previous-symbolic", tooltip_text=_("Back"))
            back.connect("clicked", lambda *_: self.close_subpage())
            header.pack_start(back)
            self.present_subpage(view)
