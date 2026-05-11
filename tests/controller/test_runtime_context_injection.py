from __future__ import annotations

from waydroid_helper.controller.android import AMotionEventButtons
from waydroid_helper.controller.core.event_bus import EventBus, EventType
from waydroid_helper.controller.core.handler.default.default_event_handler import (
    DefaultEventHandler,
)
from waydroid_helper.controller.core.handler.default.default_key_handler import (
    KeyInjectMode,
)
from waydroid_helper.controller.core.handler.default.default_mouse_handler import (
    MouseDefault,
)
from waydroid_helper.controller.core.handler.event_handlers import (
    InputEvent,
    InputEventType,
)
from waydroid_helper.controller.core.key_system import KeyRegistry
from waydroid_helper.controller.core.runtime import (
    ControllerRuntimeContext,
    DefaultHandlerRuntimeConfig,
    ScreenGeometry,
)
from waydroid_helper.controller.core.utils import PointerIdManager


def test_default_mouse_handler_uses_injected_screen_geometry():
    bus = EventBus()
    screen_geometry = ScreenGeometry()
    screen_geometry.set_host_resolution(100, 50)
    screen_geometry.set_resolution(1000, 500)
    context = ControllerRuntimeContext(
        event_bus=bus,
        screen_geometry=screen_geometry,
        pointer_id_manager=PointerIdManager(),
        key_registry=KeyRegistry(),
    )
    messages = []
    bus.subscribe(EventType.CONTROL_MSG, lambda event: messages.append(event.data))

    handler = MouseDefault(context.event_bus, context.screen_geometry)
    handled = handler.click_processor(
        InputEvent(
            event_type=InputEventType.MOUSE_PRESS,
            position=(50, 25),
            action_button=AMotionEventButtons.PRIMARY,
            buttons=AMotionEventButtons.PRIMARY,
        )
    )

    assert handled is True
    assert messages[0].position == (50, 25, 100, 50)
    assert messages[0].device_resolution == (1000, 500)


def test_default_event_handler_uses_runtime_handler_config():
    context = ControllerRuntimeContext(
        event_bus=EventBus(),
        screen_geometry=ScreenGeometry(),
        pointer_id_manager=PointerIdManager(),
        key_registry=KeyRegistry(),
        default_handler_config=DefaultHandlerRuntimeConfig(
            keyboard_inject_mode="raw",
            mouse_natural_scroll=False,
            mouse_hover=True,
        ),
    )

    handler = DefaultEventHandler(context)

    assert handler.keyboard_handler.inject_mode is KeyInjectMode.RAW
    assert handler.mouse_handler.natural_scroll is False
    assert handler.mouse_handler.mouse_hover is True
