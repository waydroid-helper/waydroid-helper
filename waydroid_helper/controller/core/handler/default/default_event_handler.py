#!/usr/bin/env python3
# pyright: reportAny=false
"""
默认事件处理器
处理未被其他处理器处理的事件，提供兜底的默认行为
"""

from waydroid_helper.util.log import logger
from typing import Callable

from waydroid_helper.controller.core.handler.default.default_key_handler import (
    KeyboardDefault,
    KeyInjectMode,
)
from waydroid_helper.controller.core.handler.default.default_mouse_handler import \
    MouseDefault
from waydroid_helper.controller.core.handler.event_handlers import (
    EventHandlerPriority, InputEvent, InputEventHandler, InputEventType)
from waydroid_helper.controller.core.runtime import ControllerRuntimeContext


class DefaultEventHandler(InputEventHandler):
    """默认事件处理器 - 处理未被widget处理的事件"""

    def __init__(self, runtime_context: ControllerRuntimeContext):
        super().__init__(EventHandlerPriority.LOWEST)
        self.name = "DefaultEventHandler"

        # 可配置的默认行为
        self.key_mappings: dict[str, Callable[[InputEvent], None]] = {}
        self.mouse_mappings: dict[int, Callable[[InputEvent], None]] = {}
        default_config = runtime_context.default_handler_config
        self.keyboard_handler: KeyboardDefault = KeyboardDefault(
            runtime_context.event_bus,
            self._resolve_keyboard_inject_mode(default_config.keyboard_inject_mode),
        )
        self.mouse_handler: MouseDefault = MouseDefault(
            runtime_context.event_bus,
            runtime_context.screen_geometry,
            natural_scroll=default_config.mouse_natural_scroll,
            mouse_hover=default_config.mouse_hover,
        )
        self.handler_map: dict[InputEventType | str, Callable[[InputEvent], bool]] = {
            InputEventType.KEY_PRESS: self._handle_default_key_press,
            InputEventType.KEY_RELEASE: self._handle_default_key_release,
            InputEventType.MOUSE_PRESS: self._handle_default_mouse_press,
            InputEventType.MOUSE_RELEASE: self._handle_default_mouse_release,
            InputEventType.MOUSE_MOTION: self._handle_default_mouse_motion,
            InputEventType.MOUSE_SCROLL: self._handle_default_mouse_scroll,
            InputEventType.MOUSE_ZOOM: self._handle_default_mouse_zoom,
        }

    def _resolve_keyboard_inject_mode(self, config_value: str) -> KeyInjectMode:
        inject_mode = KeyInjectMode.from_config_value(config_value)
        if inject_mode.config_value != config_value:
            logger.error(
                "Unknown default keyboard inject mode %r; falling back to %s",
                config_value,
                inject_mode.config_value,
            )
        return inject_mode

    def can_handle(self, event: InputEvent) -> bool:
        """默认处理器可以处理所有事件"""
        return self.enabled

    def handle_event(self, event: InputEvent) -> bool:
        """处理默认事件"""
        try:
            handler = self.handler_map.get(event.event_type, lambda x: False)
            return handler(event)

        except Exception as e:
            logger.error(f"Default event handler failed to process event: {e}")

        return False

    def _handle_default_mouse_motion(self, event: InputEvent) -> bool:
        """处理默认鼠标移动"""
        if not event.position:
            return False

        self.mouse_handler.motion_processor(event)
        return True

    def _handle_default_key_press(self, event: InputEvent) -> bool:
        """处理默认按键按下"""
        if not event.key:
            return False

        key_name = event.key.name
        # 检查是否有自定义映射
        if key_name in self.key_mappings:
            try:
                self.key_mappings[key_name](event)
                return True
            except Exception as e:
                logger.error(f"Failed to execute custom key mapping: {e}")

        if event.keyval is None:
            return False

        self.keyboard_handler.key_processor(event)
        return True

    def _handle_default_key_release(self, event: InputEvent) -> bool:
        """处理默认按键释放"""
        if not event.key:
            return False

        if event.keyval is None:
            return False

        self.keyboard_handler.key_processor(event)
        return True

    def _handle_default_mouse_press(self, event: InputEvent) -> bool:
        """处理默认鼠标按下"""
        if not event.button:
            return False

        # 检查是否有自定义映射
        if event.button in self.mouse_mappings:
            try:
                self.mouse_mappings[event.button](event)
                return True
            except Exception as e:
                logger.error(f"Failed to execute custom mouse mapping: {e}")

        if not event.position:
            return False

        self.mouse_handler.click_processor(event)
        return True

    def _handle_default_mouse_release(self, event: InputEvent) -> bool:
        """处理默认鼠标释放"""
        if not event.button:
            return False

        if not event.position:
            return False

        self.mouse_handler.click_processor(event)
        return True

    def add_key_mapping(self, key_name: str, callback: Callable[[InputEvent], None]):
        """添加自定义按键映射"""
        self.key_mappings[key_name] = callback

    def add_mouse_mapping(self, button: int, callback: Callable[[InputEvent], None]):
        """添加自定义鼠标映射"""
        self.mouse_mappings[button] = callback

    def _handle_default_mouse_scroll(self, event: InputEvent) -> bool:
        """处理默认鼠标滚动"""
        if event.scroll_delta is None:
            return False
        self.mouse_handler.scroll_processor(event)
        return True

    def _handle_default_mouse_zoom(self, event: InputEvent) -> bool:
        """处理默认鼠标缩放"""
        if event.zoom is None:
            return False
        self.mouse_handler.zoom_processor(event)
        return True
