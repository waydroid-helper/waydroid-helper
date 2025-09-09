"""
平台相关功能模块
提供不同平台的特定功能支持
"""

import os

from waydroid_helper.util.log import logger

from .base import PlatformBase

def get_platform(widget):
    """获取当前平台的实现"""
    display = widget.get_display()
    if display.__class__.__name__ == "GdkWaylandDisplay":
        try:
            from .wayland import WaylandPlatform
            return WaylandPlatform(widget)
        except ImportError as e:
            logger.error(f"Failed to load Wayland platform support: {e}")
    else:
        try:
            from .x11 import X11Platform
            return X11Platform(widget)
        except ImportError as e:
            logger.error(f"Failed to load X11 platform support: {e}")

    logger.warning("No suitable platform implementation found")
    return None


__all__ = ["PlatformBase", "get_platform"]
