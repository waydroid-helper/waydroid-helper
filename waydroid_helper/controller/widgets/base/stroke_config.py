"""Persist the normalized touch path. Recording belongs to the guest canvas."""

from gi.repository import Gtk

from waydroid_helper.controller.widgets.config import ConfigItem


class StrokeConfig(ConfigItem):
    def validate(self, value):
        return (
            isinstance(value, list)
            and len(value) >= 2
            and all(
                isinstance(point, (list, tuple))
                and len(point) == 2
                and all(type(n) in (int, float) and 0 <= n <= 1 for n in point)
                for point in value
            )
        )

    def create_ui_widget(self, changed):
        # The property remains in the layout for old profiles and is edited by
        # the placement gesture, never through a second coordinate system.
        return Gtk.Box(visible=False)

    def get_value_from_ui(self, widget):
        return self.value

    def set_value_to_ui(self, widget, value):
        pass
