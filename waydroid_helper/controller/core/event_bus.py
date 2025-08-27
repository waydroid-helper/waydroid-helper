#!/usr/bin/env python3
"""
事件总线模块
提供事件驱动的组件通信和状态管理
"""

import threading
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, Generic, List, TypeVar

import gi

gi.require_version("GObject", "2.0")
from gi.repository import GObject

from waydroid_helper.util.log import logger

# 事件数据类型
T = TypeVar("T")


class EventType(str, Enum):
    """事件类型 - 字符串枚举，可直接用作GTK信号名"""

    # 系统事件
    MODE_CHANGED = "mode-changed"  # 模式改变

    # aim 事件
    AIM_TRIGGERED = "aim-triggered"  # 瞄准触发
    AIM_RELEASED = "aim-released"  # 瞄准释放

    # ControlMsg
    CONTROL_MSG = "control-msg"  # 控制消息

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
    priority: int = 0
    filter_func: Callable[[Any, Any, Any], bool] | None = None
    subscriber: Any = None


class GlobalEventEmitter(GObject.Object):
    """全局事件发射器 - 处理跨组件通信 (严格单例模式)"""

    _instance = None
    _lock = threading.Lock()
    _initialized = False

    __gsignals__ = {
        # 系统事件
        EventType.MODE_CHANGED: (GObject.SignalFlags.RUN_FIRST, None, (object, object)),

        # aim 事件
        EventType.AIM_TRIGGERED: (GObject.SignalFlags.RUN_FIRST, None, (object, object)),
        EventType.AIM_RELEASED: (GObject.SignalFlags.RUN_FIRST, None, (object, object)),

        # ControlMsg
        EventType.CONTROL_MSG: (GObject.SignalFlags.RUN_FIRST, None, (object, object)),

        # 宏命令事件
        EventType.MACRO_KEY_PRESSED: (GObject.SignalFlags.RUN_FIRST, None, (object, object)),
        EventType.MACRO_KEY_RELEASED: (GObject.SignalFlags.RUN_FIRST, None, (object, object)),
        EventType.MACRO_RELEASE_ALL: (GObject.SignalFlags.RUN_FIRST, None, (object, object)),

        # 自定义事件
        EventType.CUSTOM: (GObject.SignalFlags.RUN_FIRST, None, (object, object)),
        EventType.CREATE_WIDGET: (GObject.SignalFlags.RUN_FIRST, None, (object, object)),
        EventType.DELETE_WIDGET: (GObject.SignalFlags.RUN_FIRST, None, (object, object)),
        EventType.SETTINGS_WIDGET: (GObject.SignalFlags.RUN_FIRST, None, (object, object)),
        EventType.WIDGET_SELECTION_OVERLAY: (GObject.SignalFlags.RUN_FIRST, None, (object, object)),

        # 交互事件
        EventType.MOUSE_MOTION: (GObject.SignalFlags.RUN_FIRST, None, (object, object)),
        EventType.CANCEL_CASTING: (GObject.SignalFlags.RUN_FIRST, None, (object, object)),
        EventType.MASK_CLICKED: (GObject.SignalFlags.RUN_FIRST, None, (object, object)),
        EventType.ENTER_STARING: (GObject.SignalFlags.RUN_FIRST, None, (object, object)),
        EventType.EXIT_STARING: (GObject.SignalFlags.RUN_FIRST, None, (object, object)),
        EventType.SWIPEHOLD_RADIUS: (GObject.SignalFlags.RUN_FIRST, None, (object, object)),
    }

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # 防止重复初始化
        if GlobalEventEmitter._initialized:
            return

        with GlobalEventEmitter._lock:
            if GlobalEventEmitter._initialized:
                return

            super().__init__()
            # 存储处理器信息用于优先级和过滤
            self._handler_info: Dict[EventType, List[HandlerInfo]] = {}

            GlobalEventEmitter._initialized = True

    def emit_event(self, event_type: EventType, source: Any, data: Any):
        """发射事件信号"""
        self.emit(event_type.value, source, data)

    @classmethod
    def reset_singleton(cls) -> None:
        """重置单例状态 - 主要用于测试和窗口重新打开"""
        with cls._lock:
            cls._instance = None
            cls._initialized = False


@dataclass
class Event(Generic[T]):
    """事件基类"""

    type: EventType  # 事件类型
    source: Any  # 事件源
    data: T  # 事件数据
    timestamp: float = field(default_factory=lambda: __import__("time").time())


class EventBus:
    """事件总线 - 基于GTK信号系统的兼容层 (严格单例模式)"""

    _instance = None
    _lock = threading.Lock()
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance

    def __init__(self):
        # 防止重复初始化
        if EventBus._initialized:
            return

        with EventBus._lock:
            if EventBus._initialized:
                return

            # 获取全局事件发射器单例
            self._emitter = GlobalEventEmitter()

            # 存储处理器信息用于优先级和过滤
            self._handler_info: Dict[EventType, List[HandlerInfo]] = {}

            # 存储连接ID用于断开连接
            self._connections: Dict[int, int] = {}  # handler_id -> connection_id
            self._next_handler_id = 1

            EventBus._initialized = True

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
        # 创建包装处理器来处理优先级和过滤
        def wrapped_handler(emitter, source, data):
            # 创建Event对象
            event = Event(event_type, source, data)

            # 应用过滤器
            if filter and not filter(event):
                return

            # 调用原始处理器
            try:
                handler(event)
            except Exception as e:
                logger.error(f"Failed to handle event {event_type.value}: {e}")

        # 连接GTK信号
        connection_id = self._emitter.connect(event_type.value, wrapped_handler)

        # 生成处理器ID
        handler_id = self._next_handler_id
        self._next_handler_id += 1

        # 存储处理器信息
        if event_type not in self._handler_info:
            self._handler_info[event_type] = []

        info = HandlerInfo(handler_id, priority, filter, subscriber)
        self._handler_info[event_type].append(info)
        self._connections[handler_id] = connection_id

        # 按优先级重新排序连接（需要断开重连来保证顺序）
        self._reorder_handlers(event_type)


    def _reorder_handlers(self, event_type: EventType) -> None:
        """按优先级重新排序处理器"""
        if event_type not in self._handler_info:
            return

        # 按优先级排序
        self._handler_info[event_type].sort(key=lambda h: h.priority, reverse=True)

        # 注意：GTK信号的调用顺序由连接顺序决定，
        # 如果需要严格的优先级控制，可能需要在包装处理器中实现

    def unsubscribe(
        self, event_type: EventType, handler: Callable[[Event[Any]], None]
    ) -> bool:
        """取消事件订阅"""
        # 注意：由于我们使用了包装处理器，直接按handler取消订阅比较困难
        # 这个方法主要为了兼容性，实际使用中建议使用unsubscribe_by_subscriber
        return False

    def unsubscribe_by_subscriber(self, subscriber: Any) -> int:
        """根据订阅者对象取消所有相关的事件订阅

        :param subscriber: 订阅者对象
        :return: 取消的订阅数量
        """
        unsubscribed_count = 0
        subscriber_id = id(subscriber)

        for event_type in list(self._handler_info.keys()):
            handlers_to_remove = []

            for handler_info in self._handler_info[event_type]:
                if handler_info.subscriber is not None and id(handler_info.subscriber) == subscriber_id:
                    # 断开GTK信号连接
                    connection_id = self._connections.get(handler_info.handler_id)
                    if connection_id is not None:
                        self._emitter.disconnect(connection_id)
                        del self._connections[handler_info.handler_id]

                    handlers_to_remove.append(handler_info)
                    unsubscribed_count += 1

            # 从列表中移除处理器信息
            for handler_info in handlers_to_remove:
                self._handler_info[event_type].remove(handler_info)

        return unsubscribed_count

    def emit(self, event: Event[Any]) -> None:
        """
        发送事件
        事件会按优先级顺序传递给所有订阅者
        """
        # 使用GTK信号系统发射事件
        self._emitter.emit_event(event.type, event.source, event.data)

    def clear(self) -> None:
        """清空所有订阅"""
        # 断开所有GTK信号连接
        for connection_id in self._connections.values():
            self._emitter.disconnect(connection_id)

        # 清空所有数据结构
        self._connections.clear()
        self._handler_info.clear()

    @classmethod
    def reset_singleton(cls) -> None:
        """重置单例状态 - 主要用于测试和窗口重新打开"""
        with cls._lock:
            if cls._instance is not None:
                cls._instance.clear()
            cls._instance = None
            cls._initialized = False
            # 同时重置全局事件发射器
            GlobalEventEmitter.reset_singleton()


# # 全局事件总线实例
# event_bus = EventBus()
