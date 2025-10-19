#!/usr/bin/env python3
"""
事件处理器系统
提供可扩展的事件处理链
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import IntEnum
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


# TODO: refactor this shit
@dataclass
class InputEvent:
    """输入事件数据结构"""

    event_type: str  # "key_press", "key_release", "mouse_press", "mouse_release"
    key: Key | None = None
    button: int | None = None  # 鼠标按钮
    position: tuple[int, int] | None = None  # (x, y)
    modifiers: list[Key] | None = None  # 修饰键列表
    raw_data: dict[str, Any] | None = None  # 原始事件数据


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
