from __future__ import annotations

import asyncio
import math
from enum import Enum
from gettext import pgettext
from typing import TYPE_CHECKING, Callable, TypedDict, cast

from waydroid_helper.controller.core.handler.event_handlers import InputEvent

if TYPE_CHECKING:
    from cairo import Context, Surface
    from gi.repository import Gtk
    from waydroid_helper.controller.widgets.base.base_widget import EditableRegion

from waydroid_helper.controller.android.input import (AMotionEventAction,
                                                      AMotionEventButtons)
from waydroid_helper.controller.core import KeyCombination, KeyRegistry
from waydroid_helper.controller.core.control_msg import InjectTouchEventMsg, ScreenInfo
from waydroid_helper.controller.core.event_bus import (Event, EventType,
                                                       EventBus)
from waydroid_helper.controller.core.utils import PointerIdManager
from waydroid_helper.controller.widgets import BaseWidget
from waydroid_helper.controller.widgets.config import create_dropdown_config
from waydroid_helper.controller.widgets.decorators import (Editable, Resizable,
                                                           ResizableDecorator)

class MovementMode(Enum):
    SMOOTH = "smooth"
    INSTANT = "instant"

class MovementState(Enum):
    """方向盘移动状态"""
    IDLE = "idle"           # 空闲状态
    MOVING = "moving"       # 正在移动
    STOPPING = "stopping"   # 正在停止

class DirectionalPadEditableRegion(TypedDict):
    """可编辑区域信息"""

    center: tuple[float, float]
    size: float
    key: KeyCombination | None
    name: str


# 使用带参数的 Resizable 装饰器，设置中心缩放策略
@Resizable(resize_strategy=ResizableDecorator.RESIZE_CENTER)
@Editable(max_keys=1)
class DirectionalPad(BaseWidget):
    """方向键组件"""

    MAPPING_MODE_WIDTH = 80
    MAPPING_MODE_HEIGHT = 80
    WIDGET_NAME = pgettext("Controller Widgets", "Directional Pad")
    WIDGET_DESCRIPTION = pgettext(
        "Controller Widgets",
        "Drag and place it onto the game's movement wheel to control walking direction. After assigning keys, drag the dotted frame to resize the button; make sure the blue frame of the directional pad matches the size of the game wheel.",
    )

    # 方向常量
    DIRECTIONS = ["up", "down", "left", "right"]
    DEFAULT_KEYS = {"up": "W", "down": "S", "left": "A", "right": "D"}

    def __init__(
        self,
        x: int = 0,
        y: int = 0,
        width: int = 150,
        height: int = 150,
        text: str = "",
        direction_keys: dict[str, KeyCombination | None] | None = None,
        event_bus: EventBus | None = None,
        pointer_id_manager: PointerIdManager | None = None,
        key_registry: KeyRegistry | None = None,
    ):
        super().__init__(
            x,
            y,
            min(width, height),
            min(width, height),
            pgettext("Controller Widgets", "Directional Pad"),
            text,
            min_width=60,
            min_height=60,
            event_bus = event_bus,
            pointer_id_manager = pointer_id_manager,
            key_registry = key_registry,
        )
        self.direction_keys: dict[str, KeyCombination | None] = {
            "up": None,
            "down": None,
            "left": None,
            "right": None,
        }
        self._set_default_keys()
        if direction_keys is not None:
            self.direction_keys = {
                "up": direction_keys["up"],
                "down": direction_keys["down"],
                "left": direction_keys["left"],
                "right": direction_keys["right"],
            }

        # 收集所有按键到 final_keys 中（用于兼容性和显示）
        all_keys: set[KeyCombination] = set()
        for key_combo in self.direction_keys.values():
            if key_combo:
                all_keys.add(key_combo)
        
        self.set_default_keys(all_keys)

        self.pressed_directions: dict[str, bool] = {
            direction: False for direction in self.DIRECTIONS
        }

        self._joystick_active: bool = False  # 摇杆是否已离开中心

        self._current_position: tuple[float, float] = (x + width / 2, y + height / 2)

        # region 异步移动系统
        self._movement_state: MovementState = MovementState.IDLE
        self._state_lock = asyncio.Lock()
        self._movement_task: asyncio.Task[None] | None = None

        # 移动参数
        self._move_interval: float = 0.02  # 20ms in seconds
        self._move_steps_total: int = 6
        self._target_position: tuple[float, float] = self._current_position

        self._target_points_map: dict[
            tuple[bool, bool, bool, bool], Callable[[], tuple[float, float]]
        ] = {
            (True, False, False, False): lambda: self.top_with_factor,  # Up
            (False, True, False, False): lambda: self.left_with_factor,  # Left
            (False, False, True, False): lambda: self.bottom_with_factor,  # Down
            (False, False, False, True): lambda: self.right_with_factor,  # Right
            (True, True, False, False): lambda: self.top_left_with_factor,
            (True, False, False, True): lambda: self.top_right_with_factor,
            (False, True, True, False): lambda: self.bottom_left_with_factor,
            (False, False, True, True): lambda: self.bottom_right_with_factor,
            # 3-key combos resolve to the middle key's axis
            (True, True, True, False): lambda: self.left_with_factor,
            (True, True, False, True): lambda: self.top_with_factor,
            (True, False, True, True): lambda: self.right_with_factor,
            (False, True, True, True): lambda: self.bottom_with_factor,
            # 4-key combo returns to center
            (True, True, True, True): lambda: self.center,
        }

        # 初始化编辑区域字典
        self.edit_regions: dict[str, DirectionalPadEditableRegion] = {}

        

        # 移动模式设置
        # self._movement_mode: MovementMode = MovementMode.SMOOTH
        movement_mode_config = create_dropdown_config(
            key="movement_mode",
            label=pgettext("Controller Widgets", "Operating Method"),
            options=[MovementMode.SMOOTH.value, MovementMode.INSTANT.value],
            option_labels={
                MovementMode.SMOOTH.value: pgettext("Controller Widgets", "Slide control"),
                MovementMode.INSTANT.value: pgettext("Controller Widgets", "Click control"),
            },
            value=MovementMode.SMOOTH.value,
            description=pgettext("Controller Widgets", "Adjusts the operating method of the directional pad")
        )
        self.add_config_item(movement_mode_config)
        self.add_config_change_callback("movement_mode", lambda key, value, restoring: self.set_movement_mode(value))
        self.swipehold_radius_factor = 1

        self.event_bus.subscribe(EventType.SWIPEHOLD_RADIUS, self.on_swipehold_radius_changed, subscriber=self)
        self.screen_info = ScreenInfo()
    
    def on_swipehold_radius_changed(self, event: Event[float]):
        """滑动半径系数设置"""
        self.swipehold_radius_factor = event.data

        # 如果摇杆处于激活状态且有按键按下，立即移动到新的目标位置
        if self._joystick_active and any(self.pressed_directions.values()):
            new_target = self._get_target_position()
            self._move_to(new_target, smooth=False)     

    def set_movement_params(self, interval: int, max_steps: int):
        """设置平滑移动的参数"""
        self._move_interval = interval / 1000.0  # 转换为秒
        self._move_steps_total = max_steps

    def set_movement_mode(self, mode: str):
        if mode not in [MovementMode.SMOOTH.value, MovementMode.INSTANT.value]:
            # self._movement_mode = MovementMode.SMOOTH
            return
        # self._movement_mode = MovementMode(mode)

    def __del__(self):
        """清理异步任务"""
        self._cancel_movement_task()

    def _cancel_movement_task(self) -> None:
        """取消当前的移动任务"""
        if self._movement_task and not self._movement_task.done():
            self._movement_task.cancel()
            self._movement_task = None

    async def _get_movement_state(self) -> MovementState:
        """获取当前移动状态"""
        async with self._state_lock:
            return self._movement_state

    async def _set_movement_state(self, state: MovementState) -> None:
        """设置移动状态"""
        async with self._state_lock:
            self._movement_state = state

    def _get_target_position(self) -> tuple[float, float]:
        """根据当前按键状态获取目标位置"""
        key_state = tuple(
            self.pressed_directions[d] for d in ["up", "left", "down", "right"]
        )
        key_state = cast(tuple[bool, bool, bool, bool], key_state)
        return self._target_points_map.get(key_state, lambda: self.center)()

    def _move_to(self, target: tuple[float, float], smooth: bool = False):
        """统一的移动入口点 - 创建异步任务"""
        self._target_position = target

        # 取消现有的移动任务
        self._cancel_movement_task()

        # 根据移动模式决定是否使用平滑移动
        use_smooth = smooth and self.get_config_value("movement_mode") == MovementMode.SMOOTH.value

        if use_smooth:
            # 创建平滑移动任务
            self._movement_task = asyncio.create_task(
                self._smooth_move_to(target)
            )
        else:
            # 创建瞬间移动任务
            self._movement_task = asyncio.create_task(
                self._instant_move_to(target)
            )

    async def _instant_move_to(self, target: tuple[float, float]) -> None:
        """瞬间移动到目标位置"""
        try:
            await self._set_movement_state(MovementState.MOVING)
            self._current_position = target
            self.queue_draw()
            if self._joystick_active:
                self._emit_touch_event(AMotionEventAction.MOVE)
        except Exception:
            pass
        finally:
            await self._set_movement_state(MovementState.IDLE)

    async def _smooth_move_to(self, target: tuple[float, float]) -> None:
        """平滑移动到目标位置"""
        try:
            await self._set_movement_state(MovementState.MOVING)

            start_position = self._current_position
            move_steps_count = 0

            while move_steps_count < self._move_steps_total:
                # 检查是否被取消
                current_state = await self._get_movement_state()
                if current_state == MovementState.STOPPING:
                    break

                # 计算当前步骤的位置
                progress = (move_steps_count + 1) / self._move_steps_total
                dx = target[0] - start_position[0]
                dy = target[1] - start_position[1]

                self._current_position = (
                    start_position[0] + dx * progress,
                    start_position[1] + dy * progress,
                )

                if self._joystick_active:
                    self._emit_touch_event(AMotionEventAction.MOVE)
                self.queue_draw()

                move_steps_count += 1

                # 等待下一帧
                if move_steps_count < self._move_steps_total:
                    await asyncio.sleep(self._move_interval)

            # 确保到达最终位置
            self._current_position = target
            self.queue_draw()

        except Exception:
            pass
        finally:
            await self._set_movement_state(MovementState.IDLE)

    def _set_default_keys(self):
        """为未设置的方向设置默认按键"""
        for direction in self.DIRECTIONS:
            if not self.direction_keys[direction]:
                key_name = self.DEFAULT_KEYS[direction]
                key = self.key_registry.get_by_name(key_name)
                if key:
                    self.direction_keys[direction] = KeyCombination([key])

    def _update_edit_regions(self):
        """更新四个方向的编辑区域"""
        # 计算方向按钮的位置（与绘制逻辑保持一致）
        center_x = self.width / 2
        center_y = self.height / 2
        radius = min(self.width, self.height) / 2 - 8
        inner_radius = radius * 0.3
        button_radius = (radius + inner_radius) / 2
        button_size = (radius - inner_radius) / 2

        # 方向位置计算
        direction_positions = {
            "up": (center_x, center_y - button_radius),
            "down": (center_x, center_y + button_radius),
            "left": (center_x - button_radius, center_y),
            "right": (center_x + button_radius, center_y),
        }

        # 存储编辑区域信息
        self.edit_regions = {}
        for direction in self.DIRECTIONS:
            self.edit_regions[direction] = {
                "center": direction_positions[direction],
                "size": button_size,
                "key": self.direction_keys[direction],
                "name": f"{direction}方向",
            }

    def get_editable_regions(self) -> list[EditableRegion]:
        """重写：返回四个方向的可编辑区域"""
        self._update_edit_regions()
        regions: list[EditableRegion] = []

        for direction in self.DIRECTIONS:
            region_info = self.edit_regions.get(direction)
            if not region_info:
                continue

            center = region_info.get("center")
            size = region_info.get("size")
            name = region_info.get("name", direction)

            if center and size:
                center_x, center_y = center

                # 计算圆形区域的边界矩形
                bounds = (
                    int(center_x - size),
                    int(center_y - size),
                    int(size * 2),
                    int(size * 2),
                )

                regions.append(
                    {
                        "id": direction,
                        "name": name,
                        "bounds": bounds,
                        "get_keys": self._make_key_getter(direction),
                        "set_keys": self._make_key_setter(direction),
                    }
                )

        return regions

    def _make_key_getter(self, direction: str):
        """为指定方向创建按键获取函数"""

        def get_keys() -> set[KeyCombination]:
            key = self.direction_keys.get(direction)
            return {key} if key else set()

        return get_keys

    def _make_key_setter(self, direction: str) -> Callable[[set[KeyCombination]], None]:
        """为指定方向创建按键设置函数"""

        def set_keys(keys: set[KeyCombination]):
            # 设置对应方向的按键（取第一个，因为现在只支持单个按键）
            if keys:
                self.direction_keys[direction] = next(iter(keys))
            else:
                self.direction_keys[direction] = None

            self._update_final_keys()

            # 重绘以更新显示
            self.queue_draw()

        return set_keys

    def _update_final_keys(self):
        """更新总的按键列表（用于兼容性）"""
        all_keys: set[KeyCombination] = set()
        for key_combo in self.direction_keys.values():
            if key_combo:
                all_keys.add(key_combo)
        self.final_keys: set[KeyCombination] = all_keys

    def get_all_key_mappings(self) -> dict[KeyCombination, str]:
        """获取所有按键映射的字典，用于注册到window系统"""
        mappings: dict[KeyCombination, str] = {}
        for direction, key_combo in self.direction_keys.items():
            if key_combo:
                mappings[key_combo] = direction
        return mappings

    def draw_direction_buttons(
        self,
        cr: "Context[Surface]",
        center_x: float,
        center_y: float,
        outer_radius: float,
        inner_radius: float,
    ):
        """绘制四个方向的按钮区域"""
        button_radius = (outer_radius + inner_radius) / 2
        button_size = (outer_radius - inner_radius) / 2

        # 方向位置计算
        direction_positions = {
            "up": (center_x, center_y - button_radius),
            "down": (center_x, center_y + button_radius),
            "left": (center_x - button_radius, center_y),
            "right": (center_x + button_radius, center_y),
        }

        for direction in self.DIRECTIONS:
            x, y = direction_positions[direction]
            key = self.direction_keys[direction]
            is_pressed = self.pressed_directions[direction]

            # 根据按下状态选择颜色
            if is_pressed:
                cr.set_source_rgba(0.2, 0.7, 0.2, 0.9)  # 按下时为绿色
            else:
                cr.set_source_rgba(0.5, 0.5, 0.5, 0.8)  # 默认为灰色

            # 绘制方向按钮圆圈
            cr.arc(x, y, button_size, 0, 2 * math.pi)
            cr.fill()

            # 绘制方向按钮边框
            cr.set_source_rgba(0.3, 0.3, 0.3, 1.0)
            cr.set_line_width(1)
            cr.arc(x, y, button_size, 0, 2 * math.pi)
            cr.stroke()

            # 绘制按键文字
            key_text = str(key) if key else ""

            cr.set_source_rgba(1, 1, 1, 1)  # 白色文字
            cr.select_font_face("Arial", 0, 1)

            # 根据按键长度调整字体大小
            if len(key_text) <= 1:
                cr.set_font_size(14)
            elif len(key_text) <= 3:
                cr.set_font_size(10)
            else:
                cr.set_font_size(8)

            text_extents = cr.text_extents(key_text)
            text_x = x - text_extents.width / 2
            text_y = y + text_extents.height / 2
            cr.move_to(text_x, text_y)
            cr.show_text(key_text)
            cr.new_path()  # 清除路径

    def draw_text_content(self, cr: "Context[Surface]", width: int, height: int):
        """重写文本绘制 - 显示按键映射信息"""

    def draw_selection_border(self, cr: "Context[Surface]", width: int, height: int):
        """重写选择边框绘制 - 绘制圆形边框适配圆形方向盘"""
        center_x = width / 2
        center_y = height / 2
        radius = min(width, height) / 2 - 5

        # 绘制圆形选择边框
        cr.set_source_rgba(0.2, 0.6, 1.0, 0.8)
        cr.set_line_width(3)
        cr.arc(center_x, center_y, radius + 3, 0, 2 * math.pi)
        cr.stroke()

    def draw_mapping_mode_background(
        self, cr: "Context[Surface]", width: int, height: int
    ):
        """映射模式下的背景绘制 - 圆形背景"""
        center_x = width / 2
        center_y = height / 2
        radius = min(width, height) / 2 - 2  # 减少边距

        # 绘制单一背景色的圆形
        cr.set_source_rgba(0.6, 0.6, 0.6, 0.5)  # 统一的半透明灰色
        cr.arc(center_x, center_y, radius, 0, 2 * math.pi)
        cr.fill()

    def draw_mapping_mode_content(
        self, cr: "Context[Surface]", width: int, height: int
    ):
        """映射模式下的内容绘制 - 只显示四个方向的按键文字"""
        center_x = width / 2
        center_y = height / 2
        radius = min(width, height) / 2 - 2  # 减少边距
        inner_radius = radius * 0.3
        button_radius = (radius + inner_radius) / 2

        # 方向位置计算
        direction_positions = {
            "up": (center_x, center_y - button_radius),
            "down": (center_x, center_y + button_radius),
            "left": (center_x - button_radius, center_y),
            "right": (center_x + button_radius, center_y),
        }

        for direction in self.DIRECTIONS:
            x, y = direction_positions[direction]
            key = self.direction_keys[direction]

            # 只绘制按键文字，不绘制按钮背景和边框
            key_text = str(key) if key else "?"

            cr.set_source_rgba(1, 1, 1, 0.9)  # 白色文字
            cr.select_font_face("Arial", 0, 1)

            # 根据按键长度调整字体大小
            if len(key_text) <= 1:
                cr.set_font_size(10)  # 映射模式下稍小的字体
            elif len(key_text) <= 3:
                cr.set_font_size(8)
            else:
                cr.set_font_size(6)

            text_extents = cr.text_extents(key_text)
            text_x = x - text_extents.width / 2
            text_y = y + text_extents.height / 2
            cr.move_to(text_x, text_y)
            cr.show_text(key_text)
            cr.new_path()  # 清除路径

        if self._joystick_active:
            self._draw_joystick_dot(cr, width, height)

    def get_direction_from_key(self, key_combination: KeyCombination) -> str | None:
        """根据按键组合获取对应的方向"""
        for direction, key in self.direction_keys.items():
            if key == key_combination:
                return direction
        return None

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

    def on_key_triggered(self, key_combination: KeyCombination | None = None, event: "InputEvent | None" = None) -> bool:
        """当映射的按键被触发时的行为 - 根据按键确定方向"""
        if not key_combination:
            return False

        direction = self.get_direction_from_key(key_combination)
        if direction:
            self.pressed_directions[direction] = True
            target = self._get_target_position()
            if not self._joystick_active:
                pointer_id = self.pointer_id_manager.allocate(self)
                if pointer_id is None:
                    return False
                self._joystick_active = True
                self._current_position = self.center
                self._emit_touch_event(AMotionEventAction.DOWN, position=self.center)
                self._move_to(target, smooth=True)
            else:
                self._move_to(target, smooth=False)


            # 这里可以调用具体的方向处理方法
            self.on_direction_triggered(direction, key_combination)
            return True
        else:
            return False

    def on_key_released(self, key_combination: KeyCombination | None = None, event: "InputEvent | None" = None) -> bool:
        """当映射的按键被弹起时的行为 - 根据按键确定方向"""
        if not key_combination:
            return False

        direction = self.get_direction_from_key(key_combination)
        if direction:
            self.pressed_directions[direction] = False

            if not any(self.pressed_directions.values()):
                # 所有键释放: 停用摇杆，瞬移回中心
                self._joystick_active = False
                self._cancel_movement_task()
                self._emit_touch_event(AMotionEventAction.UP)
                self.pointer_id_manager.release(self)
                self._move_to(self.center, smooth=False)
            else:
                # 还有其他键按下: 更新目标位置并瞬移
                self._move_to(self._get_target_position(), smooth=False)
            # 这里可以调用具体的方向处理方法
            self.on_direction_released(direction, key_combination)
            return True
        else:
            return False

    def _draw_joystick_dot(
        self, cr: "Context[Surface]", map_width: int, map_height: int
    ):
        """在映射模式下绘制代表摇杆位置的红点"""
        # 1. 计算摇杆相对于其编辑模式中心的归一化偏移
        edit_center_x, edit_center_y = self.center
        offset_x = self._current_position[0] - edit_center_x
        offset_y = self._current_position[1] - edit_center_y

        edit_radius_x = self.width / 2
        edit_radius_y = self.height / 2

        norm_x = offset_x / edit_radius_x if edit_radius_x != 0 else 0
        norm_y = offset_y / edit_radius_y if edit_radius_y != 0 else 0

        # 2. 将归一化偏移应用到映射模式的尺寸上
        map_center_x, map_center_y = map_width / 2, map_height / 2
        draw_x = map_center_x + norm_x * (map_width / 2)
        draw_y = map_center_y + norm_y * (map_height / 2)

        # 3. 绘制红点
        cr.set_source_rgba(1.0, 0.2, 0.2, 0.9)
        cr.arc(draw_x, draw_y, 4, 0, 2 * math.pi)
        cr.fill()

    def on_direction_triggered(self, direction: str, key_combination: KeyCombination):
        """方向被触发时的具体处理 - 子类可以重写此方法"""
        pass

    def on_direction_released(self, direction: str, key_combination: KeyCombination):
        """方向被释放时的具体处理 - 子类可以重写此方法"""
        pass

    def draw_widget_content(self, cr: "Context[Surface]", width: int, height: int):
        # 计算圆心和半径
        center_x = width / 2
        center_y = height / 2
        radius = min(width, height) / 2 - 8  # 留出边距

        # 绘制外圆背景
        cr.set_source_rgba(0.4, 0.4, 0.4, 0.7)
        cr.arc(center_x, center_y, radius, 0, 2 * math.pi)
        cr.fill()

        # 绘制外圆边框
        cr.set_source_rgba(0.2, 0.2, 0.2, 0.9)
        cr.set_line_width(2)
        cr.arc(center_x, center_y, radius, 0, 2 * math.pi)
        cr.stroke()

        # 绘制中心圆
        inner_radius = radius * 0.3
        cr.set_source_rgba(0.6, 0.6, 0.6, 0.8)
        cr.arc(center_x, center_y, inner_radius, 0, 2 * math.pi)
        cr.fill()

        # 绘制四个方向的按钮区域和文字
        self.draw_direction_buttons(cr, center_x, center_y, radius, inner_radius)

    @property
    def mapping_start_x(self):
        return int(self.x + self.width / 2 - self.MAPPING_MODE_WIDTH / 2)

    @property
    def mapping_start_y(self):
        return int(self.y + self.height / 2 - self.MAPPING_MODE_HEIGHT / 2)

    @property
    def center(self) -> tuple[float, float]:
        return (self.x + self.width / 2, self.y + self.height / 2)

    @property
    def left(self):
        return (self.x, self.y + self.height / 2)

    @property
    def right(self):
        return (self.x + self.width, self.y + self.height / 2)

    @property
    def top(self):
        return (self.x + self.width / 2, self.y)

    @property
    def bottom(self):
        return (self.x + self.width / 2, self.y + self.height)

    @property
    def top_left(self) -> tuple[float, float]:
        r = min(self.width, self.height) / 2
        return (self.center[0] - 0.7071 * r, self.center[1] - 0.7071 * r)

    @property
    def top_right(self) -> tuple[float, float]:
        r = min(self.width, self.height) / 2
        return (self.center[0] + 0.7071 * r, self.center[1] - 0.7071 * r)

    @property
    def bottom_left(self) -> tuple[float, float]:
        r = min(self.width, self.height) / 2
        return (self.center[0] - 0.7071 * r, self.center[1] + 0.7071 * r)

    @property
    def bottom_right(self) -> tuple[float, float]:
        r = min(self.width, self.height) / 2
        return (self.center[0] + 0.7071 * r, self.center[1] + 0.7071 * r)

     # 乘了系数的左
    @property
    def left_with_factor(self):
        return (self.center[0]-self.width/2*self.swipehold_radius_factor, self.center[1])

    @property
    def right_with_factor(self):
        return (self.center[0]+self.width/2*self.swipehold_radius_factor, self.center[1])

    @property
    def top_with_factor(self):
        return (self.center[0], self.center[1]-self.height/2*self.swipehold_radius_factor)

    @property
    def bottom_with_factor(self):
        return (self.center[0], self.center[1]+self.height/2*self.swipehold_radius_factor)

    @property
    def top_left_with_factor(self) -> tuple[float, float]:
        r = min(self.width, self.height) / 2 * self.swipehold_radius_factor
        return (self.center[0] - 0.7071 * r, self.center[1] - 0.7071 * r)

    @property
    def top_right_with_factor(self) -> tuple[float, float]:
        r = min(self.width, self.height) / 2 * self.swipehold_radius_factor
        return (self.center[0] + 0.7071 * r, self.center[1] - 0.7071 * r)

    @property
    def bottom_left_with_factor(self) -> tuple[float, float]:
        r = min(self.width, self.height) / 2 * self.swipehold_radius_factor
        return (self.center[0] - 0.7071 * r, self.center[1] + 0.7071 * r)

    @property
    def bottom_right_with_factor(self) -> tuple[float, float]:
        r = min(self.width, self.height) / 2 * self.swipehold_radius_factor
        return (self.center[0] + 0.7071 * r, self.center[1] + 0.7071 * r)


    def on_delete(self):
        """清理资源"""
        # 取消异步任务
        self._cancel_movement_task()
        # 取消事件订阅
        self.event_bus.unsubscribe_by_subscriber(self)
        return super().on_delete()
