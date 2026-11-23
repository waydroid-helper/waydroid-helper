#!/usr/bin/env python3
"""
可编辑装饰器
在点选的键名位置捕获绑定。
"""

import gi

gi.require_version('Gtk', '4.0')
from gi.repository import GLib, Gtk

from waydroid_helper.controller.core.handler import InputEventType
from waydroid_helper.controller.core.runtime import WidgetInputEventFactory
from waydroid_helper.util.log import logger

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
            self._wrapped_widget.runtime_context.key_mapping_service,
        )
        
        # Capture starts on a keycap release, after workspace drag arbitration.
        self._blink_source = 0
        self._hook_keyboard_events()
        self._hook_mouse_events()
        focus = Gtk.EventControllerFocus()
        focus.connect("leave", lambda *_: self.finish_editing())
        self._wrapped_widget.add_controller(focus)
        self._wrapped_widget.connect("unmap", lambda *_: self.finish_editing())
        
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
    
    def capture_at(self, x, y):
        region = self._wrapped_widget.get_region_at_position(x, y)
        current = self._capture_session.current_edit_region
        if current and region and current["id"] == region["id"]:
            return
        if current:
            self.finish_editing()
        if region:
            self.start_region_editing(region)

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
        scroll = Gtk.EventControllerScroll.new(Gtk.EventControllerScrollFlags.BOTH_AXES)
        scroll.connect("scroll", self._capture_scroll)
        self._wrapped_widget.add_controller(scroll)
        
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
            self.capture_external_key(input_event.key, True)
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
            self.capture_external_key(input_event.key, False)
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
        
        widget = self._wrapped_widget
        widget.capture_region = region["id"]
        widget.caret_visible = True
        widget.grab_focus()
        widget.queue_draw()

        def blink():
            widget.caret_visible = not widget.caret_visible
            widget.queue_draw()
            return GLib.SOURCE_CONTINUE

        self._blink_source = GLib.timeout_add(500, blink)

    def _get_input_event_factory(self) -> WidgetInputEventFactory:
        """Return the input adapter injected by the controller composition root."""
        return self._wrapped_widget.runtime_context.input_event_factory

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
            self.capture_external_key(input_event.key, False)
            logger.debug(f"Key released: {input_event.key} ({keyval})")
        return True
    
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
            self.capture_external_key(input_event.key, True)
            self._wrapped_widget.queue_draw()
        return True
    
    def _capture_scroll(self, controller, dx, dy):
        if not self._capture_session.is_editing:
            return False
        event = self._get_input_event_factory().create_scroll_event(controller, dx, dy)
        if event.key is None:
            return False
        self.capture_external_key(event.key, True)
        self.capture_external_key(event.key, False)
        return True

    def capture_external_key(self, key, pressed):
        if not self._capture_session.is_editing:
            return False
        if pressed:
            self._capture_session.capture_key(self._wrapped_widget, key)
        else:
            result = self._capture_session.release_key(self._wrapped_widget, key)
            if result:
                self._register_capture(result)
        self._wrapped_widget.queue_draw()
        return True

    def finish_editing(self, apply_changes=True):
        """结束按键捕获"""
        result = self._capture_session.finish(self._wrapped_widget, apply_changes)
        if result is None:
            return

        if self._blink_source:
            GLib.source_remove(self._blink_source)
            self._blink_source = 0
        self._wrapped_widget.capture_region = None
        self._wrapped_widget.queue_draw()
        self._register_capture(result)

    def _register_capture(self, result):
        if result.region is not None and result.original_keys is not None:
            self._mapping_registrar.register_region_mappings(
                result.region,
                result.original_keys,
            )
        elif result.register_widget_mappings:
            self._mapping_registrar.register_widget_mappings()
    
    def _is_toplevel_in_edit_mode(self) -> bool:
        if not self._wrapped_widget.runtime_context.is_edit_mode():
            logger.debug("Controller is not in edit mode; skip capture")
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
