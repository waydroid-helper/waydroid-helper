import gi
import pytest

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib, Gtk

from waydroid_helper.controller.android.input import AMotionEventAction as Motion
from waydroid_helper.controller.app.widget_layout_service import WidgetLayoutService
from waydroid_helper.controller.core.event_bus import Event, EventBus, EventType, GamepadTrigger
from waydroid_helper.controller.core.key_system import KeyCombination, KeyRegistry, KeyType
from waydroid_helper.controller.core.runtime import ControllerRuntimeContext, ScreenGeometry
from waydroid_helper.controller.core.utils import PointerIdManager
from waydroid_helper.controller.widgets.factory import WidgetFactory


@pytest.fixture
def setup():
    if not Gtk.init_check() or not Gdk.Display.get_default():
        pytest.skip("GTK display unavailable")
    registry = KeyRegistry()
    for code, button in enumerate(("LT", "RT", "A")):
        registry.register_key("Pad_" + button, -70000 - code, KeyType.SPECIAL)
    ctx = ControllerRuntimeContext(
        EventBus(), ScreenGeometry(), PointerIdManager(), registry, None, None, lambda: False
    )
    ctx.screen_geometry.set_host_resolution(800, 600)
    ctx.screen_geometry.set_resolution(1600, 1200)
    messages = []
    ctx.event_bus.subscribe(EventType.CONTROL_MSG, lambda event: messages.append(event.data))
    return WidgetFactory(ctx), messages


def drive(widget, travel, name="RT", device="one"):
    widget.event_bus.emit(Event(EventType.GAMEPAD_TRIGGER, None, GamepadTrigger(device, name, travel)))


def test_slider_crosses_corners_backwards_and_cancels_in_place(setup):
    factory, messages = setup
    widget = factory.create_widget("triggerslider")
    points = [(100, 100), (160, 100), (160, 180)]
    widget.x, widget.y = widget.set_recorded_path(points, 50, 800, 600)
    widget.set_config_value("deadzone", 0)
    widget.set_mapping_mode(True)
    drive(widget, .5)
    assert [m.position[:2] for m in messages] == [points[0], points[1], (160, 110)]
    drive(widget, 1, device="another")
    assert len(messages) == 3
    drive(widget, 1)
    drive(widget, .25)
    drive(widget, 0)
    assert [m.position[:2] for m in messages[3:]] == [points[2], points[1], (135, 100), points[0], points[0]]
    assert messages[-1].action == Motion.UP
    assert len({m.pointer_id for m in messages}) == 1
    drive(widget, .75)
    last = messages[-1].position
    count = len(messages)
    drive(widget, None)
    assert (len(messages), messages[-1].action, messages[-1].position) == (count + 1, Motion.UP, last)
    assert not widget.contacts


def test_dual_stage_hysteresis_numeric_editor_and_reload(setup):
    factory, messages = setup
    widget = factory.create_widget("dualstagetrigger")
    start, end = (70, 40), (340, 220)
    widget.x, widget.y = widget.set_recorded_path([start, (180, 170), end], 600, 800, 600)
    manager = widget.get_config_manager()
    manager.create_ui_panel()
    spins = manager.ui_widgets["thresholds"].spins
    spins[0].set_value(20)
    spins[1].set_value(80)
    assert widget.get_config_value("thresholds") == [20, 80]
    assert not widget.set_config_value("thresholds", [80, 20])
    data = WidgetLayoutService(widget.runtime_context)
    saved = data.serialize_layout([widget])
    widget.on_delete()
    restored = []
    def place(control, x, y):
        control.x, control.y = x, y
        restored.append(control)
    assert data.restore_layout(saved, factory, lambda: None, place) == 1
    control, = restored
    control.set_mapping_mode(True)
    for value in (.19, .21, .199, .82, .79, .70, .84, 0):
        drive(control, value, "LT")
    assert [(m.action, m.position[:2]) for m in messages] == [
        (Motion.DOWN, start), (Motion.DOWN, end), (Motion.UP, end),
        (Motion.DOWN, end), (Motion.UP, end), (Motion.UP, start),
    ]
    assert messages[0].pointer_id != messages[1].pointer_id
    assert not control.contacts


def test_variable_repeat_does_not_restart_at_digital_threshold_or_leave_timers(setup):
    factory, messages = setup
    combo = KeyCombination.from_names(["Pad_LT"], factory.runtime_context.key_registry)
    repeat = factory.create_widget("repeatedclick", default_keys={combo})
    repeat.enable_trigger_repeat({"LT"})
    repeat.set_config_value("variable_rate", True)
    repeat.set_mapping_mode(True)
    drive(repeat, .15, "LT")
    timer = repeat.trigger_repeat
    old_deadline = timer.next_tap.get_ready_time()
    assert [m.action for m in messages] == [Motion.DOWN]
    drive(repeat, 1, "LT")
    assert timer.next_tap.get_ready_time() < old_deadline
    assert timer.interval_us == 50000
    assert not repeat.on_key_triggered(combo)
    assert not repeat.on_key_released(combo)
    assert not repeat._click_task
    timer.next_tap.set_ready_time(GLib.get_monotonic_time())
    ctx = GLib.MainContext.default()
    while ctx.pending():
        ctx.iteration(False)
    assert [m.action for m in messages] == [Motion.DOWN, Motion.UP, Motion.DOWN]
    repeat.set_mapping_mode(False)
    assert messages[-1].action == Motion.UP
    assert timer.next_tap is None and not timer.lift and not repeat.contacts
    repeat.final_keys = {KeyCombination.from_names(["Pad_A", "Pad_LT"], repeat.key_registry)}
    repeat.enable_trigger_repeat({"LT"})
    assert not repeat.get_config_manager().configs["variable_rate"].visible


def test_digital_trigger_uses_fixed_rate_without_activating_analog_targets(setup):
    factory, messages = setup
    slider = factory.create_widget("triggerslider")
    slider.set_mapping_mode(True)
    repeat = factory.create_widget("repeatedclick", default_keys=slider.final_keys)
    repeat.enable_trigger_repeat(set())
    repeat.set_config_value("variable_rate", True)
    repeat.set_mapping_mode(True)
    assert not repeat.config_manager.configs["variable_rate"].visible
    for travel in (1., 0.):
        event = GamepadTrigger("digital", "RT", travel, analog=False)
        slider.event_bus.emit(Event(EventType.GAMEPAD_TRIGGER, None, event))
    assert [m.action for m in messages] == [Motion.DOWN, Motion.UP]
    assert messages[0].position[:2] == tuple(map(round, repeat.center))
    assert repeat.trigger_repeat.interval_us == 50000
    assert not slider.contacts and not repeat.contacts


def test_focus_reset_cancels_in_place_and_requires_release_before_reactivation(setup):
    from types import SimpleNamespace
    from unittest.mock import patch
    from waydroid_helper.controller.app.emulator_gamepad import GamepadInput, ConnectedGamepad

    factory, msgs = setup
    slider = factory.create_widget("triggerslider")
    slider.set_mapping_mode(True)
    window = SimpleNamespace(
        key_registry=factory.runtime_context.key_registry,
        current_mode=1, MAPPING_MODE=1, profiles=SimpleNamespace(kind="gamepad"),
        is_active=lambda: True, key_mapping_handler=SimpleNamespace(ime_visible=False),
        server=SimpleNamespace(connected_event=SimpleNamespace(is_set=lambda: True)),
        event_bus=slider.event_bus,
    )
    with patch("gi.require_version", side_effect=ValueError):
        adapter = GamepadInput(window)
    adapter.devices["pad"] = ConnectedGamepad("pad", None, analog_triggers={"RT"})
    adapter._trigger("pad", "RT", .7)
    adapter.reset()
    count = len(msgs)
    assert msgs[-1].action == Motion.UP
    adapter._trigger("pad", "RT", .9)
    adapter._trigger("pad", "RT", .3)
    assert len(msgs) == count
    adapter._trigger("pad", "RT", 0)
    adapter._trigger("pad", "RT", .3)
    assert msgs[count].action == Motion.DOWN
    adapter._disconnect(None, "pad")
    assert msgs[-1].action == Motion.UP
