#!/usr/bin/env python3
"""
按键映射事件处理器
"""

from waydroid_helper.controller.core.handler.event_handlers import (
    EventHandlerPriority, InputEvent, InputEventHandler, InputEventType)

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
        return self.enabled and event.event_type in {
            InputEventType.KEY_PRESS,
            InputEventType.KEY_RELEASE,
            InputEventType.MOUSE_PRESS,
            InputEventType.MOUSE_SCROLL,
            InputEventType.MOUSE_RELEASE,
        }

    def handle_event(self, event: InputEvent) -> bool:
        """
        处理事件，将其传递给 key_mapping_manager，并返回是否被消费。
        """
        if not self.can_handle(event):
            return False

        if event.event_type == InputEventType.MOUSE_SCROLL:
            return self.key_mapping_manager.pulse_key(event)

        # 对于按键事件，我们只关心主键（Key对象），组合逻辑由manager处理
        if event.event_type in {InputEventType.KEY_PRESS, InputEventType.MOUSE_PRESS}:
            return self.key_mapping_manager.handle_key_press(event)
        elif event.event_type in {
            InputEventType.KEY_RELEASE,
            InputEventType.MOUSE_RELEASE,
        }:
            return self.key_mapping_manager.handle_key_release(event)
        # 如果事件没有被按键处理器消费，则返回False
        return False


class TextInputMappingHandler(KeyMappingEventHandler):
    """Keep physical presses on one input route across Android IME transitions."""

    def __init__(self, key_mapping_manager, dismiss_ime):
        super().__init__(key_mapping_manager)
        self.dismiss_ime = dismiss_ime
        self.ime_visible = False
        self._pressed = {}
        self._until_release = {}

    def set_ime_visible(self, visible):
        if visible:
            # The caller cancels the mapped gestures when text entry begins.
            # Swallow their repeats and eventual up; keys whose down reached
            # Android must still send their up to Android, even after a close.
            self._until_release.update(self._pressed)
            self._pressed.clear()
        self.ime_visible = visible

    def forget_presses(self):
        # GTK may deliver the physical release to a different window.
        self._pressed.clear()
        self._until_release.clear()

    def handle_event(self, event):
        if not self.can_handle(event):
            return False
        if event.event_type == InputEventType.MOUSE_SCROLL:
            return not self.ime_visible and super().handle_event(event)

        # GTK keyvals can change while Shift is held; the hardware keycode
        # identifies both halves of the press independently of the symbol.
        token = (
            ("mouse", event.button) if event.button else ("key", event.keycode or event.key)
        )
        if event.event_type in (InputEventType.KEY_RELEASE, InputEventType.MOUSE_RELEASE):
            self._pressed.pop(token, None)
            if token in self._until_release:
                return self._until_release.pop(token)
            return not self.ime_visible and super().handle_event(event)
        if token in self._until_release:
            return self._until_release[token]
        if self.ime_visible:
            # Android IMEs are dismissed with BACK. A desktop Escape keycode
            # is otherwise delivered to the editor and can leave the IME open.
            dismiss = event.key_symbol_name == "Escape"
            self._until_release[token] = dismiss
            if dismiss:
                self.dismiss_ime()
            return dismiss
        consumed = super().handle_event(event)
        self._pressed.setdefault(token, consumed)
        return consumed
