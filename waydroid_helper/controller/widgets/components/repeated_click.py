#!/usr/bin/env python3
"""
重复点击组件
一个圆形的半透明蓝色按钮，支持重复点击操作
"""

import asyncio
import math
from enum import Enum
from gettext import pgettext
from typing import TYPE_CHECKING, cast

import gi

from waydroid_helper.controller.core.key_system import KeyRegistry

gi.require_version("GLib", "2.0")
from gi.repository import GLib

if TYPE_CHECKING:
    from cairo import Context, Surface
    from gi.repository import Gtk
    from waydroid_helper.controller.widgets.base.base_widget import EditableRegion

from waydroid_helper.controller.android.input import (
    AMotionEventAction,
    AMotionEventButtons,
)
from waydroid_helper.controller.core import (
    Event,
    EventType,
    KeyCombination,
    EventBus,
    PointerIdManager,
)
from waydroid_helper.controller.core.control_msg import InjectTouchEventMsg, ScreenInfo
from waydroid_helper.controller.core.handler.event_handlers import InputEvent
from waydroid_helper.controller.widgets.base.base_widget import BaseWidget
from waydroid_helper.controller.widgets.config import (
    create_dropdown_config,
    create_text_config,
)
from waydroid_helper.controller.widgets.decorators import Editable


class OperatingMethod(Enum):
    """重复点击操作方式枚举"""

    LONG_PRESS_COMBO = "long_press_combo"
    CLICK_AFTER_BUTTON = "click_after_button"


@Editable
class RepeatedClick(BaseWidget):
    """重复点击组件 - 圆形半透明蓝色按钮"""

    # 组件元数据
    WIDGET_NAME = pgettext("Controller Widgets", "Repeated Click")
    WIDGET_DESCRIPTION = pgettext(
        "Controller Widgets",
        "Simulate repeated click operations at a specific position.",
    )

    # 映射模式固定尺寸
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
        event_bus: EventBus | None = None,
        pointer_id_manager: PointerIdManager | None = None,
        key_registry: KeyRegistry | None = None,
    ):
        # 初始化基类，传入默认按键
        super().__init__(
            x,
            y,
            50,
            50,
            pgettext("Controller Widgets", "Repeated Click"),
            text,
            default_keys,
            min_width=25,
            min_height=25,
            event_bus=event_bus,
            pointer_id_manager=pointer_id_manager,
            key_registry=key_registry,
        )

        # 设置配置项
        self.setup_config()

        # 异步任务相关
        self._click_task: asyncio.Task[None] | None = None
        self._click_count = 0
        self._is_clicking = False
        self.screen_info = ScreenInfo()

    def draw_widget_content(self, cr: "Context[Surface]", width: int, height: int):
        """绘制圆形按钮的具体内容"""
        # 计算圆心和半径
        center_x = width / 2
        center_y = height / 2
        radius = min(width, height) / 2 - 5  # 留出边距

        # 绘制圆形背景
        cr.set_source_rgba(0.5, 0.5, 0.5, 0.6)

        cr.arc(center_x, center_y, radius, 0, 2 * math.pi)
        cr.fill()

        # 绘制圆形边框
        cr.set_source_rgba(0.3, 0.3, 0.3, 0.9)
        cr.set_line_width(2)
        cr.arc(center_x, center_y, radius, 0, 2 * math.pi)
        cr.stroke()

    def draw_text_content(self, cr: "Context[Surface]", width: int, height: int):
        """重写文本绘制 - 使用白色文字适配圆形按钮"""
        if self.text:
            center_x = width / 2
            center_y = height / 2

            cr.set_source_rgba(1, 1, 1, 1)  # 白色文字
            cr.select_font_face("Arial", 0, 1)
            cr.set_font_size(12)
            text_extents = cr.text_extents(self.text)
            x = center_x - text_extents.width / 2
            y = center_y + text_extents.height / 2
            cr.move_to(x, y)
            cr.show_text(self.text)

            # 清除路径，避免影响后续绘制
            cr.new_path()

    def draw_selection_border(self, cr: "Context[Surface]", width: int, height: int):
        """重写选择边框绘制 - 绘制圆形边框适配圆形按钮"""
        center_x = width / 2
        center_y = height / 2
        radius = min(width, height) / 2 - 5

        # 绘制圆形选择边框
        cr.set_source_rgba(0.2, 0.6, 1.0, 0.8)
        cr.set_line_width(3)
        cr.arc(center_x, center_y, radius + 3, 0, 2 * math.pi)
        cr.stroke()

    def draw_mapping_mode_background(
        self, cr: "Context[Surface]", width: int, height: int
    ):
        """映射模式下的背景绘制 - 根据文字长度的圆角矩形"""
        center_x = width / 2
        center_y = height / 2

        # 计算文字尺寸
        if self.text:
            cr.set_font_size(12)
            text_extents = cr.text_extents(self.text)
            text_width = text_extents.width
            text_height = text_extents.height
        else:
            text_width = 20  # 默认宽度
            text_height = 12  # 默认高度

        # 圆角矩形参数
        padding_x = 8  # 左右内边距
        padding_y = 4  # 上下内边距
        corner_radius = 6  # 圆角半径

        rect_width = text_width + 2 * padding_x
        rect_height = text_height + 2 * padding_y

        # 确保矩形不会太小
        rect_width = max(rect_width, 24)
        rect_height = max(rect_height, 16)

        # 计算矩形位置（居中）
        rect_x = center_x - rect_width / 2
        rect_y = center_y - rect_height / 2

        # 绘制圆角矩形背景
        cr.set_source_rgba(0.6, 0.6, 0.6, 0.7)  # 稍微加深一点透明度

        # 使用路径绘制圆角矩形
        # 左上角
        cr.move_to(rect_x + corner_radius, rect_y)
        # 上边
        cr.line_to(rect_x + rect_width - corner_radius, rect_y)
        # 右上角
        cr.arc(
            rect_x + rect_width - corner_radius,
            rect_y + corner_radius,
            corner_radius,
            -math.pi / 2,
            0,
        )
        # 右边
        cr.line_to(rect_x + rect_width, rect_y + rect_height - corner_radius)
        # 右下角
        cr.arc(
            rect_x + rect_width - corner_radius,
            rect_y + rect_height - corner_radius,
            corner_radius,
            0,
            math.pi / 2,
        )
        # 下边
        cr.line_to(rect_x + corner_radius, rect_y + rect_height)
        # 左下角
        cr.arc(
            rect_x + corner_radius,
            rect_y + rect_height - corner_radius,
            corner_radius,
            math.pi / 2,
            math.pi,
        )
        # 左边
        cr.line_to(rect_x, rect_y + corner_radius)
        # 左上角
        cr.arc(
            rect_x + corner_radius,
            rect_y + corner_radius,
            corner_radius,
            math.pi,
            3 * math.pi / 2,
        )
        cr.close_path()
        cr.fill()

        # 绘制圆角矩形边框
        cr.set_source_rgba(0.4, 0.4, 0.4, 0.9)
        cr.set_line_width(1)
        # 重复上面的路径
        cr.move_to(rect_x + corner_radius, rect_y)
        cr.line_to(rect_x + rect_width - corner_radius, rect_y)
        cr.arc(
            rect_x + rect_width - corner_radius,
            rect_y + corner_radius,
            corner_radius,
            -math.pi / 2,
            0,
        )
        cr.line_to(rect_x + rect_width, rect_y + rect_height - corner_radius)
        cr.arc(
            rect_x + rect_width - corner_radius,
            rect_y + rect_height - corner_radius,
            corner_radius,
            0,
            math.pi / 2,
        )
        cr.line_to(rect_x + corner_radius, rect_y + rect_height)
        cr.arc(
            rect_x + corner_radius,
            rect_y + rect_height - corner_radius,
            corner_radius,
            math.pi / 2,
            math.pi,
        )
        cr.line_to(rect_x, rect_y + corner_radius)
        cr.arc(
            rect_x + corner_radius,
            rect_y + corner_radius,
            corner_radius,
            math.pi,
            3 * math.pi / 2,
        )
        cr.close_path()
        cr.stroke()

    def draw_mapping_mode_content(
        self, cr: "Context[Surface]", width: int, height: int
    ):
        if self.text:
            center_x = width / 2
            center_y = height / 2

            # 使用白色文字以在蓝色背景上清晰显示
            cr.set_source_rgba(1, 1, 1, 1)  # 白色文字
            cr.select_font_face("Arial", 0, 1)
            cr.set_font_size(12)
            text_extents = cr.text_extents(self.text)
            x = center_x - text_extents.width / 2
            y = center_y + text_extents.height / 2
            cr.move_to(x, y)
            cr.show_text(self.text)

            # 清除路径，避免影响后续绘制
            cr.new_path()

    async def _long_press_combo_click(self, clicks_per_second: int):
        """长按连击模式的异步点击任务"""
        interval = 1.0 / clicks_per_second

        pointer_id = self._allocate_pointer()
        if pointer_id is None:
            return

        root_dimensions = self._get_root_dimensions()
        if root_dimensions is None:
            return
        w, h = root_dimensions

        try:
            while self._is_clicking:
                await self._send_click_sequence(w, h, pointer_id)

                await asyncio.sleep(interval - 0.001)  # 剩余时间等待

        except Exception:
            pass
        finally:
            if self._is_clicking:  # Only send UP if not cancelled
                await self._send_click_sequence(w, h, pointer_id)
            self.pointer_id_manager.release(self)

    async def _click_after_button_click(self, click_count: int):
        """按键后连击模式的异步点击任务"""
        interval = 1.0 / 20.0  # 每秒20次

        root_dimensions = self._get_root_dimensions()
        if root_dimensions is None:
            return
        w, h = root_dimensions

        pointer_id = self._allocate_pointer()
        if pointer_id is None:
            return

        try:
            for i in range(click_count):
                if not self._is_clicking:  # 检查是否应该停止
                    break

                await self._send_click_sequence(w, h, pointer_id)

                if i < click_count - 1:  # 最后一次点击后不需要等待
                    await asyncio.sleep(interval - 0.001)

        except Exception:
            pass
        finally:
            if self._is_clicking:  # Only send UP if not cancelled
                await self._send_click_sequence(w, h, pointer_id)
            self.pointer_id_manager.release(self)

    async def _send_touch_event(
        self,
        action: AMotionEventAction,
        pointer_id: int,
        root_width: int,
        root_height: int,
        pressure: float = 1.0,
    ) -> None:
        """发送触摸事件的辅助方法"""
        msg = InjectTouchEventMsg(
            action=action,
            pointer_id=pointer_id,
            position=(int(self.center_x), int(self.center_y), root_width, root_height),
            pressure=pressure,
            action_button=AMotionEventButtons.PRIMARY,
            buttons=(
                AMotionEventButtons.PRIMARY if action == AMotionEventAction.DOWN else 0
            ),
        )
        self.event_bus.emit(Event(EventType.CONTROL_MSG, self, msg))

    async def _send_click_sequence(
        self, root_width: int, root_height: int, pointer_id: int
    ) -> None:
        """发送一次完整的点击序列（DOWN + UP）"""
        await self._send_touch_event(
            AMotionEventAction.DOWN, pointer_id, root_width, root_height, 1.0
        )
        await asyncio.sleep(0.001)  # 短暂延迟确保事件处理
        await self._send_touch_event(
            AMotionEventAction.UP, pointer_id, root_width, root_height, 0.0
        )

    def _get_root_dimensions(self) -> tuple[int, int] | None:
        """获取根窗口的尺寸"""
        return self.screen_info.get_host_resolution()

    def _allocate_pointer(self) -> int | None:
        """分配 pointer_id，如果失败则记录警告"""
        pointer_id = self.pointer_id_manager.allocate(self)
        if pointer_id is None:
            return None
        return pointer_id

    def on_key_triggered(
        self,
        key_combination: KeyCombination | None = None,
        event: "InputEvent | None" = None,
    ) -> bool:
        """按键触发时的处理逻辑"""

        operating_method = self.get_config_value("operating_method")

        # 取消之前的任务
        if self._click_task and not self._click_task.done():
            self._click_task.cancel()

        if operating_method == OperatingMethod.LONG_PRESS_COMBO.value:
            self._is_clicking = True
            # LONG_PRESS_COMBO模式：开始连击
            try:
                clicks_per_second = int(
                    self.get_config_value("clicks_per_second") or "20"
                )
                clicks_per_second = max(1, min(clicks_per_second, 100))  # 限制范围1-100

                # 创建新的异步任务
                self._click_task = asyncio.create_task(
                    self._long_press_combo_click(clicks_per_second)
                )

            except ValueError:
                pass

        elif operating_method == OperatingMethod.CLICK_AFTER_BUTTON.value:
            # CLICK_AFTER_BUTTON模式：按下时不操作
            pass

        return True

    def on_key_released(
        self,
        key_combination: KeyCombination | None = None,
        event: "InputEvent | None" = None,
    ) -> bool:
        """按键释放时的处理逻辑"""

        operating_method = self.get_config_value("operating_method")

        # 停止当前点击
        self._is_clicking = False

        if self._click_task and not self._click_task.done():
            self._click_task.cancel()

        if operating_method == OperatingMethod.LONG_PRESS_COMBO.value:
            # LONG_PRESS_COMBO模式：停止连击
            pass
        elif operating_method == OperatingMethod.CLICK_AFTER_BUTTON.value:
            # CLICK_AFTER_BUTTON模式：松开后开始连击

            self._is_clicking = True
            try:
                click_count = int(self.get_config_value("repeated_click_count") or "20")
                click_count = max(1, min(click_count, 999))  # 限制范围1-100

                # 创建新的异步任务
                self._click_task = asyncio.create_task(
                    self._click_after_button_click(click_count)
                )

            except ValueError:
                pass

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
    def mapping_start_x(self):
        return int(self.x + self.width / 2)

    @property
    def mapping_start_y(self):
        return int(self.y + self.height / 2)

    @property
    def center_x(self):
        return self.x + self.width / 2

    @property
    def center_y(self):
        return self.y + self.height / 2

    def setup_config(self) -> None:
        """设置配置项"""

        # 操作方式配置
        operating_method_config = create_dropdown_config(
            key="operating_method",
            label=pgettext("Controller Widgets", "Operating Method"),
            options=[
                OperatingMethod.LONG_PRESS_COMBO.value,
                OperatingMethod.CLICK_AFTER_BUTTON.value,
            ],
            option_labels={
                OperatingMethod.LONG_PRESS_COMBO.value: pgettext(
                    "Controller Widgets", "Long-press combo"
                ),
                OperatingMethod.CLICK_AFTER_BUTTON.value: pgettext(
                    "Controller Widgets", "Click after button"
                ),
            },
            value=OperatingMethod.LONG_PRESS_COMBO.value,
            description=pgettext(
                "Controller Widgets",
                "Choose the operating method for repeated clicking",
            ),
        )

        # 每秒点击次数配置（长按连击模式）
        clicks_per_second_config = create_text_config(
            key="clicks_per_second",
            label=pgettext("Controller Widgets", "Number of clicks per second"),
            value="20",
            description=pgettext(
                "Controller Widgets",
                "Number of clicks to perform per second in long-press combo mode",
            ),
        )

        # 重复点击次数配置（按键后连击模式）
        repeated_click_count_config = create_text_config(
            key="repeated_click_count",
            label=pgettext("Controller Widgets", "Number of clicks"),
            value="20",
            description=pgettext(
                "Controller Widgets",
                "Number of repeated clicks to perform in click after button mode",
            ),
            visible=False,
        )

        # 添加配置项
        self.add_config_item(operating_method_config)
        self.add_config_item(clicks_per_second_config)
        self.add_config_item(repeated_click_count_config)

        # 添加配置变更回调
        self.add_config_change_callback(
            "operating_method", self._on_operating_method_changed
        )

    def _on_operating_method_changed(self, key: str, value: str, from_ui: bool) -> None:
        """操作方式配置变更回调"""
        self._update_config_visibility()

    def create_config_ui(self) -> "Gtk.Widget":
        """创建配置UI，重写以支持动态可见性"""
        # 调用父类方法创建UI
        ui_widget = self.get_config_manager().create_ui()

        # 使用GLib.idle_add延迟设置可见性，确保UI完全初始化后再执行
        GLib.idle_add(self._update_config_visibility)

        return ui_widget

    def _update_config_visibility(self) -> None:
        """根据操作方式更新配置项的可见性"""
        operating_method = self.get_config_value("operating_method")
        config_manager = self.get_config_manager()

        if not config_manager.ui_widgets:
            # UI还未创建，无需更新
            return

        config_manager.set_visible(
            "clicks_per_second",
            operating_method == OperatingMethod.LONG_PRESS_COMBO.value,
        )
        config_manager.set_visible(
            "repeated_click_count",
            operating_method == OperatingMethod.CLICK_AFTER_BUTTON.value,
        )
