#!/usr/bin/env python3
"""
技能释放按钮组件
一个圆形的半透明灰色按钮，支持技能释放操作
"""

import asyncio
import math
import time
from dataclasses import dataclass
from enum import Enum
from gettext import pgettext
from typing import TYPE_CHECKING, cast

from waydroid_helper.controller.widgets.base import control_art as art

from waydroid_helper.controller.widgets.components.cancel_casting import \
    CancelCasting
from waydroid_helper.util.log import logger
from gi.repository import Gtk

if TYPE_CHECKING:
    from cairo import Context, Surface
    from waydroid_helper.controller.widgets.base.base_widget import EditableRegion

from cairo import FONT_SLANT_NORMAL, FONT_WEIGHT_BOLD

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
from waydroid_helper.controller.widgets.config import (create_dropdown_config,
                                                       create_slider_config,
                                                       create_switch_config)
from waydroid_helper.controller.widgets.decorators import (Editable, Resizable,
                                                           ResizableDecorator)

class SkillState(Enum):
    """技能释放状态枚举"""

    INACTIVE = "inactive"  # 未激活
    MOVING = "moving"  # 移动中（向目标位置移动）
    ACTIVE = "active"  # 激活状态（可以瞬移）
    LOCKED = "locked"  # 锁定状态（手动释放模式）
    CANCELING = "canceling"  # 取消施法移动状态


class CastTiming(Enum):
    """施法时机枚举"""

    ON_RELEASE = "on_release"  # 松开释放
    IMMEDIATE = "immediate"  # 立即释放
    MANUAL = "manual"  # 手动释放


@dataclass
class SkillEvent:
    """技能事件数据类"""

    type: str  # "key_press", "key_release", "mouse_motion", "cancel_casting"
    data: dict
    timestamp: float = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = time.time()


@Editable
@Resizable(resize_strategy=ResizableDecorator.RESIZE_CENTER)
class SkillCasting(BaseWidget):
    """技能释放按钮组件 - 圆形半透明按钮"""

    # 组件元数据
    WIDGET_NAME = pgettext("Controller Widgets", "Skill Casting")
    PLACED_HINT = pgettext(
        "Controller Widgets",
        "Place this over the skill button, bind a key and aim with the mouse",
    )
    WIDGET_DESCRIPTION = pgettext(
        "Controller Widgets",
        "Commonly used when using the characters' skills, click and cooperate with the mouse to release skills.",
    )

    # 映射模式固定尺寸
    MAPPING_MODE_HEIGHT = 30

    cancel_button_widget = {"widget": None}
    cancel_button_config = create_switch_config(
        key="enable_cancel_button",
        label=pgettext("Controller Widgets", "Enable Cancel Button"),
        value=False,
        description=pgettext(
            "Controller Widgets",
            "Enable a cancel casting button that can interrupt ongoing skill casting",
        ),
    )

    @property
    def MAPPING_MODE_WIDTH(self):
        """根据文字长度计算映射模式宽度，与draw_mapping_mode_background的逻辑保持一致"""
        if self.text:
            # 估算文字宽度：对于12px的Arial字体
            # 英文数字字符平均约7-8px，为保险起见用8px
            # 中文字符约12px，这里简化统一按8px估算（略保守）
            estimated_text_width = len(self.text) * 8

            # 加上左右内边距 (padding_x = 8 * 2 = 16)
            padding_x = 8
            rect_width = estimated_text_width + 2 * padding_x

            # 确保最小宽度 24，与draw_mapping_mode_background一致
            rect_width = max(rect_width, 24)

            # 为了保险起见，再加4px缓冲，确保不会被截断
            return rect_width + 4
        else:
            # 无文字时的默认宽度，与draw_mapping_mode_background的default保持一致
            return 24 + 4  # 24是最小宽度，+4是缓冲

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
        # 初始化基类，传入默认按键
        super().__init__(
            x,
            y,
            min(width, height),
            min(width, height),
            pgettext("Controller Widgets", "Skill Casting"),
            text,
            default_keys,
            min_width=25,
            min_height=25,
            runtime_context=runtime_context,
        )

        # 异步状态管理
        self._skill_state: SkillState = SkillState.INACTIVE
        self._current_position: tuple[float, float] = (x + width / 2, y + height / 2)
        self._target_position: tuple[float, float] = (x + width / 2, y + height / 2)
        self.is_reentrant: bool = True

        # 异步任务管理
        self._current_task: asyncio.Task | None = None
        self._event_queue: asyncio.Queue = asyncio.Queue()
        self._event_processor_task: asyncio.Task | None = None

        # 技能释放控制标志
        self._target_locked: bool = False  # 是否锁定目标位置（所有模式共用）
        self._key_released_during_moving: bool = (
            False  # 移动过程中按键是否已释放（ON_RELEASE模式专用）
        )

        # 取消施法相关变量
        self._cancel_target_position: tuple[float, float] | None = (
            None  # 取消施法的目标位置
        )

        # 平滑移动系统参数
        self._move_interval: float = 0.02  # 20ms，转换为秒
        self._move_steps_total: int = 6

        # 圆形映射参数（像素值）
        # self.circle_radius: int = 200  # 圆半径，单位像素
        self._mouse_x: float = 0
        self._mouse_y: float = 0

        # 施法时机配置
        # self.cast_timing: str = CastTiming.ON_RELEASE.value  # 默认为松开释放

        # 设置配置项
        self.setup_config()
        self._install_radius_drag()

        # 监听选中状态变化，用于圆形绘制通知
        self.connect("notify::is-selected", self._on_selection_changed)

        # 启动异步事件处理器
        self._start_event_processor()

        # 订阅事件总线
        self.event_bus.subscribe(EventType.MOUSE_MOTION, self._on_mouse_motion, subscriber=self)
        self.event_bus.subscribe(EventType.CANCEL_CASTING, self._on_cancel_casting, subscriber=self)

        # # 测试：监听取消按钮销毁事件
        # event_bus.subscribe(
        #     EventType.CANCEL_BUTTON_DESTROYED,
        #     self._on_custom_event,
        #     filter=lambda e: e.data.get("widget_class") == "CancelCasting"
        #     and self._cancel_button_widget["widget"] is not None,
        #     subscriber=self,
        # )

    def _start_event_processor(self):
        """启动异步事件处理器"""
        if self._event_processor_task is None or self._event_processor_task.done():
            self._event_processor_task = asyncio.create_task(self._process_events())

    async def _process_events(self):
        """异步事件处理器主循环"""
        try:
            while True:
                # 等待事件
                event = await self._event_queue.get()
                await self._handle_event(event)
                self._event_queue.task_done()
        except asyncio.CancelledError:
            logger.debug("SkillCasting event processor cancelled")
            raise
        except Exception:
            logger.exception("SkillCasting event processor failed")

    async def _handle_event(self, event: SkillEvent):
        """处理单个事件"""
        try:
            if event.type == "key_press":
                await self._handle_key_press(event)
            elif event.type == "key_release":
                await self._handle_key_release(event)
            elif event.type == "mouse_motion":
                await self._handle_mouse_motion_async(event)
            elif event.type == "cancel_casting":
                await self._handle_cancel_casting_async(event)
            else:
                logger.warning("Unknown SkillCasting event type: %s", event.type)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Failed to handle SkillCasting event: %s", event.type)

    def _on_mouse_motion(self, event):
        """鼠标移动事件回调 - 将事件放入队列"""
        # 窗口发送的 MOUSE_MOTION 事件包含 InputEvent 对象
        if hasattr(event, "data") and hasattr(event.data, "position"):
            # 这是 InputEvent 对象
            position = event.data.position
        elif (
            hasattr(event, "data")
            and isinstance(event.data, dict)
            and event.data.get("position")
        ):
            # 这是字典格式的事件数据
            position = event.data["position"]
        else:
            return

        skill_event = SkillEvent(
            type="mouse_motion", data={"position": position, "timestamp": time.time()}
        )

        # 非阻塞方式放入队列
        try:
            self._event_queue.put_nowait(skill_event)
        except asyncio.QueueFull:
            logger.warning("SkillCasting event queue is full; dropping mouse motion")

    def _on_cancel_casting(self, event):
        """取消施法事件回调 - 将事件放入队列"""
        skill_event = SkillEvent(
            type="cancel_casting", data=event.data if hasattr(event, "data") else event
        )

        # 非阻塞方式放入队列
        try:
            self._event_queue.put_nowait(skill_event)
        except asyncio.QueueFull:
            logger.warning("SkillCasting event queue is full; dropping cancel event")

    async def _handle_key_press(self, event: SkillEvent):
        """异步处理按键按下事件"""
        if self._skill_state == SkillState.INACTIVE:
            # 首次激活
            await self._activate_skill()
        elif self._skill_state == SkillState.LOCKED:
            # 手动释放模式的第二次按键
            await self._release_skill()

    async def _handle_key_release(self, event: SkillEvent):
        """异步处理按键释放事件"""
        if self._skill_state == SkillState.INACTIVE:
            return

        # 取消施法状态下不响应按键弹起
        if self._skill_state == SkillState.CANCELING:
            return

        # 根据施法时机决定处理方式
        if self.get_config_value("cast_timing") == CastTiming.ON_RELEASE.value:
            if self._skill_state == SkillState.MOVING:
                # 正在移动中，设置标志表示按键已释放
                self._key_released_during_moving = True
            elif self._skill_state == SkillState.ACTIVE:
                # 已到达目标，立即发送UP事件并重置
                await self._release_skill()

    async def _handle_mouse_motion_async(self, event: SkillEvent):
        """异步处理鼠标移动事件"""
        if not event.data.get("position"):
            return

        self._mouse_x, self._mouse_y = event.data["position"]
        mapped_target = self._map_circle_to_circle(self._mouse_x, self._mouse_y)

        if self._skill_state == SkillState.INACTIVE:
            # 未激活状态下不处理鼠标移动
            return
        elif self._skill_state == SkillState.MOVING:
            # 移动中忽略鼠标移动（目标已锁定）
            return
        elif self._skill_state == SkillState.ACTIVE:
            # 激活状态：更新目标位置并瞬移
            await self._instant_move_to_target(mapped_target)
        elif self._skill_state == SkillState.LOCKED:
            # 锁定状态：鼠标移动，瞬移到新目标位置
            await self._instant_move_to_target(mapped_target)

    async def _handle_cancel_casting_async(self, event: SkillEvent):
        """异步处理取消施法事件"""
        if self._skill_state == SkillState.INACTIVE:
            return

        # 从事件中获取取消施法的目标位置
        event_data = event.data
        if (
            not isinstance(event_data, dict)
            or "x" not in event_data
            or "y" not in event_data
        ):
            return

        cancel_x = event_data["x"]
        cancel_y = event_data["y"]
        self._cancel_target_position = (cancel_x, cancel_y)

        if self._skill_state == SkillState.MOVING:
            # 当前正在移动中，等待移动完成后再执行取消流程
            pass
            # 不取消当前任务，让它自然完成，然后在 _skill_casting_flow 中处理取消
        else:
            # 当前不在移动状态，立即开始取消施法移动
            # 取消当前任务
            if self._current_task and not self._current_task.done():
                self._current_task.cancel()

            # 开始取消施法移动
            self._current_task = asyncio.create_task(self._cancel_casting_move())

    async def _activate_skill(self):
        """激活技能"""
        # 将鼠标位置映射到虚拟摇杆位置
        mapped_target = self._map_circle_to_circle(self._mouse_x, self._mouse_y)

        # 设置目标位置并锁定
        self._target_position = mapped_target
        self._target_locked = True

        # 分配指针ID并发送DOWN事件
        pointer_id = self.pointer_id_manager.allocate(self)
        if pointer_id is None:
            return

        self._current_position = (self.center_x, self.center_y)
        self._emit_touch_event(AMotionEventAction.DOWN, position=self._current_position)

        # 开始技能流程
        self._current_task = asyncio.create_task(self._skill_casting_flow())

    async def _skill_casting_flow(self):
        """技能释放主流程"""
        try:
            # 开始移动
            self._skill_state = SkillState.MOVING
            await self._smooth_move_to_target(self._target_position)

            # 移动完成后，检查是否有取消请求
            if self._cancel_target_position is not None:
                # 有待处理的取消事件，开始取消施法移动
                await self._cancel_casting_move()
                return

            # 根据施法时机处理
            if self.get_config_value("cast_timing") == CastTiming.IMMEDIATE.value:
                # 立即释放模式：移动完成后立即发送UP事件并重置
                await self._release_skill()
            elif self.get_config_value("cast_timing") == CastTiming.MANUAL.value:
                # 手动释放模式：进入锁定状态，等待第二次按键
                self._skill_state = SkillState.LOCKED
                self._target_locked = False  # 解锁目标位置，允许瞬移
            else:  # ON_RELEASE
                # ON_RELEASE模式：检查是否在移动过程中按键已释放
                if self._key_released_during_moving:
                    # 移动过程中按键已释放，立即发送UP事件并重置
                    await self._release_skill()
                else:
                    # 按键未释放，进入激活状态，等待按键松开
                    self._skill_state = SkillState.ACTIVE
                    self._target_locked = False  # 解锁目标位置，允许瞬移

        except asyncio.CancelledError:
            # 被取消时的处理
            await self._release_skill()
        except Exception as e:
            logger.exception("Failed to activate SkillCasting")
            await self._release_skill()

    async def _cancel_casting_move(self):
        """取消施法的平滑移动"""
        if self._cancel_target_position is None:
            return

        try:
            # 设置目标位置并开始移动
            self._target_position = self._cancel_target_position
            self._skill_state = SkillState.CANCELING
            self._target_locked = True  # 锁定目标，不允许中断

            # 开始平滑移动
            await self._smooth_move_to_target(self._cancel_target_position)

            # 移动完成，发送UP事件并重置
            await self._release_skill()

        except asyncio.CancelledError:
            await self._release_skill()
        except Exception:
            logger.exception("Failed to cancel SkillCasting move")
            await self._release_skill()

    async def _smooth_move_to_target(self, target: tuple[float, float]):
        """异步平滑移动到目标位置"""
        start_pos = self._current_position
        steps = self._move_steps_total

        for step in range(1, steps + 1):
            # 计算当前位置
            progress = step / steps
            current_x = start_pos[0] + (target[0] - start_pos[0]) * progress
            current_y = start_pos[1] + (target[1] - start_pos[1]) * progress

            self._current_position = (current_x, current_y)
            self._emit_touch_event(AMotionEventAction.MOVE)

            # 等待间隔
            await asyncio.sleep(self._move_interval)

            # 检查是否被取消
            if self._skill_state == SkillState.INACTIVE:
                return

        # 移动完成
        self._current_position = target

    async def _instant_move_to_target(self, target: tuple[float, float]):
        """瞬间移动到目标位置"""
        self._current_position = target
        self._target_position = target
        self._emit_touch_event(AMotionEventAction.MOVE)

    def stop_gesture(self):
        # A press and release may still be queued on the event processor.
        # Discard them before releasing a manually locked or moving contact.
        while not self._event_queue.empty():
            self._event_queue.get_nowait()
            self._event_queue.task_done()
        if self._skill_state != SkillState.INACTIVE:
            self._emit_touch_event(AMotionEventAction.UP)
            self._reset_skill()

    async def _release_skill(self):
        """释放技能"""
        self._emit_touch_event(AMotionEventAction.UP)
        self._reset_skill()

    def _reset_skill(self):
        """异步重置技能状态"""
        self._skill_state = SkillState.INACTIVE
        self._current_position = (self.center_x, self.center_y)
        self._target_locked = False
        self._key_released_during_moving = False

        # 清理取消施法相关状态
        self._cancel_target_position = None

        # 取消当前任务
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()
            self._current_task = None

        # 释放指针ID
        self.pointer_id_manager.release(self)

    def setup_config(self) -> None:
        """设置配置项"""

        # 添加圆半径配置（世界空间半径，而非屏幕像素）
        circle_radius_config = create_slider_config(
            key="circle_radius",
            label=pgettext("Controller Widgets", "Casting Radius"),
            value=5.0,
            min_value=1.0,
            max_value=12.0,
            step=0.1,
            description=pgettext(
                "Controller Widgets",
                "Radius of the ground-circle in world space used for perspective mapping",
            ),
        )

        # 相机俯仰角（tilt）
        tilt_angle_config = create_slider_config(
            key="tilt_angle",
            label=pgettext("Controller Widgets", "Camera Tilt"),
            value=45.0,
            min_value=8.0,
            max_value=85.0,
            step=0.5,
            description=pgettext(
                "Controller Widgets",
                "Camera tilt angle for perspective circle mapping",
            ),
        )

        # 垂直视野（FOV）
        camera_fov_config = create_slider_config(
            key="camera_fov",
            label=pgettext("Controller Widgets", "Vertical FOV"),
            value=36.0,
            min_value=20.0,
            max_value=120.0,
            step=0.5,
            description=pgettext(
                "Controller Widgets",
                "Vertical field of view used in the perspective projection",
            ),
        )

        # 地面原点在屏幕上的位置，使用百分比（0~100）
        origin_x_config = create_slider_config(
            key="origin_x",
            label=pgettext("Controller Widgets", "Origin X"),
            value=50.0,
            min_value=0.0,
            max_value=100.0,
            step=0.1,
            description=pgettext(
                "Controller Widgets",
                "Horizontal position of ground origin on screen",
            ),
        )

        origin_y_config = create_slider_config(
            key="origin_y",
            label=pgettext("Controller Widgets", "Origin Y"),
            value=50.0,
            min_value=0.0,
            max_value=100.0,
            step=0.1,
            description=pgettext(
                "Controller Widgets",
                "Vertical position of ground origin on screen",
            ),
        )

        # 添加施法时机配置
        cast_timing_config = create_dropdown_config(
            key="cast_timing",
            label=pgettext("Controller Widgets", "Cast Timing"),
            options=[
                CastTiming.ON_RELEASE.value,
                CastTiming.IMMEDIATE.value,
                CastTiming.MANUAL.value,
            ],
            option_labels={
                CastTiming.ON_RELEASE.value: pgettext(
                    "Controller Widgets", "On Release"
                ),
                CastTiming.IMMEDIATE.value: pgettext("Controller Widgets", "Immediate"),
                CastTiming.MANUAL.value: pgettext("Controller Widgets", "Manual"),
            },
            value=CastTiming.ON_RELEASE.value,
            description=pgettext(
                "Controller Widgets",
                "Determines when the skill casting ends: On Release (default), Immediate (auto-release after moving), or Manual (sticky mode)",
            ),
        )

        # 添加取消施法按钮配置

        self.add_config_item(circle_radius_config)
        self._radius_config = circle_radius_config
        self.add_config_item(tilt_angle_config)
        self.add_config_item(camera_fov_config)
        self.add_config_item(origin_x_config)
        self.add_config_item(origin_y_config)
        self.add_config_item(cast_timing_config)
        self.add_config_item(self.cancel_button_config)

        # 添加配置变更回调
        self.add_config_change_callback("circle_radius", self._on_circle_radius_changed)
        self.add_config_change_callback("tilt_angle", self._on_tilt_angle_changed)
        self.add_config_change_callback("camera_fov", self._on_camera_fov_changed)
        self.add_config_change_callback("origin_x", self._on_origin_x_changed)
        self.add_config_change_callback("origin_y", self._on_origin_y_changed)
        self.add_config_change_callback("cast_timing", self._on_cast_timing_changed)
        self.add_config_change_callback(
            "enable_cancel_button", self._on_cancel_button_config_changed
        )

    def _on_circle_radius_changed(self, key: str, value: int, restoring:bool) -> None:
        """处理圆半径配置变更"""
        try:
            # self.circle_radius = int(value)
            # 如果当前选中状态，重新发送圆形绘制事件
            self._update_circle_if_selected()
            self.queue_draw()
        except (ValueError, TypeError):
            pass

    def _on_tilt_angle_changed(self, key: str, value: float, restoring: bool) -> None:
        """处理相机俯仰角配置变更"""
        try:
            # 仅影响映射算法，不需要立即触摸事件；更新选区叠加即可
            self._update_circle_if_selected()
        except (ValueError, TypeError):
            pass

    def _on_camera_fov_changed(self, key: str, value: float, restoring: bool) -> None:
        """处理相机FOV配置变更"""
        try:
            self._update_circle_if_selected()
        except (ValueError, TypeError):
            pass

    def _on_origin_x_changed(self, key: str, value: float, restoring: bool) -> None:
        """处理原点X配置变更"""
        try:
            self._update_circle_if_selected()
        except (ValueError, TypeError):
            pass

    def _on_origin_y_changed(self, key: str, value: float, restoring: bool) -> None:
        """处理原点Y配置变更"""
        try:
            self._update_circle_if_selected()
        except (ValueError, TypeError):
            pass

    def _on_cast_timing_changed(self, key: str, value: str, restoring:bool) -> None:
        """处理施法时机配置变更"""
        try:
            # self.cast_timing = str(value)
            pass
        except (ValueError, TypeError):
            pass

    def _on_cancel_button_config_changed(self, key: str, value: bool, restoring:bool) -> None:
        """处理取消施法按钮配置变更"""
        if restoring:
            return
        try:
            if value:
                self._enable_cancel_button()
            else:
                self._disable_cancel_button()
        except (ValueError, TypeError) as e:
            logger.error(f"SkillCasting {id(self)} _on_cancel_button_config_changed error: {e}")

    # def _on_custom_event(self, event):
    #     """处理自定义事件"""
    #     logger.debug(f"SkillCasting {id(self)} received custom event: {event.data}")

    #     if self._cancel_button_widget["widget"] is not None and id(
    #         self._cancel_button_widget["widget"]
    #     ) == event.data.get("widget_id"):

    #         logger.info(f"Detected cancel button destruction, resetting state")
    #         self._cancel_button_widget["widget"] = None
    #         self.cancel_button_config.value = False

    def _enable_cancel_button(self):
        """启用取消施法按钮"""
        if self.cancel_button_widget["widget"] is not None:
            return

        w, h = self.screen_geometry.get_host_resolution()
        # 发送事件通知window创建取消按钮
        create_data = {
            "widget": CancelCasting(runtime_context=self.runtime_context),
            "x": 0.8 * w,
            "y": h / 2,
        }

        self.event_bus.emit(Event(EventType.CREATE_WIDGET, self, create_data))
        self.cancel_button_widget["widget"] = create_data["widget"]

    def _disable_cancel_button(self):
        """禁用取消施法按钮"""
        if self.cancel_button_widget["widget"] is None:
            return

        # 发送事件通知window删除取消按钮
        self.event_bus.emit(
            Event(EventType.DELETE_WIDGET, self, self.cancel_button_widget["widget"])
        )
        self.cancel_button_widget["widget"] = None

    def __del__(self):
        """析构时清理取消按钮和异步任务"""
        # if self._cancel_button_widget is not None:
        #     self._disable_cancel_button()

        # 取消异步任务
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()
        if self._event_processor_task and not self._event_processor_task.done():
            self._event_processor_task.cancel()

    def _update_circle_if_selected(self):
        """如果当前组件被选中，更新圆形绘制"""
        if self.is_selected:
            circle_data = {
                "widget_id": id(self),
                "widget_type": "skill_casting",
                "circle_radius": self.get_config_value("circle_radius"),
                "tilt_angle": self.get_config_value("tilt_angle"),
                "camera_fov": self.get_config_value("camera_fov"),
                "origin_x": self.get_config_value("origin_x"),
                "origin_y": self.get_config_value("origin_y"),
                "action": "show",
            }
            self.event_bus.emit(Event(EventType.WIDGET_SELECTION_OVERLAY, self, circle_data))

    def _on_selection_changed(self, widget, pspec):
        """当选中状态变化时的回调"""
        if self.is_selected:
            # 发送显示圆形的事件
            circle_data = {
                "widget_id": id(self),
                "widget_type": "skill_casting",
                "circle_radius": self.get_config_value("circle_radius"),
                "tilt_angle": self.get_config_value("tilt_angle"),
                "camera_fov": self.get_config_value("camera_fov"),
                "origin_x": self.get_config_value("origin_x"),
                "origin_y": self.get_config_value("origin_y"),
                "action": "show",
            }
            self.event_bus.emit(Event(EventType.WIDGET_SELECTION_OVERLAY, self, circle_data))
        else:
            # 发送隐藏圆形的事件
            circle_data = {
                "widget_id": id(self),
                "widget_type": "skill_casting",
                "action": "hide",
            }
            self.event_bus.emit(Event(EventType.WIDGET_SELECTION_OVERLAY, self, circle_data))

    def get_edit_chrome_radius(self):
        return max(5, min(24, min(self.width, self.height) / 2 - 4))

    def _radius_track(self):
        """Leave the center and resize handles usable in small saved layouts."""
        x = self.width / 2 - self.get_edit_chrome_radius() - 15
        if x < 13:
            return None
        half = min(28, self.height / 3)
        return x, self.height / 2 - half, self.height / 2 + half

    def _install_radius_drag(self):
        # Claim only presses on the scale. Ordinary drags and keycap clicks
        # must continue to reach the shared workspace interaction handlers.
        drag = Gtk.GestureDrag(button=1)
        drag.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)

        def begin(gesture, x, y):
            track = self._radius_track()
            if (
                self.mapping_mode or not track
                or abs(x - track[0]) > 10
                or not track[1] - 5 <= y <= track[2] + 5
            ):
                gesture.set_state(Gtk.EventSequenceState.DENIED)
                return
            gesture.set_state(Gtk.EventSequenceState.CLAIMED)
            self._set_radius_at(y)

        def update(gesture, dx, dy):
            valid, _, start_y = gesture.get_start_point()
            if valid and gesture.is_recognized():
                self._set_radius_at(start_y + dy)

        drag.connect("drag-begin", begin)
        drag.connect("drag-update", update)
        self.add_controller(drag)

    def _set_radius_at(self, y):
        _, top, bottom = self._radius_track()
        cfg = self._radius_config
        fraction = max(0, min(1, (bottom - y) / (bottom - top)))
        value = cfg.min_value + fraction * (cfg.max_value - cfg.min_value)
        self.set_config_value(cfg.key, round(round(value / cfg.step) * cfg.step, 1))

    def _draw_radius_track(self, cr):
        track = self._radius_track()
        if not track:
            return
        x, top, bottom = track
        cfg = self._radius_config
        value = float(cfg.value)
        fraction = (value - cfg.min_value) / (cfg.max_value - cfg.min_value)
        knob = bottom - fraction * (bottom - top)
        cr.set_line_width(2)
        for start, end, color in ((top, knob, art.OUTLINE), (knob, bottom, (0.02, 0.77, 1, 1))):
            cr.set_source_rgba(*color)
            cr.move_to(x, start)
            cr.line_to(x, end)
            cr.stroke()
        art.rounded(cr, x - 11, knob - 6, 22, 12, 2)
        cr.set_source_rgba(1, 1, 1, 0.94)
        cr.fill()
        art.caption(cr, x, knob, f"{value:g}", 8, (0.12, 0.14, 0.19, 1))

    def draw_selection_border(self, cr, width, height):
        art.ring(cr, width / 2, height / 2, self.get_edit_chrome_radius(), self.is_selected)

    def draw_widget_content(self, cr, width, height):
        # Keep the key legible independently of the configured cast radius.
        # The selected range still follows the original projection and resize
        # geometry, which is also used by the runtime touch calculation.
        x, y, radius = width / 2, height / 2, self.get_edit_chrome_radius()
        art.disc(cr, x, y, radius, art.BODY, art.OUTLINE)
        art.disc(cr, x, y, radius * .74, (.16, .26, .32, .78))
        art.disc(cr, x, y, radius * .48, (.2, .34, .40, .66))
        self._draw_radius_track(cr)
        if self.is_selected:
            cr.set_source_rgba(.6, .85, 1, .65)
            cr.set_line_width(1)
            # The slider caption leaves a current point. Start the range circle
            # separately so Cairo does not connect that point to the arc.
            cr.new_sub_path()
            cr.arc(x, y, max(radius, min(x, y) - 4), 0, math.tau)
            cr.stroke()

    def _get_window_center(self) -> tuple[float, float]:
        """获取窗口中心坐标"""
        w, h = self.screen_geometry.get_host_resolution()
        return (w / 2, h / 2)

    def _get_window_size(self) -> tuple[int, int]:
        """获取窗口大小"""
        w, h = self.screen_geometry.get_host_resolution()
        return w, h

    def _map_circle_to_circle(
        self, mouse_x: float, mouse_y: float
    ) -> tuple[float, float]:
        """
        使用透视投影，将屏幕上的坐标映射到地面圆（世界空间）上，
        再将该圆上的点归一化映射到技能按钮自身的圆形范围内。

        参考 `perspective_circle_static.html` 中的 screenToWorld + 归一化逻辑：
        - 世界平面：X 轴向右，Z 轴向前，Y=0 为地面
        - 相机绕 X 轴俯仰 tilt_angle，垂直视野 camera_fov
        - (origin_x, origin_y) 定义地面原点在屏幕上的位置（归一化 0~1）
        """
        # 获取窗口分辨率
        window_width, window_height = self._get_window_size()
        if window_width <= 0 or window_height <= 0:
            return (self.center_x, self.center_y)

        # 读取透视相关配置
        radius_world = float(self.get_config_value("circle_radius") or 5.0)
        tilt_deg = float(self.get_config_value("tilt_angle") or 45.0)
        fov_deg = float(self.get_config_value("camera_fov") or 36.0)
        origin_x_percent = float(self.get_config_value("origin_x") or 50.0)
        origin_y_percent = float(self.get_config_value("origin_y") or 50.0)
        origin_x_ratio = origin_x_percent / 100.0
        origin_y_ratio = origin_y_percent / 100.0

        # 屏幕上的地面原点（像素）
        origin_sx = origin_x_ratio * window_width
        origin_sy = origin_y_ratio * window_height

        # 垂直 FOV -> 焦距（以窗口高度为参考）
        if fov_deg <= 0 or fov_deg >= 180:
            fov_deg = 36.0
        fov_rad = math.radians(fov_deg)
        focal = (window_height / 2.0) / math.tan(fov_rad / 2.0)

        # 相机到原点的距离 L：保持常量，避免被半径缩放抵消屏幕效果
        # 对齐 HTML demo：默认半径 5、距离约 13.66
        cam_dist = 13.66

        tilt_rad = math.radians(tilt_deg)

        # 将屏幕坐标反投影到地面 (Y=0) 上的世界坐标 (wx, wz)
        sx_n = (mouse_x - origin_sx) / focal
        sy_n = (origin_sy - mouse_y) / focal

        denom = math.sin(tilt_rad) - sy_n * math.cos(tilt_rad)
        if abs(denom) < 1e-7:
            # 退化情况，直接返回技能按钮中心
            return (self.center_x, self.center_y)

        wz = sy_n * cam_dist / denom
        depth = cam_dist + wz * math.cos(tilt_rad)
        wx = sx_n * depth

        # 世界空间中，地面圆心固定为 (0, 0)
        dx = wx
        dz = wz
        dist = math.hypot(dx, dz)

        widget_center_x = self.center_x
        widget_center_y = self.center_y
        widget_radius = self.width / 2.0

        if dist <= 1e-6 or radius_world <= 0 or widget_radius <= 0:
            return (widget_center_x, widget_center_y)

        # 归一化到 [0, 1]，超过圆半径则截断到边界
        ratio_world = min(1.0, dist / radius_world)
        nx = dx / dist * ratio_world
        nz = dz / dist * ratio_world

        # 将世界归一化坐标映射到 widget 自身的圆形范围
        # 注意：世界中的 +Z 在屏幕上是“向上”（参考 perspective_circle_static.html 的 top view），
        # 所以这里要对 Y 轴取反，保证方向一致。
        target_x = widget_center_x + nx * widget_radius
        target_y = widget_center_y - nz * widget_radius

        return (target_x, target_y)

    def _emit_touch_event(
        self, action: AMotionEventAction, position: tuple[float, float] | None = None
    ):
        """发送触摸事件"""
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

    def on_key_triggered(
        self,
        key_combination: KeyCombination | None = None,
        event: "InputEvent | None" = None,
    ):
        """按键触发事件处理 - 将事件放入异步队列"""
        if not event or not event.event_type:
            return False

        # 取消施法状态下不响应任何用户输入
        if self._skill_state == SkillState.CANCELING:
            return True

        # 判断事件类型
        is_key_press = event.event_type == InputEventType.KEY_PRESS
        is_mouse_motion = event.event_type == InputEventType.MOUSE_MOTION

        if not (is_key_press or is_mouse_motion):
            return False

        if is_mouse_motion:
            if not event.position:
                return False
            self._mouse_x, self._mouse_y = event.position

        # 将事件放入异步队列
        skill_event = SkillEvent(
            type=event.event_type,
            data={
                "key_combination": key_combination,
                "position": event.position,
                "timestamp": time.time(),
            },
        )

        # 非阻塞方式放入队列
        try:
            self._event_queue.put_nowait(skill_event)
        except asyncio.QueueFull:
            pass

        return True

    def on_key_released(
        self,
        key_combination: KeyCombination | None = None,
        event: "InputEvent | None" = None,
    ):
        """按键释放事件处理 - 将事件放入异步队列"""
        # 将事件放入异步队列
        skill_event = SkillEvent(
            type="key_release",
            data={"key_combination": key_combination, "timestamp": time.time()},
        )

        # 非阻塞方式放入队列
        try:
            self._event_queue.put_nowait(skill_event)
        except asyncio.QueueFull:
            pass

        return True

    def get_editable_regions(self) -> list["EditableRegion"]:
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
    def center_x(self):
        return self.x + self.width / 2

    @property
    def center_y(self):
        return self.y + self.height / 2
