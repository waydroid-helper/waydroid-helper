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

from waydroid_helper.controller.android.input import (AMotionEventAction,
                                                      AMotionEventButtons)
from waydroid_helper.controller.core import (Event, EventType, KeyCombination,
                                             EventBus, KeyRegistry,
                                             PointerIdManager)
from waydroid_helper.controller.core.control_msg import InjectTouchEventMsg, ScreenInfo
from waydroid_helper.controller.core.handler.event_handlers import InputEvent
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
        event_bus: EventBus | None = None,
        pointer_id_manager: PointerIdManager | None = None,
        key_registry: KeyRegistry | None = None,
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
            event_bus=event_bus,
            pointer_id_manager=pointer_id_manager,
            key_registry=key_registry,
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

        self.screen_info = ScreenInfo()

    def draw_widget_content(self, cr: "Context[Surface]", width: int, height: int):
        """绘制组件的具体内容 - 圆形背景，上下左右箭头，中心鼠标图标"""
        # 计算圆心和半径
        center_x = width / 2
        center_y = height / 2
        radius = min(width, height) / 2 - 8  # 留出边距，与 dpad 一致

        # 绘制外圆背景
        cr.set_source_rgba(0.4, 0.4, 0.4, 0.7)
        cr.arc(center_x, center_y, radius, 0, 2 * math.pi)
        cr.fill()

        # 绘制外圆边框
        cr.set_source_rgba(0.2, 0.2, 0.2, 0.9)
        cr.set_line_width(2)
        cr.arc(center_x, center_y, radius, 0, 2 * math.pi)
        cr.stroke()

        # 绘制上下左右箭头
        self._draw_direction_arrows(cr, center_x, center_y, radius)

        # 绘制中心圆 - 与 dpad 相同的样式
        inner_radius = radius * 0.3
        cr.set_source_rgba(0.6, 0.6, 0.6, 0.8)
        cr.arc(center_x, center_y, inner_radius, 0, 2 * math.pi)
        cr.fill()

        # 在中心圆里绘制鼠标图标
        self._draw_mouse_in_center(cr, center_x, center_y, inner_radius)

    def _draw_direction_arrows(
        self, cr: "Context[Surface]", center_x: float, center_y: float, radius: float
    ):
        """绘制上下左右四个方向的好看箭头 - 实心三角形样式"""
        arrow_distance = radius * 0.65  # 箭头距离中心的距离
        arrow_size = radius * 0.12  # 箭头大小

        # 箭头位置
        positions = {
            "up": (center_x, center_y - arrow_distance),
            "down": (center_x, center_y + arrow_distance),
            "left": (center_x - arrow_distance, center_y),
            "right": (center_x + arrow_distance, center_y),
        }

        # 设置箭头颜色 - 白色带轻微透明度
        cr.set_source_rgba(1.0, 1.0, 1.0, 0.9)

        # 上箭头 ↑ - 实心三角形
        x, y = positions["up"]
        cr.move_to(x, y - arrow_size)  # 顶点
        cr.line_to(x - arrow_size * 0.6, y + arrow_size * 0.5)  # 左下
        cr.line_to(x + arrow_size * 0.6, y + arrow_size * 0.5)  # 右下
        cr.close_path()
        cr.fill()

        # 下箭头 ↓ - 实心三角形
        x, y = positions["down"]
        cr.move_to(x, y + arrow_size)  # 底点
        cr.line_to(x - arrow_size * 0.6, y - arrow_size * 0.5)  # 左上
        cr.line_to(x + arrow_size * 0.6, y - arrow_size * 0.5)  # 右上
        cr.close_path()
        cr.fill()

        # 左箭头 ← - 实心三角形
        x, y = positions["left"]
        cr.move_to(x - arrow_size, y)  # 左点
        cr.line_to(x + arrow_size * 0.5, y - arrow_size * 0.6)  # 右上
        cr.line_to(x + arrow_size * 0.5, y + arrow_size * 0.6)  # 右下
        cr.close_path()
        cr.fill()

        # 右箭头 → - 实心三角形
        x, y = positions["right"]
        cr.move_to(x + arrow_size, y)  # 右点
        cr.line_to(x - arrow_size * 0.5, y - arrow_size * 0.6)  # 左上
        cr.line_to(x - arrow_size * 0.5, y + arrow_size * 0.6)  # 左下
        cr.close_path()
        cr.fill()

        # 可选：添加轻微的边框让箭头更突出
        cr.set_source_rgba(0.0, 0.0, 0.0, 0.3)  # 半透明黑色边框
        cr.set_line_width(0.5)

        # 重新绘制上箭头的边框
        x, y = positions["up"]
        cr.move_to(x, y - arrow_size)
        cr.line_to(x - arrow_size * 0.6, y + arrow_size * 0.5)
        cr.line_to(x + arrow_size * 0.6, y + arrow_size * 0.5)
        cr.close_path()
        cr.stroke()

        # 重新绘制下箭头的边框
        x, y = positions["down"]
        cr.move_to(x, y + arrow_size)
        cr.line_to(x - arrow_size * 0.6, y - arrow_size * 0.5)
        cr.line_to(x + arrow_size * 0.6, y - arrow_size * 0.5)
        cr.close_path()
        cr.stroke()

        # 重新绘制左箭头的边框
        x, y = positions["left"]
        cr.move_to(x - arrow_size, y)
        cr.line_to(x + arrow_size * 0.5, y - arrow_size * 0.6)
        cr.line_to(x + arrow_size * 0.5, y + arrow_size * 0.6)
        cr.close_path()
        cr.stroke()

        # 重新绘制右箭头的边框
        x, y = positions["right"]
        cr.move_to(x + arrow_size, y)
        cr.line_to(x - arrow_size * 0.5, y - arrow_size * 0.6)
        cr.line_to(x - arrow_size * 0.5, y + arrow_size * 0.6)
        cr.close_path()
        cr.stroke()

    def _draw_mouse_in_center(
        self,
        cr: "Context[Surface]",
        center_x: float,
        center_y: float,
        circle_radius: float,
    ):
        """在中心圆内绘制鼠标图标 - 右键蓝色高亮"""
        # 鼠标尺寸适应中心圆
        mouse_w = circle_radius * 1.2  # 适当大小，不超出中心圆
        mouse_h = mouse_w * 1.25  # 稍微拉高，接近真实鼠标比例
        border_width = 1.0

        # 1. 先绘制整个鼠标为白色填充
        cr.save()
        cr.translate(center_x, center_y)
        cr.scale(mouse_w / 2, mouse_h / 2)
        cr.set_source_rgba(1, 1, 1, 1)  # 白色背景
        cr.arc(0, 0, 1, 0, 2 * math.pi)
        cr.fill()
        cr.restore()

        # 2. 右键（右上区域）用蓝色覆盖 - 修正为右键蓝色
        cr.save()
        cr.translate(center_x, center_y)
        cr.scale(mouse_w / 2, mouse_h / 2)
        cr.set_source_rgba(0.2, 0.6, 1.0, 1.0)  # 蓝色
        cr.move_to(0, 0)
        cr.arc(0, 0, 1, math.pi * 1.5, math.pi * 2)  # 右上区域 (0° 到 90°)
        cr.line_to(0, 0)
        cr.close_path()
        cr.fill()
        cr.restore()

        # 3. 鼠标外轮廓（黑色椭圆描边）
        cr.set_line_width(border_width)
        cr.set_source_rgba(0, 0, 0, 1)
        cr.save()
        cr.translate(center_x, center_y)
        cr.scale(mouse_w / 2, mouse_h / 2)
        cr.arc(0, 0, 1, 0, 2 * math.pi)
        cr.restore()
        cr.stroke()

        # 4. 绘制横线分割（上半/下半）
        mouse_x = center_x - mouse_w / 2
        mouse_y = center_y - mouse_h / 2
        cr.set_line_width(border_width)
        cr.set_source_rgba(0, 0, 0, 1)
        split_y = center_y
        cr.move_to(mouse_x, split_y)
        cr.line_to(mouse_x + mouse_w, split_y)
        cr.stroke()

        # 5. 绘制竖线分割（上半左右键）
        cr.set_line_width(border_width)
        cr.set_source_rgba(0, 0, 0, 1)
        split_x = center_x
        cr.move_to(split_x, mouse_y)
        cr.line_to(split_x, split_y)
        cr.stroke()

        # 清除路径，避免影响后续绘制
        cr.new_path()

    def draw_text_content(self, cr: "Context[Surface]", width: int, height: int):
        """重写文本绘制 - 鼠标图标已在 draw_widget_content 中绘制，这里为空"""

    def draw_selection_border(self, cr: "Context[Surface]", width: int, height: int):
        """Override selection border drawing - circular border for circular button"""
        center_x = width / 2
        center_y = height / 2
        radius = min(width, height) / 2 - 5

        # Draw circular selection border
        cr.set_source_rgba(0.2, 0.6, 1.0, 0.8)
        cr.set_line_width(3)
        cr.arc(center_x, center_y, radius + 3, 0, 2 * math.pi)
        cr.stroke()

    def draw_mapping_mode_background(
        self, cr: "Context[Surface]", width: int, height: int
    ):
        """Mapping mode background drawing - circular background"""
        center_x = width / 2
        center_y = height / 2
        radius = min(width, height) / 2 - 2  # Reduce margin

        # Draw single background color circle
        cr.set_source_rgba(0.6, 0.6, 0.6, 0.5)  # Unified semi-transparent gray
        cr.arc(center_x, center_y, radius, 0, 2 * math.pi)
        cr.fill()

    def draw_mapping_mode_content(
        self, cr: "Context[Surface]", width: int, height: int
    ):
        """映射模式下的内容绘制 - 只显示鼠标图标，与 fire 组件类似，右键蓝色高亮"""
        # 在映射模式下只绘制鼠标图标，尺寸与 fire 组件一致
        center_x = width / 2
        center_y = height / 2

        # 鼠标主体参数（与 fire.py 相同的尺寸）
        mouse_w = min(width, height) * 0.38
        mouse_h = mouse_w * 1.25  # 稍微拉高，接近真实鼠标比例
        mouse_x = center_x - mouse_w / 2
        mouse_y = center_y - mouse_h / 2
        border_width = 1.2

        # 1. 先绘制整个鼠标为白色填充
        cr.save()
        cr.translate(center_x, center_y)
        cr.scale(mouse_w / 2, mouse_h / 2)
        cr.set_source_rgba(1, 1, 1, 1)  # 白色背景
        cr.arc(0, 0, 1, 0, 2 * math.pi)
        cr.fill()
        cr.restore()

        # 2. 右键（右上区域）用蓝色覆盖 - 修正为右键蓝色
        cr.save()
        cr.translate(center_x, center_y)
        cr.scale(mouse_w / 2, mouse_h / 2)
        cr.set_source_rgba(0.2, 0.6, 1.0, 1.0)  # 蓝色
        cr.move_to(0, 0)
        cr.arc(0, 0, 1, math.pi * 1.5, math.pi * 2)  # 右上区域 (270° 到 360°)
        cr.line_to(0, 0)
        cr.close_path()
        cr.fill()
        cr.restore()

        # 3. 鼠标外轮廓（黑色椭圆描边）
        cr.set_line_width(border_width)
        cr.set_source_rgba(0, 0, 0, 1)
        cr.save()
        cr.translate(center_x, center_y)
        cr.scale(mouse_w / 2, mouse_h / 2)
        cr.arc(0, 0, 1, 0, 2 * math.pi)
        cr.restore()
        cr.stroke()

        # 4. 绘制横线分割（上半/下半）
        cr.set_line_width(border_width)
        cr.set_source_rgba(0, 0, 0, 1)
        split_y = center_y
        cr.move_to(mouse_x, split_y)
        cr.line_to(mouse_x + mouse_w, split_y)
        cr.stroke()

        # 5. 绘制竖线分割（上半左右键）
        cr.set_line_width(border_width)
        cr.set_source_rgba(0, 0, 0, 1)
        split_x = center_x
        cr.move_to(split_x, mouse_y)
        cr.line_to(split_x, split_y)
        cr.stroke()

        # 清除路径，避免影响后续绘制
        cr.new_path()

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
        w, h = self.screen_info.get_host_resolution()
        return (w / 2, h / 2)

    def _get_window_size(self) -> tuple[int, int]:
        """获取窗口大小"""
        return self.screen_info.get_host_resolution()

    def _emit_touch_event(
        self, action: AMotionEventAction, position: tuple[float, float] | None = None
    ):
        pos = position if position is not None else self._current_position
        w, h = self.screen_info.get_host_resolution()
        pressure = 1.0 if action != AMotionEventAction.UP else 0.0
        buttons = AMotionEventButtons.PRIMARY if action != AMotionEventAction.UP else 0
        pointer_id = self.pointer_id_manager.get_allocated_id(self)
        if pointer_id is None:
            return

        msg = InjectTouchEventMsg(
            action=action,
            pointer_id=pointer_id,
            position=(int(pos[0]), int(pos[1]), w, h),
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
        is_click_event = event.event_type == "mouse_press"
        is_motion_event = event.event_type == "mouse_motion"
        
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
    def mapping_start_x(self):
        return self.x + self.width / 2 - self.MAPPING_MODE_WIDTH / 2

    @property
    def mapping_start_y(self):
        return self.y + self.height / 2 - self.MAPPING_MODE_HEIGHT / 2

    @property
    def center_x(self):
        return self.x + self.width / 2

    @property
    def center_y(self):
        return self.y + self.height / 2
