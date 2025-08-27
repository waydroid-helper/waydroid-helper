#!/usr/bin/env python3
"""
工作区管理器
负责处理所有在编辑模式下的UI交互，例如拖拽、选择、缩放、删除等。
"""

from gi.repository import Gdk, GLib

from waydroid_helper.controller.core import (EventType, EventBus,
                                             is_point_in_rect)
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
        self.event_bus.subscribe(EventType.CREATE_WIDGET, lambda event: self.window.create_widget_at_position(event.data['widget'], event.data['x'], event.data['y']), subscriber=self)
        self.event_bus.subscribe(EventType.DELETE_WIDGET, lambda event: self.delete_specific_widget(event.data), subscriber=self)

    def handle_mouse_press(self, controller, n_press, x, y):
        """处理鼠标按下事件"""
        button = controller.get_current_button()
        
        # 右键逻辑保持在 window 中，因为它涉及菜单创建，属于窗口功能
        if button == Gdk.BUTTON_PRIMARY:  # 左键
            widget_at_position = self.get_widget_at_position(x, y)
            
            if not widget_at_position:
                # 点击空白区域，取消所有选择
                self.clear_all_selections()
            else:
                # 点击widget，处理选择、拖拽或调整大小
                self.handle_widget_interaction(widget_at_position, x, y, n_press)

    def handle_mouse_motion(self, controller, x, y):
        """处理鼠标移动事件"""
        # 只在编辑模式下处理
        if hasattr(self.window, 'current_mode') and hasattr(self.window, 'EDIT_MODE'):
            if self.window.current_mode != self.window.EDIT_MODE:
                return

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
            if hasattr(widget_at_position, "check_resize_direction"):
                resize_direction = widget_at_position.check_resize_direction(local_x, local_y)
                if resize_direction:
                    cursor_name = self.get_cursor_name_for_resize_direction(resize_direction)
                    self.set_cursor_from_name(cursor_name)
                    return

            # 默认鼠标指针（可拖拽）
            self.set_cursor_from_name("grab")
        else:
            # 空白区域，默认指针
            self.set_cursor_from_name("default")

    def handle_mouse_release(self, controller, n_press, x, y):
        """处理鼠标释放事件"""
        # 停止拖拽和调整大小
        if self.dragging_widget:
            self.dragging_widget = None
        
        if self.resizing_widget:
            if hasattr(self.resizing_widget, 'on_resize_release'):
                self.resizing_widget.on_resize_release()
            self.resizing_widget = None
            self.resize_direction = None
        
        # 清除待处理状态
        self.selected_widget = None
        self.pending_resize_direction = None

    def handle_widget_interaction(self, widget, x, y, n_press=1):
        """处理widget交互 - 支持双击检测"""
        
        local_x, local_y = self.global_to_local_coords(widget, x, y)
        
        should_keep_editing = False
        if hasattr(widget, 'should_keep_editing_on_click'):
            should_keep_editing = widget.should_keep_editing_on_click(local_x, local_y)
        
        if should_keep_editing:
            if not hasattr(widget, '_skip_delayed_bring_to_front'):
                 widget._skip_delayed_bring_to_front = True
            return
        
        self.clear_all_selections(exclude_widget=widget)
        if hasattr(widget, 'set_selected'):
            widget.set_selected(True)
        
        if hasattr(widget, '_skip_delayed_bring_to_front'):
            delattr(widget, '_skip_delayed_bring_to_front')
        
        self.schedule_bring_to_front(widget)
        
        local_x, local_y = self.global_to_local_coords(widget, x, y)
        
        if n_press == 2:
            if not hasattr(widget, '_skip_delayed_bring_to_front'):
                widget._skip_delayed_bring_to_front = True
            
            if hasattr(widget, 'on_widget_double_clicked'):
                widget.on_widget_double_clicked(local_x, local_y)
            return
        
        self.selected_widget = widget
        self.interaction_start_x = x
        self.interaction_start_y = y
        
        if hasattr(widget, 'check_resize_direction'):
            resize_direction = widget.check_resize_direction(local_x, local_y)
            if resize_direction:
                if hasattr(widget, 'should_keep_editing_on_click'):
                    self.clear_all_selections()
                    if hasattr(widget, 'set_selected'):
                        widget.set_selected(True)
                
                self.pending_resize_direction = resize_direction
                return
        
        self.pending_resize_direction = None
        
        if hasattr(widget, 'on_widget_clicked'):
            widget.on_widget_clicked(local_x, local_y)

    def get_widget_at_position(self, x, y):
        """获取指定位置的组件"""
        child = self.fixed.get_first_child()
        while child:
            child_x, child_y = self.fixed.get_child_position(child)
            child_width = child.get_allocated_width()
            child_height = child.get_allocated_height()
            
            if is_point_in_rect(x, y, child_x, child_y, child_width, child_height):
                return child
            
            child = child.get_next_sibling()
        return None

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
        
        if hasattr(self.dragging_widget, 'get_widget_bounds'):
            widget_bounds = self.dragging_widget.get_widget_bounds()
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
        
        if hasattr(widget, 'start_resize'):
            local_x, local_y = self.global_to_local_coords(widget, x, y)
            widget.start_resize(local_x, local_y, direction)

    def handle_widget_resize(self, x, y):
        """处理widget调整大小"""
        if not self.resizing_widget or not hasattr(self.resizing_widget, 'handle_resize_motion'):
            return
            
        self.resizing_widget.handle_resize_motion(x, y)

    def clear_all_selections(self, exclude_widget=None):
        """取消所有组件的选择状态"""
        child = self.fixed.get_first_child()
        while child:
            if hasattr(child, 'set_selected') and child != exclude_widget:
                child.set_selected(False)
            child = child.get_next_sibling()
        
        self.dragging_widget = None
        self.resizing_widget = None

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
            widget.on_delete()

    def cleanup(self):
        """清理WorkspaceManager的资源，包括事件订阅"""
        self.event_bus.unsubscribe_by_subscriber(self)

        # 清理状态
        self.dragging_widget = None
        self.resizing_widget = None
        self.selected_widget = None


    # def delete_selected_widgets(self):
    #     """删除所有选中的widget"""
    #     widgets_to_delete = []
    #     child = self.fixed.get_first_child()
    #     while child:
    #         if hasattr(child, 'is_selected') and child.is_selected:
    #             widgets_to_delete.append(child)
    #         child = child.get_next_sibling()
        
    #     for widget in widgets_to_delete:
    #         self.delete_specific_widget(widget)
        
    #     self.dragging_widget = None
    #     self.resizing_widget = None

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
            if hasattr(widget, '_skip_delayed_bring_to_front') and widget._skip_delayed_bring_to_front:
                delattr(widget, '_skip_delayed_bring_to_front')
                return False
            
            if not widget.get_parent() or widget.get_parent() != self.fixed:
                return False
                
            x, y = self.fixed.get_child_position(widget)
            
            selected_state = getattr(widget, 'is_selected', False)
            
            self.fixed.remove(widget)
            self.window.fixed_put(widget, x, y)
            
            if hasattr(widget, 'set_selected'):
                current_state = getattr(widget, 'is_selected', False)
                if current_state != selected_state:
                    widget.set_selected(selected_state)
        except Exception as e:
            logger.error(f"Error during delayed bring to front: {e}")
        
        return False

    # def update_cursor_for_position(self, x, y):
        # """根据位置更新鼠标指针"""
        # widget_at_position = self.get_widget_at_position(x, y)
        # if widget_at_position:
        #     local_x, local_y = self.global_to_local_coords(widget_at_position, x, y)
            
        #     if hasattr(widget_at_position, 'check_resize_direction'):
        #         resize_direction = widget_at_position.check_resize_direction(local_x, local_y)
        #         if resize_direction:
        #             cursor_name = self.get_cursor_name_for_resize_direction(resize_direction)
        #             self.set_cursor_from_name(cursor_name)
        #             return
            
        #     self.set_cursor_from_name("grab")
        # else:
        #     self.set_cursor_from_name("default")

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
            except:
                pass 