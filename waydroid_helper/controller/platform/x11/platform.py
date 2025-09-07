"""
X11 平台实现
提供 X11 特定的功能，如指针锁定、相对鼠标移动等
"""

import ctypes
import ctypes.util
import threading
import os
from typing import Callable
import time

from gi.repository import GObject, Gdk, GLib, GdkX11, Gtk

from ..base import PlatformBase
from waydroid_helper.util.log import logger

# 加载 X11 库
libx11_path = ctypes.util.find_library('X11')
libx11 = ctypes.CDLL(libx11_path)

libx11.XWarpPointer.argtypes = [
    ctypes.c_void_p, ctypes.c_ulong, ctypes.c_ulong,
    ctypes.c_int, ctypes.c_int, ctypes.c_uint, ctypes.c_uint,
    ctypes.c_int, ctypes.c_int
]
libx11.XFlush.argtypes = [ctypes.c_void_p]
libgtk_path = ctypes.util.find_library("gtk-4")

libgtk = ctypes.CDLL(libgtk_path)
libgtk.gdk_x11_display_get_xdisplay.restype = ctypes.c_void_p
libgtk.gdk_x11_display_get_xdisplay.argtypes = [ctypes.c_void_p]
class X11Platform(PlatformBase):
    def __init__(self, widget):
        super().__init__(widget)
        self.pointer_locked = False
        self._ignore_motion = False
        self._xdisplay = ctypes.c_void_p(libgtk.gdk_x11_display_get_xdisplay(hash(widget.get_display())))
        self._x11_window = GdkX11.X11Surface.get_xid(widget.get_surface())
        self._factor = widget.get_display().get_monitor_at_surface(widget.get_surface()).get_scale_factor()
        self._relative_pointer_callback = None

        self.motion_controller = Gtk.EventControllerMotion.new()
        self.motion_controller.connect("motion", self.on_motion)
        self.motion_controller.set_propagation_phase(Gtk.PropagationPhase.NONE)
        self.widget.add_controller(self.motion_controller)

    def lock_pointer(self)->bool:
        """锁定鼠标指针"""
        if self.pointer_locked:
            return True
        self.pointer_locked = True
        self.ignore_motion = True
        self._disable_window_controllers()
        self.warp_to_center()
        GLib.idle_add(self.clear_ignore_once)

    def unlock_pointer(self)->bool:
        """解锁鼠标指针"""
        if not self.pointer_locked:
            return True
        self.pointer_locked = False
        self._restore_window_controllers()
        return True

    def is_pointer_locked(self)->bool:
        """检查鼠标是否被锁定"""
        return self.pointer_locked

    def set_relative_pointer_callback(self, callback:Callable[[float, float, float, float], None]):
        """设置相对鼠标移动回调"""
        self._relative_pointer_callback = callback
    
    def cleanup(self):
        """清理 X11 相关资源"""
        pass

    def on_motion(self, controller, x, y):
        if not self.pointer_locked:
            return False
        if self._ignore_motion:
            self._ignore_motion = False
            return False
        logger.info(f"motion {time.time_ns()}")
        dx = x - self.widget.get_allocated_width() // 2 
        dy = y - self.widget.get_allocated_height() // 2 
        if self._relative_pointer_callback:
            self._relative_pointer_callback(dx, dy, dx, dy)
        self._ignore_motion = True
        self.warp_to_center()
        GLib.idle_add(self.clear_ignore_once)

        logger.info(f"motion end {time.time_ns()}")
        return True

    def warp_to_center(self):
        logger.info(f"warp to center {time.time_ns()}")
        libx11.XWarpPointer(
            self._xdisplay,
            ctypes.c_ulong(0),
            ctypes.c_ulong(self._x11_window),
            0, 0, 0, 0,
            self.widget.get_allocated_width() // 2 * self._factor,
            self.widget.get_allocated_height() // 2 * self._factor
        )
        libx11.XFlush(self._xdisplay)
        logger.info(f"warp to center end {time.time_ns()}")

    def clear_ignore_once(self):
        self._ignore_motion = False
        logger.info(f"clear ignore once {time.time_ns()}")
        return False
    
    def _disable_window_controllers(self):
        for controller in self.widget.observe_controllers():
            if isinstance(controller, Gtk.EventControllerMotion):
                controller.set_propagation_phase(Gtk.PropagationPhase.NONE)
        self.motion_controller.set_propagation_phase(Gtk.PropagationPhase.BUBBLE)

    def _restore_window_controllers(self):
        for controller in self.widget.observe_controllers():
            if isinstance(controller, Gtk.EventControllerMotion):
                controller.set_propagation_phase(Gtk.PropagationPhase.BUBBLE)
        self.motion_controller.set_propagation_phase(Gtk.PropagationPhase.NONE)