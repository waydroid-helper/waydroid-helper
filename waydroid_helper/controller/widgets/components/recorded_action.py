"""Keep a copy of an Android input recording inside the mapping layout."""

from gettext import gettext as _

from gi.repository import Gtk

from waydroid_helper.controller.widgets.base import control_art as art

from waydroid_helper.controller.core.event_bus import Event, EventType
from waydroid_helper.controller.widgets.base.touch_control import TouchControl
from waydroid_helper.controller.widgets.config import ConfigItem
from waydroid_helper.controller.widgets.decorators import Editable


class RecordingConfig(ConfigItem):
    def validate(self, value):
        return (
            isinstance(value, dict)
            and value.get("version") == 1
            and isinstance(value.get("events"), list)
        )

    def bind_event_bus(self, event_bus):
        self.event_bus = event_bus

    def create_ui_widget(self, changed):
        button = Gtk.Button()
        self.set_value_to_ui(button, self.value)

        def capture(*_):
            def assign(data):
                changed(self.key, data)
                self.set_value_to_ui(button, data)

            self.event_bus.emit(Event(EventType.COPY_RECORDING, self, assign))

        button.connect("clicked", capture)
        return button

    def get_value_from_ui(self, widget):
        return self.value

    def set_value_to_ui(self, button, data):
        count = len(data["events"]) if data else 0
        button.set_label(_("Use latest recording (%d events attached)") % count)


@Editable
class RecordedAction(TouchControl):
    EMBEDDED_ONLY = True
    SETTINGS_SYMBOL = "record"
    WIDGET_NAME = _("Recorded action")
    WIDGET_DESCRIPTION = _(
        "Bind a recording made or imported from the Input recording menu"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_config_item(
            RecordingConfig(
                "recording", _("Input recording"), value={"version": 1, "events": []}
            )
        )

    def get_delete_button_bounds(self):
        return int(self.width / 2 + 8), int(self.height / 2 - 23), 14, 14

    def get_settings_button_bounds(self):
        return int(self.width / 2 + 16), int(self.height / 2 + 7), 16, 16

    def draw_selection_border(self, cr, width, height):
        art.ring(
            cr,
            width / 2,
            height / 2,
            min(20, min(width, height) / 2 - 4),
            self.is_selected,
        )

    def draw_widget_content(self, cr, width, height):
        radius = min(20, min(width, height) / 2 - 4)
        art.disc(cr, width / 2, height / 2, radius, art.BODY, art.OUTLINE)
        x, y = width / 2 + radius * 0.55, height / 2 + radius * 0.84
        art.rounded(cr, x - 8, y - 5, 16, 10, 2)
        cr.set_source_rgb(0.04, 0.57, 0.88)
        cr.fill()
        art.caption(cr, x, y, "REC", 7)

    def on_key_triggered(self, key_combination=None, event=None):
        self.event_bus.emit(
            Event(EventType.PLAY_RECORDING, self, self.get_config_value("recording"))
        )
        return True

    def on_key_released(self, key_combination=None, event=None):
        return True
