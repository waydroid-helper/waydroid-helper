#!/usr/bin/env python3
"""
基础组件类
提供可拖动、可调整大小的组件基类
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING, Any, Callable, TypedDict, cast

import gi

from waydroid_helper.controller.core.key_system import KeyRegistry
from waydroid_helper.controller.core.utils import PointerIdManager

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, GObject, Gtk

from waydroid_helper.controller.core import (Event, EventType, KeyCombination,
                                             EventBus)
from waydroid_helper.controller.widgets.config import ConfigManager

if TYPE_CHECKING:
    from cairo import Context, Surface
    from waydroid_helper.controller.widgets.config import ConfigItem
from cairo import FontSlant, FontWeight

class EditableRegion(TypedDict):
    """可编辑区域类型定义"""

    id: str
    name: str
    bounds: tuple[int, int, int, int]
    get_keys: Callable[[], set[KeyCombination]]
    set_keys: Callable[[set[KeyCombination]], None]


class BaseWidget(Gtk.DrawingArea):
    """基础可拖动调整大小组件"""

    # 组件元数据 - 子类可以覆盖这些属性
    WIDGET_NAME = "Base Widget"
    WIDGET_DESCRIPTION = "Base widget, providing basic drag and select functionality"
    WIDGET_VERSION = "1.1"

    # 映射模式固定尺寸 - 子类可以覆盖这些值
    MAPPING_MODE_WIDTH = 50  # 默认映射模式宽度
    MAPPING_MODE_HEIGHT = 50  # 默认映射模式高度

    # 按键映射特性 - 子类可以覆盖这个值
    IS_REENTRANT = False  # 是否支持可重入（长按重复触发），默认不支持
    ALLOW_CONTEXT_MENU_CREATION = True  # 是否允许通过右键菜单创建

    SETTINGS_PANEL_AUTO_HIDE = True

    # 定义GObject属性
    __gtype_name__ = "BaseWidget"

    # 将is_selected设为可观察的属性
    is_selected = GObject.Property(type=bool, default=False)

    # 添加mapping_mode属性，用于控制绘制样式
    mapping_mode = GObject.Property(type=bool, default=False)

    def __init__(
        self,
        x:int=0,
        y:int=0,
        width:int=150,
        height:int=100,
        title:str="Component",
        text:str="",
        default_keys:set[KeyCombination]|None=None,
        min_width:int=100,
        min_height:int=100,
        event_bus:EventBus|None=None,
        pointer_id_manager:PointerIdManager|None=None,
        key_registry:KeyRegistry|None=None,
    ):
        super().__init__()

        # 基础属性
        self.original_width:int = width  # 保存原始尺寸
        self.original_height:int = height
        self.title:str = title
        self.text:str = text  # 显示文本，独立于按键映射

        # 编辑模式下的坐标也是业务实际使用的坐标
        self.x:int = x  # 编辑模式下x坐标
        self.y:int = y  # 编辑模式下y坐标
        self.width:int = width  # 编辑模式下宽度
        self.height:int = height  # 编辑模式下高度

        self.min_width:int = min_width
        self.min_height:int = min_height

        # 按键映射属性
        self.final_keys: set[KeyCombination] = (
            set(default_keys) if default_keys else set()
        )  # 最终保存的按键组合集合

        # 交互状态
        self.is_dragging:bool = False
        self.drag_start_x:int = 0
        self.drag_start_y:int = 0

        # 设置大小
        self.set_size_request(width, height)

        # 添加删除按钮悬停状态
        self.delete_button_hovered = False
        self.settings_button_hovered = False

        # 设置绘制函数
        self.set_draw_func(self.draw_func, None)

        # 添加事件控制器
        self.setup_event_controllers()

        # 配置管理器
        if not event_bus or not pointer_id_manager or not key_registry:
            raise ValueError("event_bus and pointer_id_manager and key_registry are required")
        self.config_manager = ConfigManager(event_bus)
        self.event_bus = event_bus
        self.pointer_id_manager = pointer_id_manager
        self.key_registry = key_registry

    def set_default_keys(self, default_keys: set[KeyCombination]):
        self.final_keys = (set(default_keys))

    def add_config_item(self, config_item: "ConfigItem") -> None:
        """添加配置项"""
        self.config_manager.add_config(config_item)

    def get_config_manager(self) -> ConfigManager:
        """获取配置管理器"""
        return self.config_manager

    def set_config_value(self, key: str, value: Any) -> bool:
        """设置配置值"""
        return self.config_manager.set_value(key, value)

    def get_config_value(self, key: str) -> Any:
        """获取配置值"""
        return self.config_manager.get_value(key)

    def add_config_change_callback(self, key: str, callback: Callable[[str, Any, bool], None]) -> None:
        """添加配置变更回调"""
        self.config_manager.add_change_callback(key, callback)

    @property
    def mapping_start_x(self)->float:
        return self.x

    @property
    def mapping_start_y(self)->float:
        return self.y

    def setup_event_controllers(self):
        """设置基础事件控制器 - 只处理widget特定的事件"""
        # 使组件可获得焦点（用于键盘事件）
        self.set_focusable(True)

        # 添加删除按钮的鼠标事件控制器
        self._motion_controller = Gtk.EventControllerMotion.new()
        self._motion_controller.connect("motion", self._on_motion)
        self._motion_controller.connect("leave", self._on_leave)
        # click
        self._click_controller = Gtk.GestureClick.new()
        self._click_controller.set_button(Gdk.BUTTON_PRIMARY)  # 只处理左键
        self._click_controller.connect("pressed", self._on_clicked)
        self.add_controller(self._motion_controller)
        self.add_controller(self._click_controller)

    def _on_clicked(self, controller, n_press, x, y):
        """处理删除按钮的点击事件"""
        if not self.is_selected or self.mapping_mode:
            return False
            
        # 直接判断点击位置是否在删除按钮区域内
        if self.is_point_in_delete_button(x, y):
            self.event_bus.emit(Event(EventType.DELETE_WIDGET, self, self))
            return True  # 阻止事件继续传播
        
        if self.is_point_in_settings_button(x, y):
            self.event_bus.emit(Event(EventType.SETTINGS_WIDGET, self, self.SETTINGS_PANEL_AUTO_HIDE))
            return True

        return False

    def _on_motion(self, controller, x, y):
        """处理删除按钮的鼠标移动事件"""
        if not self.is_selected or self.mapping_mode:
            return

        # 统一处理悬停状态
        on_delete = self.is_point_in_delete_button(x, y)
        if self.delete_button_hovered != on_delete:
            self.delete_button_hovered = on_delete
            self.queue_draw()

        on_settings = self.is_point_in_settings_button(x, y)
        if self.settings_button_hovered != on_settings:
            self.settings_button_hovered = on_settings
            self.queue_draw()

        # 更新鼠标指针
        if on_delete or on_settings:
            self.set_cursor_from_name("pointer")
        else:
            self.set_cursor(None)

    def _on_leave(self, controller):
        """处理鼠标离开删除按钮事件"""
        changed = False
        if self.delete_button_hovered:
            self.delete_button_hovered = False
            changed = True
        
        if self.settings_button_hovered:
            self.settings_button_hovered = False
            changed = True

        if changed:
            self.queue_draw()

        # 清除widget级别的指针设置，让窗口级别的指针生效
        self.set_cursor(None)

    def draw_func(self, widget:Gtk.DrawingArea, cr:'Context[Surface]', width:int, height:int, user_data:Any):
        """基础绘制函数 - 调用子类的具体绘制方法"""
        if self.mapping_mode:
            # 映射模式下的精简绘制
            self.draw_mapping_mode(cr, width, height)
        else:
            # 编辑模式下的正常绘制
            self.draw_widget_content(cr, width, height)
            self.draw_text_content(cr, width, height)
            self.draw_selection_indicators(cr, width, height)

    def draw_widget_content(self, cr:'Context[Surface]', width:int, height:int)->None:
        """绘制widget的具体内容 - 子类应重写此方法"""
        # 默认绘制一个简单的矩形背景
        raise NotImplementedError("子类必须实现draw_widget_content方法")

    def draw_text_content(self, cr:'Context[Surface]', width:int, height:int)->None:
        """绘制文本内容 - 公共逻辑"""
        if self.text:
            raise NotImplementedError("子类必须实现draw_text_content方法")
        elif hasattr(self, "title") and self.title and self.title != "组件":
            # 如果没有text但有标题，绘制标题
            cr.set_source_rgba(0, 0, 0, 1)
            cr.select_font_face("Arial", FontSlant.NORMAL, FontWeight.BOLD)
            cr.set_font_size(12)
            text_extents = cr.text_extents(self.title)
            x = (width - text_extents.width) / 2
            y = (height + text_extents.height) / 2
            cr.move_to(x, y)
            cr.show_text(self.title)

    def draw_selection_indicators(self, cr:'Context[Surface]', width:int, height:int):
        """绘制选择状态指示器"""
        if self.is_selected:
            # 绘制默认的矩形选择边框
            self.draw_selection_border(cr, width, height)
            self.draw_delete_button(cr)
            self.draw_settings_button(cr)

    def draw_selection_border(self, cr:'Context[Surface]', width:int, height:int)->None:
        """绘制选择边框 - 子类可以重写此方法来自定义边框样式"""
        raise NotImplementedError("子类必须实现draw_selection_border方法")

    def draw_mapping_mode(self, cr:'Context[Surface]', width:int, height:int)->None:
        """映射模式下的精简绘制"""
        # 绘制统一的背景
        self.draw_mapping_mode_background(cr, width, height)

        # 调用子类的映射模式内容绘制
        self.draw_mapping_mode_content(cr, width, height)

    def draw_mapping_mode_background(self, cr:'Context[Surface]', width:int, height:int)->None:
        """映射模式下的背景绘制 - 统一样式"""
        # 默认绘制单一背景色矩形
        cr.set_source_rgba(0.6, 0.6, 0.6, 0.5)  # 半透明灰色
        cr.rectangle(0, 0, width, height)
        cr.fill()

    def draw_mapping_mode_content(self, cr:'Context[Surface]', width:int, height:int)->None:
        """映射模式下的内容绘制 - 子类必须重写此方法"""
        # 默认什么都不绘制，子类应该重写此方法

    def set_selected(self, selected: bool)->None:
        """设置选择状态"""
        self.is_selected = selected
        self.queue_draw()

    def set_mapping_mode(self, mapping_mode: bool)->None:
        """设置映射模式"""
        if self.mapping_mode != mapping_mode:
            self.mapping_mode = mapping_mode

            if mapping_mode:
                parent = self.get_parent()
                parent = cast('Gtk.Fixed', parent)
                parent.move(self, self.mapping_start_x, self.mapping_start_y)

                self.set_size_request(self.MAPPING_MODE_WIDTH, self.MAPPING_MODE_HEIGHT)

                if hasattr(self, "set_content_width"):
                    self.set_content_width(self.MAPPING_MODE_WIDTH)
                if hasattr(self, "set_content_height"):
                    self.set_content_height(self.MAPPING_MODE_HEIGHT)

            else:
                parent = self.get_parent()
                parent = cast('Gtk.Fixed', parent)
                parent.move(self, self.x, self.y)

                self.set_size_request(self.width, self.height)

                if hasattr(self, "set_content_width"):
                    self.set_content_width(self.width)
                if hasattr(self, "set_content_height"):
                    self.set_content_height(self.height)

            self.queue_draw()

    def get_widget_bounds(self):
        """获取widget的边界信息"""
        parent = self.get_parent()
        parent = cast('Gtk.Fixed', parent)
        if parent:
            x, y = parent.get_child_position(self)
            width = self.get_allocated_width()
            height = self.get_allocated_height()
            return x, y, width, height
        return 0, 0, self.width, self.height

    def draw_delete_button(self, cr:'Context[Surface]'):
        """绘制删除按钮"""
        if self.mapping_mode:
            return

        bounds = self.get_delete_button_bounds()
        x, y, w, h = bounds

        # 绘制白色圆形背景
        cr.set_source_rgba(1, 1, 1, 0.9)
        cr.arc(x + w / 2, y + h / 2, w / 2, 0, 2 * math.pi)
        cr.fill()
        
        # 如果鼠标悬停，绘制蓝色背景
        if self.delete_button_hovered:
            cr.set_source_rgba(1.0, 0.2, 0.2, 0.9)  # 红色
            cr.arc(x + w / 2, y + h / 2, w / 2, 0, 2 * math.pi)
            cr.fill()
        
        # 绘制黑色或白色 'X'，根据悬停状态决定颜色
        if self.delete_button_hovered:
            cr.set_source_rgba(1, 1, 1, 1)  # 白色
        else:
            cr.set_source_rgba(0, 0, 0, 0.7)  # 黑色
        cr.set_line_width(2)
        padding = 4
        cr.move_to(x + padding, y + padding)
        cr.line_to(x + w - padding, y + h - padding)
        cr.move_to(x + w - padding, y + padding)
        cr.line_to(x + padding, y + h - padding)
        cr.stroke()

    def draw_settings_button(self, cr:'Context[Surface]'):
        """绘制一个更清晰的齿轮设置按钮"""
        if self.mapping_mode:
            return

        bounds = self.get_settings_button_bounds()
        x, y, w, h = bounds
        center_x, center_y = x + w / 2, y + h / 2

        # 1. 绘制圆形背景
        cr.set_source_rgba(1, 1, 1, 0.9)
        cr.arc(center_x, center_y, w / 2, 0, 2 * math.pi)
        cr.fill()
        
        # 2. 如果鼠标悬停，绘制蓝色背景
        if self.settings_button_hovered:
            cr.set_source_rgba(0.2, 0.6, 1.0, 0.9)
            cr.arc(center_x, center_y, w / 2, 0, 2 * math.pi)
            cr.fill()
        
        # 3. 绘制齿轮图标
        # 根据悬停状态设置齿轮颜色
        if self.settings_button_hovered:
            cr.set_source_rgba(1, 1, 1, 1)  # 白色
        else:
            cr.set_source_rgba(0.2, 0.2, 0.2, 0.8)  # 深灰色
        
        num_teeth = 6
        outer_radius = w / 2 - 2  # 齿轮外径
        inner_radius = outer_radius * 0.6  # 齿轮内径
        hole_radius = outer_radius * 0.4 # 中心孔径

        cr.set_line_width(1.5)
        
        # 绘制齿
        for i in range(num_teeth):
            angle = i * (2 * math.pi / num_teeth)
            
            # 计算齿的四个角
            start_angle = angle - math.pi / num_teeth / 2
            end_angle = angle + math.pi / num_teeth / 2
            
            # 外顶点
            x1 = center_x + outer_radius * math.cos(start_angle)
            y1 = center_y + outer_radius * math.sin(start_angle)
            x2 = center_x + outer_radius * math.cos(end_angle)
            y2 = center_y + outer_radius * math.sin(end_angle)
            
            # 内顶点
            x3 = center_x + inner_radius * math.cos(end_angle)
            y3 = center_y + inner_radius * math.sin(end_angle)
            x4 = center_x + inner_radius * math.cos(start_angle)
            y4 = center_y + inner_radius * math.sin(start_angle)
            
            # 绘制一个齿 (梯形)
            cr.new_path()
            cr.move_to(x1, y1)
            cr.line_to(x2, y2)
            cr.line_to(x3, y3)
            cr.line_to(x4, y4)
            cr.close_path()
            cr.fill()
            
        # 绘制齿轮主体（覆盖内侧）
        cr.new_path()
        cr.arc(center_x, center_y, inner_radius, 0, 2 * math.pi)
        cr.fill()

        # 4. 绘制中心孔（用背景色覆盖）
        cr.save()
        if self.settings_button_hovered:
            cr.set_source_rgba(0.2, 0.6, 1.0, 1.0) # 悬停时的背景色
        else:
            cr.set_source_rgba(1, 1, 1, 1.0) # 默认背景色
            
        cr.new_path()
        cr.arc(center_x, center_y, hole_radius, 0, 2 * math.pi)
        cr.fill()
        cr.restore()


    def get_delete_button_bounds(self) -> tuple[int, int, int, int]:
        """获取删除按钮的边界 (x, y, w, h) - 子类可以重写"""
        size = 16
        center_x = self.width / 2
        center_y = self.height / 2
        radius = min(self.width, self.height) / 2   # 留出边距
        angle = -math.pi / 4
        button_center_x = center_x + radius * math.cos(angle)
        button_center_y = center_y + radius * math.sin(angle)
        x = button_center_x - size / 2
        y = button_center_y - size / 2
        return (int(x), int(y), size, size)

    def get_settings_button_bounds(self) -> tuple[int, int, int, int]:
        """获取设置按钮的边界 (x, y, w, h) - 子类可以重写"""
        size = 16
        center_x = self.width / 2
        center_y = self.height / 2
        radius = min(self.width, self.height) / 2
        angle = math.pi / 4  # 右下角
        button_center_x = center_x + radius * math.cos(angle)
        button_center_y = center_y + radius * math.sin(angle)
        x = button_center_x - size / 2
        y = button_center_y - size / 2
        return (int(x), int(y), size, size)

    def on_widget_clicked(self, x, y):
        """widget被点击时的回调 - 子类可以重写"""

    def on_widget_double_clicked(self, x, y):
        """widget被双击时的回调 - 子类可以重写"""

    def on_widget_right_clicked(self, x, y):
        """widget被右键点击时的回调 - 子类可以重写"""
        return False

    def on_key_triggered(
        self, key_combination: KeyCombination|None = None
    ) -> bool:
        """按键触发时调用的方法（按键按下）

        Args:
            key_combination: 触发的按键组合
        """
        raise NotImplementedError("子类必须实现on_key_triggered方法")

    def on_key_released(self, key_combination: KeyCombination|None = None) -> bool:
        """按键弹起时调用的方法（按键弹起）

        Args:
            key_combination: 弹起的按键组合
        """
        raise NotImplementedError("子类必须实现on_key_released方法")

    # 为了向后兼容，保留原有的方法
    # def get_config(self) -> dict[str, Any]:
    #     """获取widget的配置信息 - 已弃用，请使用get_config_manager()"""
    #     logger.warning(f"get_config() is deprecated, use get_config_manager() instead")
    #     return {}

    # def set_config(self, config: dict[str, Any]) -> None:
    #     """设置widget的配置信息 - 已弃用，请使用set_config_value()"""
    #     logger.warning(f"set_config() is deprecated, use set_config_value() instead")
    #     for key, value in config.items():
    #         self.set_config_value(key, value)

    # def add_config_handler(self, key: str, handler: Callable[[Any], None]) -> None:
    #     """添加配置处理函数 - 已弃用，请使用add_config_change_callback()"""
    #     logger.warning(f"add_config_handler() is deprecated, use add_config_change_callback() instead")
    #     def wrapper(config_key: str, value: Any) -> None:
    #         handler(value)
    #     self.add_config_change_callback(key, wrapper)

    def get_editable_regions(self) -> list[EditableRegion]:
        """获取可编辑区域列表 - 支持多区域编辑的widget应重写此方法

        返回格式: [
            {
                'id': 'region_id',           # 区域唯一标识
                'name': 'Region Name',       # 区域显示名称
                'bounds': (x, y, w, h),      # 区域边界 (相对于widget坐标)
                'get_keys': lambda: [...],   # 获取当前按键的函数
                'set_keys': lambda keys: ... # 设置按键的函数
            },
            ...
        ]
        """
        # 默认返回单个编辑区域（整个widget）
        return []

    def get_region_at_position(self, x:int|float, y:int|float) -> EditableRegion|None:
        """获取指定位置的区域ID - 支持多区域编辑的widget应重写此方法"""
        regions = self.get_editable_regions()
        if not regions:
            return None
        for region in regions:
            bounds = region.get("bounds")
            if bounds and len(bounds) == 4:
                rx, ry, rw, rh = bounds
                if rx <= x <= rx + rw and ry <= y <= ry + rh:
                    return region
        return None

    def is_point_in_delete_button(self, x:int|float, y:int|float) -> bool:
        """检查点是否在删除按钮区域内"""
        if not self.is_selected or self.mapping_mode:
            return False
            
        bounds = self.get_delete_button_bounds()
        bx, by, bw, bh = bounds
        center_x = bx + bw / 2
        center_y = by + bh / 2
        radius = bw / 2  # 按钮是圆形的，所以用半径判断
        
        # 计算点到圆心的距离
        distance = math.sqrt((x - center_x) ** 2 + (y - center_y) ** 2)
        return distance <= radius

    def is_point_in_settings_button(self, x: int | float, y: int | float) -> bool:
        """检查点是否在设置按钮区域内"""
        if not self.is_selected or self.mapping_mode:
            return False
            
        bounds = self.get_settings_button_bounds()
        bx, by, bw, bh = bounds
        center_x = bx + bw / 2
        center_y = by + bh / 2
        radius = bw / 2
        
        distance = math.sqrt((x - center_x) ** 2 + (y - center_y) ** 2)
        return distance <= radius

    def on_delete(self):
        """Widget被删除时的清理方法"""
        self.set_selected(False)
        self.pointer_id_manager.release(self)

        # 清理事件总线订阅
        self.event_bus.unsubscribe_by_subscriber(self)