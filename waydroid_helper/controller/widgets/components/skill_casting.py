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

from waydroid_helper.controller.widgets.components.cancel_casting import \
    CancelCasting
from waydroid_helper.util.log import logger

if TYPE_CHECKING:
    from cairo import Context, Surface
    from gi.repository import Gtk
    from waydroid_helper.controller.widgets.base.base_widget import EditableRegion

from cairo import FONT_SLANT_NORMAL, FONT_WEIGHT_BOLD

from waydroid_helper.controller.android.input import (AMotionEventAction,
                                                      AMotionEventButtons)
from waydroid_helper.controller.core import (Event, EventType, KeyCombination,
                                             EventBus, PointerIdManager, KeyRegistry)
from waydroid_helper.controller.core.control_msg import InjectTouchEventMsg, ScreenInfo
from waydroid_helper.controller.core.handler.event_handlers import InputEvent
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
        event_bus: EventBus | None = None,
        pointer_id_manager: PointerIdManager | None = None,
        key_registry: KeyRegistry | None = None,
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
            event_bus=event_bus,
            pointer_id_manager=pointer_id_manager,
            key_registry=key_registry,
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
        self.screen_info = ScreenInfo()

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
        except:
            pass

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
        except:
            pass

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
        except:
            pass

    def _on_cancel_casting(self, event):
        """取消施法事件回调 - 将事件放入队列"""
        skill_event = SkillEvent(
            type="cancel_casting", data=event.data if hasattr(event, "data") else event
        )

        # 非阻塞方式放入队列
        try:
            self._event_queue.put_nowait(skill_event)
        except:
            pass

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

    async def _release_skill(self):
        """释放技能"""
        self._emit_touch_event(AMotionEventAction.UP)
        await self._reset_skill()

    async def _reset_skill(self):
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

        # 添加圆半径配置
        circle_radius_config = create_slider_config(
            key="circle_radius",
            label=pgettext("Controller Widgets", "Casting Radius"),
            value=200,
            min_value=50,
            max_value=500,
            step=10,
            description=pgettext(
                "Controller Widgets",
                "Fine-tune according to the casting range of different skills",
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
        self.add_config_item(cast_timing_config)
        self.add_config_item(self.cancel_button_config)

        # 添加配置变更回调
        self.add_config_change_callback("circle_radius", self._on_circle_radius_changed)
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

        w, h = self.screen_info.get_host_resolution()
        # 发送事件通知window创建取消按钮
        create_data = {
            "widget": CancelCasting(event_bus=self.event_bus, pointer_id_manager=self.pointer_id_manager, key_registry=self.key_registry),
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

    def draw_widget_content(self, cr: "Context[Surface]", width: int, height: int):
        """绘制圆形按钮的具体内容"""
        # 计算圆心和半径
        center_x = width / 2
        center_y = height / 2
        radius = min(width, height) / 2 - 5  # 留出边距

        # 绘制圆形背景
        cr.set_source_rgba(0.5, 0.5, 0.5, 0.6)
        cr.arc(center_x, center_y, radius, 0, 2 * math.pi)
        cr.fill()

        # 绘制雷达扫描效果
        # 绘制同心圆（类似雷达的圆圈）- 从内向外颜色加深
        # 内圆 - 最浅灰色 (133/400 = 0.33)
        inner_radius = radius * 0.33
        cr.set_source_rgba(0.8, 0.8, 0.8, 0.8)  # 最浅灰色
        cr.arc(center_x, center_y, inner_radius, 0, 2 * math.pi)
        cr.fill()

        # 中圆 - 中等灰色 (266/400 = 0.66)
        middle_radius = radius * 0.66
        cr.set_source_rgba(0.6, 0.6, 0.6, 0.8)  # 中等灰色
        cr.arc(center_x, center_y, middle_radius, 0, 2 * math.pi)
        cr.fill()

        # 外圆已经是原本的圆形背景(0.5, 0.5, 0.5, 0.6)，是最深的，保持不变

        # 绘制135度扇形朝上 - 透明度高
        cr.set_source_rgba(64 / 255, 224 / 255, 208 / 255, 0.25)  # 青绿色，透明度0.25
        cr.move_to(center_x, center_y)
        # 135度扇形，以向上(-π/2)为中心，向两边扩展67.5度
        start_angle_135 = -math.pi / 2 - 135 * math.pi / 360  # 向上中心-67.5度
        end_angle_135 = -math.pi / 2 + 135 * math.pi / 360  # 向上中心+67.5度
        cr.arc(center_x, center_y, radius, start_angle_135, end_angle_135)
        cr.close_path()
        cr.fill()

        # 绘制45度扇形朝上 - 透明度低
        cr.set_source_rgba(64 / 255, 224 / 255, 208 / 255, 0.15)  # 青绿色，透明度0.15
        cr.move_to(center_x, center_y)
        # 45度扇形，以向上(-π/2)为中心，向两边扩展22.5度
        start_angle_45 = -math.pi / 2 - 45 * math.pi / 360  # 向上中心-22.5度
        end_angle_45 = -math.pi / 2 + 45 * math.pi / 360  # 向上中心+22.5度
        cr.arc(center_x, center_y, radius, start_angle_45, end_angle_45)
        cr.close_path()
        cr.fill()

        # 绘制圆形边框
        cr.set_source_rgba(0.3, 0.3, 0.3, 0.9)
        cr.set_line_width(2)
        cr.arc(center_x, center_y, radius, 0, 2 * math.pi)
        cr.stroke()

    def draw_text_content(self, cr: "Context[Surface]", width: int, height: int):
        """重写文本绘制 - 使用白色文字适配圆形按钮"""
        if self.text:
            center_x = width / 2
            center_y = height / 2

            cr.set_source_rgba(1, 1, 1, 1)  # 白色文字
            cr.select_font_face(
                "Arial", FONT_SLANT_NORMAL, FONT_WEIGHT_BOLD
            )
            cr.set_font_size(12)
            text_extents = cr.text_extents(self.text)
            x = center_x - text_extents.width / 2
            y = center_y + text_extents.height / 2
            cr.move_to(x, y)
            cr.show_text(self.text)

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
        """映射模式下的背景绘制 - 根据文字长度的圆角矩形"""
        center_x = width / 2
        center_y = height / 2

        # 计算文字尺寸
        if self.text:
            cr.set_font_size(12)
            text_extents = cr.text_extents(self.text)
            text_width = text_extents.width
            text_height = text_extents.height
        else:
            text_width = 20  # 默认宽度
            text_height = 12  # 默认高度

        # 圆角矩形参数
        padding_x = 8  # 左右内边距
        padding_y = 4  # 上下内边距
        corner_radius = 6  # 圆角半径

        rect_width = text_width + 2 * padding_x
        rect_height = text_height + 2 * padding_y

        # 确保矩形不会太小
        rect_width = max(rect_width, 24)
        rect_height = max(rect_height, 16)

        # 计算矩形位置（居中）
        rect_x = center_x - rect_width / 2
        rect_y = center_y - rect_height / 2

        # 绘制圆角矩形背景
        cr.set_source_rgba(0.6, 0.6, 0.6, 0.7)  # 稍微加深一点透明度

        # 使用路径绘制圆角矩形
        # 左上角
        cr.move_to(rect_x + corner_radius, rect_y)
        # 上边
        cr.line_to(rect_x + rect_width - corner_radius, rect_y)
        # 右上角
        cr.arc(
            rect_x + rect_width - corner_radius,
            rect_y + corner_radius,
            corner_radius,
            -math.pi / 2,
            0,
        )
        # 右边
        cr.line_to(rect_x + rect_width, rect_y + rect_height - corner_radius)
        # 右下角
        cr.arc(
            rect_x + rect_width - corner_radius,
            rect_y + rect_height - corner_radius,
            corner_radius,
            0,
            math.pi / 2,
        )
        # 下边
        cr.line_to(rect_x + corner_radius, rect_y + rect_height)
        # 左下角
        cr.arc(
            rect_x + corner_radius,
            rect_y + rect_height - corner_radius,
            corner_radius,
            math.pi / 2,
            math.pi,
        )
        # 左边
        cr.line_to(rect_x, rect_y + corner_radius)
        # 左上角
        cr.arc(
            rect_x + corner_radius,
            rect_y + corner_radius,
            corner_radius,
            math.pi,
            3 * math.pi / 2,
        )
        cr.close_path()
        cr.fill()

        # 绘制圆角矩形边框
        cr.set_source_rgba(0.4, 0.4, 0.4, 0.9)
        cr.set_line_width(1)
        # 重复上面的路径
        cr.move_to(rect_x + corner_radius, rect_y)
        cr.line_to(rect_x + rect_width - corner_radius, rect_y)
        cr.arc(
            rect_x + rect_width - corner_radius,
            rect_y + corner_radius,
            corner_radius,
            -math.pi / 2,
            0,
        )
        cr.line_to(rect_x + rect_width, rect_y + rect_height - corner_radius)
        cr.arc(
            rect_x + rect_width - corner_radius,
            rect_y + rect_height - corner_radius,
            corner_radius,
            0,
            math.pi / 2,
        )
        cr.line_to(rect_x + corner_radius, rect_y + rect_height)
        cr.arc(
            rect_x + corner_radius,
            rect_y + rect_height - corner_radius,
            corner_radius,
            math.pi / 2,
            math.pi,
        )
        cr.line_to(rect_x, rect_y + corner_radius)
        cr.arc(
            rect_x + corner_radius,
            rect_y + corner_radius,
            corner_radius,
            math.pi,
            3 * math.pi / 2,
        )
        cr.close_path()
        cr.stroke()

    def draw_mapping_mode_content(
        self, cr: "Context[Surface]", width: int, height: int
    ):
        if self.text:
            center_x = width / 2
            center_y = height / 2

            # 使用白色文字以在灰色背景上清晰显示
            cr.set_source_rgba(1, 1, 1, 1)  # 白色文字
            cr.select_font_face(
                "Arial", FONT_SLANT_NORMAL, FONT_WEIGHT_BOLD
            )
            cr.set_font_size(12)
            text_extents = cr.text_extents(self.text)
            x = center_x - text_extents.width / 2
            y = center_y + text_extents.height / 2
            cr.move_to(x, y)
            cr.show_text(self.text)

            # 清除路径，避免影响后续绘制
            cr.new_path()

    def _get_window_center(self) -> tuple[float, float]:
        """获取窗口中心坐标"""
        w, h = self.screen_info.get_host_resolution()
        return (w / 2, h / 2)

    def _get_window_size(self) -> tuple[int, int]:
        """获取窗口大小"""
        w, h = self.screen_info.get_host_resolution()
        return w, h

    def _map_circle_to_circle(
        self, mouse_x: float, mouse_y: float
    ) -> tuple[float, float]:
        """
        将鼠标在圆形范围内的坐标映射到虚拟摇杆圆形范围内的坐标

        外圆：窗口中心为圆心，半径按百分比缩放
        内圆：widget中心为圆心，宽度/2为半径
        """
        # 获取窗口信息
        window_center_x, window_center_y = self._get_window_center()
        window_width, window_height = self._get_window_size()

        # 外圆参数（使用像素值）
        outer_radius = self.get_config_value("circle_radius")

        # 虚拟摇杆圆形参数
        widget_center_x = self.center_x
        widget_center_y = self.center_y
        widget_radius = self.width / 2

        # 计算鼠标相对于外圆中心的位置
        rel_x = mouse_x - window_center_x
        rel_y = mouse_y - window_center_y

        # 计算距离
        distance = math.sqrt(rel_x * rel_x + rel_y * rel_y)

        if distance <= outer_radius:
            # 鼠标在外圆内，直接按比例映射
            if distance == 0:
                # 避免除零，直接返回widget中心
                target_x = widget_center_x
                target_y = widget_center_y
            else:
                # 按距离比例映射
                ratio = distance / outer_radius
                target_x = widget_center_x + (rel_x / distance) * ratio * widget_radius
                target_y = widget_center_y + (rel_y / distance) * ratio * widget_radius
        else:
            # 鼠标在外圆外，投影到圆形边界，再映射到widget圆形边界
            if distance == 0:
                target_x = widget_center_x
                target_y = widget_center_y
            else:
                # 投影到外圆边界，然后映射到widget圆形边界
                target_x = widget_center_x + (rel_x / distance) * widget_radius
                target_y = widget_center_y + (rel_y / distance) * widget_radius

        return (target_x, target_y)

    def _emit_touch_event(
        self, action: AMotionEventAction, position: tuple[float, float] | None = None
    ):
        """发送触摸事件"""
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
        is_key_press = event.event_type == "key_press"
        is_mouse_motion = event.event_type == "mouse_motion"

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
    def mapping_start_x(self):
        return int(self.x + self.width / 2)

    @property
    def mapping_start_y(self):
        return int(self.y + self.height / 2)

    @property
    def center_x(self):
        return self.x + self.width / 2

    @property
    def center_y(self):
        return self.y + self.height / 2
