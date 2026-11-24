"""Use an information bar on libadwaita versions earlier than 1.3."""

from gi.repository import Adw, GObject, Gtk


if hasattr(Adw, "Banner"):
    Banner = Adw.Banner
else:
    class Banner(Gtk.InfoBar):
        __gsignals__ = {
            "button-clicked": (GObject.SignalFlags.RUN_LAST, None, ()),
        }

        def __init__(self):
            super().__init__(revealed=False)
            self._label = Gtk.Label(wrap=True)
            self.add_child(self._label)
            self._button = self.add_button("", Gtk.ResponseType.OK)
            self.connect("response", lambda *_: self.emit("button-clicked"))

        def set_title(self, title):
            self._label.set_label(title)

        def set_button_label(self, label):
            self._button.set_label(label)
