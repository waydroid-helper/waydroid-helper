#!/usr/bin/env python3
"""
事件处理器系统
提供可扩展的事件处理链
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import Enum, IntEnum, IntFlag
from typing import Any

from waydroid_helper.controller.core.key_system import Key
from waydroid_helper.util.log import logger


class EventHandlerPriority(IntEnum):
    """事件处理器优先级"""

    HIGHEST = 0  # 最高优先级
    HIGH = 10  # 高优先级
    NORMAL = 50  # 普通优先级
    LOW = 90  # 低优先级
    LOWEST = 100  # 最低优先级（默认处理器）


class InputEventType(str, Enum):
    """Source-neutral input event types."""

    KEY_PRESS = "key_press"
    KEY_RELEASE = "key_release"
    MOUSE_PRESS = "mouse_press"
    MOUSE_RELEASE = "mouse_release"
    MOUSE_MOTION = "mouse_motion"
    MOUSE_SCROLL = "mouse_scroll"
    MOUSE_ZOOM = "mouse_zoom"


class InputEventSource(str, Enum):
    """Normalized input source names.

    Source adapters own toolkit-specific objects. Handlers should use these
    names only for diagnostics or source-specific policy, never to reach back
    into a native event object.
    """

    UNKNOWN = "unknown"
    GTK = "gtk"
    MACRO = "macro"


class InputModifierState(IntFlag):
    """Source-neutral modifier and pointer-button state."""

    NONE = 0
    SHIFT = 1 << 0
    ALT = 1 << 1
    META = 1 << 2
    CTRL = 1 << 3

    BUTTON_PRIMARY = 1 << 8
    BUTTON_MIDDLE = 1 << 9
    BUTTON_SECONDARY = 1 << 10
    BUTTON_BACK = 1 << 11
    BUTTON_FORWARD = 1 << 12


@dataclass
class InputEvent:
    """Normalized input event consumed by mapping and default handlers.

    Window/platform code adapts raw toolkit events into this shape. The handler
    chain must not depend on GTK controllers, Gdk.Event instances, or other
    source-owned objects, so adding a new input source only requires another
    adapter that fills the same fields.
    """

    event_type: InputEventType | str
    key: Key | None = None
    button: int | None = None  # 鼠标按钮
    position: tuple[int, int] | None = None  # (x, y)
    modifiers: list[Key] | None = None  # 修饰键列表
    source: InputEventSource | str = InputEventSource.UNKNOWN

    # Keyboard payload. keyval is the translated symbol, while
    # physical_keyval is the layout-level symbol for the physical key.
    keyval: int | None = None
    physical_keyval: int | None = None
    key_symbol_name: str | None = None
    physical_key_symbol_name: str | None = None
    keycode: int | None = None
    modifier_state: InputModifierState = InputModifierState.NONE
    text: str | None = None
    is_modifier: bool = False

    # Pointer payload. button is the raw source button number. action_button and
    # buttons are normalized to Android AMotionEventButtons-compatible masks.
    n_press: int = 1
    action_button: int = 0
    buttons: int = 0

    # Gesture payload.
    scroll_delta: tuple[float, float] | None = None
    scroll_is_surface: bool = False
    zoom: float | None = None
    zoom_status: str | None = None
    zoom_is_touchpad: bool = False


class InputEventHandler(ABC):
    """事件处理器基类"""

    def __init__(self, priority: EventHandlerPriority = EventHandlerPriority.NORMAL):
        self.priority = priority
        self.enabled = True

    @abstractmethod
    def can_handle(self, event: InputEvent) -> bool:
        """判断是否可以处理此事件"""

    @abstractmethod
    def handle_event(self, event: InputEvent) -> bool:
        """处理事件，返回True表示事件已被消费，不再传递给后续处理器"""

    def get_priority(self) -> int:
        """获取处理器优先级"""
        return self.priority.value

    def set_enabled(self, enabled: bool):
        """设置处理器是否启用"""
        self.enabled = enabled


class InputEventHandlerChain:
    """输入事件处理器链 - 管理多个输入事件处理器"""

    def __init__(self):
        self.handlers: list[InputEventHandler] = []
        self.enabled = True

    def add_handler(self, handler: InputEventHandler):
        """添加事件处理器"""
        self.handlers.append(handler)
        # 按优先级排序（数值越小优先级越高）
        self.handlers.sort(key=lambda h: h.get_priority())
        logger.info(
            f"Add event handler: {handler.__class__.__name__} (priority: {handler.get_priority()})"
        )

    def remove_handler(self, handler: InputEventHandler):
        """移除事件处理器"""
        if handler in self.handlers:
            self.handlers.remove(handler)
            logger.info(f"Remove event handler: {handler.__class__.__name__}")

    def process_event(self, event: InputEvent) -> bool:
        """处理事件，返回True表示事件已被处理"""
        if not self.enabled:
            return False

        for handler in self.handlers:
            if not handler.enabled:
                continue

            if handler.can_handle(event):
                try:
                    if handler.handle_event(event):
                        return True  # 事件已被消费，停止传递
                except Exception as e:
                    logger.error(
                        f"Handler {handler.__class__.__name__} failed to process event: {e}"
                    )
                    continue

        logger.debug("Event not consumed by any handler")
        return False

    def set_enabled(self, enabled: bool):
        """设置处理器链是否启用"""
        self.enabled = enabled

    def get_handlers_info(self) -> list[dict[str, Any]]:
        """获取所有处理器的信息"""
        return [
            {
                "name": handler.__class__.__name__,
                "priority": handler.get_priority(),
                "enabled": handler.enabled,
            }
            for handler in self.handlers
        ]
