#!/usr/bin/env python3
"""
可编辑装饰器
为组件添加双击编辑文本的功能，直接在组件上编辑
"""

import gi

gi.require_version('Gtk', '4.0')
from gi.repository import Gdk, GLib, Gtk

from waydroid_helper.controller.core.handler import KeyMappingManager
from waydroid_helper.controller.core.key_system import (Key, KeyCombination)
from waydroid_helper.util.log import logger

from .base_decorator import WidgetDecorator, parameterized_widget_decorator


class EditableDecorator(WidgetDecorator):
    """可编辑装饰器"""
    
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
        
        self.is_editing = False
        self.edit_text = ""
        self.original_text = ""
        
        # 多区域编辑相关属性
        self.current_edit_region = None  # 当前正在编辑的区域
        self.original_keys: set[KeyCombination] = set()       # 编辑前的原始按键集合 set[KeyCombination]
        
        # 按键捕获相关属性
        self.realtime_keys: set[Key] = set()  # 实时捕获：当前按下但未弹起的按键集合
        self.max_keys = self.max_keys_param  # 最多捕获的按键数量（从参数获取）
        
        # 移除编辑提示相关属性（简化为直接在text中显示）
        
        logger.debug("EditableDecorator initialized")
        
        # Hook双击事件、键盘事件、鼠标事件和绘制函数
        self._hook_double_click()
        self._hook_keyboard_events()
        self._hook_mouse_events()
        self._hook_draw_function()
        
        # 不再使用拦截器，改为提供查询方法给window使用
        
        # 监听is_selected属性变化
        self._wrapped_widget.connect('notify::is-selected', self._on_selection_changed)
        
        # 将装饰器的方法暴露给被装饰的widget
        self._wrapped_widget.should_keep_editing_on_click = self.should_keep_editing_on_click
        
        logger.debug(f"EditableDecorator applied to {type(self._wrapped_widget).__name__}")
        logger.debug(f"Editable Hook draw function: {self._wrapped_widget.draw_func}")
        logger.debug(f"Component focusable: {self._wrapped_widget.get_focusable()}")
    
    def should_keep_editing_on_click(self, x, y):
        """供window查询：在指定位置点击时是否应该保持编辑状态"""
        if not self.is_editing:
            return False
            
        logger.debug(f"Query if should keep editing: position({x:.1f}, {y:.1f}), editing: {self.is_editing}")
        
        if self.current_edit_region:
            # 区域编辑模式：检查是否点击了当前编辑的区域
            clicked_region = self._wrapped_widget.get_region_at_position(x, y)
            logger.debug(f"Current edit region: {self.current_edit_region['id']}, clicked region: {clicked_region['id'] if clicked_region else 'None'}")
            
            if clicked_region and clicked_region['id'] == self.current_edit_region['id']:
                logger.debug(f"Clicked current edit region {clicked_region['id']}, keep editing")
                return True
            else:
                logger.debug("Clicked other region, should exit editing")
                return False
        else:
            # 传统编辑模式：点击widget内任意位置都保持编辑状态
            logger.debug("Traditional editing mode, clicked widget internal, should keep editing")
            return True
    
    def _hook_double_click(self):
        """Hook双击事件，添加编辑功能"""
        logger.debug("Hook double click")
        original_double_click = getattr(self._wrapped_widget, 'on_widget_double_clicked', None)
        
        def enhanced_double_click(x, y):
            logger.debug(f"Double click event triggered, position: ({x}, {y})")
            if original_double_click:
                original_double_click(x, y)
            
            # 检查是否支持多区域编辑
            if hasattr(self._wrapped_widget, 'get_editable_regions'):
                region = self._wrapped_widget.get_region_at_position(x, y)
                if region:
                    logger.debug(f"Start editing region: {region['name']} ({region['id']})")
                    self.start_region_editing(region)
                else:
                    logger.debug("Clicked position not in any editable region")
            else:
                # 传统的单区域编辑
                logger.debug("Start traditional editing mode")
                self.start_editing()
        
        self._wrapped_widget.on_widget_double_clicked = enhanced_double_click
    
    def _hook_draw_function(self):
        """Hook绘制函数，在编辑模式下绘制光标和编辑文本"""
        # 初始化装饰器绘制列表（如果不存在）
        if not hasattr(self._wrapped_widget, '_decorator_draws'):
            self._wrapped_widget._decorator_draws = []
            # 保存原始绘制函数
            original_draw = self._wrapped_widget.draw_func
            
            def master_draw_func(widget, cr, width, height, user_data):
                # 调用原始绘制
                original_draw(widget, cr, width, height, user_data)
                # 调用所有装饰器的绘制
                for draw_func in widget._decorator_draws:
                    draw_func(cr, width, height)
            
            # 设置主绘制函数
            self._wrapped_widget.set_draw_func(master_draw_func, None)
        
        # 添加此装饰器的绘制函数到列表
        def editable_draw(cr, width, height):
            if self.is_editing:
                self._draw_edit_overlay(cr, width, height)
        
        self._wrapped_widget._decorator_draws.append(editable_draw)
    
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
        if not self.is_editing:
            return False
        
        # 检查当前是否处于编辑模式（而不是映射模式）
        window = self._get_toplevel_window()
        if window and hasattr(window, 'current_mode') and hasattr(window, 'EDIT_MODE'):
            if window.current_mode != window.EDIT_MODE:
                logger.debug(f"Not in edit mode({window.current_mode}), not capture mouse button")
                return False
            
        button = controller.get_current_button()
        logger.debug(f"Mouse button pressed: button={button}, position=({x:.1f}, {y:.1f}), editing={self.is_editing}")
        
        if button == 1:  # 左键
            logger.debug(f"Ignore mouse left button (conflict of duty)")
            return False
        
        # 获取鼠标按键的Key对象
        mouse_key = self._wrapped_widget.key_registry.create_mouse_key(button)
        if mouse_key:
            logger.debug(f"Mouse button pressed: {mouse_key}")
            self._add_key_to_realtime(mouse_key)
            self._wrapped_widget.queue_draw()
            return True  # 消费掉这个事件，避免触发其他逻辑
        
        return False
    
    def _on_mouse_released(self, controller, n_press, x, y):
        """处理鼠标按键释放事件"""
        # 只有在编辑状态且处于编辑模式时才处理鼠标释放
        if not self.is_editing:
            return False
        
        # 检查当前是否处于编辑模式（而不是映射模式）
        window = self._get_toplevel_window()
        if window and hasattr(window, 'current_mode') and hasattr(window, 'EDIT_MODE'):
            if window.current_mode != window.EDIT_MODE:
                logger.debug(f"Not in edit mode({window.current_mode}), not handle mouse release")
                return False
            
        button = controller.get_current_button()
        logger.debug(f"Mouse button released: button={button}")
        
        if button == 1:  # 左键
            logger.debug(f"Ignore mouse left button (conflict of duty)")
            return False
        
        # 获取鼠标按键的Key对象
        mouse_key = self._wrapped_widget.key_registry.create_mouse_key(button)
        if mouse_key:
            logger.debug(f"Mouse button released: {mouse_key}")
            self._remove_key_from_realtime(mouse_key)
            self._wrapped_widget.queue_draw()
            return True
        
        return False
    
    def _on_selection_changed(self, widget, pspec):
        """当选择状态改变时的回调"""
        if not widget.is_selected and self.is_editing:
            logger.debug(f"Component lost selection, confirm key capture")
            self.finish_editing(True)
    
    def start_editing(self):
        """开始编辑按键"""
        if self.is_editing:
            return
        
        logger.debug(f"Start key capture: '{self._wrapped_widget.text}'")
        
        self.is_editing = True
        self.original_text = self._wrapped_widget.text or ""
        # 清空实时捕获
        self.realtime_keys = set()
        
        # 如果没有保存的按键，显示提示文本
        if not self._wrapped_widget.final_keys and not self.original_text:
            self._wrapped_widget.text = "Press keys to capture"
            logger.debug(f"Show capture hint text")
        
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
        if self.is_editing:
            return
        
        logger.debug(f"Start region key capture: {region['name']} ({region['id']})")
        
        self.is_editing = True
        self.current_edit_region = region
        
        # 获取当前区域的按键
        current_keys = region['get_keys']()
        self.original_keys = set(current_keys)
        
        # 显示提示信息
        if hasattr(self._wrapped_widget, 'text'):
            self.original_text = getattr(self._wrapped_widget, 'text', "")
        
        # 清空实时捕获
        self.realtime_keys = set()
        
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
    
    def _get_physical_keyval(self, keycode):
        """获取物理按键对应的标准 keyval（不受修饰键影响）"""
        try:
            # 尝试获取顶级窗口的方法
            window = self._get_toplevel_window()
            if window and hasattr(window, 'get_physical_keyval'):
                return window.get_physical_keyval(keycode)
            else:
                # 如果无法获取window，尝试直接实现
                widget = self._wrapped_widget
                if widget and hasattr(widget, 'get_display'):
                    display = widget.get_display()
                    if display:
                        success, keyval, _, _, _ = display.translate_key(
                            keycode=keycode, state=Gdk.ModifierType(0), group=0
                        )
                        if success:
                            return Gdk.keyval_to_upper(keyval)
        except Exception as e:
            logger.debug(f"Failed to get physical keyval: {e}")
        return 0

    def _get_key_name(self, keyval, keycode, state) -> Key | None:
        """获取按键对象（使用物理按键标准化）"""
        # 如果是修饰键，直接使用原始keyval
        if self._is_modifier_key(keyval):
            return self._wrapped_widget.key_registry.create_from_keyval(keyval, state)
        
        # 非修饰键：获取物理按键的标准keyval
        physical_keyval = self._get_physical_keyval(keycode)
        if physical_keyval == 0:
            # 如果获取失败，回退到原始keyval
            physical_keyval = keyval
            logger.debug(f"Edit mode fallback to original keyval: {Gdk.keyval_name(keyval)}")
        
        return self._wrapped_widget.key_registry.create_from_keyval(physical_keyval, 0)  # 不包含修饰符状态
    
    def _add_key_to_realtime(self, key: Key):
        """添加按键到实时捕获集合"""
        # 限制实时捕获的按键数量
        if len(self.realtime_keys) >= self.max_keys:
            removed_key = next(iter(self.realtime_keys))
            self.realtime_keys.remove(removed_key)
            logger.debug(f"Real-time set is full, remove oldest key: {removed_key}")
        
        # 添加新按键到实时捕获
        self.realtime_keys.add(key)
        logger.debug(f"Add key to real-time set: {key}, current real-time set: {[str(k) for k in self.realtime_keys]}")
        
        # 实时更新最终捕获（保存当前组合）
        self._update_final_capture()
    
    def _remove_key_from_realtime(self, key: Key):
        """从实时捕获集合中移除按键"""
        if key in self.realtime_keys:
            self.realtime_keys.remove(key)
            logger.debug(f"Remove key from real-time set: {key}, current real-time set: {[str(k) for k in self.realtime_keys]}")
            
            # 如果实时捕获变空，保持最终捕获的状态不变（已经在按下时更新了）
            # 只需要更新显示
            self._update_display()
            return True
        return False
    
    def _update_final_capture(self):
        """更新最终捕获集合（保存当前实时捕获的状态）"""
        if self.realtime_keys:
            # 创建 KeyCombination
            current_combination = KeyCombination(list(self.realtime_keys))
            
            if self.current_edit_region:
                # 区域编辑模式：更新区域的按键
                self.current_edit_region['set_keys']({current_combination})
                logger.debug(f"Update region {self.current_edit_region['id']} keys: {current_combination}")
            else:
                # 传统编辑模式：更新widget的final_keys
                self._wrapped_widget.final_keys = {current_combination}
                logger.debug(f"Update final capture: {current_combination}")
        # 更新显示
        self._update_display()
    
    def _update_display(self):
        """更新显示文本"""
        if self._wrapped_widget.final_keys:
            # 显示第一个按键组合（通常只有一个）
            if self._wrapped_widget.final_keys:
                first_combination = next(iter(self._wrapped_widget.final_keys))
                self._wrapped_widget.text = str(first_combination)
            else:
                self._wrapped_widget.text = ""
        else:
            if self.is_editing:
                self._wrapped_widget.text = "Press keys to capture"
            else:
                self._wrapped_widget.text = ""
    
    def _remove_last_final_key(self):
        """移除最后一个最终捕获的按键（用于Delete键）"""
        if self._wrapped_widget.final_keys:
            # 移除一个按键组合
            removed_combination = self._wrapped_widget.final_keys.pop()
            self._update_display()
            logger.debug(f"Delete key combination: {removed_combination}")
            
            # 删除按键后，需要更新全局映射
            self._update_global_mapping()
            return True
        return False
    
    def _update_global_mapping(self):
        """更新全局的按键映射（删除旧映射，添加新映射）"""
        try:
            # 先取消旧的映射
            key_mapping_manager = self._get_toplevel_window().key_mapping_manager
            key_mapping_manager.unsubscribe(self._wrapped_widget)
            
            # 如果还有按键，重新注册新的映射
            if self._wrapped_widget.final_keys:
                # 注册每个按键组合
                for key_combination in self._wrapped_widget.final_keys:
                    key_mapping_manager.subscribe(self._wrapped_widget, key_combination)
                    logger.debug(f"Update global mapping: {key_combination}")
            else:
                logger.debug(f"Clear global mapping (no keys)")
                
        except Exception as e:
            logger.error(f"Error updating global mapping: {e}")
    
    def _on_key_released(self, controller, keyval, keycode, state):
        """处理按键弹起事件"""
        if not self.is_editing:
            return False
            
        # 获取按键并从实时捕获集合中移除
        key = self._get_key_name(keyval, keycode, 0)  # 不包含修饰符状态
        if key:
            self._remove_key_from_realtime(key)
            logger.debug(f"Key released: {key} ({keyval})")
        return True
    
    def _is_modifier_key(self, keyval):
        """检查是否是修饰键"""
        modifier_keys = {
            Gdk.KEY_Control_L, Gdk.KEY_Control_R,
            Gdk.KEY_Alt_L, Gdk.KEY_Alt_R,
            Gdk.KEY_Shift_L, Gdk.KEY_Shift_R,
            Gdk.KEY_Super_L, Gdk.KEY_Super_R,
            Gdk.KEY_Meta_L, Gdk.KEY_Meta_R,
            Gdk.KEY_Hyper_L, Gdk.KEY_Hyper_R
        }
        return keyval in modifier_keys
    
    def _draw_edit_overlay(self, cr, width, height):
        """在编辑模式下绘制编辑边框"""
        if not self.is_editing:
            return
            
        logger.debug(f"Draw edit overlay: is_editing={self.is_editing}")
        
        # 只绘制编辑状态的边框提示
        self._draw_edit_border(cr, width, height)
    
    def _draw_edit_border(self, cr, width, height):
        """绘制编辑状态的边框提示"""
        # 绘制蓝色虚线边框表示编辑状态
        cr.set_source_rgba(0.2, 0.6, 1.0, 0.8)  # 蓝色
        cr.set_line_width(2)
        cr.set_dash([5, 3])  # 虚线样式
        
        if self.current_edit_region:
            # 区域编辑模式：绘制区域特定的边框
            bounds = self.current_edit_region['bounds']
            if bounds and len(bounds) == 4:
                rx, ry, rw, rh = bounds
                cr.rectangle(rx, ry, rw, rh)
                cr.stroke()
            
            # 显示区域名称
            region_name = self.current_edit_region.get('name', 'Unknown Region')
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
        logger.debug(f"Keyboard key event: keyval={keyval}, keycode={keycode}, state={state}, is_editing={self.is_editing}")
        
        if not self.is_editing:
            logger.debug(f"Received key but not in edit mode: {keyval}")
            return False
        
        logger.debug(f"Key capture mode key: {keyval} (keycode: {keycode})")
        
        # if keyval == Gdk.KEY_Escape:
        #     # ESC取消编辑
        #     logger.debug(f"ESC cancel editing")
        #     self.finish_editing(False)
        #     return True
        # elif keyval == Gdk.KEY_Delete:
        #     # Delete删除最后一个最终捕获的按键
        #     logger.debug(f"Delete last final captured key")
        #     if self._remove_last_final_key():
        #         self._wrapped_widget.queue_draw()
        #     return True
        # else:
        # 获取按键（不包含修饰键状态，确保物理按键唯一性）
        key = self._get_key_name(keyval, keycode, 0)  # state=0，不包含修饰键状态
        if key:
            logger.debug(f"Key pressed: {key} (original keyval: {Gdk.keyval_name(keyval)})")
            self._add_key_to_realtime(key)
            self._wrapped_widget.queue_draw()
        return True
        
        # return False
    
    def finish_editing(self, apply_changes=True):
        """结束按键捕获"""
        if not self.is_editing:
            return
        
        self.is_editing = False
        
        if self.current_edit_region:
            # 区域编辑模式
            region = self.current_edit_region
            if not apply_changes:
                # 取消编辑，恢复原始按键
                logger.debug(f"Cancel region {region['id']} key capture")
                region['set_keys'](list(self.original_keys))
            else:
                logger.debug(f"Region {region['id']} key capture completed")
                # 应用更改已经在_update_final_capture中完成
                
                # 注册到全局的按键映射系统
                self._register_region_key_mapping()
            
            # 清理区域编辑状态
            self.current_edit_region = None
            self.original_keys = set()
            
        else:
            # 传统编辑模式
            current_text = getattr(self._wrapped_widget, 'text', '')
            if not apply_changes:
                # 取消编辑，恢复原始文本
                logger.debug(f"Cancel key capture: '{current_text}' -> '{self.original_text}'")
                if hasattr(self._wrapped_widget, 'text'):
                    self._wrapped_widget.text = self.original_text
                    
                # 恢复原始按键
                self._wrapped_widget.final_keys = self.original_keys.copy()
            else:
                logger.debug(f"Key capture completed: '{self.original_text}' -> '{current_text}'")
                logger.debug(f"Final captured keys: {self._wrapped_widget.final_keys}")
                
                # 如果退出时没有捕获任何按键且原来也是空的，就显示空文本
                if not self._wrapped_widget.final_keys and current_text == "Press keys to capture":
                    if hasattr(self._wrapped_widget, 'text'):
                        self._wrapped_widget.text = ""
                    logger.debug(f"No keys captured, restore empty text")
                
                # 如果有捕获到按键，注册到window的按键映射系统
                if self._wrapped_widget.final_keys:
                    self._register_key_mapping()
        
        # 清空实时捕获
        self.realtime_keys = set()
        self._wrapped_widget.queue_draw()
    
    def _register_key_mapping(self):
        """注册按键映射到全局管理器"""
        try:
            # 先清除旧的映射（如果有的话）
            key_mapping_manager = self._get_toplevel_window().key_mapping_manager
            key_mapping_manager.unsubscribe(self._wrapped_widget)
            
            # 自动读取widget的可重入属性
            reentrant = getattr(self._wrapped_widget, 'IS_REENTRANT', False)
            
            # 注册新的映射
            for key_combination in self._wrapped_widget.final_keys:
                key_mapping_manager = self._get_toplevel_window().key_mapping_manager
                success = key_mapping_manager.subscribe(
                    self._wrapped_widget, 
                    key_combination, 
                    reentrant=reentrant
                )
                if success:
                    logger.debug(f"Successfully register key mapping: {key_combination} -> {type(self._wrapped_widget).__name__} (reentrant={reentrant})")
                else:
                    logger.debug(f"Failed to register key mapping: {key_combination}")
                    
        except Exception as e:
            logger.error(f"Error registering key mapping: {e}")
    
    def _register_region_key_mapping(self):
        """注册区域按键映射到全局管理器"""
        try:
            region = self.current_edit_region
            if not region:
                return
            
            # 先取消当前区域的旧映射
            original_keys = self.original_keys
            for old_key_combination in original_keys:
                key_mapping_manager = self._get_toplevel_window().key_mapping_manager
                key_mapping_manager.unsubscribe_key(self._wrapped_widget, old_key_combination)
                logger.debug(f"Cancel region {region['id']} old key mapping: {old_key_combination}")
            
            current_keys = region['get_keys']()
            if not current_keys:
                logger.debug(f"Region {region['id']} has no keys, skip mapping registration")
                return
            
            # 自动读取widget的可重入属性
            reentrant = getattr(self._wrapped_widget, 'IS_REENTRANT', False)
            
            # 注册当前区域的新按键映射
            for key_combination in current_keys:
                key_mapping_manager = self._get_toplevel_window().key_mapping_manager
                success = key_mapping_manager.subscribe(
                    self._wrapped_widget, 
                    key_combination, 
                    reentrant=reentrant
                )
                if success:
                    logger.debug(f"Successfully register region key mapping: {key_combination} -> {type(self._wrapped_widget).__name__}[{region['id']}] (reentrant={reentrant})")
                else:
                    logger.debug(f"Failed to register region key mapping: {key_combination}")
                    
        except Exception as e:
            logger.error(f"Error registering region key mapping: {e}")
    
    def _get_toplevel_window(self):
        """获取顶级窗口"""
        widget = self._wrapped_widget
        while widget:
            if hasattr(widget, 'get_root'):
                root = widget.get_root()
                if root and isinstance(root, Gtk.Window):
                    return root
            
            if hasattr(widget, 'get_parent'):
                widget = widget.get_parent()
            else:
                break
                
        return None
    
    def cancel_editing(self):
        """取消按键捕获"""
        self.finish_editing(False)
    
    def get_captured_keys(self):
        """获取当前最终捕获的按键列表"""
        return self._wrapped_widget.final_keys.copy()
    



# 创建装饰器函数
Editable = parameterized_widget_decorator(EditableDecorator) 