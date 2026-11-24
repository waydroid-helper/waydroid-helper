#!/usr/bin/env python3
import math
import time
from enum import Enum
from gettext import pgettext
from typing import TYPE_CHECKING, cast

if TYPE_CHECKING:
    from cairo import Context, Surface
    from gi.repository import Gtk

from gi.repository import GLib

from waydroid_helper.controller.widgets.base import control_art as art

from waydroid_helper.controller.android.input import (AMotionEventAction,
                                                      AMotionEventButtons)
from waydroid_helper.controller.core import (
    ControllerRuntimeContext,
    Event,
    EventType,
    KeyCombination,
)
from waydroid_helper.controller.core.control_msg import InjectTouchEventMsg
from waydroid_helper.controller.core.handler.event_handlers import (
    InputEvent,
    InputEventType,
)
from waydroid_helper.controller.widgets.base.base_widget import BaseWidget
from waydroid_helper.controller.widgets.decorators import (Resizable,
                                                           ResizableDecorator)

class JoystickState(Enum):
    """摇杆状态枚举"""
    INACTIVE = "inactive"      # 未激活
    MOVING = "moving"          # 移动中（向边界移动）
    HOLDING = "holding"        # 在边界保持中


@Resizable(resize_strategy=ResizableDecorator.RESIZE_CENTER)
class RightClickToWalk(BaseWidget):
    """Right click widget for work or context menu actions"""

    CENTER_MAPPING_HINT = True
    MAPPING_MODE_WIDTH = 30
    MAPPING_MODE_HEIGHT = 30
    WIDGET_NAME = pgettext("Controller Widgets", "Right Click to Walk")
    WIDGET_DESCRIPTION = pgettext(
        "Controller Widgets",
        "Add to the game's movement wheel: hold and drag to steer, single-click to auto-walk to cursor. Ideal for MOBAs.",
    )

    def __init__(
        self,
        x: int = 0,
        y: int = 0,
        width: int = 150,
        height: int = 150,
        text: str = "",
        default_keys: set[KeyCombination] | None = None,
        *,
        runtime_context: ControllerRuntimeContext,
    ):
        super().__init__(
            x,
            y,
            min(width, height),
            min(width, height),
            pgettext("Controller Widgets", "Right Click to Walk"),
            text,
            min_width=25,
            min_height=25,
            runtime_context=runtime_context,
        )
        # Fix the default keys issue
        if default_keys is None:
            mouse_right_key = self.key_registry.get_by_name("Mouse_Right")
            if mouse_right_key is not None:
                default_keys = set([KeyCombination([mouse_right_key])])
            else:
                default_keys = set()
        
        self.set_default_keys(default_keys)
 
        self.event_bus.subscribe(EventType.MOUSE_MOTION, lambda event: (self.on_key_triggered(None, event.data), None)[1])

        # 摇杆状态管理
        self._joystick_state: JoystickState = JoystickState.INACTIVE
        self._current_position: tuple[float, float] = (x + width / 2, y + height / 2)
        self._target_position: tuple[float, float] = (x + width / 2, y + height / 2)
        self.is_reentrant: bool = True

        # 平滑移动系统
        self._timer_interval: int = 20  # ms
        self._move_steps_total: int = 6
        self._move_steps_count: int = 0
        self._move_timer: int | None = None

        # 点按/长按检测
        self._key_press_start_time: float = 0.0
        self._is_long_press: bool = False
        self._long_press_threshold: float = 0.3  # 300ms 区分点按和长按
        self._key_is_currently_pressed: bool = False  # 跟踪右键是否仍然按下

        # 边界保持系统
        self._hold_timer: int | None = None
        self._hold_duration: float = 0.0  # 保持时间（秒）
        self._max_hold_duration: float = 5.0  # 最大保持时间

        # 距离检测
        self._mouse_distance_from_center: float = 0.0

    def draw_widget_content(self, cr, width, height):
        x, y, r = width / 2, height / 2, min(width, height) / 2 - 6
        art.disc(cr, x, y, r, art.BODY, art.OUTLINE)
        art.disc(cr, x, y, r * .76, (.08, .09, .12, .52), art.OUTLINE, 1)
        art.compass(cr, x, y, r * .57)
        art.mouse(cr, x, y, min(15, r * .28), True)

    def draw_text_content(self, cr, width, height):
        pass

    def draw_mapping_mode_content(self, cr, width, height):
        art.mouse(cr, width / 2, height / 2, min(width, height) * .27, True)

    def _calculate_hold_duration(self, mouse_distance: float, window_center: tuple[float, float], window_size: tuple[int, int]) -> float:
        """根据鼠标距离窗口中心的距离计算保持时间"""
        # 计算窗口对角线长度作为最大距离
        max_distance = math.sqrt(window_size[0]**2 + window_size[1]**2) / 2
        
        # 距离比例（0-1）
        distance_ratio = min(mouse_distance / max_distance, 1.0)
        
        # 保持时间与距离成正比，最多5秒
        hold_duration = distance_ratio * self._max_hold_duration
        
        return max(0.5, hold_duration)  # 最少0.5秒

    def _start_smooth_move_to_boundary(self):
        """开始平滑移动到边界"""
        if self._move_timer:
            GLib.source_remove(self._move_timer)
        
        self._joystick_state = JoystickState.MOVING
        self._move_steps_count = 0
        self._move_timer = GLib.timeout_add(
            self._timer_interval, self._update_smooth_move
        )

    def _update_smooth_move(self) -> bool:
        """平滑移动的定时器回调"""
        if self._move_steps_count < self._move_steps_total:
            dx = self._target_position[0] - self._current_position[0]
            dy = self._target_position[1] - self._current_position[1]
            remaining_steps = self._move_steps_total - self._move_steps_count

            self._current_position = (
                self._current_position[0] + dx / remaining_steps,
                self._current_position[1] + dy / remaining_steps,
            )
            self._move_steps_count += 1
            
            if self._joystick_state == JoystickState.MOVING:
                self._emit_touch_event(AMotionEventAction.MOVE)
            
            return True  # Continue timer

        # 移动完成，到达边界
        self._current_position = self._target_position
        self._move_timer = None
        
        if self._joystick_state == JoystickState.MOVING:
            self._on_reached_boundary()
        
        return False  # Stop timer

    def _on_reached_boundary(self):
        """到达边界时的处理"""
        self._joystick_state = JoystickState.HOLDING
        
        # 如果是点按模式且用户已经松开右键，立即开始保持计时
        if not self._is_long_press and not self._key_is_currently_pressed:
            self._start_hold_timer()
        else:
            pass

    def _start_hold_timer(self):
        """开始保持计时器"""
        # 清除之前的计时器（如果有）
        if self._hold_timer:
            GLib.source_remove(self._hold_timer)
            self._hold_timer = None
        
        # 计算保持时间
        self._hold_duration = self._calculate_hold_duration(
            self._mouse_distance_from_center, 
            self._get_window_center(),
            self._get_window_size()
        )
        
        # 启动计时器
        self._hold_timer = GLib.timeout_add(
            int(self._hold_duration * 1000), 
            self._on_hold_timeout
        )

    def _on_hold_timeout(self) -> bool:
        """保持时间到达后的回调"""
        self._hold_timer = None
        self._finish_joystick_action()
        return False  # Stop timer

    def _instant_move_to_boundary(self, new_trigger_time: float):
        """瞬间移动到边界（保持状态下的新触发）"""
        self._current_position = self._target_position
        self._emit_touch_event(AMotionEventAction.MOVE)
        
        # 更新触发时间和距离信息
        self._key_press_start_time = new_trigger_time
        self._is_long_press = False  # 重置长按状态，等待新的判断
        
        # 清除之前的保持计时器（如果有）
        if self._hold_timer:
            GLib.source_remove(self._hold_timer)
            self._hold_timer = None
        

    def stop_gesture(self):
        if self._joystick_state != JoystickState.INACTIVE:
            self._finish_joystick_action()

    def _finish_joystick_action(self):
        """完成摇杆动作，发送UP事件并重置"""
        self._emit_touch_event(AMotionEventAction.UP)
        self._reset_joystick()

    def _reset_joystick(self):
        """重置摇杆状态"""
        self._joystick_state = JoystickState.INACTIVE
        self._current_position = (self.center_x, self.center_y)
        
        # 清理定时器
        if self._move_timer:
            GLib.source_remove(self._move_timer)
            self._move_timer = None
        if self._hold_timer:
            GLib.source_remove(self._hold_timer)
            self._hold_timer = None
        
        # 释放指针ID
        self.pointer_id_manager.release(self)
        

    def _get_window_center(self) -> tuple[float, float]:
        """获取窗口中心坐标"""
        w, h = self.screen_geometry.get_host_resolution()
        return (w / 2, h / 2)

    def _get_window_size(self) -> tuple[int, int]:
        """获取窗口大小"""
        return self.screen_geometry.get_host_resolution()

    def _emit_touch_event(
        self, action: AMotionEventAction, position: tuple[float, float] | None = None
    ):
        pos = position if position is not None else self._current_position
        w, h = self.screen_geometry.get_host_resolution()
        device_resolution = self.screen_geometry.get_device_resolution_for_client(w, h)
        pressure = 1.0 if action != AMotionEventAction.UP else 0.0
        buttons = AMotionEventButtons.PRIMARY if action != AMotionEventAction.UP else 0
        pointer_id = self.pointer_id_manager.get_allocated_id(self)
        if pointer_id is None:
            return

        msg = InjectTouchEventMsg(
            action=action,
            pointer_id=pointer_id,
            position=(int(pos[0]), int(pos[1]), w, h),
            device_resolution=device_resolution,
            pressure=pressure,
            action_button=AMotionEventButtons.PRIMARY,
            buttons=buttons,
        )
        self.event_bus.emit(Event(EventType.CONTROL_MSG, self, msg))

    def _get_target_position(
        self,
        cx: float,
        cy: float,
        r: float,
        x0: float,
        y0: float,
        x1: float,
        y1: float,
    ) -> tuple[float, float]:
        """计算目标位置（圆边界上的交点）"""
        dx = x1 - x0
        dy = y1 - y0
        length = math.hypot(dx, dy)
        if length == 0:
            return (cx, cy)  # 如果没有方向，返回中心点

        # 单位方向向量
        dx /= length
        dy /= length

        # 从圆心出发沿着方向 (dx, dy)，走 r 的距离
        px = cx + dx * r
        py = cy + dy * r

        return (px, py)

    def on_key_triggered(
        self,
        key_combination: KeyCombination | None = None,
        event: "InputEvent | None" = None,
    ):
        if not event or event.position is None:
            return False

        current_time = time.time()
        
        # 获取鼠标位置和窗口信息
        mouse_x, mouse_y = event.position
        window_center_x, window_center_y = self._get_window_center()
        
        # 计算鼠标距离窗口中心的距离
        self._mouse_distance_from_center = math.hypot(
            mouse_x - window_center_x, 
            mouse_y - window_center_y
        )
        
        # 计算目标位置
        widget_radius = self.width / 2
        self._target_position = self._get_target_position(
            self.center_x,
            self.center_y,
            widget_radius,
            window_center_x,
            window_center_y,
            mouse_x,
            mouse_y,
        )

        # 判断是点击事件还是移动事件
        is_click_event = event.event_type == InputEventType.MOUSE_PRESS
        is_motion_event = event.event_type == InputEventType.MOUSE_MOTION
        
        if self._joystick_state == JoystickState.INACTIVE:
            # 首次激活 - 只有点击事件才能激活
            if is_click_event:
                self._key_press_start_time = current_time
                self._is_long_press = False
                self._key_is_currently_pressed = True
                self._joystick_state = JoystickState.MOVING
                
                # 分配指针ID并发送DOWN事件
                pointer_id = self.pointer_id_manager.allocate(self)
                if pointer_id is None:
                    return False
                
                self._current_position = (self.center_x, self.center_y)
                self._emit_touch_event(AMotionEventAction.DOWN, position=self._current_position)
                
                # 开始平滑移动到边界
                self._start_smooth_move_to_boundary()
                
            else:
                # 移动事件在未激活状态下不处理
                return False
            
        elif self._joystick_state == JoystickState.MOVING:
            if is_click_event:
                # 移动中收到新点击，重置触发时间和长按状态
                self._key_press_start_time = current_time
                self._is_long_press = False
            elif is_motion_event:
                # 移动事件只更新目标位置，不重置计时
                pass
            
        elif self._joystick_state == JoystickState.HOLDING:
            if is_click_event:
                # 保持状态下收到新点击，瞬移并重置状态
                self._instant_move_to_boundary(current_time)
                self._key_is_currently_pressed = True
            elif is_motion_event:
                # 保持状态下的移动事件，瞬移但不重置计时状态
                self._current_position = self._target_position
                self._emit_touch_event(AMotionEventAction.MOVE)

        return True

    def on_key_released(
        self,
        key_combination: KeyCombination | None = None,
        event: "InputEvent | None" = None,
    ):
        """当映射的键释放时"""
        if self._joystick_state == JoystickState.INACTIVE:
            return True

        current_time = time.time()
        press_duration = current_time - self._key_press_start_time
        self._key_is_currently_pressed = False
        
        # 判断是点按还是长按
        if press_duration >= self._long_press_threshold:
            self._is_long_press = True

        if self._is_long_press:
            # 长按模式：立即结束
            self._finish_joystick_action()
        else:
            # 点按模式：松开右键后开始保持计时
            if self._joystick_state == JoystickState.MOVING:
                # 还在移动中，设置标记，等移动完成后开始计时
                pass
            elif self._joystick_state == JoystickState.HOLDING:
                # 已经在边界，立即开始保持计时
                self._start_hold_timer()

        return True

    @property
    def center_x(self):
        return self.x + self.width / 2

    @property
    def center_y(self):
        return self.y + self.height / 2
