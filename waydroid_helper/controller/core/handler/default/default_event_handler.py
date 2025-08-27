#!/usr/bin/env python3
# pyright: reportAny=false
"""
默认事件处理器
处理未被其他处理器处理的事件，提供兜底的默认行为
"""

from waydroid_helper.controller.core.event_bus import EventBus
from waydroid_helper.util.log import logger
from typing import Callable

from waydroid_helper.controller.core.handler.default.default_key_handler import \
    KeyboardDefault
from waydroid_helper.controller.core.handler.default.default_mouse_handler import \
    MouseDefault
from waydroid_helper.controller.core.handler.event_handlers import (
    EventHandlerPriority, InputEvent, InputEventHandler)


class DefaultEventHandler(InputEventHandler):
    """默认事件处理器 - 处理未被widget处理的事件"""

    def __init__(self, event_bus: EventBus):
        super().__init__(EventHandlerPriority.LOWEST)
        self.name = "DefaultEventHandler"

        # 可配置的默认行为
        self.key_mappings: dict[str, Callable[[InputEvent], None]] = {}
        self.mouse_mappings: dict[int, Callable[[InputEvent], None]] = {}
        self.keyboard_handler: KeyboardDefault = KeyboardDefault(event_bus)
        self.mouse_handler: MouseDefault = MouseDefault(event_bus)

    def can_handle(self, event: InputEvent) -> bool:
        """默认处理器可以处理所有事件"""
        return self.enabled

    def handle_event(self, event: InputEvent) -> bool:
        """处理默认事件"""
        try:
            if event.event_type == "key_press":
                return self._handle_default_key_press(event)
            elif event.event_type == "key_release":
                return self._handle_default_key_release(event)
            elif event.event_type == "mouse_press":
                return self._handle_default_mouse_press(event)
            elif event.event_type == "mouse_release":
                return self._handle_default_mouse_release(event)
            elif event.event_type == "mouse_motion":
                return self._handle_default_mouse_motion(event)
            elif event.event_type == "mouse_scroll":
                return self._handle_default_mouse_scroll(event)
            elif event.event_type == "mouse_zoom":
                return self._handle_default_mouse_zoom(event)

        except Exception as e:
            logger.error(f"Default event handler failed to process event: {e}")

        return False

    def _handle_default_mouse_motion(self, event: InputEvent) -> bool:
        """处理默认鼠标移动"""
        if not event.position or not event.raw_data:
            return False

        self.mouse_handler.motion_processor(
            event.raw_data["controller"], event.raw_data["x"], event.raw_data["y"]
        )
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

        if not event.raw_data:
            return False

        self.keyboard_handler.key_processor(
            event.raw_data["controller"],
            event.raw_data["keyval"],
            event.raw_data["keycode"],
            event.raw_data["state"],
        )
        return True

    def _handle_default_key_release(self, event: InputEvent) -> bool:
        """处理默认按键释放"""
        if not event.key:
            return False

        if not event.raw_data:
            return False

        self.keyboard_handler.key_processor(
            event.raw_data["controller"],
            event.raw_data["keyval"],
            event.raw_data["keycode"],
            event.raw_data["state"],
        )
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

        if not event.raw_data:
            return False

        self.mouse_handler.click_processor(
            event.raw_data["controller"],
            event.raw_data["n_press"],
            event.raw_data["x"],
            event.raw_data["y"],
        )
        return True

    def _handle_default_mouse_release(self, event: InputEvent) -> bool:
        """处理默认鼠标释放"""
        if not event.button:
            return False

        if not event.raw_data:
            return False

        self.mouse_handler.click_processor(
            event.raw_data["controller"],
            event.raw_data["n_press"],
            event.raw_data["x"],
            event.raw_data["y"],
        )
        return True

    def add_key_mapping(self, key_name: str, callback: Callable[[InputEvent], None]):
        """添加自定义按键映射"""
        self.key_mappings[key_name] = callback

    def add_mouse_mapping(self, button: int, callback: Callable[[InputEvent], None]):
        """添加自定义鼠标映射"""
        self.mouse_mappings[button] = callback

    def _handle_default_mouse_scroll(self, event: InputEvent) -> bool:
        """处理默认鼠标滚动"""
        if not event.raw_data:
            return False
        self.mouse_handler.scroll_processor(
            event.raw_data["controller"], event.raw_data["dx"], event.raw_data["dy"]
        )
        return True

    def _handle_default_mouse_zoom(self, event: InputEvent) -> bool:
        """处理默认鼠标缩放"""
        if not event.raw_data:
            return False
        self.mouse_handler.zoom_processor(
            event.raw_data["controller"], event.raw_data["range"]
        )
        return True
