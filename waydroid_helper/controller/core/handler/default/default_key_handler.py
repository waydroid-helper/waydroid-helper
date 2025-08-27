#!/usr/bin/env python3
"""
默认按键处理器
"""

from abc import ABC, abstractmethod
from enum import Enum
from typing import cast

import gi

from waydroid_helper.controller.android import (AKeyCode, AKeyEventAction,
                                                AMetaState)
from waydroid_helper.controller.core.control_msg import (InjectKeycodeMsg,
                                                         InjectTextMsg)
from waydroid_helper.controller.core.event_bus import (Event, EventType,
                                                       EventBus)

gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, Gtk


class KeyInjectMode(Enum):
    # 特殊按键, 空格, 字母作为 key event;数字和标点作为 text
    MIXED = 0
    # 特殊按键作为 key event;  空格, 字母, 数字和标点作为 text
    TEXT = 1
    # 所有的都作为 key event
    RAW = 2


class KeyboardBase(ABC):
    @abstractmethod
    def key_processor(
        self, controller: Gtk.EventControllerKey, keyval: int, keycode: int, state: int
    ) -> bool:
        pass


class KeyboardDefault(KeyboardBase):
    # 所有模式都用
    special_keys: dict[int, AKeyCode] = {
        Gdk.KEY_Return: AKeyCode.AKEYCODE_ENTER,
        Gdk.KEY_KP_Enter: AKeyCode.AKEYCODE_NUMPAD_ENTER,
        Gdk.KEY_Escape: AKeyCode.AKEYCODE_ESCAPE,
        Gdk.KEY_BackSpace: AKeyCode.AKEYCODE_DEL,
        Gdk.KEY_Delete: AKeyCode.AKEYCODE_FORWARD_DEL,
        Gdk.KEY_Tab: AKeyCode.AKEYCODE_TAB,
        Gdk.KEY_ISO_Left_Tab: AKeyCode.AKEYCODE_TAB,
        Gdk.KEY_Page_Up: AKeyCode.AKEYCODE_PAGE_UP,
        Gdk.KEY_Delete: AKeyCode.AKEYCODE_FORWARD_DEL,
        Gdk.KEY_Home: AKeyCode.AKEYCODE_MOVE_HOME,
        Gdk.KEY_End: AKeyCode.AKEYCODE_MOVE_END,
        Gdk.KEY_Page_Down: AKeyCode.AKEYCODE_PAGE_DOWN,
        Gdk.KEY_Up: AKeyCode.AKEYCODE_DPAD_UP,
        Gdk.KEY_Down: AKeyCode.AKEYCODE_DPAD_DOWN,
        Gdk.KEY_Left: AKeyCode.AKEYCODE_DPAD_LEFT,
        Gdk.KEY_Right: AKeyCode.AKEYCODE_DPAD_RIGHT,
        Gdk.KEY_Control_L: AKeyCode.AKEYCODE_CTRL_LEFT,
        Gdk.KEY_Control_R: AKeyCode.AKEYCODE_CTRL_RIGHT,
        Gdk.KEY_Shift_L: AKeyCode.AKEYCODE_SHIFT_LEFT,
        Gdk.KEY_Shift_R: AKeyCode.AKEYCODE_SHIFT_RIGHT,
    }
    # 非 text 模式用
    alphaspace_keys: dict[int, AKeyCode] = {
        Gdk.KEY_a: AKeyCode.AKEYCODE_A,
        Gdk.KEY_b: AKeyCode.AKEYCODE_B,
        Gdk.KEY_c: AKeyCode.AKEYCODE_C,
        Gdk.KEY_d: AKeyCode.AKEYCODE_D,
        Gdk.KEY_e: AKeyCode.AKEYCODE_E,
        Gdk.KEY_f: AKeyCode.AKEYCODE_F,
        Gdk.KEY_g: AKeyCode.AKEYCODE_G,
        Gdk.KEY_h: AKeyCode.AKEYCODE_H,
        Gdk.KEY_i: AKeyCode.AKEYCODE_I,
        Gdk.KEY_j: AKeyCode.AKEYCODE_J,
        Gdk.KEY_k: AKeyCode.AKEYCODE_K,
        Gdk.KEY_l: AKeyCode.AKEYCODE_L,
        Gdk.KEY_m: AKeyCode.AKEYCODE_M,
        Gdk.KEY_n: AKeyCode.AKEYCODE_N,
        Gdk.KEY_o: AKeyCode.AKEYCODE_O,
        Gdk.KEY_p: AKeyCode.AKEYCODE_P,
        Gdk.KEY_q: AKeyCode.AKEYCODE_Q,
        Gdk.KEY_h: AKeyCode.AKEYCODE_H,
        Gdk.KEY_i: AKeyCode.AKEYCODE_I,
        Gdk.KEY_j: AKeyCode.AKEYCODE_J,
        Gdk.KEY_k: AKeyCode.AKEYCODE_K,
        Gdk.KEY_l: AKeyCode.AKEYCODE_L,
        Gdk.KEY_m: AKeyCode.AKEYCODE_M,
        Gdk.KEY_n: AKeyCode.AKEYCODE_N,
        Gdk.KEY_o: AKeyCode.AKEYCODE_O,
        Gdk.KEY_p: AKeyCode.AKEYCODE_P,
        Gdk.KEY_q: AKeyCode.AKEYCODE_Q,
        Gdk.KEY_r: AKeyCode.AKEYCODE_R,
        Gdk.KEY_s: AKeyCode.AKEYCODE_S,
        Gdk.KEY_t: AKeyCode.AKEYCODE_T,
        Gdk.KEY_u: AKeyCode.AKEYCODE_U,
        Gdk.KEY_v: AKeyCode.AKEYCODE_V,
        Gdk.KEY_w: AKeyCode.AKEYCODE_W,
        Gdk.KEY_x: AKeyCode.AKEYCODE_X,
        Gdk.KEY_y: AKeyCode.AKEYCODE_Y,
        Gdk.KEY_z: AKeyCode.AKEYCODE_Z,
        Gdk.KEY_space: AKeyCode.AKEYCODE_SPACE,
    }
    # raw 模式用
    numbers_punct_keys: dict[int, AKeyCode] = {
        Gdk.KEY_numbersign: AKeyCode.AKEYCODE_POUND,
        Gdk.KEY_percent: AKeyCode.AKEYCODE_PERIOD,
        Gdk.KEY_apostrophe: AKeyCode.AKEYCODE_APOSTROPHE,
        Gdk.KEY_asterisk: AKeyCode.AKEYCODE_STAR,
        Gdk.KEY_plus: AKeyCode.AKEYCODE_PLUS,
        Gdk.KEY_comma: AKeyCode.AKEYCODE_COMMA,
        Gdk.KEY_minus: AKeyCode.AKEYCODE_MINUS,
        Gdk.KEY_period: AKeyCode.AKEYCODE_PERIOD,
        Gdk.KEY_slash: AKeyCode.AKEYCODE_SLASH,
        Gdk.KEY_0: AKeyCode.AKEYCODE_0,
        Gdk.KEY_1: AKeyCode.AKEYCODE_1,
        Gdk.KEY_2: AKeyCode.AKEYCODE_2,
        Gdk.KEY_3: AKeyCode.AKEYCODE_3,
        Gdk.KEY_4: AKeyCode.AKEYCODE_4,
        Gdk.KEY_5: AKeyCode.AKEYCODE_5,
        Gdk.KEY_6: AKeyCode.AKEYCODE_6,
        Gdk.KEY_7: AKeyCode.AKEYCODE_7,
        Gdk.KEY_8: AKeyCode.AKEYCODE_8,
        Gdk.KEY_9: AKeyCode.AKEYCODE_9,
        Gdk.KEY_semicolon: AKeyCode.AKEYCODE_SEMICOLON,
        Gdk.KEY_equal: AKeyCode.AKEYCODE_EQUALS,
        Gdk.KEY_at: AKeyCode.AKEYCODE_AT,
        Gdk.KEY_bracketleft: AKeyCode.AKEYCODE_LEFT_BRACKET,
        Gdk.KEY_backslash: AKeyCode.AKEYCODE_BACKSLASH,
        Gdk.KEY_bracketright: AKeyCode.AKEYCODE_RIGHT_BRACKET,
        Gdk.KEY_grave: AKeyCode.AKEYCODE_GRAVE,
        Gdk.KEY_KP_0: AKeyCode.AKEYCODE_NUMPAD_0,
        Gdk.KEY_KP_1: AKeyCode.AKEYCODE_NUMPAD_1,
        Gdk.KEY_KP_2: AKeyCode.AKEYCODE_NUMPAD_2,
        Gdk.KEY_KP_3: AKeyCode.AKEYCODE_NUMPAD_3,
        Gdk.KEY_KP_4: AKeyCode.AKEYCODE_NUMPAD_4,
        Gdk.KEY_KP_5: AKeyCode.AKEYCODE_NUMPAD_5,
        Gdk.KEY_KP_6: AKeyCode.AKEYCODE_NUMPAD_6,
        Gdk.KEY_KP_7: AKeyCode.AKEYCODE_NUMPAD_7,
        Gdk.KEY_KP_8: AKeyCode.AKEYCODE_NUMPAD_8,
        Gdk.KEY_KP_9: AKeyCode.AKEYCODE_NUMPAD_9,
        Gdk.KEY_KP_Divide: AKeyCode.AKEYCODE_NUMPAD_DIVIDE,
        Gdk.KEY_KP_Multiply: AKeyCode.AKEYCODE_NUMPAD_MULTIPLY,
        Gdk.KEY_KP_Subtract: AKeyCode.AKEYCODE_NUMPAD_SUBTRACT,
        Gdk.KEY_KP_Decimal: AKeyCode.AKEYCODE_NUMPAD_DOT,
        Gdk.KEY_KP_Equal: AKeyCode.AKEYCODE_NUMPAD_EQUALS,
        Gdk.KEY_KP_Left: AKeyCode.AKEYCODE_NUMPAD_LEFT_PAREN,
        Gdk.KEY_KP_Right: AKeyCode.AKEYCODE_NUMPAD_RIGHT_PAREN,
    }

    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus
        self.last_key: int | None = None
        self.key_repeat: int = 0
        # TODO 从配置中读取
        self.inject_mode: KeyInjectMode = KeyInjectMode.MIXED

    def convert_action(self, event: Gdk.Event) -> AKeyEventAction:
        if event.get_event_type() == Gdk.EventType.KEY_PRESS:
            return AKeyEventAction.DOWN
        else:
            return AKeyEventAction.UP

    def convert_text(self, keyval: int) -> str | None:
        if keyval in self.special_keys.keys():
            # special keys
            return None
        if self.inject_mode == KeyInjectMode.RAW:
            return None

        keyval = Gdk.keyval_to_unicode(keyval)
        if self.inject_mode == KeyInjectMode.MIXED:
            if chr(keyval).isalpha() or chr(keyval) == " ":
                return None
        return chr(keyval)

    def convert_keycode(
        self, controller: Gtk.EventControllerKey, keyval: int, keycode: int, state: int
    ) -> AKeyCode | None:
        # 特殊按键, 所有 inject_mode 都需要
        key = self.special_keys.get(keyval, None)
        if key is not None:
            return key
        # inject_mod == TEXT 并且 Ctrl 没有按下, 作为 text 处理
        if self.inject_mode == KeyInjectMode.TEXT and not (
            state & (Gdk.ModifierType.CONTROL_MASK)
        ):
            return None

        # Alt 按下, 不作处理
        if state & (Gdk.ModifierType.ALT_MASK | Gdk.ModifierType.META_MASK):
            return None

        # Alt 和 Meta 没有按下, 将字母和空格按键仍作为 key event 处理
        key = self.alphaspace_keys.get(Gdk.keyval_to_lower(keyval), None)
        if key is not None:
            return key

        # inject_mod == RAW, 数字和标点按键作为 key event 处理
        if self.inject_mode == KeyInjectMode.RAW:
            key = self.numbers_punct_keys.get(keyval, None)
            if key is not None:
                return key

            widget = controller.get_widget()
            if widget is None:
                return None
            display = widget.get_display()

            # 因为 gtk 获得的 keyval 已经加上修饰键翻译后的, 需要获取同一个 keycode 上较低 level 的 keyval
            keyval = self.get_low_level_keyval(display, keycode)
            key = self.numbers_punct_keys.get(keyval, None)
            # print(y_keyval, chr(y_keyval),"+shift=", keyval, chr(keyval))
            return key

    def convert_mod(self, state: int) -> AMetaState | int:
        meta = 0
        if state & Gdk.ModifierType.SHIFT_MASK:
            meta |= AMetaState.SHIFT_ON
        if state & Gdk.ModifierType.ALT_MASK:
            meta |= AMetaState.ALT_ON
        if state & Gdk.ModifierType.META_MASK:
            meta |= AMetaState.META_ON
        if state & Gdk.ModifierType.CONTROL_MASK:
            meta |= AMetaState.CTRL_ON
        return meta

    def get_low_level_keyval(self, display: Gdk.Display, keycode: int) -> int:
        if display.map_keycode(keycode)[0]:
            low_level_keyval = display.translate_key(
                keycode=keycode, state=0, group=0
            ).keyval
            return low_level_keyval

        return 0
        # if display.map_keyval(keyval)[0]:
        #     keycode = display.map_keyval(keyval)[1][0].keycode
        #     low_level_keyval = display.translate_key(
        #         keycode=keycode, state=0, group=0
        #     ).keyval
        # else:
        #     low_level_keyval = keyval
        # return low_level_keyval

    # keyval: the pressed key
    # keycode: the raw code of the pressed key
    # state: the bitmask, representing the state of modifier keys and pointer buttons
    def key_processor(
        self, controller: Gtk.EventControllerKey, keyval: int, keycode: int, state: int
    ) -> bool:
        # print(low_level_keyval, chr(low_level_keyval),"+shift=", keyval, chr(keyval))
        result = self.__key_processor(controller, keyval, keycode, state)
        if not result:
            result = self.__text_processor(controller, keyval, keycode, state)
        return result

    def get_reapeat(self, keyval: int, action: AKeyEventAction) -> int:
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

    def __key_processor(
        self, controller: Gtk.EventControllerKey, keyval: int, keycode: int, state: int
    ) -> bool:
        event = controller.get_current_event()
        if event is None:
            return False
        action = self.convert_action(event)
        key_code = self.convert_keycode(controller, keyval, keycode, state)
        if key_code is None:
            return False
        # metastate = self.convert_mod(state)
        device = controller.get_current_event_device()
        if device is None:
            return False
        metastate = self.convert_mod(device.get_modifier_state())

        msg = InjectKeycodeMsg(
            action,
            key_code,
            self.get_reapeat(keyval, action),
            metastate,
        )
        self.event_bus.emit(Event[InjectKeycodeMsg](EventType.CONTROL_MSG, self, msg))
        return True

    def __text_processor(
        self, controller: Gtk.EventControllerKey, keyval: int, keycode: int, state: int
    ) -> bool:
        event = controller.get_current_event()
        event = cast(Gdk.KeyEvent, event)
        event_type = event.get_event_type()

        if (not event.is_modifier()) and event_type == Gdk.EventType.KEY_PRESS:
            text = self.convert_text(keyval)
            if text is None:
                return False
            msg = InjectTextMsg(text)
            self.event_bus.emit(Event(EventType.CONTROL_MSG, self, msg))
            return True
        return False
