"""Adaptive libadwaita preference sheets used by the emulator's local tools."""

from gi.repository import Adw, Gtk

_Preferences = getattr(Adw, "PreferencesDialog", None) or Adw.PreferencesWindow


class EmulatorPreferences(_Preferences):
    def __init__(self, parent, title, height=440):
        # Let libadwaita choose the dialog presentation for the parent window.
        # Before 1.5, the same rows live in a transient preferences window,
        # whose presentation, close signal and close inhibition use GTK APIs.
        if _Preferences is Adw.PreferencesWindow:
            super().__init__(
                title=title,
                transient_for=parent,
                modal=True,
                default_width=520,
                default_height=height,
            )
        else:
            super().__init__(title=title, content_width=520, content_height=height)
        self.parent_window = parent
        self.set_search_enabled(False)
        self.page = Adw.PreferencesPage()
        self.add(self.page)

    def present(self):
        if isinstance(self, Gtk.Window):
            super().present()
        else:
            super().present(self.parent_window)

    def on_dismissed(self, callback):
        self.connect("destroy" if isinstance(self, Gtk.Window) else "closed", callback)

    def set_busy(self, busy):
        self.page.set_sensitive(not busy)
        if isinstance(self, Gtk.Window):
            self.set_deletable(not busy)
        else:
            self.set_can_close(not busy)


def add_spin(group, title, value, low, high, step=1, digits=0):
    if hasattr(Adw, "SpinRow"):
        control = row = Adw.SpinRow.new_with_range(low, high, step)
        row.set_title(title)
    else:
        control = Gtk.SpinButton.new_with_range(low, high, step)
        control.set_valign(Gtk.Align.CENTER)
        row = Adw.ActionRow(title=title, activatable_widget=control)
        row.add_suffix(control)
    control.set_digits(digits)
    control.set_value(value)
    group.add(row)
    return control


def add_switch_row(group, title):
    if hasattr(Adw, "SwitchRow"):
        control = row = Adw.SwitchRow(title=title)
    else:
        control = Gtk.Switch(valign=Gtk.Align.CENTER)
        row = Adw.ActionRow(title=title, activatable_widget=control)
        row.add_suffix(control)
    group.add(row)
    return control


def add_switch(group, title, settings, key):
    control = add_switch_row(group, title)
    settings.bind(key, control, "active", 0)


def add_hint_opacity(group, title, settings):
    scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0, 1, 0.01)
    scale.set_draw_value(False)
    scale.set_valign(Gtk.Align.CENTER)
    scale.set_size_request(140, -1)
    scale.set_tooltip_text(title)
    settings.bind("emulator-hint-opacity", scale.get_adjustment(), "value", 0)
    row = Adw.ActionRow(title=title, activatable_widget=scale)
    row.add_suffix(scale)
    group.add(row)
    return row
