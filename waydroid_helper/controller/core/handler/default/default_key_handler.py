#!/usr/bin/env python3
"""
默认按键处理器
"""

from abc import ABC, abstractmethod
from enum import Enum

from waydroid_helper.controller.android import (AKeyCode, AKeyEventAction,
                                                AMetaState)
from waydroid_helper.controller.core.control_msg import (InjectKeycodeMsg,
                                                         InjectTextMsg)
from waydroid_helper.controller.core.event_bus import (Event, EventType,
                                                       EventBus)
from waydroid_helper.controller.core.handler.event_handlers import (
    InputEvent,
    InputEventType,
    InputModifierState,
)


class KeyInjectMode(Enum):
    # 特殊按键, 空格, 字母作为 key event;数字和标点作为 text
    MIXED = 0
    # 特殊按键作为 key event;  空格, 字母, 数字和标点作为 text
    TEXT = 1
    # 所有的都作为 key event
    RAW = 2


class KeyboardBase(ABC):
    @abstractmethod
    def key_processor(self, event: InputEvent) -> bool:
        pass


class KeyboardDefault(KeyboardBase):
    # 所有模式都用
    special_keys: dict[str, AKeyCode] = {
        "Return": AKeyCode.AKEYCODE_ENTER,
        "KP_Enter": AKeyCode.AKEYCODE_NUMPAD_ENTER,
        "Escape": AKeyCode.AKEYCODE_ESCAPE,
        "BackSpace": AKeyCode.AKEYCODE_DEL,
        "Delete": AKeyCode.AKEYCODE_FORWARD_DEL,
        "Tab": AKeyCode.AKEYCODE_TAB,
        "ISO_Left_Tab": AKeyCode.AKEYCODE_TAB,
        "Page_Up": AKeyCode.AKEYCODE_PAGE_UP,
        "Home": AKeyCode.AKEYCODE_MOVE_HOME,
        "End": AKeyCode.AKEYCODE_MOVE_END,
        "Page_Down": AKeyCode.AKEYCODE_PAGE_DOWN,
        "Up": AKeyCode.AKEYCODE_DPAD_UP,
        "Down": AKeyCode.AKEYCODE_DPAD_DOWN,
        "Left": AKeyCode.AKEYCODE_DPAD_LEFT,
        "Right": AKeyCode.AKEYCODE_DPAD_RIGHT,
        "Control_L": AKeyCode.AKEYCODE_CTRL_LEFT,
        "Control_R": AKeyCode.AKEYCODE_CTRL_RIGHT,
        "Shift_L": AKeyCode.AKEYCODE_SHIFT_LEFT,
        "Shift_R": AKeyCode.AKEYCODE_SHIFT_RIGHT,
    }
    # 非 text 模式用
    alphaspace_keys: dict[str, AKeyCode] = {
        "A": AKeyCode.AKEYCODE_A,
        "B": AKeyCode.AKEYCODE_B,
        "C": AKeyCode.AKEYCODE_C,
        "D": AKeyCode.AKEYCODE_D,
        "E": AKeyCode.AKEYCODE_E,
        "F": AKeyCode.AKEYCODE_F,
        "G": AKeyCode.AKEYCODE_G,
        "H": AKeyCode.AKEYCODE_H,
        "I": AKeyCode.AKEYCODE_I,
        "J": AKeyCode.AKEYCODE_J,
        "K": AKeyCode.AKEYCODE_K,
        "L": AKeyCode.AKEYCODE_L,
        "M": AKeyCode.AKEYCODE_M,
        "N": AKeyCode.AKEYCODE_N,
        "O": AKeyCode.AKEYCODE_O,
        "P": AKeyCode.AKEYCODE_P,
        "Q": AKeyCode.AKEYCODE_Q,
        "R": AKeyCode.AKEYCODE_R,
        "S": AKeyCode.AKEYCODE_S,
        "T": AKeyCode.AKEYCODE_T,
        "U": AKeyCode.AKEYCODE_U,
        "V": AKeyCode.AKEYCODE_V,
        "W": AKeyCode.AKEYCODE_W,
        "X": AKeyCode.AKEYCODE_X,
        "Y": AKeyCode.AKEYCODE_Y,
        "Z": AKeyCode.AKEYCODE_Z,
        "space": AKeyCode.AKEYCODE_SPACE,
    }
    # raw 模式用
    numbers_punct_keys: dict[str, AKeyCode] = {
        "numbersign": AKeyCode.AKEYCODE_POUND,
        "percent": AKeyCode.AKEYCODE_PERIOD,
        "apostrophe": AKeyCode.AKEYCODE_APOSTROPHE,
        "asterisk": AKeyCode.AKEYCODE_STAR,
        "plus": AKeyCode.AKEYCODE_PLUS,
        "comma": AKeyCode.AKEYCODE_COMMA,
        "minus": AKeyCode.AKEYCODE_MINUS,
        "period": AKeyCode.AKEYCODE_PERIOD,
        "slash": AKeyCode.AKEYCODE_SLASH,
        "0": AKeyCode.AKEYCODE_0,
        "1": AKeyCode.AKEYCODE_1,
        "2": AKeyCode.AKEYCODE_2,
        "3": AKeyCode.AKEYCODE_3,
        "4": AKeyCode.AKEYCODE_4,
        "5": AKeyCode.AKEYCODE_5,
        "6": AKeyCode.AKEYCODE_6,
        "7": AKeyCode.AKEYCODE_7,
        "8": AKeyCode.AKEYCODE_8,
        "9": AKeyCode.AKEYCODE_9,
        "semicolon": AKeyCode.AKEYCODE_SEMICOLON,
        "equal": AKeyCode.AKEYCODE_EQUALS,
        "at": AKeyCode.AKEYCODE_AT,
        "bracketleft": AKeyCode.AKEYCODE_LEFT_BRACKET,
        "backslash": AKeyCode.AKEYCODE_BACKSLASH,
        "bracketright": AKeyCode.AKEYCODE_RIGHT_BRACKET,
        "grave": AKeyCode.AKEYCODE_GRAVE,
        "KP_0": AKeyCode.AKEYCODE_NUMPAD_0,
        "KP_1": AKeyCode.AKEYCODE_NUMPAD_1,
        "KP_2": AKeyCode.AKEYCODE_NUMPAD_2,
        "KP_3": AKeyCode.AKEYCODE_NUMPAD_3,
        "KP_4": AKeyCode.AKEYCODE_NUMPAD_4,
        "KP_5": AKeyCode.AKEYCODE_NUMPAD_5,
        "KP_6": AKeyCode.AKEYCODE_NUMPAD_6,
        "KP_7": AKeyCode.AKEYCODE_NUMPAD_7,
        "KP_8": AKeyCode.AKEYCODE_NUMPAD_8,
        "KP_9": AKeyCode.AKEYCODE_NUMPAD_9,
        "KP_Divide": AKeyCode.AKEYCODE_NUMPAD_DIVIDE,
        "KP_Multiply": AKeyCode.AKEYCODE_NUMPAD_MULTIPLY,
        "KP_Subtract": AKeyCode.AKEYCODE_NUMPAD_SUBTRACT,
        "KP_Decimal": AKeyCode.AKEYCODE_NUMPAD_DOT,
        "KP_Equal": AKeyCode.AKEYCODE_NUMPAD_EQUALS,
        "KP_Left": AKeyCode.AKEYCODE_NUMPAD_LEFT_PAREN,
        "KP_Right": AKeyCode.AKEYCODE_NUMPAD_RIGHT_PAREN,
    }

    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus
        self.last_key: int | None = None
        self.key_repeat: int = 0
        # TODO 从配置中读取
        self.inject_mode: KeyInjectMode = KeyInjectMode.MIXED

    def convert_action(self, event: InputEvent) -> AKeyEventAction:
        if event.event_type == InputEventType.KEY_PRESS:
            return AKeyEventAction.DOWN
        else:
            return AKeyEventAction.UP

    def convert_text(self, event: InputEvent) -> str | None:
        key_name = event.key_symbol_name
        if key_name in self.special_keys:
            # special keys
            return None
        if self.inject_mode == KeyInjectMode.RAW:
            return None

        text = event.text
        if text is None:
            return None
        if self.inject_mode == KeyInjectMode.MIXED:
            if text.isalpha() or text == " ":
                return None
        return text

    def convert_keycode(self, event: InputEvent) -> AKeyCode | None:
        key_name = event.key_symbol_name
        if key_name is None:
            return None

        # 特殊按键, 所有 inject_mode 都需要
        key = self.special_keys.get(key_name, None)
        if key is not None:
            return key
        # inject_mod == TEXT 并且 Ctrl 没有按下, 作为 text 处理
        if self.inject_mode == KeyInjectMode.TEXT and not (
            event.modifier_state & InputModifierState.CTRL
        ):
            return None

        # Alt 按下, 不作处理
        if event.modifier_state & (InputModifierState.ALT | InputModifierState.META):
            return None

        # Alt 和 Meta 没有按下, 将字母和空格按键仍作为 key event 处理
        alpha_name = self._normalize_alpha_space_name(key_name)
        key = self.alphaspace_keys.get(alpha_name, None)
        if key is not None:
            return key

        # inject_mod == RAW, 数字和标点按键作为 key event 处理
        if self.inject_mode == KeyInjectMode.RAW:
            key = self.numbers_punct_keys.get(key_name, None)
            if key is not None:
                return key

            # Source adapters provide the layout-level key symbol so default
            # injection does not need to reach back into a display object.
            key = self.numbers_punct_keys.get(event.physical_key_symbol_name, None)
            return key

    def _normalize_alpha_space_name(self, key_name: str) -> str:
        if len(key_name) == 1 and key_name.isalpha():
            return key_name.upper()
        return key_name

    def convert_mod(self, state: InputModifierState) -> AMetaState | int:
        meta = 0
        if state & InputModifierState.SHIFT:
            meta |= AMetaState.SHIFT_ON
        if state & InputModifierState.ALT:
            meta |= AMetaState.ALT_ON
        if state & InputModifierState.META:
            meta |= AMetaState.META_ON
        if state & InputModifierState.CTRL:
            meta |= AMetaState.CTRL_ON
        return meta

    def key_processor(self, event: InputEvent) -> bool:
        # print(low_level_keyval, chr(low_level_keyval),"+shift=", keyval, chr(keyval))
        result = self.__key_processor(event)
        if not result:
            result = self.__text_processor(event)
        return result

    def get_reapeat(self, keyval: int | None, action: AKeyEventAction) -> int:
        if keyval is None:
            return 0
        if action == AKeyEventAction.DOWN:
            if self.last_key == keyval:
                self.key_repeat += 1
            else:
                self.last_key = keyval
                self.key_repeat = 0
        else:
            self.last_key = None
            self.key_repeat = 0
        return self.key_repeat

    def __key_processor(self, event: InputEvent) -> bool:
        action = self.convert_action(event)
        key_code = self.convert_keycode(event)
        if key_code is None:
            return False
        metastate = self.convert_mod(event.modifier_state)

        msg = InjectKeycodeMsg(
            action,
            key_code,
            self.get_reapeat(event.keyval, action),
            metastate,
        )
        self.event_bus.emit(Event[InjectKeycodeMsg](EventType.CONTROL_MSG, self, msg))
        return True

    def __text_processor(self, event: InputEvent) -> bool:
        if (not event.is_modifier) and event.event_type == InputEventType.KEY_PRESS:
            text = self.convert_text(event)
            if text is None:
                return False
            msg = InjectTextMsg(text)
            self.event_bus.emit(Event(EventType.CONTROL_MSG, self, msg))
            return True
        return False
