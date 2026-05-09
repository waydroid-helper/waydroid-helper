#!/usr/bin/env python3
"""
可编辑装饰器
为组件添加双击编辑文本的功能，直接在组件上编辑
"""

import gi

gi.require_version('Gtk', '4.0')
from gi.repository import GLib, Gtk

from waydroid_helper.controller.app.input_event_factory import GtkInputEventFactory
from waydroid_helper.controller.core.handler import InputEventType
from waydroid_helper.util.log import logger

from waydroid_helper.controller.widgets.base.draw_overlay import (
    add_decorator_draw_overlay,
)
from waydroid_helper.controller.widgets.base.decorator_contracts import (
    EditableWidgetBehavior,
)

from .base_decorator import WidgetDecorator, parameterized_widget_decorator
from .editable_mapping import EditableKeyMappingRegistrar
from .editable_session import EditableCaptureSession


class EditableDecorator(WidgetDecorator, EditableWidgetBehavior):
    """可编辑装饰器"""

    BEHAVIOR_CONTRACTS = (EditableWidgetBehavior,)
    
    def __init__(self, widget, max_keys=2, **kwargs):
        """初始化可编辑装饰器
        
        Args:
            widget: 要装饰的组件
            max_keys: 最多可以捕获的按键数量，默认为2
            **kwargs: 其他参数
        """
        self.max_keys_param = max_keys
        super().__init__(widget, **kwargs)
    
    def _setup_decorator(self):
        """设置可编辑功能"""
        logger.debug(f"EditableDecorator for {type(self._wrapped_widget).__name__}")
        
        self._capture_session = EditableCaptureSession(self.max_keys_param)
        logger.debug("EditableDecorator initialized")
        self._mapping_registrar = EditableKeyMappingRegistrar(
            self._wrapped_widget,
            self._get_toplevel_window,
        )
        
        # Hook双击事件、键盘事件、鼠标事件和绘制函数
        self._hook_double_click()
        self._hook_keyboard_events()
        self._hook_mouse_events()
        self._hook_draw_function()
        
        # 不再使用拦截器，改为提供查询方法给window使用
        
        # 监听is_selected属性变化
        self._wrapped_widget.connect('notify::is-selected', self._on_selection_changed)
        
        logger.debug(f"EditableDecorator applied to {type(self._wrapped_widget).__name__}")
        logger.debug(f"Editable Hook draw function: {self._wrapped_widget.draw_func}")
        logger.debug(f"Component focusable: {self._wrapped_widget.get_focusable()}")
    
    def should_keep_editing_on_click(self, x, y):
        """供window查询：在指定位置点击时是否应该保持编辑状态"""
        return self._capture_session.should_keep_editing_on_click(
            self._wrapped_widget,
            x,
            y,
        )
    
    def _hook_double_click(self):
        """Hook双击事件，添加编辑功能"""
        logger.debug("Hook double click")
        original_double_click = self._wrapped_widget.on_widget_double_clicked
        
        def enhanced_double_click(x, y):
            logger.debug(f"Double click event triggered, position: ({x}, {y})")
            original_double_click(x, y)

            region = self._wrapped_widget.get_region_at_position(x, y)
            if region:
                logger.debug(f"Start editing region: {region['name']} ({region['id']})")
                self.start_region_editing(region)
            else:
                logger.debug("Clicked position not in any editable region")
        
        self._wrapped_widget.on_widget_double_clicked = enhanced_double_click
    
    def _hook_draw_function(self):
        """Hook绘制函数，在编辑模式下绘制光标和编辑文本"""
        def editable_draw(cr, width, height):
            if self._capture_session.is_editing:
                self._draw_edit_overlay(cr, width, height)

        add_decorator_draw_overlay(self._wrapped_widget, editable_draw)
    
    def _hook_keyboard_events(self):
        """Hook键盘事件处理文本输入"""
        # 确保组件可获得焦点
        self._wrapped_widget.set_focusable(True)
        self._wrapped_widget.set_can_focus(True)
        
        # 添加键盘事件控制器
        self.key_controller = Gtk.EventControllerKey()
        self.key_controller.connect('key-pressed', self._on_key_pressed)
        self.key_controller.connect('key-released', self._on_key_released)
        self._wrapped_widget.add_controller(self.key_controller)
        
        logger.debug(f"Keyboard event controller set, component focusable: {self._wrapped_widget.get_focusable()}")
    
    def _hook_mouse_events(self):
        """Hook鼠标事件处理鼠标按键捕获"""
        # 添加鼠标点击事件控制器
        self.mouse_controller = Gtk.GestureClick()
        self.mouse_controller.set_button(0)  # 监听所有鼠标按键
        self.mouse_controller.connect('pressed', self._on_mouse_pressed)
        self.mouse_controller.connect('released', self._on_mouse_released)
        self._wrapped_widget.add_controller(self.mouse_controller)
        
        logger.debug("Mouse event controller set")
    
    def _on_mouse_pressed(self, controller, n_press, x, y):
        """处理鼠标按键按下事件 - 鼠标按键捕获模式"""
        # 只有在编辑状态且处于编辑模式时才捕获鼠标按键
        if not self._capture_session.is_editing:
            return False
        
        # 检查当前是否处于编辑模式（而不是映射模式）
        if not self._is_toplevel_in_edit_mode():
            return False
            
        input_event = self._create_capture_mouse_event(
            InputEventType.MOUSE_PRESS, controller, n_press, x, y
        )
        if input_event is None or input_event.button is None:
            return False

        logger.debug(
            "Mouse button pressed: button=%s, position=(%.1f, %.1f), editing=%s",
            input_event.button,
            x,
            y,
            self._capture_session.is_editing,
        )

        if input_event.button == 1:  # 左键
            logger.debug(f"Ignore mouse left button (conflict of duty)")
            return False

        if input_event.key:
            logger.debug(f"Mouse button pressed: {input_event.key}")
            self._capture_session.capture_key(self._wrapped_widget, input_event.key)
            self._wrapped_widget.queue_draw()
            return True  # 消费掉这个事件，避免触发其他逻辑
        
        return False
    
    def _on_mouse_released(self, controller, n_press, x, y):
        """处理鼠标按键释放事件"""
        # 只有在编辑状态且处于编辑模式时才处理鼠标释放
        if not self._capture_session.is_editing:
            return False
        
        # 检查当前是否处于编辑模式（而不是映射模式）
        if not self._is_toplevel_in_edit_mode():
            return False
            
        input_event = self._create_capture_mouse_event(
            InputEventType.MOUSE_RELEASE, controller, n_press, x, y
        )
        if input_event is None or input_event.button is None:
            return False

        logger.debug(f"Mouse button released: button={input_event.button}")

        if input_event.button == 1:  # 左键
            logger.debug(f"Ignore mouse left button (conflict of duty)")
            return False

        if input_event.key:
            logger.debug(f"Mouse button released: {input_event.key}")
            self._capture_session.release_key(self._wrapped_widget, input_event.key)
            self._wrapped_widget.queue_draw()
            return True
        
        return False
    
    def _on_selection_changed(self, widget, pspec):
        """当选择状态改变时的回调"""
        if not widget.is_selected and self._capture_session.is_editing:
            logger.debug(f"Component lost selection, confirm key capture")
            self.finish_editing(True)
    
    def start_editing(self):
        """开始编辑按键"""
        if not self._capture_session.begin_widget_editing(self._wrapped_widget):
            return
        
        # 强制获取焦点以接收键盘输入
        self._wrapped_widget.grab_focus()
        
        # 等待一个事件循环后再次检查焦点状态
        def check_focus():
            has_focus = self._wrapped_widget.has_focus()
            logger.debug(f"After editing, focus state: {has_focus}")
            if not has_focus:
                logger.debug(f"Focus failed, retry...")
                self._wrapped_widget.grab_focus()
            return False
            
        GLib.timeout_add(10, check_focus)
        
        # 重绘组件
        self._wrapped_widget.queue_draw()
    
    def start_region_editing(self, region):
        """开始编辑指定区域的按键"""
        if not self._capture_session.begin_region_editing(
            self._wrapped_widget,
            region,
        ):
            return
        
        # 强制获取焦点以接收键盘输入
        self._wrapped_widget.grab_focus()
        
        # 检查焦点状态
        def check_focus():
            has_focus = self._wrapped_widget.has_focus()
            logger.debug(f"After region editing, focus state: {has_focus}")
            if not has_focus:
                logger.debug(f"Focus failed, retry...")
                self._wrapped_widget.grab_focus()
            return False
            
        GLib.timeout_add(10, check_focus)
        
        # 重绘组件
        self._wrapped_widget.queue_draw()
    
    def _get_input_event_factory(self) -> GtkInputEventFactory:
        """Return the window input adapter, or build one for detached widgets.

        The fallback keeps tests and standalone widget construction working,
        while normal windows still use the exact same adapter instance as
        mapping mode.
        """
        window = self._get_toplevel_window()
        if window is not None:
            try:
                factory = window.input_event_factory
            except AttributeError:
                logger.warning(
                    "Top-level window %s has no input_event_factory",
                    type(window).__name__,
                )
            else:
                if isinstance(factory, GtkInputEventFactory):
                    return factory
        return GtkInputEventFactory(
            self._wrapped_widget,
            self._wrapped_widget.key_registry,
        )

    def _create_capture_key_event(
        self,
        event_type: InputEventType,
        controller,
        keyval,
        keycode,
    ):
        return self._get_input_event_factory().create_key_event(
            event_type,
            controller,
            keyval,
            keycode,
            0,
        )

    def _create_capture_mouse_event(
        self,
        event_type: InputEventType,
        controller,
        n_press,
        x,
        y,
    ):
        return self._get_input_event_factory().create_mouse_capture_event(
            event_type,
            controller,
            n_press,
            x,
            y,
        )
    
    def _remove_last_final_key(self):
        """移除最后一个最终捕获的按键（用于Delete键）"""
        removed_combination = self._capture_session.remove_last_final_key(
            self._wrapped_widget
        )
        if removed_combination is not None:
            # 删除按键后，需要更新全局映射
            self._mapping_registrar.update_global_mapping()
            return True
        return False
    
    def _on_key_released(self, controller, keyval, keycode, state):
        """处理按键弹起事件"""
        if not self._capture_session.is_editing:
            return False
            
        input_event = self._create_capture_key_event(
            InputEventType.KEY_RELEASE, controller, keyval, keycode
        )
        if input_event and input_event.key:
            self._capture_session.release_key(self._wrapped_widget, input_event.key)
            logger.debug(f"Key released: {input_event.key} ({keyval})")
        return True
    
    def _draw_edit_overlay(self, cr, width, height):
        """在编辑模式下绘制编辑边框"""
        if not self._capture_session.is_editing:
            return
            
        logger.debug(f"Draw edit overlay: is_editing={self._capture_session.is_editing}")
        
        # 只绘制编辑状态的边框提示
        self._draw_edit_border(cr, width, height)
    
    def _draw_edit_border(self, cr, width, height):
        """绘制编辑状态的边框提示"""
        # 绘制蓝色虚线边框表示编辑状态
        cr.set_source_rgba(0.2, 0.6, 1.0, 0.8)  # 蓝色
        cr.set_line_width(2)
        cr.set_dash([5, 3])  # 虚线样式
        
        current_edit_region = self._capture_session.current_edit_region
        if current_edit_region:
            # 区域编辑模式：绘制区域特定的边框
            bounds = current_edit_region['bounds']
            if bounds and len(bounds) == 4:
                rx, ry, rw, rh = bounds
                cr.rectangle(rx, ry, rw, rh)
                cr.stroke()
            
            # 显示区域名称
            region_name = current_edit_region.get('name', 'Unknown Region')
            cr.set_source_rgba(0.2, 0.6, 1.0, 1.0)
            cr.select_font_face("Arial", 0, 1)
            cr.set_font_size(10)
            cr.move_to(5, 15)
            cr.new_path()
        else:
            # 传统编辑模式：绘制整个widget边框
            cr.rectangle(1, 1, width - 2, height - 2)
            cr.stroke()
        
        # 重置虚线样式
        cr.set_dash([])
    
    def _on_key_pressed(self, controller, keyval, keycode, state):
        """处理键盘按键 - 按键捕获模式"""
        logger.debug(f"Keyboard key event: keyval={keyval}, keycode={keycode}, state={state}, is_editing={self._capture_session.is_editing}")
        
        if not self._capture_session.is_editing:
            logger.debug(f"Received key but not in edit mode: {keyval}")
            return False
        
        logger.debug(f"Key capture mode key: {keyval} (keycode: {keycode})")
        
        input_event = self._create_capture_key_event(
            InputEventType.KEY_PRESS, controller, keyval, keycode
        )
        if input_event and input_event.key:
            logger.debug(
                f"Key pressed: {input_event.key} "
                f"(original keyval: {input_event.key_symbol_name})"
            )
            self._capture_session.capture_key(self._wrapped_widget, input_event.key)
            self._wrapped_widget.queue_draw()
        return True
    
    def finish_editing(self, apply_changes=True):
        """结束按键捕获"""
        result = self._capture_session.finish(self._wrapped_widget, apply_changes)
        if result is None:
            return

        if result.region is not None and result.original_keys is not None:
            self._mapping_registrar.register_region_mappings(
                result.region,
                result.original_keys,
            )
        elif result.register_widget_mappings:
            self._mapping_registrar.register_widget_mappings()
    
    def _get_toplevel_window(self):
        """获取顶级窗口"""
        root = self._wrapped_widget.get_root()
        if root and isinstance(root, Gtk.Window):
            return root
        return None

    def _is_toplevel_in_edit_mode(self) -> bool:
        window = self._get_toplevel_window()
        if window is None:
            return True

        try:
            current_mode = window.current_mode
            edit_mode = window.EDIT_MODE
        except AttributeError:
            logger.warning(
                "Top-level window %s has no controller mode state",
                type(window).__name__,
            )
            return True

        if current_mode != edit_mode:
            logger.debug("Not in edit mode(%s), skip capture", current_mode)
            return False

        return True
    
    def cancel_editing(self):
        """取消按键捕获"""
        self.finish_editing(False)
    
    def get_captured_keys(self):
        """获取当前最终捕获的按键列表"""
        return self._wrapped_widget.final_keys.copy()
# 创建装饰器函数
Editable = parameterized_widget_decorator(EditableDecorator)
