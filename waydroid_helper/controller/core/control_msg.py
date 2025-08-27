#!/usr/bin/env python3
"""
控制消息模块
"""
import struct
from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import IntEnum

from waydroid_helper.util.log import logger
from waydroid_helper.controller.android import (AKeyCode, AKeyEventAction,
                                                AMetaState, AMotionEventAction,
                                                AMotionEventButtons)


class ScreenInfo:
    _instance = None
    host_width: int = 0
    host_height: int = 0
    width: int = 0
    height: int = 0

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def set_resolution(self, width: int, height: int):
        self.width = width
        self.height = height

    def get_resolution(self) -> tuple[int, int]:
        return self.width, self.height
    
    def set_host_resolution(self, width: int, height: int):
        self.host_width = width
        self.host_height = height
    
    def get_host_resolution(self) -> tuple[int, int]:
        return self.host_width, self.host_height


# 全局单例实例，避免重复创建
_screen_info = ScreenInfo()
_resolution_warning_shown = False


def scale_coordinates(client_x: int, client_y: int, client_w: int, client_h: int) -> tuple[int, int, int, int]:
    """优化的坐标缩放函数，减少重复代码和计算"""
    global _resolution_warning_shown
    device_w, device_h = _screen_info.get_resolution()

    if device_w == 0 or device_h == 0:
        # 只在第一次警告，避免日志洪水
        if not _resolution_warning_shown:
            logger.warning("Device resolution not set, using client resolution. Coordinates may be incorrect.")
            _resolution_warning_shown = True
        device_w, device_h = client_w, client_h

    # 使用整数除法优化
    scaled_x = (client_x * device_w) // client_w if client_w != 0 else 0
    scaled_y = (client_y * device_h) // client_h if client_h != 0 else 0

    return scaled_x, scaled_y, device_w, device_h


class ControlMsgType(IntEnum):
    INJECT_KEYCODE = 0
    INJECT_TEXT = 1
    INJECT_TOUCH_EVENT = 2
    INJECT_SCROLL_EVENT = 3
    BACK_OR_SCREEN_ON = 4
    EXPAND_NOTIFICATION_PANEL = 5
    EXPAND_SETTINGS_PANEL = 6
    COLLAPSE_PANELS = 7
    GET_CLIPBOARD = 8
    SET_CLIPBOARD = 9
    SET_SCREEN_POWER_MODE = 10
    ROTATE_DEVICE = 11
    UHID_CREATE = 12
    UHID_INPUT = 13
    OPEN_HARD_KEYBOARD_SETTINGS = 14

def to_fixed_point_u16(f_val: float) -> int:
    """优化版本：将浮点数转换为 Q16 格式的定点数，移除分支预测"""
    # 使用 max/min 进行 clamp，比 if 语句更高效
    clamped = max(0.0, min(1.0, f_val))
    return int(clamped * 0xFFFF)

def to_fixed_point_i16(f: float) -> int:
    """优化版本：移除断言以提高性能，假设输入已经验证"""
    # 直接计算，假设输入在有效范围内
    i = int(f * 0x8000)  # 32768 = 2^15
    # 处理边界情况，避免溢出
    return min(0x7FFF, max(-0x8000, i))

@dataclass
class ControlMsg(ABC):
    @property
    @abstractmethod
    def msg_type(self) -> ControlMsgType:
        raise NotImplementedError

    @abstractmethod
    def pack(self) -> bytes:
        raise NotImplementedError


@dataclass
class InjectKeycodeMsg(ControlMsg):
    action: AKeyEventAction
    keycode: AKeyCode
    repeat: int
    metastate: AMetaState|int

    @property
    def msg_type(self) -> ControlMsgType:
        return ControlMsgType.INJECT_KEYCODE

    def pack(self) -> bytes:
        """优化版本：移除异常处理以提高性能"""
        return struct.pack(
            ">BBIII",
            self.msg_type,
            self.action,
            self.keycode,
            self.repeat,
            self.metastate,
        )


@dataclass
class InjectTextMsg(ControlMsg):
    text: str

    @property
    def msg_type(self) -> ControlMsgType:
        return ControlMsgType.INJECT_TEXT

    def pack(self) -> bytes:
        """优化版本：移除异常处理，使用更高效的字节拼接"""
        text_bytes = self.text.encode('utf-8')
        return struct.pack(">BI", self.msg_type, len(text_bytes)) + text_bytes


@dataclass
class InjectTouchEventMsg(ControlMsg):
    action: AMotionEventAction
    pointer_id: int
    position: tuple[int, int, int, int] # x, y, screen_width, screen_height
    pressure: float
    action_button: AMotionEventButtons | int
    buttons: AMotionEventButtons | int

    @property
    def msg_type(self) -> ControlMsgType:
        return ControlMsgType.INJECT_TOUCH_EVENT
        
    def pack(self) -> bytes:
        """优化版本：使用共享的坐标缩放函数和预计算的压力值"""
        client_x, client_y, client_w, client_h = self.position
        scaled_x, scaled_y, device_w, device_h = scale_coordinates(client_x, client_y, client_w, client_h)

        # 预计算压力值以避免重复调用
        pressure_fixed = to_fixed_point_u16(self.pressure)

        return struct.pack(
            ">BBQIIHHHII",
            self.msg_type,
            self.action,
            self.pointer_id,
            scaled_x,
            scaled_y,
            device_w,
            device_h,
            pressure_fixed,
            self.action_button,
            self.buttons,
        )


@dataclass
class InjectScrollEventMsg(ControlMsg):
    position: tuple[int, int, int, int] # x, y, screen_width, screen_height
    hscroll: float
    vscroll: float
    buttons: AMotionEventButtons | int

    @property
    def msg_type(self) -> ControlMsgType:
        return ControlMsgType.INJECT_SCROLL_EVENT

    def pack(self) -> bytes:
        """优化版本：使用共享的坐标缩放函数和预计算的滚动值"""
        client_x, client_y, client_w, client_h = self.position
        scaled_x, scaled_y, device_w, device_h = scale_coordinates(client_x, client_y, client_w, client_h)

        hscroll_fixed = to_fixed_point_i16(self.hscroll)
        vscroll_fixed = to_fixed_point_i16(self.vscroll)

        return struct.pack(
            ">BIIHHhhI",
            self.msg_type,
            scaled_x,
            scaled_y,
            device_w,
            device_h,
            hscroll_fixed,
            vscroll_fixed,
            self.buttons,
        )