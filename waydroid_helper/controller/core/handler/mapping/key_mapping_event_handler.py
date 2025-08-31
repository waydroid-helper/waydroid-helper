#!/usr/bin/env python3
"""
按键映射事件处理器
"""

from waydroid_helper.controller.core.handler.event_handlers import (
    EventHandlerPriority, InputEvent, InputEventHandler)

from .key_mapping_manager import KeyMappingManager


class KeyMappingEventHandler(InputEventHandler):
    """
    一个专门处理按键/鼠标映射的事件处理器。
    它使用全局的 key_mapping_manager 来触发已注册的映射。
    """

    def __init__(self, key_mapping_manager: KeyMappingManager):
        # 这个处理器的优先级应该比较高，确保它在默认处理器之前执行
        super().__init__(EventHandlerPriority.NORMAL)
        self.name = "KeyMappingEventHandler"
        self.key_mapping_manager = key_mapping_manager

    def can_handle(self, event: InputEvent) -> bool:
        """此处理器只处理按键和鼠标事件"""
        return self.enabled and event.event_type in [
            "key_press",
            "key_release",
            "mouse_press",
            "mouse_release",
        ]

    def handle_event(self, event: InputEvent) -> bool:
        """
        处理事件，将其传递给 key_mapping_manager，并返回是否被消费。
        """
        if not self.can_handle(event):
            return False

        # 对于按键事件，我们只关心主键（Key对象），组合逻辑由manager处理
        if event.event_type in ["key_press", "mouse_press"]:
            return self.key_mapping_manager.handle_key_press(event)
        elif event.event_type in ["key_release", "mouse_release"]:
            return self.key_mapping_manager.handle_key_release(event)
        # 如果事件没有被按键处理器消费，则返回False
        return False
