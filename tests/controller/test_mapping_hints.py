import cairo
import gi
import pytest

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gtk

from waydroid_helper.controller.core import (
    ControllerRuntimeContext, EventBus, KeyCombination, KeyRegistry, PointerIdManager,
)
from waydroid_helper.controller.core.handler.event_handlers import InputEvent, InputEventType
from waydroid_helper.controller.core.handler.mapping.key_mapping_manager import KeyMappingManager
from waydroid_helper.controller.core.runtime import ScreenGeometry
from waydroid_helper.controller.widgets.components.aim import Aim, AimState
from waydroid_helper.controller.widgets.components.single_click import SingleClick


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
    tap = SingleClick(runtime_context=runtime, default_keys={binding}, text="J")
    tap.set_mapping_mode(True)
    manager = runtime.key_mapping_service
    manager.subscribe(tap, binding)
    key = next(iter(binding))
    idle = render(tap)
    assert any(idle)
    assert manager.handle_key_press(InputEvent(event_type=InputEventType.KEY_PRESS, key=key))
    assert render(tap) == idle
    assert manager.handle_key_release(InputEvent(event_type=InputEventType.KEY_RELEASE, key=key))
    assert render(tap) == idle
