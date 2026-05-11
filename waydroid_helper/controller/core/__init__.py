"""
核心模块
"""

from .constants import *
from .control_msg import *
from .event_bus import Event, EventType, EventBus
from .handler.event_handlers import (
    InputEventHandler,
    InputEventHandlerChain,
    InputEventSource,
    InputEventType,
    InputModifierState,
)
from .key_system import (
    Key,
    KeyCombination,
    KeyRegistry,
    KeySymbolResolver,
    KeyType,
)
from .runtime import ControllerRuntimeContext, DefaultHandlerRuntimeConfig, ScreenGeometry
from .server import Server
from .types import *
from .utils import *

__all__ = [
    # 事件系统
    "EventBus",
    "Event",
    "EventType",
    # 输入事件处理
    "InputEventHandler",
    "InputEventHandlerChain",
    "InputEventSource",
    "InputEventType",
    "InputModifierState",
    # 按键系统
    "KeyCombination",
    "Key",
    "KeyType",
    "KeyRegistry",
    "KeySymbolResolver",
    "ControllerRuntimeContext",
    "DefaultHandlerRuntimeConfig",
    "ScreenGeometry",
    # 服务器
    "Server",
    'PointerIdManager',
]
