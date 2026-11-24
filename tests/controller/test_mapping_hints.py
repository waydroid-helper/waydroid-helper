import asyncio
from unittest.mock import Mock, patch

import cairo
import gi
import pytest

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gtk

from waydroid_helper.controller.android.input import AMotionEventAction as Motion
from waydroid_helper.controller.app.emulator_gamepad import ConnectedGamepad
from waydroid_helper.controller.app.widget_layout_service import WidgetLayoutService
from waydroid_helper.controller.core import (
    ControllerRuntimeContext, EventBus, KeyCombination, KeyRegistry, PointerIdManager,
)
from waydroid_helper.controller.core.event_bus import Event, EventType
from waydroid_helper.controller.core.key_system import KeyType
from waydroid_helper.controller.core.handler.event_handlers import InputEvent, InputEventType
from waydroid_helper.controller.core.handler.mapping.key_mapping_manager import KeyMappingManager
from waydroid_helper.controller.core.runtime import ScreenGeometry
from waydroid_helper.controller.widgets.base.binding_art import keycap
from waydroid_helper.controller.widgets.base import control_art
from waydroid_helper.controller.widgets.components.aim import Aim, AimState
from waydroid_helper.controller.widgets.components.analog_stick import AnalogStick, RightStick
from waydroid_helper.controller.widgets.components.directional_pad import DirectionalPad
from waydroid_helper.controller.widgets.components.single_click import SingleClick
from waydroid_helper.controller.widgets.factory import WidgetFactory


@pytest.fixture
def runtime():
    if not Gtk.init_check() or not Gdk.Display.get_default():
        pytest.skip("GTK display unavailable")
    bus = EventBus()
    geometry = ScreenGeometry()
    geometry.set_host_resolution(800, 600)
    geometry.set_resolution(800, 600)
    return ControllerRuntimeContext(
        event_bus=bus, screen_geometry=geometry, pointer_id_manager=PointerIdManager(),
        key_registry=KeyRegistry(), key_mapping_service=KeyMappingManager(bus),
        input_event_factory=None, is_edit_mode=lambda: False,
    )


def render(widget):
    width, height = widget.MAPPING_MODE_WIDTH, widget.MAPPING_MODE_HEIGHT
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, width, height)
    widget.draw_func(widget, cairo.Context(surface), width, height, None)
    surface.flush()
    return bytes(surface.get_data())


def painted_bounds(widget, fixed):
    """Measure the visible hint in canvas coordinates, including GTK placement."""
    width, height = widget.MAPPING_MODE_WIDTH, widget.MAPPING_MODE_HEIGHT
    surface = cairo.ImageSurface(cairo.FORMAT_A8, width, height)
    widget.draw_func(widget, cairo.Context(surface), width, height, None)
    surface.flush()
    data = bytes(surface.get_data())
    stride = surface.get_stride()
    pixels = [(x, y) for y in range(height) for x in range(width)
              if data[y * stride + x] > 16]
    xs, ys = zip(*pixels)
    x, y = fixed.get_child_transform(widget).to_translate()
    return x + min(xs), y + min(ys), x + max(xs) + 1, y + max(ys) + 1


@pytest.mark.parametrize("kind,placement", [
    ("singleclick", "point"), ("repeatedclick", "point"), ("fire", "point"),
    ("skillcasting", "point"), ("gamepadskillcasting", "point"),
    ("cancelcasting", "point"), ("gamepadcancelcasting", "point"),
    ("macro", "point"), ("recordedaction", "point"),
    ("swipe", "endpoint"), ("triggerslider", "endpoint"), ("dualstagetrigger", "endpoint"),
    ("directionalpad", "center"), ("rightclicktowalk", "center"),
    ("analogstick", "center"), ("rightstick", "center"),
    ("scroll", "center"), ("pinch", "center"),
])
def test_visible_hint_anchor_through_mode_changes(runtime, kind, placement):
    async def switch_modes():
        widget = WidgetFactory(runtime).create_widget(kind, x=120.5, y=94.5, text="J")
        fixed = Gtk.Fixed()
        fixed.put(widget, widget.x, widget.y)
        if placement == "endpoint":
            widget.set_config_value("path", [[.5, .8], [.9, .1], [.22, .65]])
            target = (widget.x + .22 * widget.width, widget.y + .65 * widget.height)
        else:
            target = (widget.x + widget.width / 2, widget.y + widget.height / 2)
        service = WidgetLayoutService(runtime)
        saved = service.serialize_layout([widget])

        try:
            for _ in range(2):
                widget.set_mapping_mode(True)
                left, top, right, bottom = painted_bounds(widget, fixed)
                anchor = (left, top)
                if placement == "center":
                    anchor = ((left + right) / 2, (top + bottom) / 2)
                assert anchor == pytest.approx(target, abs=1)
                assert service.serialize_layout([widget]) == saved
                widget.set_mapping_mode(False)
                assert fixed.get_child_transform(widget).to_translate() == (widget.x, widget.y)
        finally:
            widget.on_delete()

    asyncio.run(switch_modes())


def test_reloaded_path_hint_keeps_its_note_visible_at_the_screen_edge(runtime):
    factory = WidgetFactory(runtime)
    service = WidgetLayoutService(runtime)
    original = factory.create_widget("swipe", x=670, y=480, width=130, height=120, text="Ctrl+J")
    original.enable_hint_settings()
    original.set_config_value("path", [[.1, .1], [1, 1]])
    original.set_config_value("hint_note", "Swipe")
    saved = service.serialize_layout([original])
    runtime.screen_geometry.set_host_resolution(400, 300)
    fixed = Gtk.Fixed()

    def attach(widget, x, y):
        widget.x, widget.y = x, y
        fixed.put(widget, x, y)
        widget.enable_hint_settings()
        widget.set_mapping_mode(True)

    assert service.restore_layout(saved, factory, lambda: None, attach) == 1
    swipe = fixed.get_first_child()
    assert swipe.mapping_anchor == (400, 300)
    assert painted_bounds(swipe, fixed)[2:] == (400, 300)
    swipe.set_config_value("hint_note", "")
    assert painted_bounds(swipe, fixed)[2:] == (400, 300)
    swipe.set_config_value("path", [[.6, .1], [.1, .3]])
    assert painted_bounds(swipe, fixed)[:2] == pytest.approx((341.5, 258), abs=1)


def test_directional_pad_uses_the_same_arrow_labels_in_both_modes(runtime):
    bindings = {
        direction: KeyCombination.from_names(keys, runtime.key_registry)
        for direction, keys in (
            ("up", ["Ctrl_L", "Up"]), ("down", ["Down"]),
            ("left", ["Left"]), ("right", ["Right"]),
        )
    }
    pad = DirectionalPad(runtime_context=runtime, direction_keys=bindings)
    expected = ["Ctrl+↑", "↓", "←", "→"]
    assert [keycap(pad, r).layout.get_text() for r in pad.get_editable_regions()] == expected

    pad.set_mapping_mode(True)
    with patch.object(control_art, "caption", wraps=control_art.caption) as caption:
        render(pad)
        assert [call.args[3] for call in caption.call_args_list] == expected


@pytest.mark.parametrize("family,faces,swapped_faces,extra_labels", [
    *[(family, "×○□△", "○×△□", ("L1", "R1", "L2", "R2", "L3", "R3"))
      for family in ("ps3", "ps4", "ps5")],
    *[(family, "BAYX", "ABXY", ("L", "R", "ZL", "ZR", "Ⓛ", "Ⓡ"))
      for family in ("switch-pro", "joycon-pair")],
])
def test_keycaps_follow_physical_buttons_without_changing_layout(runtime, family, faces, swapped_faces, extra_labels):
    device = ConnectedGamepad(Mock(), Mock(), family, mapped=True)
    keys = runtime.key_registry
    extra_buttons = ("LB", "RB", "LT", "RT", "LS", "RS")
    for index, name in enumerate((*"ABXY", *extra_buttons)):
        keys.register_key("Pad_" + name, -65536 - index, KeyType.SPECIAL)
    bindings = {
        direction: KeyCombination.from_names(["Pad_" + name], keys)
        for direction, name in zip(DirectionalPad.DIRECTIONS, "ABXY")
    }
    pad = DirectionalPad(runtime_context=runtime, direction_keys=bindings)
    combo = KeyCombination.from_names(["Pad_LB", "Pad_X", "Pad_Y"], keys)
    tap = SingleClick(runtime_context=runtime, default_keys={combo}, text=combo.display_text)
    region, = tap.get_editable_regions()
    service = WidgetLayoutService(runtime)
    saved = service.serialize_layout([tap, pad])

    for swapped, expected in [(False, faces), (True, swapped_faces)]:
        device.settings.get_boolean.return_value = swapped
        keys.keycap_labels = device.keycap_labels
        assert KeyCombination.from_names(["X"], keys).format_keycap(keys.keycap_labels) == "X"
        for name, label in zip(extra_buttons, extra_labels):
            button = KeyCombination.from_names(["Pad_" + name], keys)
            assert button.format_keycap(keys.keycap_labels) == label
            assert button.display_text == name
        chord = "+".join((extra_labels[0], *expected[2:]))
        assert keycap(tap, region).layout.get_text() == chord
        tap.capture_region = region["id"]
        tap.capture_preview = bindings["up"]
        assert keycap(tap, region).layout.get_text() == expected[0]
        tap.capture_region = tap.capture_preview = None
        assert [keycap(pad, r).layout.get_text() for r in pad.get_editable_regions()] == list(expected)
        tap.set_mapping_mode(True)
        pad.set_mapping_mode(True)
        with patch.object(control_art, "caption", wraps=control_art.caption) as caption:
            render(tap)
            assert caption.call_args.args[3] == chord
            tap.text = "Jump"
            render(tap)
            assert caption.call_args.args[3] == "Jump"
            tap.text = combo.display_text
        with patch.object(control_art, "caption", wraps=control_art.caption) as caption:
            render(pad)
            assert [call.args[3] for call in caption.call_args_list] == list(expected)
        tap.set_mapping_mode(False)
        pad.set_mapping_mode(False)
        assert service.serialize_layout([tap, pad]) == saved


def test_aim_stays_transparent_with_legacy_hint_settings(runtime):
    aim = Aim(runtime_context=runtime, text="H")
    aim.enable_hint_settings()
    aim.get_config_manager().deserialize({
        "show_hint": {"value": True}, "hint_note": {"value": "Look"},
    })
    aim.set_mapping_mode(True)
    for state in AimState:
        aim._state = state
        assert not any(render(aim)), state


def test_hold_does_not_change_the_rendered_tap_hint(runtime):
    binding = KeyCombination.from_names(["J"], runtime.key_registry)
    tap = SingleClick(x=95, y=65, runtime_context=runtime, default_keys={binding}, text="J")
    tap.set_mapping_mode(True)
    touches = []
    runtime.event_bus.subscribe(EventType.CONTROL_MSG, lambda ev: touches.append(ev.data))
    manager = runtime.key_mapping_service
    manager.subscribe(tap, binding)
    key = next(iter(binding))
    idle = render(tap)
    assert any(idle)
    assert manager.handle_key_press(InputEvent(event_type=InputEventType.KEY_PRESS, key=key))
    assert render(tap) == idle
    assert manager.handle_key_release(InputEvent(event_type=InputEventType.KEY_RELEASE, key=key))
    assert render(tap) == idle
    assert [(msg.action, msg.position[:2]) for msg in touches] == [
        (Motion.DOWN, (120, 90)), (Motion.UP, (120, 90)),
    ]


@pytest.mark.parametrize("widget_type", [AnalogStick, RightStick])
def test_stick_hint_stays_static_during_travel_and_release(runtime, widget_type):
    widget = widget_type(runtime_context=runtime)
    widget.set_mapping_mode(True)
    actions = []
    runtime.event_bus.subscribe(EventType.CONTROL_MSG, lambda ev: actions.append(ev.data.action))
    idle = render(widget)
    assert any(idle)
    try:
        for x, y in [(0.8, -0.6), (-0.4, 0.7), (0, 0)]:
            data = ("pad", widget.get_config_value("stick"), x, y)
            runtime.event_bus.emit(Event(EventType.GAMEPAD_STICK, None, data))
            assert render(widget) == idle
        assert actions[0] == Motion.DOWN and actions[-1] == Motion.UP
    finally:
        widget.on_delete()


def test_directional_hint_stays_static_while_walking_diagonally(runtime):
    pad = DirectionalPad(runtime_context=runtime)
    pad.set_mapping_mode(True)
    messages = []
    runtime.event_bus.subscribe(EventType.CONTROL_MSG, lambda ev: messages.append(ev.data))
    idle = render(pad)
    assert any(idle)
    up, right = pad.direction_keys["up"], pad.direction_keys["right"]

    async def walk():
        assert pad.on_key_triggered(up)
        assert render(pad) == idle
        await pad._movement_task
        assert render(pad) == idle
        assert pad.on_key_triggered(right)
        await pad._movement_task
        assert render(pad) == idle
        assert pad.on_key_released(up)
        await pad._movement_task
        assert render(pad) == idle
        assert pad.on_key_released(right)
        await pad._movement_task
        assert render(pad) == idle

    try:
        asyncio.run(walk())
        assert messages[0].action == Motion.DOWN and messages[-1].action == Motion.UP
        assert any(m.action == Motion.MOVE and m.position != messages[0].position for m in messages)
    finally:
        pad.on_delete()
