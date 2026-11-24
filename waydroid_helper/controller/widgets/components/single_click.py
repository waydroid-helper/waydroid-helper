#!/usr/bin/env python3
"""
单击按钮组件
一个圆形的半透明灰色按钮，支持单击操作
"""

import math
from gettext import pgettext
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from cairo import Context, Surface
    from gi.repository import Gtk
    from waydroid_helper.controller.widgets.base.base_widget import EditableRegion

from waydroid_helper.controller.android.input import (
    AMotionEventAction,
    AMotionEventButtons,
)
from waydroid_helper.controller.core import (
    ControllerRuntimeContext,
    Event,
    EventType,
    KeyCombination,
)
from waydroid_helper.controller.core.control_msg import InjectTouchEventMsg
from waydroid_helper.controller.core.handler.event_handlers import InputEvent
from waydroid_helper.controller.widgets.base.base_widget import BaseWidget
from waydroid_helper.controller.widgets.decorators import Editable


@Editable
class SingleClick(BaseWidget):
    """单击按钮组件 - 圆形半透明按钮"""

    # 组件元数据
    WIDGET_NAME = pgettext("Controller Widgets", "Single Click")
    WIDGET_DESCRIPTION = pgettext(
        "Controller Widgets",
        "Simulate a click operation at a specific position.",
    )

    # 映射模式固定尺寸
    # MAPPING_MODE_WIDTH = 30
    MAPPING_MODE_HEIGHT = 30

    @property
    def MAPPING_MODE_WIDTH(self):
        """根据文字长度计算映射模式宽度，与draw_mapping_mode_background的逻辑保持一致"""
        if self.text:
            # 估算文字宽度：对于12px的Arial字体
            # 英文数字字符平均约7-8px，为保险起见用8px
            # 中文字符约12px，这里简化统一按8px估算（略保守）
            estimated_text_width = len(self.text) * 8

            # 加上左右内边距 (padding_x = 8 * 2 = 16)
            padding_x = 8
            rect_width = estimated_text_width + 2 * padding_x

            # 确保最小宽度 24，与draw_mapping_mode_background一致
            rect_width = max(rect_width, 24)

            # 为了保险起见，再加4px缓冲，确保不会被截断
            return rect_width + 4
        else:
            # 无文字时的默认宽度，与draw_mapping_mode_background的default保持一致
            return 24 + 4  # 24是最小宽度，+4是缓冲

    def __init__(
        self,
        x: int = 0,
        y: int = 0,
        width: int = 50,
        height: int = 50,
        text: str = "",
        default_keys: set[KeyCombination] | None = None,
        *,
        runtime_context: ControllerRuntimeContext,
    ):
        # 初始化基类，传入默认按键
        super().__init__(
            x,
            y,
            50,
            50,
            pgettext("Controller Widgets", "Single Click"),
            text,
            default_keys,
            min_width=25,
            min_height=25,
            runtime_context=runtime_context,
        )

    def on_key_triggered(
        self,
        key_combination: KeyCombination | None = None,
        event: "InputEvent | None" = None,
    ):
        if key_combination:
            used_key = str(key_combination)
        elif self.final_keys:
            used_key = str(next(iter(self.final_keys)))
        else:
            used_key = "未知按键"

        # 分配 pointer_id
        pointer_id = self.pointer_id_manager.allocate(self)
        if pointer_id is None:
            return False

        x, y = self.center_x, self.center_y
        w, h = self.screen_geometry.get_host_resolution()
        device_resolution = self.screen_geometry.get_device_resolution_for_client(w, h)
        msg = InjectTouchEventMsg(
            action=AMotionEventAction.DOWN,
            pointer_id=pointer_id,
            position=(int(x), int(y), w, h),
            device_resolution=device_resolution,
            pressure=1.0,
            action_button=AMotionEventButtons.PRIMARY,
            buttons=AMotionEventButtons.PRIMARY,
        )
        self.event_bus.emit(Event(EventType.CONTROL_MSG, self, msg))
        return True

    def on_key_released(
        self,
        key_combination: KeyCombination | None = None,
        event: "InputEvent | None" = None,
    ):
        if key_combination:
            used_key = str(key_combination)
        elif self.final_keys:
            used_key = str(next(iter(self.final_keys)))
        else:
            used_key = "未知按键"
        x, y = self.center_x, self.center_y
        w, h = self.screen_geometry.get_host_resolution()
        device_resolution = self.screen_geometry.get_device_resolution_for_client(w, h)
        pointer_id = self.pointer_id_manager.allocate(self)
        if pointer_id is None:
            return False
        msg = InjectTouchEventMsg(
            action=AMotionEventAction.UP,
            pointer_id=pointer_id,
            position=(int(x), int(y), w, h),
            device_resolution=device_resolution,
            pressure=0.0,
            action_button=AMotionEventButtons.PRIMARY,
            buttons=0,
        )
        self.event_bus.emit(Event(EventType.CONTROL_MSG, self, msg))
        # 释放 pointer_id
        self.pointer_id_manager.release(self)
        return True

    def get_editable_regions(self) -> list["EditableRegion"]:
        return [
            {
                "id": "default",
                "name": "按键映射",
                "bounds": (0, 0, self.width, self.height),
                "get_keys": lambda: self.final_keys.copy(),
                "set_keys": lambda keys: setattr(
                    self, "final_keys", set(keys) if keys else set()
                ),
            }
        ]

    @property
    def center_x(self):
        return self.x + self.width / 2

    @property
    def center_y(self):
        return self.y + self.height / 2
