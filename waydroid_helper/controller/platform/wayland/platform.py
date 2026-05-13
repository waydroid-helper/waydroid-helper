"""
Wayland 平台实现
提供 Wayland 特定的功能，如指针锁定、相对鼠标移动等
"""

import ctypes
from typing import Callable

from gi.repository import GObject
from pywayland import ffi
from pywayland.client import Display
from pywayland.protocol.pointer_constraints_unstable_v1 import \
    ZwpPointerConstraintsV1
from pywayland.protocol.relative_pointer_unstable_v1 import \
    ZwpRelativePointerManagerV1
from pywayland.protocol.wayland import WlCompositor, WlSeat, WlSurface

from ..base import PlatformBase
from waydroid_helper.util.log import logger

# 加载libgtk-4.so.1
libgtk = ctypes.CDLL("libgtk-4.so.1")

# 定义函数原型
libgtk.gdk_wayland_surface_get_wl_surface.restype = ctypes.c_void_p
libgtk.gdk_wayland_surface_get_wl_surface.argtypes = [ctypes.c_void_p]
libgtk.gdk_wayland_display_get_wl_display.restype = ctypes.c_void_p
libgtk.gdk_wayland_display_get_wl_display.argtypes = [ctypes.c_void_p]


def get_wayland_surface(widget):
    gdk_surface = widget.get_surface()
    return libgtk.gdk_wayland_surface_get_wl_surface(hash(gdk_surface))


def get_wayland_display(widget):
    """获取Wayland显示"""
    logger.debug(f"Getting Wayland display: {widget}")
    gdk_display = widget.get_display()
    return libgtk.gdk_wayland_display_get_wl_display(hash(gdk_display))


class PointerConstraint(GObject.Object):
    __gsignals__ = {
        "relative-motion": (
            GObject.SignalFlags.RUN_FIRST,
            None,
            (float, float, float, float),
        )
    }

    def __init__(self, widget):
        super().__init__()
        self.widget = widget
        self.wl_display_ptr = None
        self.wl_surface_ptr = None
        self.pointer_constraints = None
        self.relative_pointer_manager = None
        self.locked_pointer = None
        self.relative_pointer = None
        self.compositor = None
        self.seat = None
        self.pointer = None

    def seat_handle_capabilities(self, seat, caps):
        if (caps & WlSeat.capability.pointer) and not self.pointer:
            self.pointer = seat.get_pointer()

    def registry_global(self, registry, id, interface, version):
        if interface == ZwpPointerConstraintsV1.name:
            self.pointer_constraints = registry.bind(
                id, ZwpPointerConstraintsV1, version
            )
        elif interface == WlCompositor.name:
            self.compositor = registry.bind(id, WlCompositor, version)
        elif interface == WlSeat.name:
            self.seat = registry.bind(id, WlSeat, version)
            self.seat.dispatcher["capabilities"] = self.seat_handle_capabilities
        elif interface == ZwpRelativePointerManagerV1.name:
            self.relative_pointer_manager = registry.bind(
                id, ZwpRelativePointerManagerV1, version
            )

    def setup(self):
        # 获取Wayland显示和表面
        self.wl_display_ptr = get_wayland_display(self.widget)
        self.wl_surface_ptr = get_wayland_surface(self.widget)

        # 创建PyWayland显示对象
        self.wl_display = Display()
        self.wl_display._ptr = ffi.cast("struct wl_display *", self.wl_display_ptr)
        self.wl_surface = WlSurface()
        self.wl_surface._ptr = ffi.cast("struct wl_proxy *", self.wl_surface_ptr)

        # 获取全局对象
        registry = self.wl_display.get_registry()
        registry.dispatcher["global"] = self.registry_global

        self.wl_display.roundtrip()
        self.wl_display.roundtrip()
        if not (self.pointer_constraints and self.pointer and self.seat):
            logger.error("Failed to get required interfaces")
            exit(1)

    def relative_pointer_handle_relative_motion(
        self,
        zwp_relative_pointer_v1,
        utime_hi,
        utime_lo,
        dx,
        dy,
        dx_unaccel,
        dy_unaccel,
    ):
        self.emit("relative-motion", dx, dy, dx_unaccel, dy_unaccel)

    def lock_pointer(self):
        try:
            if self.pointer_constraints and self.pointer:
                self.locked_pointer = self.pointer_constraints.lock_pointer(
                    self.wl_surface,
                    self.pointer,
                    None,
                    ZwpPointerConstraintsV1.lifetime.persistent,
                )

            if self.relative_pointer_manager and self.pointer:
                self.relative_pointer = (
                    self.relative_pointer_manager.get_relative_pointer(self.pointer)
                )
                if self.relative_pointer:
                    self.relative_pointer.dispatcher["relative_motion"] = (
                        self.relative_pointer_handle_relative_motion
                    )

            logger.debug(f"Successfully locked mouse to widget: {type(self.widget).__name__}")
            return True
        except Exception as e:
            logger.error(f"Failed to lock mouse: {e}")
            return False

    def unlock_pointer(self):
        try:
            if self.locked_pointer:
                self.locked_pointer.destroy()
                self.locked_pointer = None
            if self.relative_pointer:
                self.relative_pointer.destroy()
                self.relative_pointer = None
            logger.debug("Mouse unlocked")
            return True
        except Exception as e:
            logger.error(f"Failed to unlock mouse: {e}")
            return False


class WaylandPlatform(PlatformBase):
    """Wayland 平台功能实现"""

    def __init__(self, widget):
        super().__init__(widget)
        logger.debug(f"Initializing WaylandPlatform: {widget}")
        self.pointer_constraint = None
        self._relative_pointer_callback = None

    def cleanup(self):
        """清理 Wayland 资源"""
        if self.pointer_constraint:
            self.pointer_constraint.unlock_pointer()
            self.pointer_constraint = None
        logger.debug("Cleaning up Wayland platform resources")

    def relative_pointer_callback(self, obj, dx, dy, dx_unaccel, dy_unaccel):
        if self._relative_pointer_callback:
            self._relative_pointer_callback(dx, dy, dx_unaccel, dy_unaccel)

    def lock_pointer(self) -> bool:
        try:
            # 如果已经有锁定的指针，先解锁
            if self.pointer_constraint:
                self.unlock_pointer()

            # 创建新的指针约束
            self.pointer_constraint = PointerConstraint(self.widget)
            self.pointer_constraint.setup()
            self.pointer_constraint.lock_pointer()  # 不传 widget 参数
            self.pointer_constraint.connect(
                "relative-motion", self.relative_pointer_callback
            )

            logger.debug(f"Successfully locked mouse to widget: {type(self.widget).__name__}")
            return True

        except Exception as e:
            logger.error(f"Failed to lock mouse: {e}")
            self.pointer_constraint = None
            return False

    def unlock_pointer(self) -> bool:
        """解锁鼠标指针"""
        if not self.pointer_constraint:
            return True

        try:
            self.pointer_constraint.unlock_pointer()
            self.pointer_constraint.disconnect_by_func(self.relative_pointer_callback)
            self.pointer_constraint = None
            logger.debug("Mouse unlocked")
            return True

        except Exception as e:
            logger.error(f"Failed to unlock mouse: {e}")
            return False

    def is_pointer_locked(self) -> bool:
        """检查鼠标是否被锁定"""
        return self.pointer_constraint is not None

    def set_relative_pointer_callback(
        self, callback: Callable[[float, float, float, float], None] | None
    ):
        self._relative_pointer_callback = callback
