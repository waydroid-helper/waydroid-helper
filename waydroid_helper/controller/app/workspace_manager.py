#!/usr/bin/env python3
"""
工作区管理器
负责处理所有在编辑模式下的UI交互，例如拖拽、选择、缩放、删除等。
"""

from __future__ import annotations

from typing import Any

import gi

gi.require_version("Gdk", "4.0")
from gi.repository import Gdk, GLib

from waydroid_helper.controller.app import widget_capabilities as capabilities
from waydroid_helper.controller.core.event_bus import Event, EventBus, EventType
from waydroid_helper.controller.core.utils import is_point_in_rect
from waydroid_helper.util.log import logger


class WorkspaceManager:
    """处理编辑模式下的所有UI交互"""

    def __init__(self, window, fixed_container, event_bus: EventBus):
        self.window = window
        self.fixed = fixed_container
        self.event_bus = event_bus

        # 初始化拖拽和调整大小状态
        self.dragging_widget = None
        self.resizing_widget = None
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.resize_start_x = 0
        self.resize_start_y = 0
        self.resize_direction = None
        
        # 初始化交互状态
        self.selected_widget = None
        self.interaction_start_x = 0
        self.interaction_start_y = 0
        self.pending_resize_direction = None
        self.event_bus.subscribe(
            EventType.CREATE_WIDGET,
            self._on_create_widget_requested,
            subscriber=self,
        )
        self.event_bus.subscribe(
            EventType.DELETE_WIDGET,
            self._on_delete_widget_requested,
            subscriber=self,
        )

    def _on_create_widget_requested(self, event: Event[dict[str, Any]]):
        """Create-widget event adapter with payload validation."""
        if not isinstance(event.data, dict):
            logger.error("Invalid CREATE_WIDGET payload: %r", event.data)
            return

        try:
            widget = event.data["widget"]
            x = event.data["x"]
            y = event.data["y"]
        except KeyError as exc:
            logger.error("CREATE_WIDGET payload missing field: %s", exc)
            return

        self.window.create_widget_at_position(widget, x, y)

    def _on_delete_widget_requested(self, event: Event[Any]):
        """Delete-widget event adapter with payload validation."""
        if event.data is None:
            logger.error("Invalid DELETE_WIDGET payload: None")
            return

        self.delete_specific_widget(event.data)

    def handle_primary_press(self, n_press, x, y):
        """处理编辑模式下的主键按下事件"""
        widget_at_position = self.get_widget_at_position(x, y)

        if not widget_at_position:
            self.clear_all_selections()
            return

        self.handle_widget_interaction(widget_at_position, x, y, n_press)

    def handle_pointer_motion(self, x, y):
        """处理编辑模式下的指针移动事件"""

        if self.dragging_widget:
            self.handle_widget_drag(x, y)
        elif self.resizing_widget:
            self.handle_widget_resize(x, y)
        elif self.selected_widget:
            # 检查是否应该开始拖拽或调整大小
            dx = abs(x - self.interaction_start_x)
            dy = abs(y - self.interaction_start_y)
            
            # 只有移动超过阈值才开始拖拽/调整大小
            if dx > 5 or dy > 5:  # 5像素的拖拽阈值
                if self.pending_resize_direction:
                    self.start_widget_resize(self.selected_widget, self.interaction_start_x, self.interaction_start_y, self.pending_resize_direction)
                else:
                    self.start_widget_drag(self.selected_widget, self.interaction_start_x, self.interaction_start_y)

        # 更新鼠标指针样式
        widget_at_position = self.get_widget_at_position(x, y)
        if widget_at_position:
            local_x, local_y = self.global_to_local_coords(widget_at_position, x, y)

            # 检查是否有调整大小功能
            resize_direction = capabilities.check_resize_direction(
                widget_at_position, local_x, local_y
            )
            if resize_direction:
                cursor_name = self.get_cursor_name_for_resize_direction(resize_direction)
                self.set_cursor_from_name(cursor_name)
                return

            # 默认鼠标指针（可拖拽）
            self.set_cursor_from_name("grab")
        else:
            # 空白区域，默认指针
            self.set_cursor_from_name("default")

    def handle_pointer_release(self):
        """处理编辑模式下的指针释放事件"""
        if self.resizing_widget:
            capabilities.notify_resize_release(self.resizing_widget)

        self.clear_interaction_state()

    def handle_widget_interaction(self, widget, x, y, n_press=1):
        """处理widget交互 - 支持双击检测"""
        
        local_x, local_y = self.global_to_local_coords(widget, x, y)
        
        should_keep_editing = capabilities.should_keep_editing_on_click(
            widget, local_x, local_y
        )
        
        if should_keep_editing:
            capabilities.mark_skip_delayed_bring_to_front(widget)
            return
        
        self.clear_all_selections(exclude_widget=widget)
        capabilities.set_selected(widget, True)
        
        capabilities.clear_skip_delayed_bring_to_front(widget)
        
        self.schedule_bring_to_front(widget)
        
        local_x, local_y = self.global_to_local_coords(widget, x, y)
        
        if n_press == 2:
            capabilities.mark_skip_delayed_bring_to_front(widget)
            capabilities.notify_double_click(widget, local_x, local_y)
            return
        
        self.selected_widget = widget
        self.interaction_start_x = x
        self.interaction_start_y = y
        
        resize_direction = capabilities.check_resize_direction(widget, local_x, local_y)
        if resize_direction:
            if capabilities.supports_editing_interaction(widget):
                self.clear_all_selections(reset_interaction=False)
                capabilities.set_selected(widget, True)

            self.pending_resize_direction = resize_direction
            return
        
        self.pending_resize_direction = None
        
        capabilities.notify_click(widget, local_x, local_y)

    def get_widget_at_position(self, x, y):
        """获取指定位置的组件"""
        matched_child = None
        for child in self.iter_widgets():
            child_x, child_y = self.fixed.get_child_position(child)
            child_width = child.get_allocated_width()
            child_height = child.get_allocated_height()
            
            if is_point_in_rect(x, y, child_x, child_y, child_width, child_height):
                matched_child = child
            
        return matched_child

    def iter_widgets(self):
        """Iterate workspace children in GTK sibling order."""
        child = self.fixed.get_first_child()
        while child:
            yield child
            child = child.get_next_sibling()

    def global_to_local_coords(self, widget, global_x, global_y):
        """将全局坐标转换为widget内部坐标"""
        widget_x, widget_y = self.fixed.get_child_position(widget)
        return global_x - widget_x, global_y - widget_y

    def start_widget_drag(self, widget, x, y):
        """开始拖拽widget"""
        self.dragging_widget = widget
        self.drag_start_x = x
        self.drag_start_y = y
        self.bring_widget_to_front_safe(widget)

    def handle_widget_drag(self, x, y):
        """处理widget拖拽"""
        if not self.dragging_widget:
            return
            
        dx = x - self.drag_start_x
        dy = y - self.drag_start_y
        
        current_x, current_y = self.fixed.get_child_position(self.dragging_widget)
        new_x = current_x + dx
        new_y = current_y + dy
        
        widget_bounds = capabilities.get_widget_bounds(self.dragging_widget)
        if widget_bounds:
            window_width = self.window.get_allocated_width()
            window_height = self.window.get_allocated_height()
            
            new_x = max(0, min(new_x, window_width - widget_bounds[2]))
            new_y = max(0, min(new_y, window_height - widget_bounds[3]))
        
        self.window.fixed_move(self.dragging_widget, new_x, new_y)
        
        self.drag_start_x = x
        self.drag_start_y = y

    def start_widget_resize(self, widget, x, y, direction):
        """开始调整widget大小"""
        self.resizing_widget = widget
        self.resize_start_x = x
        self.resize_start_y = y
        self.resize_direction = direction
        
        local_x, local_y = self.global_to_local_coords(widget, x, y)
        capabilities.start_resize(widget, local_x, local_y, direction)

    def handle_widget_resize(self, x, y):
        """处理widget调整大小"""
        if not self.resizing_widget:
            return

        capabilities.handle_resize_motion(self.resizing_widget, x, y)

    def clear_all_selections(self, exclude_widget=None, reset_interaction: bool = True):
        """取消所有组件的选择状态"""
        for child in self.iter_widgets():
            if child != exclude_widget:
                capabilities.set_selected(child, False)

        if reset_interaction:
            self.clear_interaction_state()

    def delete_specific_widget(self, widget):
        """删除特定的widget"""
        if widget and widget.get_parent() == self.fixed:
            self.window.unregister_widget_key_mapping(widget)
            self.fixed.remove(widget)
            
            # 如果删除的是当前正在操作的widget，清除状态
            if self.dragging_widget == widget:
                self.dragging_widget = None
            if self.resizing_widget == widget:
                self.resizing_widget = None
            if self.selected_widget == widget:
                self.selected_widget = None
            capabilities.notify_delete(widget)

    def cleanup(self):
        """清理WorkspaceManager的资源，包括事件订阅"""
        self.event_bus.unsubscribe_by_subscriber(self)

        self.clear_interaction_state()

    def clear_interaction_state(self):
        """Reset transient pointer state owned by the workspace manager."""
        self.dragging_widget = None
        self.resizing_widget = None
        self.selected_widget = None
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.resize_start_x = 0
        self.resize_start_y = 0
        self.resize_direction = None
        self.interaction_start_x = 0
        self.interaction_start_y = 0
        self.pending_resize_direction = None

    def delete_selected_widgets(self):
        """删除所有选中的widget"""
        widgets_to_delete = [
            child for child in self.iter_widgets()
            if capabilities.is_selected(child)
        ]

        for widget in widgets_to_delete:
            self.delete_specific_widget(widget)

        self.clear_interaction_state()

    def bring_widget_to_front_safe(self, widget):
        """安全地将widget置于最前 - 只在拖拽时使用"""
        try:
            x, y = self.fixed.get_child_position(widget)
            self.fixed.remove(widget)
            self.window.fixed_put(widget, x, y)
            self.dragging_widget = widget
        except Exception as e:
            logger.error(f"Error bringing widget to front safely: {e}")
    
    def schedule_bring_to_front(self, widget):
        """延迟置顶 - 避免立即操作导致的状态问题"""
        GLib.idle_add(self._delayed_bring_to_front, widget)

    def _delayed_bring_to_front(self, widget):
        """延迟执行的置顶操作"""
        try:
            if capabilities.should_skip_delayed_bring_to_front(widget):
                capabilities.clear_skip_delayed_bring_to_front(widget)
                return False
            
            if not widget.get_parent() or widget.get_parent() != self.fixed:
                return False
                
            x, y = self.fixed.get_child_position(widget)
            
            selected_state = capabilities.is_selected(widget)
            
            self.fixed.remove(widget)
            self.window.fixed_put(widget, x, y)
            
            current_state = capabilities.is_selected(widget)
            if current_state != selected_state:
                capabilities.set_selected(widget, selected_state)
        except Exception as e:
            logger.error(f"Error during delayed bring to front: {e}")
        
        return False

    def get_cursor_name_for_resize_direction(self, direction):
        """根据调整大小方向获取鼠标指针名称"""
        cursor_map = {
            'se': 'se-resize', 'sw': 'sw-resize', 'ne': 'ne-resize',
            'nw': 'nw-resize', 'e': 'e-resize', 'w': 'w-resize',
            's': 's-resize', 'n': 'n-resize'
        }
        return cursor_map.get(direction, 'default')

    def set_cursor_from_name(self, cursor_name):
        """根据名称设置鼠标指针"""
        try:
            cursor = Gdk.Cursor.new_from_name(cursor_name)
            self.window.set_cursor(cursor)
        except Exception as e:
            logger.error(f"Failed to set cursor: {cursor_name}, error: {e}")
            try:
                cursor = Gdk.Cursor.new_from_name("default")
                self.window.set_cursor(cursor)
            except Exception:
                logger.exception("Failed to reset cursor to default")
