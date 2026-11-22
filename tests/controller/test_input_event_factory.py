from __future__ import annotations

from waydroid_helper.controller.app.input_event_factory import GtkInputEventFactory
from waydroid_helper.controller.core.handler.event_handlers import (
    InputEventSource,
    InputEventType,
)
from waydroid_helper.controller.core.key_system import KeyRegistry


class FakeDisplay:
    def translate_key(self, keycode, state, group):
        return True, ord("A"), 0, 0, 0


class FakeWidget:
    def get_display(self):
        return FakeDisplay()


class FakeGestureClick:
    def __init__(self, button: int):
        self._button = button

    def get_current_button(self) -> int:
        return self._button

    def get_current_event(self):
        return None


def test_key_event_uses_physical_key_for_capture_normalization():
    factory = GtkInputEventFactory(FakeWidget(), KeyRegistry())

    event = factory.create_key_event(
        InputEventType.KEY_PRESS,
        None,
        ord("a"),
        38,
        0,
    )

    assert event is not None
    assert event.event_type == InputEventType.KEY_PRESS
    assert event.source == InputEventSource.GTK
    assert event.key.name == "A"
    assert event.key_symbol_name == "a"
    assert event.text == "a"


def test_mouse_capture_event_uses_normalized_mouse_key():
    factory = GtkInputEventFactory(FakeWidget(), KeyRegistry())

    event = factory.create_mouse_capture_event(
        InputEventType.MOUSE_PRESS,
        FakeGestureClick(button=3),
        n_press=2,
        x=12.8,
        y=25.2,
    )

    assert event is not None
    assert event.event_type == InputEventType.MOUSE_PRESS
    assert event.source == InputEventSource.GTK
    assert event.key.name == "Mouse_Right"
    assert event.button == 3
    assert event.n_press == 2
    assert event.position == (12, 25)


def test_embedded_button_position_removes_csd_shadow_and_inverts_canvas_transform():
    from gi.repository import Gdk, Graphene
    from unittest.mock import Mock

    canvas = Mock()
    native = canvas.get_native.return_value
    native.get_surface_transform.return_value = (25, 25)

    def to_canvas(widget, point):
        assert widget is canvas
        # Window decoration adds a 43-unit header. The 960x540 logical
        # canvas is displayed at 720x405, a scale of three quarters.
        return True, Graphene.Point().init(point.x / .75, (point.y - 43) / .75)

    native.compute_point.side_effect = to_canvas
    event = Mock()
    event.get_event_type.return_value = Gdk.EventType.BUTTON_PRESS
    event.get_button.return_value = Gdk.BUTTON_PRIMARY
    event.get_modifier_state.return_value = 0
    event.get_position.return_value = (True, 385, 270.5)
    factory = GtkInputEventFactory(canvas, KeyRegistry(), surface_to_widget=True)

    assert factory.create_mouse_button_event(None, event).position == (480, 270)
