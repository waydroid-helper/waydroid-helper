#!/usr/bin/env python3
"""
动态菜单管理
根据发现的组件自动生成菜单项
"""

from __future__ import annotations

import json
import os
from gettext import gettext as _
from pathlib import Path
from typing import TYPE_CHECKING, Any

import gi
from gi.repository import Gdk, Gtk, GLib

from waydroid_helper.controller.core.control_msg import ScreenInfo
from waydroid_helper.controller.core.key_system import Key, KeyCombination, KeyRegistry
from waydroid_helper.util.log import logger
from waydroid_helper.compat_widget.file_dialog import FileDialog
from waydroid_helper.controller.widgets.base import BaseWidget

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

if TYPE_CHECKING:
    from waydroid_helper.controller.app.window import TransparentWindow
    from waydroid_helper.controller.widgets.factory import WidgetFactory


class ContextMenuManager:
    """动态上下文菜单管理器"""

    def __init__(self, parent_window: "TransparentWindow"):
        self.parent_window: "TransparentWindow" = parent_window
        self._popover: "Gtk.Popover | None" = None
        self._main_box: "Gtk.Box | None" = None
        self._flow_box: "Gtk.FlowBox | None" = None
        self._tool_flow: "Gtk.FlowBox | None" = None
        self.screen_info = ScreenInfo()

    def show_widget_creation_menu(
        self, x: int, y: int, widget_factory: "WidgetFactory"
    ):
        """显示动态生成的组件创建菜单（网格布局）"""
        # 如果 popover 不存在，创建一个新的
        if self._popover is None:
            self._create_popover()

        # 更新菜单内容
        self._update_menu_content(x, y, widget_factory)

        # 设置菜单位置
        rect = Gdk.Rectangle()
        # https://gitlab.gnome.org/GNOME/gtk/-/issues/4563#note_1711746
        rect.x = int(x)
        rect.y = int(y)
        rect.width = 1
        rect.height = 1
        self._popover.set_pointing_to(rect)
        self._popover.popup()

    def _create_popover(self):
        """创建可复用的 popover 结构"""
        self._popover = Gtk.Popover()
        self._popover.set_parent(self.parent_window)
        self._popover.set_has_arrow(False)
        self._popover.set_autohide(True)

        # 创建主容器
        self._main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._popover.set_child(self._main_box)

        # 创建滚动窗口
        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_max_content_height(300)  # 限制最大高度
        scrolled.set_max_content_width(400)  # 限制最大宽度
        scrolled.set_propagate_natural_height(True)
        scrolled.set_propagate_natural_width(True)
        self._main_box.append(scrolled)

        # 创建网格容器
        self._flow_box = Gtk.FlowBox()
        self._flow_box.set_orientation(Gtk.Orientation.HORIZONTAL)
        self._flow_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self._flow_box.set_column_spacing(4)
        self._flow_box.set_row_spacing(4)
        self._flow_box.set_margin_top(8)
        self._flow_box.set_margin_bottom(8)
        self._flow_box.set_margin_start(8)
        self._flow_box.set_margin_end(8)
        self._flow_box.set_min_children_per_line(2)
        self._flow_box.set_max_children_per_line(4)  # 最多4列
        scrolled.set_child(self._flow_box)

        # 添加分隔线
        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        separator.set_margin_top(4)
        separator.set_margin_bottom(4)
        self._main_box.append(separator)

        # 创建工具菜单容器
        tool_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        tool_box.set_margin_top(4)
        tool_box.set_margin_bottom(8)
        tool_box.set_margin_start(8)
        tool_box.set_margin_end(8)
        self._main_box.append(tool_box)

        # 创建工具按钮的网格
        self._tool_flow = Gtk.FlowBox()
        self._tool_flow.set_orientation(Gtk.Orientation.HORIZONTAL)
        self._tool_flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self._tool_flow.set_column_spacing(4)
        self._tool_flow.set_row_spacing(4)
        self._tool_flow.set_min_children_per_line(3)
        self._tool_flow.set_max_children_per_line(5)
        tool_box.append(self._tool_flow)

    def _clear_flow_box(self, flow_box: "Gtk.FlowBox | None"):
        """清空 FlowBox 中的所有子组件"""
        if flow_box is None:
            return
        child = flow_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            flow_box.remove(child)
            child = next_child

    def _update_menu_content(self, x: int, y: int, widget_factory: "WidgetFactory"):
        """更新菜单内容"""
        # 清空现有内容
        self._clear_flow_box(self._flow_box)
        self._clear_flow_box(self._tool_flow)

        # 确保组件已初始化
        if self._flow_box is None or self._tool_flow is None or self._popover is None:
            return

        # 动态生成组件菜单项
        available_types = widget_factory.get_available_types()

        # 过滤掉不允许通过右键菜单创建的组件
        filtered_types = []
        for widget_type in available_types:
            widget_class = widget_factory.widget_classes.get(widget_type)
            if widget_class and getattr(
                widget_class, "ALLOW_CONTEXT_MENU_CREATION", True
            ):
                filtered_types.append(widget_type)

        if not filtered_types:
            # 如果没有发现任何可创建的组件，显示提示
            label = Gtk.Label(label=_("No widgets found"))
            label.set_margin_top(20)
            label.set_margin_bottom(20)
            self._flow_box.append(label)
        else:
            # 为每个发现的组件类型创建紧凑的按钮
            for widget_type in sorted(filtered_types):
                metadata = widget_factory.get_widget_metadata(widget_type)

                # 使用metadata中的名称，如果没有则使用类型名
                display_name = metadata.get("name", widget_type.title())

                # 创建紧凑的按钮
                button = Gtk.Button(label=str(display_name))
                button.set_size_request(100, 40)  # 固定大小，更紧凑
                button.connect(
                    "clicked",
                    lambda btn, wtype=widget_type: [
                        self._create_widget_callback(wtype, x, y, widget_factory),
                        self._popover.popdown(),
                    ],
                )

                # 添加到网格
                self._flow_box.append(button)

        # 添加工具菜单项（使用更紧凑的布局）
        tool_items = [
            (_("Refresh widgets"), lambda: self._refresh_widgets(widget_factory)),
            # (_("Show widget info"), lambda: self._show_widget_info(widget_factory)),
            (_("Clear all"), lambda: self._clear_all_widgets()),
            (_("Save layout"), lambda: self._save_layout()),
            (_("Load layout"), lambda: self._load_layout(widget_factory)),
        ]

        for label, callback in tool_items:
            button = Gtk.Button(label=label)
            button.set_size_request(70, 35)  # 更小的工具按钮
            button.connect(
                "clicked", lambda btn, cb=callback: [cb(), self._popover.popdown()]
            )
            self._tool_flow.append(button)

    def _create_widget_callback(
        self, widget_type: str, x: int, y: int, widget_factory: "WidgetFactory"
    ):
        """创建组件的回调函数"""
        try:
            widget = widget_factory.create_widget(
                widget_type,
                x=x,
                y=y,
                event_bus=self.parent_window.event_bus,
                pointer_id_manager=self.parent_window.pointer_id_manager,
                key_registry=self.parent_window.key_registry,
            )
            if widget:
                self.parent_window.create_widget_at_position(widget, x, y)
        except Exception as e:
            logger.error(f"Error creating {widget_type} widget: {e}")

    def _refresh_widgets(self, widget_factory: "WidgetFactory"):
        """刷新组件列表"""
        widget_factory.reload_widgets()
        widget_factory.print_discovered_widgets()

    def _show_widget_info(self, widget_factory: "WidgetFactory"):
        """显示组件信息"""
        widget_factory.print_discovered_widgets()

    def _clear_all_widgets(self):
        """清空所有组件"""
        self.parent_window.on_clear_widgets(None)

    def _get_available_screen_size(self):
        return self.screen_info.get_host_resolution()

    def _serialize_key_combination(self, key_combination: KeyCombination) -> list[str]:
        """序列化按键组合为字符串列表"""
        if not key_combination:
            return []
        return [str(key) for key in key_combination.keys]

    def _deserialize_key_combination(
        self, key_names: list[str]
    ) -> "KeyCombination | None":
        """从字符串列表反序列化按键组合"""
        keys: list[Key] = []
        for key_name in key_names:
            key = self.parent_window.key_registry.deserialize_key(key_name)
            if key:
                keys.append(key)
        return KeyCombination(keys) if keys else None

    # TODO 在每个 widget 内部单独实现序列化/反序列化
    def _get_default_layouts_dir(self) -> str:
        """获取默认的布局文件目录"""
        # 使用 XDG 配置目录标准：~/.config/waydroid-helper/layouts/
        config_dir = os.getenv("XDG_CONFIG_HOME", GLib.get_user_config_dir())
        layouts_dir = os.path.join(config_dir, "waydroid-helper", "layouts")

        # 确保目录存在
        os.makedirs(layouts_dir, exist_ok=True)

        return layouts_dir

    def _save_layout(self):
        """保存当前布局到文件，包括屏幕尺寸信息"""
        # 创建文件过滤器，只显示 JSON 文件
        json_filter = Gtk.FileFilter()
        json_filter.set_name(_("JSON files"))
        json_filter.add_pattern("*.json")

        # 创建文件对话框
        dialog = FileDialog(
            parent=self.parent_window, title=_("Save Layout"), modal=True
        )

        # 设置默认目录
        default_dir = self._get_default_layouts_dir()

        # 显示保存对话框
        dialog.save_file(
            callback=self._on_save_layout_file_selected,
            suggested_name="layout.json",
            file_filter=json_filter,
            initial_folder=default_dir,
        )

    def _on_save_layout_file_selected(self, success: bool, file_path: str | None):
        """处理保存文件选择的回调"""
        if not success or not file_path:
            return

        try:
            # 获取当前屏幕尺寸
            screen_width, screen_height = self._get_available_screen_size()

            # 收集所有widget的信息
            widgets_data = []
            if hasattr(self.parent_window, "fixed"):
                child: "BaseWidget | None" = self.parent_window.fixed.get_first_child()
                while child:
                    # 获取widget的位置
                    x, y = child.x, child.y

                    # 获取widget的尺寸
                    width = child.width
                    height = child.height

                    # 获取widget类型
                    widget_type = type(child).__name__.lower()

                    # 创建widget数据
                    widget_data: dict[str, Any] = {
                        "type": widget_type,
                        "x": float(x),
                        "y": float(y),
                        "width": float(width),
                        "height": float(height),
                    }

                    # 如果widget有text属性，也保存
                    if hasattr(child, "text") and child.text:
                        widget_data["text"] = str(child.text)

                    # 保存按键映射 - 根据组件类型处理
                    if widget_type == "directionalpad":
                        # DirectionalPad 有四个方向的按键
                        if hasattr(child, "direction_keys") and child.direction_keys:
                            widget_data["direction_keys"] = {
                                "up": self._serialize_key_combination(
                                    child.direction_keys["up"]
                                ),
                                "down": self._serialize_key_combination(
                                    child.direction_keys["down"]
                                ),
                                "left": self._serialize_key_combination(
                                    child.direction_keys["left"]
                                ),
                                "right": self._serialize_key_combination(
                                    child.direction_keys["right"]
                                ),
                            }
                    else:
                        # 其他组件的通用按键映射
                        if hasattr(child, "final_keys") and child.final_keys:
                            widget_data["default_keys"] = [
                                self._serialize_key_combination(kc)
                                for kc in child.final_keys
                            ]

                    # 保存组件配置
                    if hasattr(child, "get_config_manager"):
                        config_manager = child.get_config_manager()
                        if config_manager.configs:
                            widget_data["config"] = config_manager.serialize()

                    widgets_data.append(widget_data)
                    child = child.get_next_sibling()

            # 创建完整的布局数据，包括屏幕尺寸信息
            layout_data = {
                "version": BaseWidget.WIDGET_VERSION,  # 增加版本号
                "screen_resolution": {"width": screen_width, "height": screen_height},
                "widgets": widgets_data,
                "created_at": str(Path().absolute()),  # 保存创建时间戳
            }

            # 保存到文件
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(layout_data, f, indent=2, ensure_ascii=False)

        except Exception as e:
            logger.error(f"Failed to save layout: {e}")

    def _load_layout(self, widget_factory: "WidgetFactory"):
        """从文件加载布局，支持屏幕尺寸缩放适配"""
        # 创建文件过滤器，只显示 JSON 文件
        json_filter = Gtk.FileFilter()
        json_filter.set_name(_("JSON files"))
        json_filter.add_pattern("*.json")

        # 创建文件对话框
        dialog = FileDialog(
            parent=self.parent_window, title=_("Load Layout"), modal=True
        )

        # 设置默认目录
        default_dir = self._get_default_layouts_dir()

        # 显示打开对话框
        dialog.open_file(
            callback=lambda success, path: self._on_load_layout_file_selected(
                success, path, widget_factory
            ),
            file_filter=json_filter,
            initial_folder=default_dir,
        )

    def _on_load_layout_file_selected(
        self, success: bool, file_path: str | None, widget_factory: "WidgetFactory"
    ):
        """处理加载文件选择的回调"""
        if not success or not file_path:
            return

        try:
            # 检查文件是否存在
            if not Path(file_path).exists():
                return

            # 读取布局文件
            with open(file_path, "r", encoding="utf-8") as f:
                layout_data = json.load(f)

            # 验证布局数据
            if "widgets" not in layout_data:
                logger.error("Invalid layout file format")
                return
            
            if layout_data.get("version") != BaseWidget.WIDGET_VERSION:
                logger.warning(f"Layout file version mismatch: {layout_data.get('version')} != {BaseWidget.WIDGET_VERSION}")

            # 获取当前屏幕尺寸
            current_screen_width, current_screen_height = (
                self._get_available_screen_size()
            )

            # 计算缩放比例
            scale_x = 1.0
            scale_y = 1.0
            saved_resolution = layout_data.get("screen_resolution")

            if saved_resolution:
                saved_width = saved_resolution.get("width", current_screen_width)
                saved_height = saved_resolution.get("height", current_screen_height)
                scale_x = current_screen_width / saved_width
                scale_y = current_screen_height / saved_height

            # 清空现有组件
            if hasattr(self.parent_window, "on_clear_widgets"):
                self.parent_window.on_clear_widgets(None)

            # 重新创建组件
            widgets_created = 0
            for widget_data in layout_data["widgets"]:
                try:
                    # 获取基本信息
                    widget_type = widget_data.get("type", "")
                    original_x = widget_data.get("x", 0)
                    original_y = widget_data.get("y", 0)
                    original_width = widget_data.get("width", 100)
                    original_height = widget_data.get("height", 100)
                    text = widget_data.get("text", "")

                    # 应用缩放比例
                    x = int(original_x * scale_x)
                    y = int(original_y * scale_y)
                    width = int(original_width * scale_x)
                    height = int(original_height * scale_y)

                    # 根据组件类型准备参数
                    create_kwargs = {
                        "width": width,
                        "height": height,
                        "text": text,
                        "event_bus": self.parent_window.event_bus,
                        "pointer_id_manager": self.parent_window.pointer_id_manager,
                        "key_registry": self.parent_window.key_registry,
                    }

                    # 添加按键映射参数
                    if widget_type == "directionalpad":
                        if "direction_keys" in widget_data:
                            create_kwargs["direction_keys"] = {
                                "up": self._deserialize_key_combination(
                                    widget_data["direction_keys"]["up"]
                                ),
                                "down": self._deserialize_key_combination(
                                    widget_data["direction_keys"]["down"]
                                ),
                                "left": self._deserialize_key_combination(
                                    widget_data["direction_keys"]["left"]
                                ),
                                "right": self._deserialize_key_combination(
                                    widget_data["direction_keys"]["right"]
                                ),
                            }
                    else:
                        # 其他组件的通用按键
                        default_keys = []
                        if "default_keys" in widget_data:
                            for key_names in widget_data["default_keys"]:
                                key_combo = self._deserialize_key_combination(key_names)
                                if key_combo:
                                    default_keys.append(key_combo)
                        create_kwargs["default_keys"] = default_keys

                    # 创建widget
                    widget = widget_factory.create_widget(widget_type, **create_kwargs)

                    if widget:
                        # 在缩放后的位置创建widget
                        if hasattr(self.parent_window, "create_widget_at_position"):
                            self.parent_window.create_widget_at_position(widget, x, y)

                            # 恢复配置
                            if "config" in widget_data and hasattr(
                                widget, "get_config_manager"
                            ):
                                config_manager = widget.get_config_manager()
                                config_manager.deserialize(widget_data["config"])

                            widgets_created += 1

                except Exception as e:
                    logger.error(f"Failed to create widget: {e}")
                    continue
        except Exception as e:
            logger.error(f"Failed to load layout: {e}")
