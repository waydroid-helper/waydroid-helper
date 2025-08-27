#!/usr/bin/env python3
"""
Widget Configuration System
统一的配置系统，提供配置项定义、UI生成、验证和序列化功能
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable

import gi

from waydroid_helper.controller.core import EventType, EventBus

gi.require_version("Gtk", "4.0")
from gi.repository import GObject, Gtk

from waydroid_helper.util.log import logger


class ConfigType(Enum):
    """配置项类型枚举"""
    SLIDER = auto()
    DROPDOWN = auto()
    TEXT = auto()
    NUMBER = auto()
    SWITCH = auto()
    COLOR = auto()
    TEXTAREA = auto()  # 新增多行文本类型


@dataclass
class ConfigItem(ABC):
    """配置项基类"""
    key: str
    label: str
    description: str = ""
    value: Any = None
    visible: bool = True
    
    @abstractmethod
    def create_ui_widget(self, on_change_callback: Callable[[str, Any], None]) -> Gtk.Widget:
        """创建对应的UI控件，并连接变更回调"""
    
    @abstractmethod
    def get_value_from_ui(self, widget: Gtk.Widget) -> Any:
        """从UI控件获取值"""
    
    @abstractmethod
    def set_value_to_ui(self, widget: Gtk.Widget, value: Any) -> None:
        """设置值到UI控件（不触发信号）"""
    
    @abstractmethod
    def validate(self, value: Any) -> bool:
        """验证值是否合法"""
    
    def serialize(self) -> dict[str, Any]:
        """序列化配置项"""
        return {
            "key": self.key,
            "label": self.label,
            "description": self.description,
            "value": self.value,
            "type": self.__class__.__name__,
            "visible": self.visible,
        }
    
    @classmethod
    def deserialize(cls, data: dict[str, Any]) -> 'ConfigItem':
        """反序列化配置项"""
        raise NotImplementedError("Subclasses must implement deserialize")


@dataclass
class SliderConfig(ConfigItem):
    """滑动条配置项"""
    min_value: float = 0.0
    max_value: float = 100.0
    step: float = 1.0
    show_value: bool = True
    
    def create_ui_widget(self, on_change_callback: Callable[[str, Any], None]) -> Gtk.Widget:
        """创建滑动条UI控件"""
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        
        # 标签
        label = Gtk.Label(label=self.label, xalign=0)
        label.set_tooltip_text(self.description)
        box.append(label)
        
        # 滑动条
        adjustment = Gtk.Adjustment(
            value=self.value if self.value is not None else self.min_value,
            lower=self.min_value,
            upper=self.max_value,
            step_increment=self.step,
        )
        scale = Gtk.Scale(orientation=Gtk.Orientation.HORIZONTAL, adjustment=adjustment)
        scale.set_draw_value(self.show_value)
        scale.set_value_pos(Gtk.PositionType.RIGHT)
        scale.set_digits(0 if self.step >= 1 else 1)
        scale.set_hexpand(True)
        
        # 连接信号并存储信号ID
        signal_id = scale.connect("value-changed", lambda s: on_change_callback(self.key, s.get_value()))
        # 将信号ID存储到widget中以便后续使用
        setattr(scale, '_config_signal_id', signal_id)
        
        box.append(scale)
        box.set_visible(self.visible)
        return box
    
    def get_value_from_ui(self, widget: Gtk.Widget) -> float:
        """从滑动条获取值"""
        if isinstance(widget, Gtk.Box):
            scale = widget.get_last_child()
            if isinstance(scale, Gtk.Scale):
                return scale.get_value()
        return self.value
    
    def set_value_to_ui(self, widget: Gtk.Widget, value: Any) -> None:
        """设置值到滑动条（不触发信号）"""
        if isinstance(widget, Gtk.Box):
            scale = widget.get_last_child()
            if isinstance(scale, Gtk.Scale):
                # 使用信号ID来阻塞和解除阻塞信号
                signal_id = getattr(scale, '_config_signal_id', None)
                if signal_id is not None:
                    scale.handler_block(signal_id)
                scale.set_value(float(value))
                if signal_id is not None:
                    scale.handler_unblock(signal_id)
    
    def validate(self, value: Any) -> bool:
        """验证值是否在有效范围内"""
        try:
            val = float(value)
            return self.min_value <= val <= self.max_value
        except (ValueError, TypeError):
            return False
    
    def serialize(self) -> dict[str, Any]:
        """序列化滑动条配置"""
        data = super().serialize()
        data.update({
            "min_value": self.min_value,
            "max_value": self.max_value,
            "step": self.step,
            "show_value": self.show_value,
        })
        return data


@dataclass
class DropdownConfig(ConfigItem):
    """下拉选择配置项"""
    options: list[str] = field(default_factory=list)
    option_labels: dict[str, str]|None = None

    def on_dropdown_changed(self, dropdown, pspec, on_change_callback: Callable[[str, Any], None]):
        """下拉框选择改变回调"""
        on_change_callback(self.key, self.options[dropdown.get_selected()] if dropdown.get_selected() < len(self.options) else self.value)
    
    def create_ui_widget(self, on_change_callback: Callable[[str, Any], None]) -> Gtk.Widget:
        """创建下拉选择UI控件"""
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        
        # 标签
        label = Gtk.Label(label=self.label, xalign=0)
        label.set_tooltip_text(self.description)
        box.append(label)
        
        # 下拉框
        dropdown = Gtk.DropDown()
        
        # 创建选项列表
        string_list = Gtk.StringList()
        for option in self.options:
            display_label = (self.option_labels or {}).get(option, option)
            string_list.append(display_label)
        
        dropdown.set_model(string_list)
        
        # 设置当前选择
        if self.value in self.options:
            dropdown.set_selected(self.options.index(self.value))
        
        # 连接信号并存储信号ID
        signal_id = dropdown.connect("notify::selected", self.on_dropdown_changed, on_change_callback)
        setattr(dropdown, '_config_signal_id', signal_id)
        
        dropdown.set_hexpand(True)
        box.append(dropdown)
        box.set_visible(self.visible)
        return box
    
    def get_value_from_ui(self, widget: Gtk.Widget) -> str:
        """从下拉框获取值"""
        if isinstance(widget, Gtk.Box):
            dropdown = widget.get_last_child()
            if isinstance(dropdown, Gtk.DropDown):
                selected = dropdown.get_selected()
                if selected < len(self.options):
                    return self.options[selected]
        return self.value
    
    def set_value_to_ui(self, widget: Gtk.Widget, value: Any) -> None:
        """设置值到下拉框（不触发信号）"""
        if isinstance(widget, Gtk.Box):
            dropdown = widget.get_last_child()
            if isinstance(dropdown, Gtk.DropDown) and value in self.options:
                # 使用信号ID来阻塞和解除阻塞信号
                signal_id = getattr(dropdown, '_config_signal_id', None)
                if signal_id is not None:
                    dropdown.handler_block(signal_id)
                dropdown.set_selected(self.options.index(value))
                if signal_id is not None:
                    dropdown.handler_unblock(signal_id)
    
    def validate(self, value: Any) -> bool:
        """验证值是否在选项列表中"""
        return value in self.options
    
    def serialize(self) -> dict[str, Any]:
        """序列化下拉选择配置"""
        data = super().serialize()
        data.update({
            "options": self.options,
            "option_labels": self.option_labels,
        })
        return data


@dataclass
class TextConfig(ConfigItem):
    """文本输入配置项"""
    placeholder: str = ""
    max_length: int = 0
    
    def create_ui_widget(self, on_change_callback: Callable[[str, Any], None]) -> Gtk.Widget:
        """创建文本输入UI控件"""
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        
        # 标签
        label = Gtk.Label(label=self.label, xalign=0)
        label.set_tooltip_text(self.description)
        box.append(label)
        
        # 文本输入框
        entry = Gtk.Entry()
        entry.set_placeholder_text(self.placeholder)
        if self.max_length > 0:
            entry.set_max_length(self.max_length)
        if self.value:
            entry.set_text(str(self.value))
        
        # 连接信号并存储信号ID
        signal_id = entry.connect("changed", lambda e: on_change_callback(self.key, e.get_text()))
        setattr(entry, '_config_signal_id', signal_id)
        
        entry.set_hexpand(True)
        box.append(entry)
        box.set_visible(self.visible)
        return box
    
    def get_value_from_ui(self, widget: Gtk.Widget) -> str:
        """从文本框获取值"""
        if isinstance(widget, Gtk.Box):
            entry = widget.get_last_child()
            if isinstance(entry, Gtk.Entry):
                return entry.get_text()
        return self.value or ""
    
    def set_value_to_ui(self, widget: Gtk.Widget, value: Any) -> None:
        """设置值到文本框（不触发信号）"""
        if isinstance(widget, Gtk.Box):
            entry = widget.get_last_child()
            if isinstance(entry, Gtk.Entry):
                # 使用信号ID来阻塞和解除阻塞信号
                signal_id = getattr(entry, '_config_signal_id', None)
                if signal_id is not None:
                    entry.handler_block(signal_id)
                entry.set_text(str(value) if value is not None else "")
                if signal_id is not None:
                    entry.handler_unblock(signal_id)
    
    def validate(self, value: Any) -> bool:
        """验证文本长度"""
        try:
            text = str(value)
            return len(text) <= self.max_length if self.max_length > 0 else True
        except:
            return False
    
    def serialize(self) -> dict[str, Any]:
        """序列化文本配置"""
        data = super().serialize()
        data.update({
            "placeholder": self.placeholder,
            "max_length": self.max_length,
        })
        return data


@dataclass
class SwitchConfig(ConfigItem):
    """开关配置项"""
    default_value: bool = False
    
    def create_ui_widget(self, on_change_callback: Callable[[str, Any], None]) -> Gtk.Widget:
        """创建开关UI控件"""
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        
        # 标签
        label = Gtk.Label(label=self.label, xalign=0)
        label.set_tooltip_text(self.description)
        box.append(label)
        
        # 开关
        switch = Gtk.Switch()
        switch.set_active(self.value if self.value is not None else self.default_value)
        switch.set_halign(Gtk.Align.END)
        
        # 连接信号并存储信号ID
        signal_id = switch.connect("state-set", lambda s, state: on_change_callback(self.key, state))
        setattr(switch, '_config_signal_id', signal_id)
        
        box.append(switch)
        box.set_visible(self.visible)
        return box
    
    def get_value_from_ui(self, widget: Gtk.Widget) -> bool:
        """从开关获取值"""
        if isinstance(widget, Gtk.Box):
            switch = widget.get_last_child()
            if isinstance(switch, Gtk.Switch):
                return switch.get_active()
        return self.value if self.value is not None else self.default_value
    
    def set_value_to_ui(self, widget: Gtk.Widget, value: Any) -> None:
        """设置值到开关（不触发信号）"""
        if isinstance(widget, Gtk.Box):
            switch = widget.get_last_child()
            if isinstance(switch, Gtk.Switch):
                # 使用信号ID来阻塞和解除阻塞信号
                signal_id = getattr(switch, '_config_signal_id', None)
                if signal_id is not None:
                    switch.handler_block(signal_id)
                switch.set_active(bool(value))
                if signal_id is not None:
                    switch.handler_unblock(signal_id)
    
    def validate(self, value: Any) -> bool:
        """验证是否为布尔值"""
        return isinstance(value, bool)
    
    def serialize(self) -> dict[str, Any]:
        """序列化开关配置"""
        data = super().serialize()
        data.update({
            "default_value": self.default_value,
        })
        return data


@dataclass
class TextAreaConfig(ConfigItem):
    """多行文本输入配置项"""
    max_length: int = 0
    event_bus: EventBus | None = None
    
    def insert_point(self, widget:Gtk.TextView, event):
        buffer = widget.get_buffer()
        data = event.data
        buffer.insert_at_cursor(f" {data['x']},{data['y']}")

    def create_ui_widget(self, on_change_callback: Callable[[str, Any], None]) -> Gtk.Widget:
        """创建多行文本输入UI控件"""
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        
        # 标签
        label = Gtk.Label(label=self.label, xalign=0)
        label.set_tooltip_text(self.description)
        box.append(label)
        
        # 创建文本视图
        text_view = Gtk.TextView()
        text_view.set_accepts_tab(True)  # 允许输入 tab
        
        # 设置初始文本
        buffer = text_view.get_buffer()
        if self.value:
            buffer.set_text(str(self.value))
        
        # 连接信号并存储信号ID
        def on_text_changed(buffer):
            start, end = buffer.get_bounds()
            text = buffer.get_text(start, end, True)
            on_change_callback(self.key, text)
        
        signal_id = buffer.connect("changed", on_text_changed)
        setattr(text_view, '_config_signal_id', signal_id)
        
        # 创建滚动窗口
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_min_content_height(150)  # 设置最小高度
        scrolled.set_vexpand(True)  # 允许垂直扩展
        scrolled.set_child(text_view)
        
        # 添加到容器
        box.append(scrolled)
        box.set_visible(self.visible)

        self.event_bus.subscribe(event_type=EventType.MASK_CLICKED, handler= lambda event: self.insert_point(text_view, event), subscriber=box)
        return box
    
    def get_value_from_ui(self, widget: Gtk.Widget) -> str:
        """从文本视图获取值"""
        if isinstance(widget, Gtk.Box):
            scrolled = widget.get_last_child()
            if isinstance(scrolled, Gtk.ScrolledWindow):
                text_view = scrolled.get_child()
                if isinstance(text_view, Gtk.TextView):
                    buffer = text_view.get_buffer()
                    start, end = buffer.get_bounds()
                    return buffer.get_text(start, end, True)
        return self.value or ""
    
    def set_value_to_ui(self, widget: Gtk.Widget, value: Any) -> None:
        """设置值到文本视图（不触发信号）"""
        if isinstance(widget, Gtk.Box):
            scrolled = widget.get_last_child()
            if isinstance(scrolled, Gtk.ScrolledWindow):
                text_view = scrolled.get_child()
                if isinstance(text_view, Gtk.TextView):
                    buffer = text_view.get_buffer()
                    # 使用信号ID来阻塞和解除阻塞信号
                    signal_id = getattr(text_view, '_config_signal_id', None)
                    if signal_id is not None:
                        buffer.handler_block(signal_id)
                    buffer.set_text(str(value) if value is not None else "")
                    if signal_id is not None:
                        buffer.handler_unblock(signal_id)
    
    def validate(self, value: Any) -> bool:
        """验证文本长度"""
        try:
            text = str(value)
            return len(text) <= self.max_length if self.max_length > 0 else True
        except:
            return False
    
    def serialize(self) -> dict[str, Any]:
        """序列化文本配置"""
        data = super().serialize()
        data.update({
            "max_length": self.max_length,
        })
        return data


class ConfigManager(GObject.Object):
    """配置管理器，使用GObject信号机制"""
    
    __gsignals__ = {
        'config-changed': (GObject.SignalFlags.RUN_FIRST, None, (str, object)),
        'config-validated': (GObject.SignalFlags.RUN_FIRST, None, (str, bool)),
        'confirmed': (GObject.SignalFlags.RUN_FIRST, None, ()),
    }
    
    def __init__(self, event_bus: EventBus):
        super().__init__()
        self.configs: dict[str, ConfigItem] = {}
        self.ui_widgets: dict[str, Gtk.Widget] = {}
        self._updating_ui = False  # 标记是否正在更新UI，防止循环
        self.restoring = False
        self.event_bus = event_bus
    
    def add_config(self, config: ConfigItem) -> None:
        """添加配置项"""
        self.configs[config.key] = config
    
    def get_config(self, key: str) -> ConfigItem|None:
        """获取配置项"""
        return self.configs.get(key)
    
    def set_value(self, key: str, value: Any, update_ui: bool = True) -> bool:
        """设置配置值"""
        if key not in self.configs:
            return False
        
        config = self.configs[key]
        if not config.validate(value):
            self.emit('config-validated', key, False)
            return False
        
        old_value = config.value
        config.value = value
        
        # 更新UI（如果需要且不在UI更新过程中）
        if update_ui and not self._updating_ui and key in self.ui_widgets:
            self._updating_ui = True
            try:
                config.set_value_to_ui(self.ui_widgets[key], value)
            finally:
                self._updating_ui = False
        
        # 发送配置变更信号
        self.emit('config-changed', key, value)
        self.emit('config-validated', key, True)
        
        return True
    
    def get_value(self, key: str) -> Any:
        """获取配置值"""
        if key in self.configs:
            return self.configs[key].value
        return None
    
    def add_change_callback(self, key: str, callback: Callable[[str, Any, bool], None]) -> None:
        """添加配置变更回调（向后兼容方法）"""
        # 连接到config-changed信号
        def signal_handler(config_manager, changed_key, value ):
            if changed_key == key:
                callback(changed_key, value, self.restoring)
        
        self.connect("config-changed", signal_handler)
    
    def _on_ui_value_changed(self, key: str, value: Any) -> None:
        """UI控件值变更回调"""
        if not self._updating_ui:
            self.set_value(key, value, update_ui=False)
    
    def create_ui_panel(self, parent: Gtk.Widget|None = None) -> Gtk.Widget:
        """创建配置面板UI"""
        if not self.configs:
            label = Gtk.Label(label="No configuration available")
            return label
        
        # 主容器
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=15)
        main_box.set_margin_top(10)
        main_box.set_margin_bottom(10)
        main_box.set_margin_start(10)
        main_box.set_margin_end(10)
        
        # 为每个配置项创建UI
        for key, config in self.configs.items():
            try:
                widget = config.create_ui_widget(self._on_ui_value_changed)
                self.ui_widgets[key] = widget
                main_box.append(widget)
            except Exception as e:
                logger.error(f"Failed to create UI for config {key}: {e}")
        
        return main_box
    
    def collect_values_from_ui(self) -> dict[str, Any]:
        """从UI收集所有配置值"""
        values = {}
        for key, config in self.configs.items():
            if key in self.ui_widgets:
                try:
                    value = config.get_value_from_ui(self.ui_widgets[key])
                    values[key] = value
                except Exception as e:
                    logger.error(f"Failed to get value from UI for config {key}: {e}")
        return values
    
    def serialize(self) -> dict[str, Any]:
        """序列化所有配置"""
        return {
            key: config.serialize() for key, config in self.configs.items()
        }
    
    def deserialize(self, data: dict[str, Any]) -> None:
        """反序列化配置"""
        self.restoring = True
        try:
            for key, config_data in data.items():
                if key in self.configs:
                    value = config_data.get("value")
                    if value is not None:
                        self.set_value(key, value)
                    self.set_visible(key, config_data.get("visible", True))
            self.emit("confirmed")
        finally:
            self.restoring = False
    
    def clear_ui_references(self) -> None:
        """清空UI控件引用，防止内存泄漏"""
        for _, w in self.ui_widgets.items():
            self.event_bus.unsubscribe_by_subscriber(w)
            w.unparent()
        self.ui_widgets.clear()

    def clear(self) -> None:
        """清空所有配置"""
        for _, w in self.ui_widgets.items():
            w.unparent()
        self.configs.clear()
        self.ui_widgets.clear()
    
    def set_visible(self, key: str, visible: bool) -> None:
        """设置配置项的可见性"""
        if key in self.configs:
            self.configs[key].visible = visible
            if key in self.ui_widgets:
                self.ui_widgets[key].set_visible(visible)


# 配置项工厂函数，方便创建常用配置项
def create_slider_config(key: str, label: str, value: float = 0.0, 
                        min_value: float = 0.0, max_value: float = 100.0, 
                        step: float = 1.0, description: str = "",
                        visible: bool = True) -> SliderConfig:
    """创建滑动条配置项"""
    return SliderConfig(
        key=key, label=label, value=value, description=description,
        min_value=min_value, max_value=max_value, step=step, visible=visible
    )


def create_dropdown_config(key: str, label: str, options: list[str], 
                          value: str|None = None, option_labels: dict[str, str]|None = None,
                          description: str = "", visible: bool = True) -> DropdownConfig:
    """创建下拉选择配置项"""
    return DropdownConfig(
        key=key, label=label, value=value or (options[0] if options else ""),
        description=description, options=options, option_labels=option_labels, visible=visible
    )


def create_text_config(key: str, label: str, value: str = "", 
                      placeholder: str = "", max_length: int = 0,
                      description: str = "", visible: bool = True) -> TextConfig:
    """创建文本输入配置项"""
    return TextConfig(
        key=key, label=label, value=value, description=description,
        placeholder=placeholder, max_length=max_length, visible=visible
    )


def create_switch_config(key: str, label: str, value: bool = False,
                        description: str = "", visible: bool = True) -> SwitchConfig:
    """创建开关配置项"""
    return SwitchConfig(
        key=key, label=label, value=value, description=description, visible=visible
    ) 


def create_textarea_config(
    key: str,
    label: str,
    value: str = "",
    description: str = "",
    max_length: int = 0,
    visible: bool = True,
    event_bus: EventBus | None = None,
) -> TextAreaConfig:
    """创建多行文本输入配置项"""
    return TextAreaConfig(
        key=key,
        label=label,
        value=value,
        description=description,
        max_length=max_length,
        event_bus=event_bus,
    ) 