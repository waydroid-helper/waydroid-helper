from __future__ import annotations

import asyncio
import math
from enum import Enum
from gettext import pgettext
from typing import TYPE_CHECKING, Any, cast

from waydroid_helper.controller.android.input import (
    AMotionEventAction,
    AMotionEventButtons,
)
from waydroid_helper.controller.core import (
    Event,
    EventType,
    KeyCombination,
    is_point_in_rect,
    PointerIdManager,
)
from waydroid_helper.controller.core.control_msg import InjectTouchEventMsg, ScreenInfo
from waydroid_helper.controller.core.event_bus import EventBus
from waydroid_helper.controller.core.key_system import KeyRegistry
from waydroid_helper.controller.platform import get_platform
from waydroid_helper.controller.widgets import BaseWidget
from waydroid_helper.controller.widgets.config import create_slider_config
from waydroid_helper.controller.widgets.decorators import (
    Editable,
    Resizable,
    ResizableDecorator,
)
from waydroid_helper.util.log import logger

if TYPE_CHECKING:
    from cairo import Context, Surface
    from gi.repository import Gtk

    from waydroid_helper.controller.core.handler import InputEvent
    from waydroid_helper.controller.platform import PlatformBase
    from waydroid_helper.controller.widgets.base.base_widget import EditableRegion


class AimState(Enum):
    """瞄准状态枚举"""

    IDLE = "idle"  # 空闲状态
    AIMING = "aiming"  # 瞄准状态
    MOVING = "moving"  # 移动状态


@Editable
@Resizable(resize_strategy=ResizableDecorator.RESIZE_SYMMETRIC)
class Aim(BaseWidget):
    MAPPING_MODE_WIDTH = 100
    MAPPING_MODE_HEIGHT = 100
    WIDGET_NAME = pgettext("Controller Widgets", "Aim")
    WIDGET_DESCRIPTION = pgettext(
        "Controller Widgets",
        "FPS staple: drag to game's view area, pair with Fire for mouse-aim shooting. Resize box to match in-game rotation zone.",
    )
    WIDGET_VERSION = "1.0"
    IS_REENTRANT = True  # 支持可重入，实现长按瞄准功能

    # 固定圆形区域大小
    CIRCLE_SIZE = 50
    CIRCLE_RADIUS = 25

    def __init__(
        self,
        x: int = 0,
        y: int = 0,
        width: int = 200,
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
            width,
            height,
            pgettext("Controller Widgets", "Aim"),
            text,
            default_keys,
            min_width=200,
            min_height=150,
            event_bus=event_bus,
            pointer_id_manager=pointer_id_manager,
            key_registry=key_registry,
        )

        # 状态管理
        self._state: AimState = AimState.IDLE
        self._state_lock = asyncio.Lock()

        # 平台相关
        self.platform: "PlatformBase | None" = None

        # 位置跟踪
        self._current_pos: tuple[float, float] | None = None

        # 异步任务管理
        self._aim_task: asyncio.Task[None] | None = None
        self._motion_task: asyncio.Task[None] | None = None
        self._motion_queue: asyncio.Queue[tuple[float, float, float, float]] = (
            asyncio.Queue()
        )
        self._motion_processor_running = False
        self.screen_info = ScreenInfo()

        # 配置
        self.setup_config()

        # 事件订阅
        self.event_bus.subscribe(
            EventType.ENTER_STARING, self._handle_enter_staring, subscriber=self
        )
        self.event_bus.subscribe(
            EventType.EXIT_STARING, self._handle_exit_staring, subscriber=self
        )

    def setup_config(self) -> None:
        """设置配置项"""

        # 添加灵敏度配置
        sensitivity_config = create_slider_config(
            key="sensitivity",
            label=pgettext("Controller Widgets", "Sensitivity"),
            # value=self.sensitivity,
            value=20,
            min_value=1,
            max_value=100,
            step=1,
            description=pgettext(
                "Controller Widgets", "Adjusts the sensitivity of aim movement"
            ),
        )

        self.add_config_item(sensitivity_config)
        # 添加配置变更回调
        self.add_config_change_callback("sensitivity", self._on_sensitivity_changed)

    def _on_sensitivity_changed(self, key: str, value: int, restoring: bool) -> None:
        """处理灵敏度配置变更"""
        pass

    async def _set_state(self, new_state: AimState) -> None:
        """安全地设置状态"""
        async with self._state_lock:
            if self._state != new_state:
                old_state = self._state
                self._state = new_state

    async def _get_state(self) -> AimState:
        """安全地获取状态"""
        async with self._state_lock:
            return self._state

    def _cancel_tasks(self) -> None:
        """取消所有异步任务"""
        if self._aim_task and not self._aim_task.done():
            self._aim_task.cancel()
            self._aim_task = None

        if self._motion_task and not self._motion_task.done():
            self._motion_task.cancel()
            self._motion_task = None

        # 清空移动队列
        while not self._motion_queue.empty():
            try:
                self._motion_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

        # 重置处理器状态
        self._motion_processor_running = False

    def on_relative_pointer_motion(
        self, dx: float, dy: float, dx_unaccel: float, dy_unaccel: float
    ) -> None:
        """处理相对鼠标移动事件 - 使用队列机制避免频繁取消任务"""
        # 将移动事件放入队列
        try:
            self._motion_queue.put_nowait((dx, dy, dx_unaccel, dy_unaccel))
        except asyncio.QueueFull:
            # 队列满了，丢弃最旧的事件
            try:
                self._motion_queue.get_nowait()
                self._motion_queue.put_nowait((dx, dy, dx_unaccel, dy_unaccel))
            except asyncio.QueueEmpty:
                pass

        # 如果处理器没有运行，启动它
        if not self._motion_processor_running:
            self._motion_task = asyncio.create_task(self._motion_processor())

    async def _motion_processor(self) -> None:
        """异步处理鼠标移动事件的处理器"""
        self._motion_processor_running = True
        try:
            while True:
                # 等待队列中的移动事件
                dx, dy, dx_unaccel, dy_unaccel = await self._motion_queue.get()

                # 检查状态
                current_state = await self._get_state()
                if current_state != AimState.AIMING:
                    # 清空队列并退出
                    while not self._motion_queue.empty():
                        try:
                            self._motion_queue.get_nowait()
                        except asyncio.QueueEmpty:
                            break
                    break

                # 处理移动事件
                await self._handle_single_motion(dx, dy, dx_unaccel, dy_unaccel)

                # 标记任务完成
                self._motion_queue.task_done()

        except Exception:
            pass
        finally:
            self._motion_processor_running = False

    async def _handle_single_motion(
        self, dx: float, dy: float, dx_unaccel: float, dy_unaccel: float
    ) -> None:
        """处理单个鼠标移动事件"""
        try:
            # 计算移动增量
            sensitivity = self.get_config_value("sensitivity")
            _dx = dx_unaccel * sensitivity / 50
            _dy = dy_unaccel * sensitivity / 50

            # 获取根窗口尺寸
            w, h = self.screen_info.get_host_resolution()

            # 处理位置更新
            await self._update_aim_position(_dx, _dy, w, h)

        except Exception:
            pass

    async def _update_aim_position(self, dx: float, dy: float, w: int, h: int) -> None:
        """更新瞄准位置"""
        # 如果没有当前位置，初始化为中心点
        if self._current_pos is None:
            self._current_pos = (float(self.center_x), float(self.center_y))
            await self._send_touch_down(w, h)

        # 计算新位置
        new_x = self._current_pos[0] + dx
        new_y = self._current_pos[1] + dy

        # 检查是否超出边界
        if not is_point_in_rect(new_x, new_y, self.x, self.y, self.width, self.height):
            # 超出边界，发送UP事件并重置位置
            await self._send_touch_up(w, h)
            self._current_pos = (float(self.center_x), float(self.center_y))
            # await asyncio.sleep(0.05)
            await self._send_touch_down(w, h)
            # self._current_pos = (float(self.center_x) + dx, float(self.center_y) + dy)
            # await self._send_touch_move(w, h)
            return

        # 更新位置并发送MOVE事件
        self._current_pos = (new_x, new_y)
        await self._send_touch_move(w, h)

    async def _send_touch_down(self, w: int, h: int) -> None:
        """发送触摸按下事件"""
        if self._current_pos is None:
            return

        pointer_id = self.pointer_id_manager.allocate(self)
        if pointer_id is None:
            return

        msg = InjectTouchEventMsg(
            action=AMotionEventAction.DOWN,
            pointer_id=pointer_id,
            position=(int(self._current_pos[0]), int(self._current_pos[1]), w, h),
            pressure=1.0,
            action_button=AMotionEventButtons.PRIMARY,
            buttons=AMotionEventButtons.PRIMARY,
        )
        self.event_bus.emit(Event(EventType.CONTROL_MSG, self, msg))

    async def _send_touch_move(self, w: int, h: int) -> None:
        """发送触摸移动事件"""
        if self._current_pos is None:
            return

        pointer_id = self.pointer_id_manager.get_allocated_id(self)
        if pointer_id is None:
            return

        msg = InjectTouchEventMsg(
            action=AMotionEventAction.MOVE,
            pointer_id=pointer_id,
            position=(int(self._current_pos[0]), int(self._current_pos[1]), w, h),
            pressure=1.0,
            action_button=0,
            buttons=AMotionEventButtons.PRIMARY,
        )
        self.event_bus.emit(Event(EventType.CONTROL_MSG, self, msg))

    async def _send_touch_up(
        self, w: int, h: int, x: float | None = None, y: float | None = None
    ) -> None:
        """发送触摸抬起事件"""
        # 使用提供的坐标或当前位置
        pos_x = (
            x
            if x is not None
            else (self._current_pos[0] if self._current_pos else self.center_x)
        )
        pos_y = (
            y
            if y is not None
            else (self._current_pos[1] if self._current_pos else self.center_y)
        )

        pointer_id = self.pointer_id_manager.get_allocated_id(self)
        if pointer_id is None:
            return

        msg = InjectTouchEventMsg(
            action=AMotionEventAction.UP,
            pointer_id=pointer_id,
            position=(int(pos_x), int(pos_y), w, h),
            pressure=0.0,
            action_button=AMotionEventButtons.PRIMARY,
            buttons=0,
        )
        self.event_bus.emit(Event(EventType.CONTROL_MSG, self, msg))
        self.pointer_id_manager.release(self)

    def draw_widget_content(self, cr: "Context[Surface]", width: int, height: int):
        """绘制瞄准按钮的具体内容 - 中心50*50圆形区域"""
        # 计算中心位置
        center_x = width / 2
        center_y = height / 2

        # 绘制固定大小的圆形区域
        cr.set_source_rgba(0.5, 0.5, 0.5, 0.6)  # 半透明灰色背景
        cr.arc(center_x, center_y, self.CIRCLE_RADIUS, 0, 2 * math.pi)
        cr.fill()

        # 绘制圆形边框
        cr.set_source_rgba(0.3, 0.3, 0.3, 0.9)
        cr.set_line_width(2)
        cr.arc(center_x, center_y, self.CIRCLE_RADIUS, 0, 2 * math.pi)
        cr.stroke()

        # 绘制准心 - 四条短线
        cr.set_source_rgba(1, 1, 1, 0.9)  # 白色准心线
        cr.set_line_width(2)

        # 准心线长度
        crosshair_length = 8

        # 上方短线 (从圆的顶部向圆心延伸)
        cr.move_to(center_x, center_y - self.CIRCLE_RADIUS)
        cr.line_to(center_x, center_y - self.CIRCLE_RADIUS + crosshair_length)
        cr.stroke()

        # 下方短线 (从圆的底部向圆心延伸)
        cr.move_to(center_x, center_y + self.CIRCLE_RADIUS)
        cr.line_to(center_x, center_y + self.CIRCLE_RADIUS - crosshair_length)
        cr.stroke()

        # 左侧短线 (从圆的左侧向圆心延伸)
        cr.move_to(center_x - self.CIRCLE_RADIUS, center_y)
        cr.line_to(center_x - self.CIRCLE_RADIUS + crosshair_length, center_y)
        cr.stroke()

        # 右侧短线 (从圆的右侧向圆心延伸)
        cr.move_to(center_x + self.CIRCLE_RADIUS, center_y)
        cr.line_to(center_x + self.CIRCLE_RADIUS - crosshair_length, center_y)
        cr.stroke()

    def draw_text_content(self, cr: "Context[Surface]", width: int, height: int):
        """绘制文本内容 - 在中心圆形区域显示"""
        if self.text:
            center_x = width / 2
            center_y = height / 2

            cr.set_source_rgba(1, 1, 1, 1)  # 白色文字
            cr.select_font_face("Arial")
            cr.set_font_size(12)
            text_extents = cr.text_extents(self.text)
            x = center_x - text_extents.width / 2
            y = center_y + text_extents.height / 2
            cr.move_to(x, y)
            cr.show_text(self.text)

            # 清除路径，避免影响后续绘制
            cr.new_path()

    def draw_selection_border(self, cr: "Context[Surface]", width: int, height: int):
        """绘制选择边框 - 整个矩形区域背景色，重新绘制内容"""
        # 绘制整个矩形的半透明背景色
        cr.set_source_rgba(0.2, 0.6, 1.0, 0.3)  # 半透明蓝色背景
        cr.rectangle(0, 0, width, height)
        cr.fill()

        # 重新绘制组件内容（避免被背景色覆盖）
        self.draw_widget_content(cr, width, height)
        self.draw_text_content(cr, width, height)

        # 绘制矩形边框
        cr.set_source_rgba(0.2, 0.6, 1.0, 0.8)  # 更深的蓝色边框
        cr.set_line_width(3)
        cr.rectangle(0, 0, width, height)
        cr.stroke()

    def draw_mapping_mode_background(
        self, cr: "Context[Surface]", width: int, height: int
    ):
        """映射模式下的背景绘制 - 完全透明，什么都不绘制"""

    def draw_mapping_mode_content(
        self, cr: "Context[Surface]", width: int, height: int
    ):
        """映射模式下的内容绘制 - 完全透明，什么都不绘制"""

    def _handle_enter_staring(self, event: Event[Any]) -> None:
        """处理进入瞄准事件 - 创建异步任务"""
        if self._aim_task and not self._aim_task.done():
            return  # 已经在瞄准状态

        self._aim_task = asyncio.create_task(self._enter_aiming_state())

    def _handle_exit_staring(self, event: Event[Any]) -> None:
        """处理退出瞄准事件 - 创建异步任务"""
        if self._aim_task and not self._aim_task.done():
            self._aim_task.cancel()

        self._aim_task = asyncio.create_task(self._exit_aiming_state())

    async def _enter_aiming_state(self) -> None:
        """异步进入瞄准状态"""
        try:
            current_state = await self._get_state()
            if current_state != AimState.IDLE:
                return

            await self._set_state(AimState.AIMING)

            # 初始化平台
            if not self.platform:
                self.platform = get_platform(self.get_root())

            if not self.platform:
                await self._set_state(AimState.IDLE)
                return

            # 设置相对指针回调
            self.platform.set_relative_pointer_callback(self.on_relative_pointer_motion)

            # 锁定指针并隐藏光标
            self.platform.lock_pointer()
            root = self.get_root()
            if root:
                root = cast("Gtk.Window", root)
                root.set_cursor_from_name("none")

            # 发送瞄准触发事件
            self.event_bus.emit(Event(type=EventType.AIM_TRIGGERED, source=self, data=None))

        except Exception as e:
            logger.error(f"Failed to enter aiming state: {e}")
            await self._set_state(AimState.IDLE)

    async def _exit_aiming_state(self) -> None:
        """异步退出瞄准状态"""
        try:
            current_state = await self._get_state()
            if current_state == AimState.IDLE:
                return

            await self._set_state(AimState.IDLE)

            # 停止运动处理器 - 设置状态为IDLE后，处理器会自动退出
            # 等待处理器完成当前正在处理的事件
            if self._motion_task and not self._motion_task.done():
                try:
                    await asyncio.wait_for(self._motion_task, timeout=0.1)
                except asyncio.TimeoutError:
                    # 如果超时，强制取消
                    self._motion_task.cancel()
                    try:
                        await self._motion_task
                    except asyncio.CancelledError:
                        pass

            # 清空队列
            while not self._motion_queue.empty():
                try:
                    self._motion_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break

            # 解锁指针并恢复光标
            if self.platform:
                self.platform.unlock_pointer()

            root = self.get_root()
            if root:
                root = cast("Gtk.Window", root)
                root.set_cursor_from_name("default")

            # 如果有当前位置，发送UP事件
            if self._current_pos is not None:
                if root:
                    w, h = self.screen_info.get_host_resolution()
                    await self._send_touch_up(w, h)
                self._current_pos = None

            # 发送瞄准释放事件
            self.event_bus.emit(Event(type=EventType.AIM_RELEASED, source=self, data=None))

        except Exception:
            pass

    def on_key_triggered(
        self,
        key_combination: KeyCombination | None = None,
        event: "InputEvent | None" = None,
    ) -> bool:
        """当映射的按键被触发时的行为 - 瞄准触发"""
        if key_combination:
            used_key = str(key_combination)
        elif self.final_keys:
            used_key = str(next(iter(self.final_keys)))
        else:
            used_key = "未知按键"

        # 创建异步任务处理按键触发
        asyncio.create_task(self._handle_key_triggered(used_key))
        return True

    async def _handle_key_triggered(self, used_key: str) -> None:
        """异步处理按键触发"""
        try:
            current_state = await self._get_state()

            if current_state == AimState.IDLE:
                # 进入瞄准状态
                await self._enter_aiming_state()
            else:
                # 退出瞄准状态
                await self._exit_aiming_state()
        except Exception:
            pass

    def on_key_released(
        self,
        key_combination: KeyCombination | None = None,
        event: "InputEvent|None" = None,
    ) -> bool:
        """按键释放处理 - 在可重入模式下不做任何操作"""
        return True

    def cleanup(self) -> None:
        """清理资源"""
        # 取消所有异步任务
        self._cancel_tasks()

        # 如果处于瞄准状态，异步退出
        asyncio.create_task(self._cleanup_async())

    async def _cleanup_async(self) -> None:
        """异步清理"""
        try:
            current_state = await self._get_state()
            if current_state != AimState.IDLE:
                await self._exit_aiming_state()
        except Exception:
            pass

    def __del__(self) -> None:
        """析构函数 - 确保资源被清理"""
        try:
            self.cleanup()
        except Exception:
            pass

    def get_delete_button_bounds(self) -> tuple[int, int, int, int]:
        """获取删除按钮的边界 (x, y, w, h) - 将按钮定位在中心圆的右上角边缘"""
        # 删除按钮应该在中心圆右上角, 恰好在圆边上
        size = 16
        center_x = self.width / 2
        center_y = self.height / 2

        # 45度角 (-pi/4)
        angle = -math.pi / 4

        # 删除按钮的中心点
        button_center_x = center_x + self.CIRCLE_RADIUS * math.cos(angle)
        button_center_y = center_y + self.CIRCLE_RADIUS * math.sin(angle)

        # 计算左上角坐标
        x = button_center_x - size / 2
        y = button_center_y - size / 2

        return (int(x), int(y), size, size)

    def get_settings_button_bounds(self) -> tuple[int, int, int, int]:
        size = 16
        center_x = self.width / 2
        center_y = self.height / 2

        angle = math.pi / 4

        button_center_x = center_x + self.CIRCLE_RADIUS * math.cos(angle)
        button_center_y = center_y + self.CIRCLE_RADIUS * math.sin(angle)

        x = button_center_x - size / 2
        y = button_center_y - size / 2

        return (int(x), int(y), size, size)

    def get_editable_regions(self) -> list["EditableRegion"]:
        """获取可编辑区域列表 - 中心50*50圆形区域为可编辑区域"""
        # 计算中心圆形区域的边界框
        center_x = self.width / 2
        center_y = self.height / 2
        circle_left = center_x - self.CIRCLE_RADIUS
        circle_top = center_y - self.CIRCLE_RADIUS

        return [
            {
                "id": "aim_center",
                "name": "瞄准区域",
                "bounds": (
                    int(circle_left),
                    int(circle_top),
                    self.CIRCLE_SIZE,
                    self.CIRCLE_SIZE,
                ),
                "get_keys": lambda: self.final_keys.copy(),
                "set_keys": lambda keys: setattr(
                    self, "final_keys", set(keys) if keys else set()
                ),
            }
        ]

    @property
    def mapping_start_x(self):
        """映射起始X坐标 - 中心位置"""
        return self.x + self.width / 2

    @property
    def mapping_start_y(self):
        """映射起始Y坐标 - 中心位置"""
        return self.y + self.height / 2

    @property
    def center_x(self):
        """中心X坐标"""
        return self.x + self.width / 2

    @property
    def center_y(self):
        """中心Y坐标"""
        return self.y + self.height / 2
