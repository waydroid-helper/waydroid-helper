"""
X11 平台实现
提供 X11 特定的功能，如指针锁定、相对鼠标移动等
"""

import ctypes
import ctypes.util
import threading
import os
from typing import Callable

from gi.repository import GObject, Gdk, GLib

from ..base import PlatformBase
from waydroid_helper.util.log import logger

# 加载 X11 库
libx11_path = ctypes.util.find_library('X11')
if not libx11_path:
    raise ImportError("Cannot find libX11")

libx11 = ctypes.CDLL(libx11_path)

# X11 常量
CurrentTime = 0
GrabSuccess = 0
GrabModeAsync = 1
PointerMotionMask = 1 << 6
ButtonPressMask = 1 << 2
ButtonReleaseMask = 1 << 3
EnterWindowMask = 1 << 4
LeaveWindowMask = 1 << 5
FocusChangeMask = 1 << 21

# 事件类型
MotionNotify = 6

# X11 结构体定义
class XEvent(ctypes.Structure):
    _fields_ = [("type", ctypes.c_int),
                ("pad", ctypes.c_long * 24)]

class XMotionEvent(ctypes.Structure):
    _fields_ = [
        ("type", ctypes.c_int),
        ("serial", ctypes.c_ulong),
        ("send_event", ctypes.c_int),
        ("display", ctypes.c_void_p),
        ("window", ctypes.c_ulong),
        ("root", ctypes.c_ulong),
        ("subwindow", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("x", ctypes.c_int),
        ("y", ctypes.c_int),
        ("x_root", ctypes.c_int),
        ("y_root", ctypes.c_int),
        ("state", ctypes.c_uint),
        ("detail", ctypes.c_char),
        ("same_screen", ctypes.c_int),
    ]

# X11 函数定义
libx11.XOpenDisplay.restype = ctypes.c_void_p
libx11.XOpenDisplay.argtypes = [ctypes.c_char_p]

libx11.XCloseDisplay.restype = ctypes.c_int
libx11.XCloseDisplay.argtypes = [ctypes.c_void_p]

libx11.XDefaultRootWindow.restype = ctypes.c_ulong
libx11.XDefaultRootWindow.argtypes = [ctypes.c_void_p]

libx11.XGrabPointer.restype = ctypes.c_int
libx11.XGrabPointer.argtypes = [
    ctypes.c_void_p,  # display
    ctypes.c_ulong,   # grab_window
    ctypes.c_int,     # owner_events
    ctypes.c_uint,    # event_mask
    ctypes.c_int,     # pointer_mode
    ctypes.c_int,     # keyboard_mode
    ctypes.c_ulong,   # confine_to
    ctypes.c_ulong,   # cursor
    ctypes.c_ulong,   # time
]

libx11.XUngrabPointer.restype = ctypes.c_int
libx11.XUngrabPointer.argtypes = [ctypes.c_void_p, ctypes.c_ulong]

libx11.XWarpPointer.restype = ctypes.c_int
libx11.XWarpPointer.argtypes = [
    ctypes.c_void_p,  # display
    ctypes.c_ulong,   # src_w
    ctypes.c_ulong,   # dest_w
    ctypes.c_int,     # src_x
    ctypes.c_int,     # src_y
    ctypes.c_uint,    # src_width
    ctypes.c_uint,    # src_height
    ctypes.c_int,     # dest_x
    ctypes.c_int,     # dest_y
]

libx11.XNextEvent.restype = ctypes.c_int
libx11.XNextEvent.argtypes = [ctypes.c_void_p, ctypes.POINTER(XEvent)]

libx11.XPending.restype = ctypes.c_int
libx11.XPending.argtypes = [ctypes.c_void_p]

libx11.XFlush.restype = ctypes.c_int
libx11.XFlush.argtypes = [ctypes.c_void_p]

libx11.XSync.restype = ctypes.c_int
libx11.XSync.argtypes = [ctypes.c_void_p, ctypes.c_int]

libx11.XQueryPointer.restype = ctypes.c_int
libx11.XQueryPointer.argtypes = [
    ctypes.c_void_p,  # display
    ctypes.c_ulong,   # window
    ctypes.POINTER(ctypes.c_ulong),  # root_return
    ctypes.POINTER(ctypes.c_ulong),  # child_return
    ctypes.POINTER(ctypes.c_int),    # root_x_return
    ctypes.POINTER(ctypes.c_int),    # root_y_return
    ctypes.POINTER(ctypes.c_int),    # win_x_return
    ctypes.POINTER(ctypes.c_int),    # win_y_return
    ctypes.POINTER(ctypes.c_uint),   # mask_return
]

# GTK4 X11 后端函数
try:
    # 尝试加载GTK4的X11后端库
    libgdk = ctypes.CDLL("libgtk-4.so.1")
    
    # GTK4 X11后端函数定义
    libgdk.gdk_x11_surface_get_xid.restype = ctypes.c_ulong
    libgdk.gdk_x11_surface_get_xid.argtypes = [ctypes.c_void_p]
    
    libgdk.gdk_x11_display_get_xdisplay.restype = ctypes.c_void_p
    libgdk.gdk_x11_display_get_xdisplay.argtypes = [ctypes.c_void_p]
    
except OSError:
    logger.error("Failed to load GTK4 library")
    raise ImportError("Cannot find libgtk-4.so.1")


def get_x11_window_id(widget):
    """获取GTK窗口的X11窗口ID"""
    try:
        gdk_surface = widget.get_surface()
        if gdk_surface is None:
            logger.error("Widget surface is None")
            return None
        # GTK4使用surface而不是window
        return libgdk.gdk_x11_surface_get_xid(hash(gdk_surface))
    except Exception as e:
        logger.error(f"Failed to get X11 window ID: {e}")
        return None


def get_x11_display(widget):
    """获取X11显示"""
    try:
        gdk_display = widget.get_display()
        return libgdk.gdk_x11_display_get_xdisplay(hash(gdk_display))
    except Exception as e:
        logger.error(f"Failed to get X11 display: {e}")
        return None


class X11PointerLock(GObject.Object):
    """X11指针锁定实现"""
    
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
        self.display = None
        self.window_id = None
        self.root_window = None
        self.is_locked = False
        self.center_x = 0
        self.center_y = 0
        self.last_x = 0
        self.last_y = 0
        self.event_thread = None
        self.should_stop = False

    def get_current_cursor_position(self):
        """获取当前鼠标在窗口内的位置"""
        if not self.display or not self.window_id:
            return None, None
        
        try:
            root_return = ctypes.c_ulong()
            child_return = ctypes.c_ulong()
            root_x = ctypes.c_int()
            root_y = ctypes.c_int()
            win_x = ctypes.c_int()
            win_y = ctypes.c_int()
            mask = ctypes.c_uint()
            
            result = libx11.XQueryPointer(
                self.display,
                self.window_id,
                ctypes.byref(root_return),
                ctypes.byref(child_return),
                ctypes.byref(root_x),
                ctypes.byref(root_y),
                ctypes.byref(win_x),
                ctypes.byref(win_y),
                ctypes.byref(mask)
            )
            
            if result:
                return win_x.value, win_y.value
            else:
                logger.warning("XQueryPointer failed")
                return None, None
                
        except Exception as e:
            logger.error(f"Failed to get cursor position: {e}")
            return None, None

    def setup(self):
        """初始化X11显示和窗口"""
        try:
            # 创建独立的X11连接，不影响主应用
            display_name = os.environ.get('DISPLAY', ':0')
            self.display = libx11.XOpenDisplay(display_name.encode('utf-8'))
            
            if not self.display:
                logger.error("Failed to open independent X11 display connection")
                return False

            # 获取窗口ID（从主应用的GTK窗口获取）
            self.window_id = get_x11_window_id(self.widget)
            
            if not self.window_id:
                logger.error("Failed to get X11 window ID")
                libx11.XCloseDisplay(self.display)
                self.display = None
                return False

            self.root_window = libx11.XDefaultRootWindow(self.display)
            
            # 获取缩放因子来处理高DPI
            gdk_display = self.widget.get_display()
            scale_factor = gdk_display.get_monitors().get_item(0).get_scale_factor()
            self.scale_factor = scale_factor
            
            # 获取当前鼠标位置作为锁定位置
            cursor_x, cursor_y = self.get_current_cursor_position()
            
            if cursor_x is not None and cursor_y is not None:
                # XQueryPointer返回的已经是物理像素坐标，无需再乘以缩放因子
                self.center_x = cursor_x
                self.center_y = cursor_y
                logger.debug(f"Using current cursor position: physical({cursor_x}x{cursor_y})")
            else:
                # 如果无法获取当前位置，回退到窗口中心
                allocation = self.widget.get_allocation()
                logical_center_x = allocation.width // 2
                logical_center_y = allocation.height // 2
                self.center_x = int(logical_center_x * scale_factor)
                self.center_y = int(logical_center_y * scale_factor)
                logger.warning(f"Failed to get cursor position, using window center: {self.center_x}x{self.center_y}")
            
            logger.debug(f"Scale factor: {scale_factor}")
            
            self.last_x = self.center_x
            self.last_y = self.center_y
            
            return True
        except Exception as e:
            logger.error(f"Failed to setup X11: {e}")
            if self.display:
                libx11.XCloseDisplay(self.display)
                self.display = None
            return False

    def lock_pointer(self):
        """锁定指针"""
        try:
            if not self.display or not self.window_id:
                logger.error("Display or window not initialized")
                return False

            # 抓取指针
            result = libx11.XGrabPointer(
                self.display,
                self.window_id,
                False,  # owner_events - 设为False确保所有事件都发送到抓取窗口
                PointerMotionMask | ButtonPressMask | ButtonReleaseMask,
                GrabModeAsync,
                GrabModeAsync,
                self.window_id,  # confine_to - 限制在当前窗口
                0,  # cursor
                CurrentTime
            )

            if result != GrabSuccess:
                logger.error(f"XGrabPointer failed with result: {result}")
                return False

            # 不再移动鼠标到中心，保持当前位置
            libx11.XFlush(self.display)

            self.is_locked = True
            self.should_stop = False
            
            # 启动事件处理线程
            self.event_thread = threading.Thread(target=self._event_loop)
            self.event_thread.daemon = True
            self.event_thread.start()

            logger.debug("X11 pointer locked successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to lock pointer: {e}")
            return False

    def unlock_pointer(self):
        """解锁指针"""
        try:
            if not self.is_locked:
                return True

            self.should_stop = True
            self.is_locked = False

            if self.display:
                try:
                    libx11.XUngrabPointer(self.display, CurrentTime)
                    libx11.XFlush(self.display)
                except Exception as e:
                    logger.warning(f"Error during XUngrabPointer: {e}")

            # 等待事件线程退出，现在应该很快了
            if self.event_thread and self.event_thread.is_alive():
                try:
                    self.event_thread.join(timeout=0.1)  # 只等待100ms
                    if self.event_thread.is_alive():
                        logger.warning("Event thread did not exit in time")
                except Exception as e:
                    logger.warning(f"Error joining event thread: {e}")

            # 标记display为None，但不要调用XCloseDisplay
            # 让X11连接由系统自动清理，避免段错误
            if self.display:
                self.display = None

            logger.debug("X11 pointer unlocked successfully")
            return True

        except Exception as e:
            logger.error(f"Failed to unlock pointer: {e}")
            return False

    def _event_loop(self):
        """事件处理循环 - 混合事件驱动和短轮询"""
        event = XEvent()
        
        while not self.should_stop and self.is_locked:
            try:
                # 检查显示连接是否还有效
                if not self.display:
                    break
                
                # 使用XPending检查是否有待处理事件，避免XNextEvent的无限阻塞
                if libx11.XPending(self.display) > 0:
                    # 有事件时才调用XNextEvent
                    libx11.XNextEvent(self.display, ctypes.byref(event))
                    
                    # 检查是否应该停止（在获取事件后再次检查）
                    if self.should_stop or not self.is_locked:
                        break
                    
                    if event.type == MotionNotify:
                        # 转换为motion event
                        motion = ctypes.cast(ctypes.byref(event), ctypes.POINTER(XMotionEvent)).contents
                        
                        # 如果鼠标离锁定位置太远，先重新定位到锁定位置，然后忽略这个事件
                        if hasattr(self, 'scale_factor') and self.display:
                            threshold = int(50 * self.scale_factor)
                            if abs(motion.x - self.center_x) > threshold or abs(motion.y - self.center_y) > threshold:
                                try:
                                    libx11.XWarpPointer(
                                        self.display,
                                        0,  # src_w
                                        self.window_id,  # dest_w
                                        0, 0, 0, 0,  # src coordinates and size
                                        self.center_x, self.center_y  # dest coordinates
                                    )
                                    libx11.XFlush(self.display)
                                    self.last_x = self.center_x
                                    self.last_y = self.center_y
                                    # 跳过这个事件，不计算相对移动，避免突变
                                    continue
                                except Exception as e:
                                    logger.warning(f"Error warping pointer: {e}")
                                    break
                        
                        # 计算相对移动（物理像素）
                        dx_physical = motion.x - self.last_x
                        dy_physical = motion.y - self.last_y
                        
                        # 更新上次位置
                        self.last_x = motion.x
                        self.last_y = motion.y
                        
                        if dx_physical != 0 or dy_physical != 0:
                            # 转换为逻辑像素的相对移动
                            dx = dx_physical / self.scale_factor if hasattr(self, 'scale_factor') else dx_physical
                            dy = dy_physical / self.scale_factor if hasattr(self, 'scale_factor') else dy_physical
                            
                            # 直接在事件发生时立即发送信号
                            try:
                                GLib.idle_add(lambda dx=dx, dy=dy: (
                                    self.emit("relative-motion", dx, dy, dx, dy) if self.is_locked else None,
                                    False  # 只执行一次
                                )[1])
                            except Exception as e:
                                logger.warning(f"Error emitting relative-motion signal: {e}")
                else:
                    # 没有事件时短暂休眠，但频繁检查停止条件
                    threading.Event().wait(0.01)  # 10ms，确保快速响应停止信号
                    
            except Exception as e:
                if not self.should_stop:  # 只有在非正常停止时才记录错误
                    logger.warning(f"Error in event loop: {e}")
                break


class X11Platform(PlatformBase):
    """X11 平台功能实现"""

    def __init__(self, widget):
        super().__init__(widget)
        logger.debug(f"Initializing X11Platform: {widget}")
        self.pointer_lock = None
        self._relative_pointer_callback = None

    def cleanup(self):
        """清理 X11 资源"""
        if self.pointer_lock:
            self.pointer_lock.unlock_pointer()
            self.pointer_lock = None
        logger.debug("Cleaning up X11 platform resources")

    def relative_pointer_callback(self, obj, dx, dy, dx_unaccel, dy_unaccel):
        """相对指针移动回调"""
        if self._relative_pointer_callback:
            self._relative_pointer_callback(dx, dy, dx_unaccel, dy_unaccel)

    def lock_pointer(self) -> bool:
        """锁定鼠标指针"""
        try:
            # 如果已经有锁定的指针，先解锁
            if self.pointer_lock:
                self.unlock_pointer()

            # 创建新的指针锁定
            self.pointer_lock = X11PointerLock(self.widget)
            
            if not self.pointer_lock.setup():
                self.pointer_lock = None
                return False

            if not self.pointer_lock.lock_pointer():
                self.pointer_lock = None
                return False

            self.pointer_lock.connect("relative-motion", self.relative_pointer_callback)

            logger.debug(f"Successfully locked mouse to widget: {type(self.widget).__name__}")
            return True

        except Exception as e:
            logger.error(f"Failed to lock mouse: {e}")
            self.pointer_lock = None
            return False

    def unlock_pointer(self) -> bool:
        """解锁鼠标指针"""
        if not self.pointer_lock:
            return True

        try:
            self.pointer_lock.disconnect_by_func(self.relative_pointer_callback)
            self.pointer_lock.unlock_pointer()
            self.pointer_lock = None
            logger.debug("Mouse unlocked")
            return True

        except Exception as e:
            logger.error(f"Failed to unlock mouse: {e}")
            return False

    def is_pointer_locked(self) -> bool:
        """检查鼠标是否被锁定"""
        return self.pointer_lock is not None and self.pointer_lock.is_locked

    def set_relative_pointer_callback(
        self, callback: Callable[[float, float, float, float], None]
    ):
        """设置相对鼠标移动回调"""
        self._relative_pointer_callback = callback