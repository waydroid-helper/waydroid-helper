#!/usr/bin/env python3
"""
事件总线模块
提供事件驱动的组件通信和状态管理
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Generic, List, TypeVar

from waydroid_helper.util.log import logger

# 事件数据类型
T = TypeVar("T")


class EventType(str, Enum):
    """事件类型 - 字符串枚举，便于日志、序列化和跨模块传递"""

    # 系统事件
    MODE_CHANGED = "mode-changed"  # 模式改变

    # aim 事件
    AIM_TRIGGERED = "aim-triggered"  # 瞄准触发
    AIM_RELEASED = "aim-released"  # 瞄准释放
    AIM_SUSPEND_REQUEST = "aim-suspend-request"  # 临时让渡瞄准指针锁
    AIM_RESUME_REQUEST = "aim-resume-request"  # 恢复临时让渡的瞄准指针锁

    # ControlMsg
    CONTROL_MSG = "control-msg"  # 控制消息
    ANDROID_INPUT_STATE_CHANGED = "android-input-state-changed"
    COMPONENT_CANCEL_TRIGGER_STATE = "component-cancel-trigger-state"

    # 宏命令事件
    MACRO_KEY_PRESSED = "macro-key-pressed"  # 宏命令按键按下
    MACRO_KEY_RELEASED = "macro-key-released"  # 宏命令按键释放
    MACRO_RELEASE_ALL = "macro-release-all"  # 宏命令释放所有

    # 自定义事件（组件可以定义自己的事件）
    CUSTOM = "custom"  # 自定义事件基类
    CREATE_WIDGET = "create-widget"  # 创建组件
    DELETE_WIDGET = "delete-widget"  # 删除组件
    SETTINGS_WIDGET = "settings-widget" # 设置组件
    WIDGET_SELECTION_OVERLAY = "widget-selection-overlay"  # 组件选中覆盖层显示

    MOUSE_MOTION = "mouse-motion"  # 鼠标移动事件
    CANCEL_CASTING = "cancel-casting"  # 取消施法事件
    MASK_CLICKED = "mask-clicked"  # 遮罩层点击事件，传递点击坐标
    ENTER_STARING = "enter-staring"  # 进入瞄准模式
    EXIT_STARING = "exit-staring"  # 退出瞄准模式
    SWIPEHOLD_RADIUS = "swipehold-radius"  # 滑动半径设置


@dataclass
class HandlerInfo:
    """处理器信息"""
    handler_id: int
    handler: Callable[["Event[Any]"], None]
    priority: int = 0
    filter_func: Callable[["Event[Any]"], bool] | None = None
    subscriber: Any = None
    sequence: int = 0


@dataclass
class Event(Generic[T]):
    """事件基类"""

    type: EventType  # 事件类型
    source: Any  # 事件源
    data: T  # 事件数据
    timestamp: float = field(default_factory=lambda: __import__("time").time())


class EventBus:
    """事件总线 - 实例内纯 Python 发布/订阅"""

    def __init__(self):
        self._handler_info: Dict[EventType, List[HandlerInfo]] = {}
        self._next_handler_id = 1
        self._next_sequence = 1

    def subscribe(
        self,
        event_type: EventType,
        handler: Callable[[Event[Any]], None],
        filter: Callable[[Event[Any]], bool] | None = None,
        priority: int = 0,
        subscriber: Any = None,
    ) -> None:
        """
        订阅事件
        :param event_type: 事件类型
        :param handler: 处理函数
        :param filter: 可选的事件过滤器
        :param priority: 处理优先级
        :param subscriber: 订阅者对象（用于批量取消订阅）
        """
        # 生成处理器ID
        handler_id = self._next_handler_id
        self._next_handler_id += 1
        sequence = self._next_sequence
        self._next_sequence += 1

        # 存储处理器信息
        if event_type not in self._handler_info:
            self._handler_info[event_type] = []

        info = HandlerInfo(handler_id, handler, priority, filter, subscriber, sequence)
        self._handler_info[event_type].append(info)

        self._reorder_handlers(event_type)

    def _dispatch_event(self, event_type: EventType, source: Any, data: Any) -> None:
        """Dispatch a normalized Event to a stable snapshot of subscribers."""
        event = Event(event_type, source, data)

        for handler_info in list(self._handler_info.get(event_type, [])):
            try:
                if handler_info.filter_func and not handler_info.filter_func(event):
                    continue
                handler_info.handler(event)
            except Exception:
                logger.exception(
                    "Failed to handle event %s with handler #%s",
                    event_type.value,
                    handler_info.handler_id,
                )

    def _reorder_handlers(self, event_type: EventType) -> None:
        """按优先级重新排序处理器"""
        if event_type not in self._handler_info:
            return

        self._handler_info[event_type].sort(key=lambda h: (-h.priority, h.sequence))

    def unsubscribe(
        self, event_type: EventType, handler: Callable[[Event[Any]], None]
    ) -> bool:
        """取消事件订阅"""
        handlers = self._handler_info.get(event_type)
        if not handlers:
            return False

        before_count = len(handlers)
        self._handler_info[event_type] = [
            info
            for info in handlers
            if info.handler is not handler and info.handler != handler
        ]
        removed = before_count - len(self._handler_info[event_type])
        if removed:
            self._drop_event_type_if_unused(event_type)
        return removed > 0

    def unsubscribe_by_subscriber(self, subscriber: Any) -> int:
        """根据订阅者对象取消所有相关的事件订阅

        :param subscriber: 订阅者对象
        :return: 取消的订阅数量
        """
        unsubscribed_count = 0
        subscriber_id = id(subscriber)

        for event_type, handlers in list(self._handler_info.items()):
            kept_handlers = []

            for handler_info in handlers:
                if (
                    handler_info.subscriber is not None
                    and id(handler_info.subscriber) == subscriber_id
                ):
                    unsubscribed_count += 1
                    continue
                kept_handlers.append(handler_info)

            self._handler_info[event_type] = kept_handlers
            self._drop_event_type_if_unused(event_type)

        return unsubscribed_count

    def _drop_event_type_if_unused(self, event_type: EventType) -> None:
        """Drop empty handler buckets to keep future emits cheap."""
        if self._handler_info.get(event_type):
            return

        self._handler_info.pop(event_type, None)

    def emit(self, event: Event[Any]) -> None:
        """
        发送事件
        事件会按优先级顺序传递给所有订阅者
        """
        self._dispatch_event(event.type, event.source, event.data)

    def clear(self) -> None:
        """清空所有订阅"""
        self._handler_info.clear()
        self._next_handler_id = 1
        self._next_sequence = 1
