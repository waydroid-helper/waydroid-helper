import asyncio
import math
from enum import Enum
from gettext import pgettext
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from cairo import Context, Surface
    from gi.repository import Gtk
    from waydroid_helper.controller.platform import PlatformBase
    from waydroid_helper.controller.widgets.base.base_widget import EditableRegion

from waydroid_helper.controller.android.input import (AMotionEventAction,
                                                      AMotionEventButtons)
from waydroid_helper.controller.core import (Event, EventType, KeyCombination,
                                             EventBus, PointerIdManager, KeyRegistry,
                                             ControllerRuntimeContext)
from waydroid_helper.controller.core.control_msg import InjectTouchEventMsg
from waydroid_helper.controller.core.handler.event_handlers import InputEvent
from waydroid_helper.controller.platform import get_platform
from waydroid_helper.controller.widgets.base.base_widget import BaseWidget
from waydroid_helper.controller.widgets.config import (
    create_dropdown_config,
    create_slider_config,
    create_switch_config,
)
from waydroid_helper.util.log import logger


class FireDragState(Enum):
    """Fire drag-shot pointer handoff state."""

    IDLE = "idle"
    ACTIVATING = "activating"
    ACTIVE = "active"
    RELEASING = "releasing"


class Fire(BaseWidget):
    MAPPING_MODE_WIDTH = 30
    MAPPING_MODE_HEIGHT = 30
    WIDGET_NAME = pgettext("Controller Widgets", "Fire")
    WIDGET_DESCRIPTION = pgettext(
        "Controller Widgets",
        "Commonly used in FPS games, add a button to the attack/fire button position, use the left mouse button to click, and must be used with the aim button. Note: Only supports left mouse button, cannot be modified, and won't work alone.",
    )

    def __init__(
        self,
        x: int = 0,
        y: int = 0,
        width: int = 50,
        height: int = 50,
        text: str = "",
        default_keys: set[KeyCombination]|None = None,
        runtime_context: ControllerRuntimeContext | None = None,
        event_bus: EventBus | None = None,
        pointer_id_manager: PointerIdManager | None = None,
        key_registry: KeyRegistry | None = None,
    ):
        resolved_key_registry = (
            runtime_context.key_registry if runtime_context is not None else key_registry
        )
        if resolved_key_registry is None:
            raise ValueError("runtime_context or key_registry is required")
        # 初始化基类，传入默认按键
        super().__init__(
            x,
            y,
            50,
            50,
            pgettext("Controller Widgets", "Fire"),
            text,
            set(
                [KeyCombination([resolved_key_registry.get_by_name("Mouse_Left")])]
            ),
            min_width=25,
            min_height=25,
            runtime_context=runtime_context,
            event_bus = event_bus,
            pointer_id_manager = pointer_id_manager,
            key_registry = key_registry,
        )
        self.aim_triggered: bool = False
        self._active_aim_source: Any | None = None
        self._drag_state: FireDragState = FireDragState.IDLE
        self._drag_state_lock = asyncio.Lock()
        self._drag_task: asyncio.Task[None] | None = None
        self._release_requested = False
        self._drag_pos: tuple[float, float] | None = None
        self._drag_shot_enabled = False
        self._drag_horizontal_sensitivity = 20.0
        self._drag_vertical_sensitivity = 20.0
        self._motion_task: asyncio.Task[None] | None = None
        self._motion_queue: asyncio.Queue[tuple[float, float, float, float]] = (
            asyncio.Queue()
        )
        self._motion_processor_running = False
        self.platform: "PlatformBase | None" = None
        self.event_bus.subscribe(EventType.AIM_TRIGGERED, self._on_aim_triggered, subscriber=self)
        self.event_bus.subscribe(EventType.AIM_RELEASED, self._on_aim_released, subscriber=self)
        
        self.setup_config()

    def _on_aim_triggered(self, event: Event[None]):
        """处理瞄准触发事件"""
        self.aim_triggered = True
        self._active_aim_source = event.source

    def _on_aim_released(self, event: Event[None]):
        """处理瞄准释放事件"""
        if self._active_aim_source is not None and event.source is not self._active_aim_source:
            return

        self.aim_triggered = False
        self._active_aim_source = None
        if self._drag_state in {FireDragState.ACTIVATING, FireDragState.ACTIVE}:
            asyncio.create_task(self._release_after_aim_released())
        elif self.pointer_id_manager.get_allocated_id(self) is not None:
            w, h = self.screen_geometry.get_host_resolution()
            self._send_touch_event(
                AMotionEventAction.UP,
                self.center_x,
                self.center_y,
                w,
                h,
                0.0,
                AMotionEventButtons.PRIMARY,
                0,
            )
        
    def setup_config(self) -> None:
        """设置配置项"""
        # 添加鼠标按键选择配置
        mouse_button_config = create_dropdown_config(
            key="mouse_button",
            label=pgettext("Controller Widgets", "Mouse Button"),
            options=["left", "right"],
            option_labels={
                "left": pgettext("Controller Widgets", "Left Button"),
                "right": pgettext("Controller Widgets", "Right Button"),
            },
            value="left",
            description=pgettext(
                "Controller Widgets", "Choose which mouse button to simulate for firing"
            ),
        )
        drag_shot_config = create_switch_config(
            key="enable_drag_shot",
            label=pgettext("Controller Widgets", "Enable Drag Shot"),
            value=False,
            description=pgettext(
                "Controller Widgets",
                "Let Fire own pointer lock while firing, so mouse movement drags the fire touch point.",
            ),
        )
        horizontal_sensitivity_config = create_slider_config(
            key="drag_horizontal_sensitivity",
            label=pgettext("Controller Widgets", "Horizontal Sensitivity"),
            value=20,
            min_value=1,
            max_value=100,
            step=1,
            description=pgettext(
                "Controller Widgets", "Adjusts horizontal drag-shot movement"
            ),
            visible=False,
        )
        vertical_sensitivity_config = create_slider_config(
            key="drag_vertical_sensitivity",
            label=pgettext("Controller Widgets", "Vertical Sensitivity"),
            value=20,
            min_value=1,
            max_value=100,
            step=1,
            description=pgettext(
                "Controller Widgets", "Adjusts vertical drag-shot movement"
            ),
            visible=False,
        )
        
        self.add_config_item(mouse_button_config)
        self.add_config_item(drag_shot_config)
        self.add_config_item(horizontal_sensitivity_config)
        self.add_config_item(vertical_sensitivity_config)
        self.add_config_change_callback("mouse_button", self._on_mouse_button_changed)
        self.add_config_change_callback(
            "enable_drag_shot", self._on_enable_drag_shot_changed
        )
        self.add_config_change_callback(
            "drag_horizontal_sensitivity",
            self._on_drag_horizontal_sensitivity_changed,
        )
        self.add_config_change_callback(
            "drag_vertical_sensitivity", self._on_drag_vertical_sensitivity_changed
        )
        self.config_manager.connect(
            "confirmed", lambda config_manager: self._update_drag_config_visibility()
        )
        
    def _on_mouse_button_changed(self, key: str, value: str, restoring: bool) -> None:
        key_mapping_manager = self.get_root().key_mapping_manager
        key_mapping_manager.unsubscribe(self)
        if value == "right":
            right_mouse_key = KeyCombination([self.key_registry.get_by_name("Mouse_Right")])
            self.final_keys = set([right_mouse_key])
            key_mapping_manager.subscribe(self, right_mouse_key)
        else:
            left_mouse_key = KeyCombination([self.key_registry.get_by_name("Mouse_Left")])
            self.final_keys = set([left_mouse_key])
            key_mapping_manager.subscribe(self, left_mouse_key)
        self.queue_draw()

    def _on_enable_drag_shot_changed(
        self, key: str, value: bool, restoring: bool
    ) -> None:
        self._drag_shot_enabled = bool(value)
        self._update_drag_config_visibility()

    def _on_drag_horizontal_sensitivity_changed(
        self, key: str, value: float, restoring: bool
    ) -> None:
        self._drag_horizontal_sensitivity = self._coerce_sensitivity(
            value, self._drag_horizontal_sensitivity, key
        )

    def _on_drag_vertical_sensitivity_changed(
        self, key: str, value: float, restoring: bool
    ) -> None:
        self._drag_vertical_sensitivity = self._coerce_sensitivity(
            value, self._drag_vertical_sensitivity, key
        )

    def _coerce_sensitivity(self, value: Any, fallback: float, key: str) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            logger.warning("Invalid Fire %s value %r; keeping %s", key, value, fallback)
            return fallback

    def _update_drag_config_visibility(self) -> None:
        enabled = bool(self.get_config_value("enable_drag_shot"))
        self._drag_shot_enabled = enabled
        config_manager = self.get_config_manager()
        config_manager.set_visible("drag_horizontal_sensitivity", enabled)
        config_manager.set_visible("drag_vertical_sensitivity", enabled)


    def draw_widget_content(self, cr: "Context[Surface]", width: int, height: int):
        """绘制开火按钮的具体内容"""
        # 计算圆心和半径
        center_x = width / 2
        center_y = height / 2
        radius = min(width, height) / 2 - 5  # 留出边距

        # 绘制圆形背景
        cr.set_source_rgba(0.5, 0.5, 0.5, 0.6)

        cr.arc(center_x, center_y, radius, 0, 2 * math.pi)
        cr.fill()

        # 绘制圆形边框
        cr.set_source_rgba(0.3, 0.3, 0.3, 0.9)
        cr.set_line_width(2)
        cr.arc(center_x, center_y, radius, 0, 2 * math.pi)
        cr.stroke()

    def draw_text_content(self, cr: "Context[Surface]", width: int, height: int):
        """重写文本绘制 - 绘制标准鼠标图标，根据配置高亮左键或右键"""
        center_x = width / 2
        center_y = height / 2

        # 鼠标主体参数（更小尺寸，不能太大）
        mouse_w = min(width, height) * 0.38
        mouse_h = mouse_w * 1.25  # 稍微拉高，接近真实鼠标比例
        mouse_x = center_x - mouse_w / 2
        mouse_y = center_y - mouse_h / 2
        border_width = 1.2

        # 获取配置的鼠标按键
        mouse_button: str = self.get_config_value("mouse_button")
        
        # 1. 先绘制整个鼠标为蓝色填充
        cr.save()
        cr.translate(center_x, center_y)
        cr.scale(mouse_w / 2, mouse_h / 2)
        cr.set_source_rgba(0.2, 0.6, 1.0, 1.0)  # 蓝色
        cr.arc(0, 0, 1, 0, 2 * math.pi)
        cr.fill()
        cr.restore()

        # 2. 根据配置决定哪个按键用白色覆盖
        cr.save()
        cr.translate(center_x, center_y)
        cr.scale(mouse_w / 2, mouse_h / 2)
        cr.set_source_rgba(1, 1, 1, 1)  # 白色
        cr.move_to(0, 0)
        
        if mouse_button == "right":
            # 右键（右上区域）用白色覆盖
            cr.arc_negative(0, 0, 1, math.pi * 1.5, 0)
        else:
            # 左键（左上区域）用白色覆盖（默认）
            cr.arc_negative(0, 0, 1, math.pi, math.pi * 1.5)
            
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

    def draw_selection_border(self, cr: "Context[Surface]", width: int, height: int):
        """重写选择边框绘制 - 绘制圆形边框适配圆形按钮"""
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
        """映射模式下的内容绘制 - 显示按键文本"""
        # 使用和编辑模式相同的文本绘制方式
        self.draw_text_content(cr, width, height)

    async def _get_drag_state(self) -> FireDragState:
        async with self._drag_state_lock:
            return self._drag_state

    async def _set_drag_state(self, new_state: FireDragState) -> None:
        async with self._drag_state_lock:
            self._drag_state = new_state

    async def _claim_drag_release(self) -> bool:
        async with self._drag_state_lock:
            if self._drag_state == FireDragState.ACTIVATING:
                self._release_requested = True
                return False
            if self._drag_state != FireDragState.ACTIVE:
                return False

            self._drag_state = FireDragState.RELEASING
            return True

    def _begin_drag_task(self) -> None:
        if self._drag_task and not self._drag_task.done():
            return

        self._release_requested = False
        self._drag_task = asyncio.create_task(self._activate_drag_shot())

    async def _wait_for_aim_handoff(self, event_type: EventType) -> bool:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[bool] = loop.create_future()
        payload: dict[str, Any] = {
            "owner": self,
            "target": self._active_aim_source,
            "future": future,
            "handled": False,
        }

        self.event_bus.emit(Event(event_type, self, payload))
        if not payload["handled"]:
            return False

        try:
            return await asyncio.wait_for(future, timeout=0.5)
        except asyncio.TimeoutError:
            logger.warning("Timed out waiting for %s", event_type.value)
            return False

    def _request_aim_resume_without_wait(self) -> None:
        payload: dict[str, Any] = {
            "owner": self,
            "target": self._active_aim_source,
            "handled": False,
        }
        self.event_bus.emit(Event(EventType.AIM_RESUME_REQUEST, self, payload))

    def _get_platform(self) -> "PlatformBase | None":
        if self.platform is not None:
            return self.platform

        root = self.get_root()
        if root is None:
            logger.warning("Cannot lock pointer for Fire because root window is missing")
            return None

        self.platform = get_platform(root)
        if self.platform is None:
            logger.warning("Cannot lock pointer for Fire because no platform is available")
        return self.platform

    def _lock_pointer_for_drag(self) -> bool:
        platform = self._get_platform()
        if platform is None:
            return False

        platform.set_relative_pointer_callback(self.on_relative_pointer_motion)
        if not platform.lock_pointer():
            logger.warning("Platform refused to lock pointer for Fire drag shot")
            return False

        root = self.get_root()
        if root:
            root = cast("Gtk.Window", root)
            root.set_cursor_from_name("none")
        return True

    def _unlock_pointer_for_drag(self) -> None:
        if self.platform is not None:
            self.platform.set_relative_pointer_callback(None)
            self.platform.unlock_pointer()

        root = self.get_root()
        if root:
            root = cast("Gtk.Window", root)
            root.set_cursor_from_name("default")

    def _clear_motion_queue(self) -> None:
        while not self._motion_queue.empty():
            try:
                self._motion_queue.get_nowait()
            except asyncio.QueueEmpty:
                break

    async def _stop_motion_processor(self) -> None:
        if self._motion_task and not self._motion_task.done():
            try:
                await asyncio.wait_for(self._motion_task, timeout=0.1)
            except asyncio.TimeoutError:
                self._motion_task.cancel()
                try:
                    await self._motion_task
                except asyncio.CancelledError:
                    pass

        self._clear_motion_queue()

    def on_relative_pointer_motion(
        self, dx: float, dy: float, dx_unaccel: float, dy_unaccel: float
    ) -> None:
        """Queue Fire-owned relative pointer movement while drag shot is active."""
        try:
            self._motion_queue.put_nowait((dx, dy, dx_unaccel, dy_unaccel))
        except asyncio.QueueFull:
            try:
                self._motion_queue.get_nowait()
                self._motion_queue.put_nowait((dx, dy, dx_unaccel, dy_unaccel))
            except asyncio.QueueEmpty:
                pass

        if not self._motion_processor_running:
            self._motion_task = asyncio.create_task(self._motion_processor())

    async def _motion_processor(self) -> None:
        self._motion_processor_running = True
        try:
            while True:
                dx, dy, dx_unaccel, dy_unaccel = await self._motion_queue.get()
                if await self._get_drag_state() != FireDragState.ACTIVE:
                    self._clear_motion_queue()
                    break

                await self._handle_single_motion(dx, dy, dx_unaccel, dy_unaccel)
                self._motion_queue.task_done()

        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Fire drag-shot motion processor failed")
        finally:
            self._motion_processor_running = False

    async def _handle_single_motion(
        self, dx: float, dy: float, dx_unaccel: float, dy_unaccel: float
    ) -> None:
        if self._drag_pos is None:
            return

        delta_x = dx_unaccel * self._drag_horizontal_sensitivity / 50
        delta_y = dy_unaccel * self._drag_vertical_sensitivity / 50

        w, h = self.screen_geometry.get_host_resolution()
        self._drag_pos = self._clamp_to_host_surface(
            self._drag_pos[0] + delta_x,
            self._drag_pos[1] + delta_y,
            w,
            h,
        )
        self._send_touch_event(
            AMotionEventAction.MOVE,
            self._drag_pos[0],
            self._drag_pos[1],
            w,
            h,
            1.0,
            0,
            AMotionEventButtons.PRIMARY,
        )

    def _clamp_to_host_surface(
        self, x: float, y: float, w: int, h: int
    ) -> tuple[float, float]:
        # Drag shot has no widget/radius limit; this clamp only keeps the
        # serialized touch coordinates inside the valid Android surface.
        if w > 0:
            x = max(0.0, min(float(w - 1), x))
        if h > 0:
            y = max(0.0, min(float(h - 1), y))
        return x, y

    async def _activate_drag_shot(self) -> None:
        """Own Fire press, Aim suspension, and pointer lock as one transaction."""
        await self._set_drag_state(FireDragState.ACTIVATING)
        touch_down_sent = False
        pointer_locked = False
        aim_suspended = False

        try:
            if not await self._wait_for_aim_handoff(EventType.AIM_SUSPEND_REQUEST):
                logger.warning("Fire drag shot could not suspend active Aim")
                await self._set_drag_state(FireDragState.IDLE)
                return

            aim_suspended = True
            if not self.aim_triggered:
                await self._cleanup_drag_shot(
                    touch_down_sent=False,
                    pointer_locked=False,
                    aim_suspended=False,
                )
                await self._set_drag_state(FireDragState.IDLE)
                return

            if not self._lock_pointer_for_drag():
                await self._cleanup_drag_shot(
                    touch_down_sent=False,
                    pointer_locked=False,
                    aim_suspended=aim_suspended,
                )
                await self._set_drag_state(FireDragState.IDLE)
                return

            pointer_locked = True
            self._drag_pos = (float(self.center_x), float(self.center_y))
            w, h = self.screen_geometry.get_host_resolution()
            touch_down_sent = self._send_touch_event(
                AMotionEventAction.DOWN,
                self._drag_pos[0],
                self._drag_pos[1],
                w,
                h,
                1.0,
                AMotionEventButtons.PRIMARY,
                AMotionEventButtons.PRIMARY,
            )
            if not touch_down_sent:
                await self._cleanup_drag_shot(
                    touch_down_sent=False,
                    pointer_locked=pointer_locked,
                    aim_suspended=aim_suspended,
                )
                await self._set_drag_state(FireDragState.IDLE)
                return

            await self._set_drag_state(FireDragState.ACTIVE)
            if self._release_requested:
                await self._release_drag_shot()

        except asyncio.CancelledError:
            await self._cleanup_drag_shot(
                touch_down_sent=touch_down_sent,
                pointer_locked=pointer_locked,
                aim_suspended=aim_suspended,
            )
            await self._set_drag_state(FireDragState.IDLE)
            raise
        except Exception:
            logger.exception("Failed to activate Fire drag shot")
            await self._cleanup_drag_shot(
                touch_down_sent=touch_down_sent,
                pointer_locked=pointer_locked,
                aim_suspended=aim_suspended,
            )
            await self._set_drag_state(FireDragState.IDLE)

    async def _release_drag_shot(self) -> bool:
        if not await self._claim_drag_release():
            state = await self._get_drag_state()
            if state == FireDragState.ACTIVATING:
                return True
            return False

        await self._cleanup_drag_shot(
            touch_down_sent=True,
            pointer_locked=True,
            aim_suspended=True,
        )
        await self._set_drag_state(FireDragState.IDLE)
        return True

    async def _release_after_aim_released(self) -> None:
        if not await self._claim_drag_release():
            return
        await self._cleanup_drag_shot(
            touch_down_sent=True,
            pointer_locked=True,
            aim_suspended=False,
        )
        await self._set_drag_state(FireDragState.IDLE)

    async def _cleanup_drag_shot(
        self,
        *,
        touch_down_sent: bool,
        pointer_locked: bool,
        aim_suspended: bool,
    ) -> None:
        """Release Fire resources before asking Aim to reclaim pointer lock."""
        await self._stop_motion_processor()

        if touch_down_sent and self._drag_pos is not None:
            w, h = self.screen_geometry.get_host_resolution()
            self._send_touch_event(
                AMotionEventAction.UP,
                self._drag_pos[0],
                self._drag_pos[1],
                w,
                h,
                0.0,
                AMotionEventButtons.PRIMARY,
                0,
            )

        self._drag_pos = None

        if pointer_locked:
            self._unlock_pointer_for_drag()

        if aim_suspended:
            resumed = await self._wait_for_aim_handoff(EventType.AIM_RESUME_REQUEST)
            if not resumed:
                logger.warning("Fire drag shot ended but Aim did not resume")

    def _send_touch_event(
        self,
        action: AMotionEventAction,
        x: float,
        y: float,
        w: int,
        h: int,
        pressure: float,
        action_button: AMotionEventButtons | int,
        buttons: AMotionEventButtons | int,
    ) -> bool:
        if action == AMotionEventAction.DOWN:
            pointer_id = self.pointer_id_manager.allocate(self)
        else:
            pointer_id = self.pointer_id_manager.get_allocated_id(self)

        if pointer_id is None:
            logger.warning("Fire could not find a pointer id for %s", action.name)
            return False

        msg = InjectTouchEventMsg(
            action=action,
            pointer_id=pointer_id,
            position=(int(x), int(y), w, h),
            device_resolution=self.screen_geometry.get_device_resolution_for_client(w, h),
            pressure=pressure,
            action_button=action_button,
            buttons=buttons,
        )
        self.event_bus.emit(Event(EventType.CONTROL_MSG, self, msg))

        if action == AMotionEventAction.UP:
            self.pointer_id_manager.release(self)
        return True

    def on_key_triggered(
        self,
        key_combination: KeyCombination | None = None,
        event: "InputEvent | None" = None,
    ) -> bool:
        """当映射的按键被触发时的行为 - 模拟点击效果（按键按下）"""
        if not self.aim_triggered:
            return False

        if self._drag_shot_enabled:
            if self._drag_state != FireDragState.IDLE:
                return True
            self._begin_drag_task()
            return True

        x, y = self.center_x, self.center_y
        w, h = self.screen_geometry.get_host_resolution()
        return self._send_touch_event(
            AMotionEventAction.DOWN,
            x,
            y,
            w,
            h,
            1.0,
            AMotionEventButtons.PRIMARY,
            AMotionEventButtons.PRIMARY,
        )

    def on_key_released(
        self,
        key_combination: KeyCombination | None = None,
        event: "InputEvent | None" = None,
    ):
        """当映射的按键被弹起时的行为 - 模拟释放效果（按键弹起）"""
        state = self._drag_state
        if state in {FireDragState.ACTIVATING, FireDragState.ACTIVE}:
            asyncio.create_task(self._release_drag_shot())
            return True
        if state == FireDragState.RELEASING:
            return True

        if not self.aim_triggered:
            return False
        x, y = self.center_x, self.center_y
        w, h = self.screen_geometry.get_host_resolution()
        return self._send_touch_event(
            AMotionEventAction.UP,
            x,
            y,
            w,
            h,
            0.0,
            AMotionEventButtons.PRIMARY,
            0,
        )

    def cleanup(self) -> None:
        """Cancel pending drag-shot work before widget destruction."""
        if self._drag_task and not self._drag_task.done():
            self._drag_task.cancel()
        if self._motion_task and not self._motion_task.done():
            self._motion_task.cancel()
        self._force_release_touch_and_pointer_lock()
        self._clear_motion_queue()

    def on_delete(self):
        self.cleanup()
        super().on_delete()

    def _force_release_touch_and_pointer_lock(self) -> None:
        pointer_id = self.pointer_id_manager.get_allocated_id(self)
        if pointer_id is not None:
            w, h = self.screen_geometry.get_host_resolution()
            x, y = self._drag_pos or (self.center_x, self.center_y)
            self._send_touch_event(
                AMotionEventAction.UP,
                x,
                y,
                w,
                h,
                0.0,
                AMotionEventButtons.PRIMARY,
                0,
            )

        if self._drag_state != FireDragState.IDLE:
            self._unlock_pointer_for_drag()
            if self.aim_triggered:
                self._request_aim_resume_without_wait()
            self._drag_state = FireDragState.IDLE
            self._drag_pos = None

    def get_editable_regions(self) -> list["EditableRegion"]:
        """获取可编辑区域列表 - 支持多区域编辑的widget应重写此方法"""
        return [
            {
                "id": "default",
                "name": "按键映射",
                "bounds": (0, 0, self.width, self.height),
                "get_keys": lambda: self.final_keys.copy(),
                "set_keys": lambda keys: setattr(
                    self, "final_keys", set(keys) if keys else set()
                ),
            }
        ]

    @property
    def mapping_start_x(self):
        return self.x + self.width / 2

    @property
    def mapping_start_y(self):
        return self.y + self.height / 2

    @property
    def center_x(self):
        return self.x + self.width / 2

    @property
    def center_y(self):
        return self.y + self.height / 2
