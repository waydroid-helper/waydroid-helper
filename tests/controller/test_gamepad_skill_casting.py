from types import SimpleNamespace
from unittest.mock import Mock, patch

import gi
import pytest

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gtk

from waydroid_helper.controller.android.input import AMotionEventAction as Motion
from waydroid_helper.controller.app.emulator_gamepad import GamepadInput
from waydroid_helper.controller.app.mapping_profiles import layout_for_input, supports_control
from waydroid_helper.controller.app.widget_layout_service import WidgetLayoutService
from waydroid_helper.controller.core.event_bus import EventBus, EventType
from waydroid_helper.controller.core.handler.mapping.key_mapping_manager import KeyMappingManager
from waydroid_helper.controller.core.key_system import KeyCombination, KeyRegistry
from waydroid_helper.controller.core.runtime import ControllerRuntimeContext, ScreenGeometry
from waydroid_helper.controller.core.utils import PointerIdManager
from waydroid_helper.controller.widgets.factory import WidgetFactory


@pytest.fixture
def mapping():
    if not Gtk.init_check() or not Gdk.Display.get_default():
        pytest.skip("GTK display unavailable")
    bus, registry = EventBus(), KeyRegistry()
    manager = KeyMappingManager(bus)
    window = SimpleNamespace(
        key_registry=registry, current_mode=1, MAPPING_MODE=1, EDIT_MODE=2,
        key_mapping_handler=SimpleNamespace(ime_visible=False),
        server=SimpleNamespace(connected_event=SimpleNamespace(is_set=lambda: True)),
        key_mapping_manager=manager, event_bus=bus,
        profiles=SimpleNamespace(kind="gamepad"), is_active=lambda: True,
    )
    with patch("gi.require_version", side_effect=ValueError):
        adapter = GamepadInput(window)
    adapter._settings_for = Mock()
    adapter._settings_for.return_value.get_boolean.return_value = False
    pads = [Mock(), Mock()]
    for pad in pads:
        pad.get_mapping.return_value = ""
        pad.get_name.return_value = "Test pad"
        pad.get_guid.return_value = ""
        adapter._connect(None, pad)
    ctx = ControllerRuntimeContext(bus, ScreenGeometry(), PointerIdManager(), registry, None, manager, lambda: False)
    ctx.screen_geometry.set_host_resolution(800, 600)
    ctx.screen_geometry.set_resolution(1600, 1200)
    factory = WidgetFactory(ctx)
    combo = KeyCombination.from_names(["Pad_A"], registry)
    skill = factory.create_widget("gamepadskillcasting", x=200, y=150, width=100, height=100, default_keys={combo})
    skill.set_mapping_mode(True)
    manager.subscribe(skill, combo)
    camera = factory.create_widget("rightstick")
    camera.set_mapping_mode(True)
    events = []
    bus.subscribe(EventType.CONTROL_MSG, lambda ev: events.append((ev.source, ev.data.action, ev.data.position[:2])))
    yield adapter, pads, skill, camera, events
    adapter.close()
    skill.on_delete()
    camera.on_delete()


def axis(adapter, pad, code, value):
    adapter._axis(pad, SimpleNamespace(get_absolute=lambda: (True, code, value)))


def test_held_skill_takes_an_active_camera_and_casts_at_stick_position(mapping):
    pad, (dev, _), skill, camera, events = mapping
    axis(pad, dev, 3, .5)
    assert camera.timer
    pad._transition(dev, "A", True)
    assert events[-3:] == [(camera, Motion.UP, camera.center), (skill, Motion.DOWN, (250, 200)),
                           (skill, Motion.MOVE, (275, 200))]
    assert not camera.timer
    axis(pad, dev, 3, 1)
    axis(pad, dev, 4, 1)
    assert events[-1] == (skill, Motion.MOVE, (285, 235))
    pad._transition(dev, "A", False)
    assert events[-1] == (skill, Motion.UP, (285, 235))
    count = len(events)
    axis(pad, dev, 3, .3)
    axis(pad, dev, 4, 0)
    axis(pad, dev, 3, 0)
    assert len(events) == count
    axis(pad, dev, 4, -.6)
    assert events[-1] == (camera, Motion.DOWN, camera.center)


def test_center_retains_contact_and_other_pad_cannot_aim_or_hold_it(mapping):
    pad, (one, two), skill, _, events = mapping
    pad._transition(one, "A", True)
    pad._transition(two, "A", True)
    axis(pad, two, 3, -.6)
    axis(pad, one, 4, .4)
    axis(pad, one, 4, 0)
    assert [e[1:] for e in events if e[0] is skill] == [
        (Motion.DOWN, (250, 200)), (Motion.MOVE, (250, 220)), (Motion.MOVE, (250, 200)),
    ]
    pad._transition(one, "A", False)
    assert events[-1] == (skill, Motion.UP, (250, 200))
    pad._transition(two, "A", False)
    assert not skill.contacts


def test_reset_and_unplug_end_a_cast_only_once(mapping):
    pad, (dev, _), skill, camera, events = mapping
    for end in (pad.reset, lambda: pad._disconnect(None, dev)):
        pad._transition(dev, "A", True)
        axis(pad, dev, 3, -.5)
        end()
        assert events[-1] == (skill, Motion.UP, (225, 200))
        assert not skill.contacts and not camera.timer
    assert sum(e[0] is skill and e[1] == Motion.UP for e in events) == 2


def test_legacy_profile_uses_one_scaled_radius_and_preserves_keycap(mapping):
    _, _, skill, _, _ = mapping
    old = {"widgets": [
        {"type": "skillcasting", "x": 100, "y": 120, "width": 150, "height": 150,
         "default_keys": [["Pad_A"]], "config": {"cast_timing": {"value": "immediate"},
         "circle_radius": {"value": 999}, "show_hint": {"value": True}}},
        {"type": "cancelcasting", "x": 350, "y": 90, "width": 50, "height": 50,
         "default_keys": [["Pad_B"]]},
    ]}
    converted = layout_for_input(old, "gamepad")
    item, cancel_item = converted["widgets"]
    assert cancel_item["type"] == "gamepadcancelcasting"
    assert item["type"] == "gamepadskillcasting" and list(item["config"]) == ["show_hint"]
    assert not supports_control("gamepad", "skillcasting")
    assert not supports_control("keyboard", item["type"])
    assert layout_for_input({"widgets": [dict(old["widgets"][0], default_keys=[["Q"]])]}, "keyboard")["widgets"][0]["type"] == "skillcasting"

    service = WidgetLayoutService(skill.runtime_context)
    factory = WidgetFactory(skill.runtime_context)
    controls = []
    def place(widget, x, y):
        widget.x, widget.y = x, y
        controls.append(widget)
    assert service.restore_layout(converted, factory, lambda: None, place) == 2
    restored, cancel = controls
    controls.clear()
    assert (cancel.center_x, cancel.center_y) == (375, 115)
    assert str(next(iter(cancel.final_keys))) == "Pad_B"
    assert (restored.center, restored.radius) == ((175, 195), 75)
    assert str(next(iter(restored.final_keys))) == "Pad_A"
    restored.set_cast_radius(82.5)
    assert restored.center == (175, 195)
    saved = service.serialize_layout([restored, cancel])
    skill.screen_geometry.set_host_resolution(1600, 1200)
    assert service.restore_layout(saved, factory, lambda: None, place) == 2
    scaled, scaled_cancel = controls
    assert (scaled_cancel.center_x, scaled_cancel.center_y) == (750, 230)
    assert (scaled.center, scaled.radius) == ((350, 390), 165)


def test_gamepad_cancel_moves_and_lifts_the_original_finger_only(mapping):
    pad, (one, other), skill, camera, _ = mapping
    ctx = skill.runtime_context
    combo = KeyCombination.from_names(["Pad_B"], ctx.key_registry)
    target = WidgetFactory(ctx).create_widget("gamepadcancelcasting", x=475, y=75, default_keys={combo})
    target.set_mapping_mode(True)
    ctx.key_mapping_service.subscribe(target, combo)
    messages = []
    ctx.event_bus.subscribe(EventType.CONTROL_MSG, lambda event: messages.append(event.data))

    pad._transition(one, "B", True)
    pad._transition(one, "B", False)
    assert messages == []
    pad._transition(one, "A", True)
    axis(pad, one, 3, .5)
    pad._transition(other, "B", True)
    pad._transition(other, "B", False)
    assert skill.contacts and messages[-1].position[:2] == (275, 200)
    pad._transition(one, "B", True)
    assert [(m.action, m.position[:2]) for m in messages] == [
        (Motion.DOWN, (250, 200)), (Motion.MOVE, (275, 200)),
        (Motion.MOVE, (500, 100)), (Motion.UP, (500, 100)),
    ]
    assert len({m.pointer_id for m in messages}) == 1
    assert not skill.contacts and not camera.contacts
    pad._transition(one, "B", False)
    pad._transition(one, "A", False)
    assert len(messages) == 4
    pad._transition(one, "A", True)
    pad._transition(one, "A", False)
    assert messages[-1].action == Motion.UP and messages[-1].position[:2] == (275, 200)
