"""
平台功能抽象基类
定义各平台需要实现的通用接口
"""

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    import gi

    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk


class PlatformBase(ABC):
    """平台功能抽象基类"""

    def __init__(self, widget: "Gtk.Window"):
        self.widget: "Gtk.Window" = widget

    @abstractmethod
    def cleanup(self):
        """清理平台资源"""

    # 鼠标相关功能
    @abstractmethod
    def lock_pointer(self) -> bool:
        pass

    @abstractmethod
    def unlock_pointer(self) -> bool:
        """解锁鼠标指针"""

    @abstractmethod
    def is_pointer_locked(self) -> bool:
        """检查鼠标是否被锁定"""

    @abstractmethod
    def set_relative_pointer_callback(
        self, callback: Callable[[float, float, float, float], None] | None
    ):
        """设置相对鼠标移动回调"""
