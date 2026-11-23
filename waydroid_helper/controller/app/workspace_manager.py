#!/usr/bin/env python3
"""
工作区管理器
负责处理所有在编辑模式下的UI交互，例如拖拽、选择、缩放、删除等。
"""

from __future__ import annotations

from typing import Any, Protocol

from waydroid_helper.controller.app import widget_capabilities as capabilities
from waydroid_helper.controller.core.event_bus import Event, EventBus, EventType
from waydroid_helper.controller.core.utils import is_point_in_rect
from waydroid_helper.controller.widgets.decorators.resize_geometry import ResizeGeometryCalculator
from waydroid_helper.util.log import logger


class WorkspaceHost(Protocol):
    """Window operations required by workspace interaction management.

    WorkspaceManager owns selection, dragging, resizing, and deletion state. It
    depends on this narrow host contract instead of the concrete controller
    window, keeping unrelated window services outside the workspace boundary.
    """

    def create_widget_at_position(self, widget: Any, x: int, y: int) -> None: ...

    def unregister_widget_key_mapping(self, widget: Any) -> bool: ...

    def fixed_put(self, widget: Any, x: int, y: int) -> None: ...

    def fixed_move(self, widget: Any, x: int, y: int) -> None: ...


class WorkspaceManager:
    """处理编辑模式下的所有UI交互"""

    _RESIZE_CURSORS = {
        "n": "ns-resize", "s": "ns-resize",
        "w": "ew-resize", "e": "ew-resize",
        "nw": "nwse-resize", "se": "nwse-resize",
        "ne": "nesw-resize", "sw": "nesw-resize",
    }

    def __init__(
        self,
        host: WorkspaceHost,
        fixed_container,
        event_bus: EventBus,
    ):
        self.host = host
        self.fixed = fixed_container
        self.event_bus = event_bus
        self._cursor_name: str | None = None

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

        self.host.create_widget_at_position(widget, x, y)

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
                    self.handle_widget_drag(x, y)

        self._update_cursor(x, y)

    def _update_cursor(self, x, y):
        # The editor uses the desktop arrow for ordinary hover and movement.
        # Only painted handles advertise resizing. Once a resize begins, keep
        # its axis even if the pointer moves past the edge of the control.
        direction = self.resize_direction
        if direction is None and self.dragging_widget is None:
            widget = self.get_widget_at_position(x, y)
            if (
                capabilities.is_selected(widget)
                and isinstance(widget, capabilities.ResizableWidget)
                and widget.supports_resizing()
            ):
                local_x, local_y = self.global_to_local_coords(widget, x, y)
                direction = ResizeGeometryCalculator.handle_at(
                    local_x, local_y, widget.get_allocated_width(), widget.get_allocated_height()
                )
        self._set_resize_cursor(direction)

    def _set_resize_cursor(self, direction):
        name = self._RESIZE_CURSORS.get(direction)
        if name != self._cursor_name:
            self.fixed.set_cursor_from_name(name)
            self._cursor_name = name

    def handle_pointer_release(self, x=None, y=None):
        """处理编辑模式下的指针释放事件"""
        if self.resizing_widget:
            capabilities.notify_resize_release(self.resizing_widget)

        elif self.dragging_widget is None and self.selected_widget and x is not None:
            widget = self.selected_widget
            if (capabilities.supports_editing_interaction(widget)
                    and abs(x - self.interaction_start_x) <= 5
                    and abs(y - self.interaction_start_y) <= 5):
                from waydroid_helper.controller.widgets.base.decorator_contracts import EditableWidgetBehavior
                behavior = widget.get_widget_behavior(EditableWidgetBehavior)
                local = self.global_to_local_coords(widget, x, y)
                if behavior:
                    behavior.capture_at(*local)
        self.clear_interaction_state()
        if x is not None and y is not None:
            self._update_cursor(x, y)

    def handle_widget_interaction(self, widget, x, y, n_press=1):
        """Select the control and defer capture until a stationary release."""
        
        local_x, local_y = self.global_to_local_coords(widget, x, y)
        
        self.clear_all_selections(exclude_widget=widget)
        capabilities.set_selected(widget, True)
        if widget.get_parent() is not self.fixed:
            return
        # Reorder siblings without unparenting. Removing the pressed GTK widget
        # here cancels its gesture sequence and loses its key capture focus.
        if hasattr(widget, "insert_after") and widget.get_next_sibling():
            widget.insert_after(self.fixed, self.fixed.get_last_child())

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
                if not hasattr(child, "contains") or child.contains(x - child_x, y - child_y):
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
        if capabilities.supports_editing_interaction(widget):
            widget.cancel_editing()

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
            window_width = self.fixed.get_allocated_width()
            window_height = self.fixed.get_allocated_height()
            
            new_x = max(0, min(new_x, window_width - widget_bounds[2]))
            new_y = max(0, min(new_y, window_height - widget_bounds[3]))
        
        self.host.fixed_move(self.dragging_widget, new_x, new_y)
        
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
            self.host.unregister_widget_key_mapping(widget)
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
        self._set_resize_cursor(None)
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
