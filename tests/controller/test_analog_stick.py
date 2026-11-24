from types import SimpleNamespace

import pytest

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")

from gi.repository import Gdk, Gtk

from waydroid_helper.controller.android.input import AMotionEventAction as Motion
from waydroid_helper.controller.core.event_bus import Event, EventBus, EventType
from waydroid_helper.controller.core.key_system import KeyRegistry
from waydroid_helper.controller.core.runtime import (
    ControllerRuntimeContext,
    ScreenGeometry,
)
from waydroid_helper.controller.core.utils import PointerIdManager
from waydroid_helper.controller.widgets.components.analog_stick import AnalogStick
from waydroid_helper.controller.app.emulator_gamepad import GamepadInput


@pytest.fixture
def control():
    if not Gtk.init_check() or not Gdk.Display.get_default():
        pytest.skip("GTK display unavailable")
    context = ControllerRuntimeContext(
        EventBus(),
        ScreenGeometry(),
        PointerIdManager(),
        KeyRegistry(),
        object(),
        object(),
        lambda: False,
    )
    context.screen_geometry.set_host_resolution(800, 600)
    context.screen_geometry.set_resolution(1600, 1200)
    messages = []
    context.event_bus.subscribe(
        EventType.CONTROL_MSG, lambda ev: messages.append(ev.data)
    )
    stick = AnalogStick(x=100, y=100, width=200, height=200, runtime_context=context)
    stick.set_mapping_mode(True)
    return stick, messages


def test_fractional_travel_and_disconnect_release(control):
    stick, events = control
    stick.set_config_value("deadzone", 0)
    pad = GamepadInput.__new__(GamepadInput)
    pad.window = SimpleNamespace(
        profiles=SimpleNamespace(kind="keyboard"),
        is_active=lambda: True,
        current_mode=1,
        MAPPING_MODE=1,
        key_mapping_handler=SimpleNamespace(ime_visible=False),
        server=SimpleNamespace(connected_event=SimpleNamespace(is_set=lambda: True)),
        event_bus=stick.event_bus,
    )
    pad.held, pad.sticks, pad.devices = set(), {}, {}
    pad._axis("one", SimpleNamespace(get_absolute=lambda: (True, 0, 0.25)))
    assert not events
    pad.window.profiles.kind = "gamepad"
    pad.window.key_mapping_handler.ime_visible = True
    pad._axis("one", SimpleNamespace(get_absolute=lambda: (True, 0, 0.25)))
    assert not events
    pad.window.key_mapping_handler.ime_visible = False
    pad._axis("one", SimpleNamespace(get_absolute=lambda: (True, 0, 0.25)))
    assert [m.action for m in events] == [Motion.DOWN, Motion.MOVE]
    assert events[-1].position == (225, 200, 800, 600)
    pad._axis("other", SimpleNamespace(get_absolute=lambda: (True, 0, -0.4)))
    assert len(events) == 2
    pad._disconnect(None, "one")
    assert events[-1].action == Motion.UP
    assert not stick.contacts


@pytest.mark.parametrize("kind", ["analogstick", "rightstick"])
def test_resizing_stick_actions_preserves_touch_center_after_reload(control, kind):
    from waydroid_helper.controller.app.widget_layout_service import WidgetLayoutService
    from waydroid_helper.controller.widgets.factory import WidgetFactory

    runtime = control[0].runtime_context
    factory = WidgetFactory(runtime)
    stick = factory.create_widget(kind, x=125, y=90, width=137, height=117)
    fixed = Gtk.Fixed()
    fixed.put(stick, stick.x, stick.y)
    center = stick.center
    for action in ("move", "look"):
        stick.set_config_value("action", action)
        for side, dx, dy in (("w", -11.5, 0), ("s", 0, 8.25)):
            fixed.allocate(800, 600, -1, None)
            w, h = stick.width, stick.height
            x, y = (2, h / 2) if side == "w" else (w / 2, h - 2)
            assert stick.check_resize_direction(x, y) == side
            gx, gy = fixed.get_child_position(stick)
            stick.start_resize(x, y, side)
            stick.handle_resize_motion(gx + x + dx, gy + y + dy)
            stick.on_resize_release()
            assert stick.center == pytest.approx(center)
            if action == "move":
                assert stick.width > w and stick.height > h
                assert stick.width / stick.height == pytest.approx(w / h)
            else:
                assert (stick.width, stick.height) == pytest.approx((w - 2 * dx, h + 2 * dy))

    service = WidgetLayoutService(runtime)
    layout = service.serialize_layout([stick])
    restored = []

    def place(widget, x, y):
        widget.x, widget.y = x, y
        restored.append(widget)

    assert service.restore_layout(layout, factory, lambda: None, place) == 1
    assert restored[0].center == pytest.approx(center)
    fixed.remove(stick)
    stick.on_delete()
    restored[0].on_delete()


def test_right_pan_balances_contacts_on_edit(control):
    stick, events = control
    stick.set_config_value("stick", "right")
    stick.set_config_value("action", "look")
    stick.event_bus.emit(Event(EventType.GAMEPAD_STICK, None, ("one", "right", 1, 0)))
    assert stick.timer and events[-1].action == Motion.DOWN
    stick.last_tick -= 0.04
    stick._pan()
    assert events[-1].position[0] > 200
    stick.set_mapping_mode(False)
    assert events[-1].action == Motion.UP
    assert not stick.timer and not stick.contacts


def test_pinch_pool_exhaustion_rolls_back_only_its_own_fingers(control):
    from waydroid_helper.controller.widgets.components.gestures import Pinch

    stick, messages = control
    pool = stick.pointer_id_manager
    for i in range(9):
        pool.allocate(("held", i))
    pinch = Pinch(runtime_context=stick.runtime_context)
    pinch.set_mapping_mode(True)
    assert not pinch.on_key_triggered()
    assert [m.action for m in messages] == [Motion.DOWN, Motion.UP]
    assert pool.get_status()["allocated_count"] == 9
    assert not pinch.contacts and not pinch.timer


def test_swipe_and_zoom_layout_round_trip(control):
    from waydroid_helper.controller.app.widget_layout_service import WidgetLayoutService
    from waydroid_helper.controller.widgets.factory import WidgetFactory

    context = control[0].runtime_context
    factory = WidgetFactory(context)
    swipe = factory.create_widget("swipe")
    assert swipe.set_config_value("path", [[0.1, 0.2], [0.3, 0.4], [0.7, 0.6]])
    zoom = factory.create_widget("pinch")
    service = WidgetLayoutService(context)
    data = service.serialize_layout([swipe, zoom])
    result = []
    service.restore_layout(
        data, factory, lambda: None, lambda widget, *_: result.append(widget)
    )
    assert result[0].paths(False) == swipe.paths(False)
    assert set(map(str, result[1].final_keys)) == {
        "Wheel_Up",
        "Wheel_Down",
    }
    assert factory.create_widget("rightstick").get_config_value("action") == "look"

    # The pre-keycap format stored both directions in a flat default_keys
    # array. Reopening it must preserve the modifier on both wheel bindings.
    original = data["widgets"][1]
    original.pop("binding_rows")
    original["default_keys"] = [["Ctrl_L", "Wheel_Up"], ["Ctrl_L", "Wheel_Down"]]
    result.clear()
    service.restore_layout(data, factory, lambda: None, lambda w, *_: result.append(w))
    assert {k: set(map(str, keys)) for k, keys in result[1].rows.items()} == {
        "forward": {"Ctrl_L+Wheel_Up"}, "reverse": {"Ctrl_L+Wheel_Down"}
    }


def test_swipe_replays_turns_even_if_a_frame_misses_the_whole_stroke(control):
    import time
    from waydroid_helper.controller.widgets.components.gestures import Swipe

    stick, events = control
    swipe = Swipe(runtime_context=stick.runtime_context)
    path = [(32, 40), (124, 63), (50, 76), (96, 30), (32, 40)]
    swipe.x, swipe.y = swipe.set_recorded_path(path, 250, 800, 600)
    swipe.set_mapping_mode(True)
    assert swipe.on_key_triggered()
    from gi.repository import GLib

    GLib.source_remove(swipe.timer)
    swipe.started = time.monotonic() - 1
    assert not swipe._advance()
    assert [event.position[:2] for event in events] == [*path, path[-1]]
    assert not swipe.contacts


def test_paired_capture_does_not_steal_a_held_prefix_from_the_other_row(control):
    from waydroid_helper.controller.core.key_system import KeyCombination
    from waydroid_helper.controller.widgets.components.gestures import Scroll
    from waydroid_helper.controller.widgets.base.decorator_contracts import EditableWidgetBehavior

    widget = Scroll(runtime_context=control[0].runtime_context)
    registry = widget.key_registry
    ctrl = KeyCombination.from_names(["Ctrl_L"], registry)
    x = KeyCombination.from_names(["X"], registry)
    reverse, forward = widget.get_editable_regions()[::-1]
    reverse["set_keys"]({ctrl})
    editor = widget.get_widget_behavior(EditableWidgetBehavior)
    left, top, width, height = forward["bounds"]
    editor.capture_at(left + width / 2, top + height / 2)
    editor.capture_external_key(next(iter(ctrl)), True)
    editor.capture_external_key(next(iter(x)), True)
    editor.capture_external_key(next(iter(x)), False)
    editor.capture_external_key(next(iter(ctrl)), False)
    assert reverse["get_keys"]() == {ctrl}
    assert forward["get_keys"]() == {x}
    assert widget.capture_region == "forward"
    editor.capture_external_key(next(iter(ctrl)), True)
    editor.cancel_editing()
    assert forward["get_keys"]() == {x}
    assert reverse["get_keys"]() == {ctrl}
