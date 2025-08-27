#!/usr/bin/env python3
"""
CSS样式管理
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

from gi.repository import Gdk, Gtk

# 透明窗口样式
CSS_TRANSPARENT = """
#transparent-window {
    background-color: rgba(0, 0, 0, 0);
}
#mapping-widget {
    background-color: rgba(0, 0, 0, 0);
}
#mode-notification-box {
    background-color: rgba(0, 0, 0, 0.7);
    border-radius: 10px;
    padding: 10px 20px;
}

#mode-notification-label {
    color: white;
    font-size: 24px;
    font-weight: bold;
}
"""


class StyleManager:
    """样式管理器"""

    def __init__(self, display: Gdk.Display):
        self.display = display
        self.provider: Gtk.CssProvider | None = None
        self.setup_styles()

    def setup_styles(self):
        """设置全局样式"""
        self.provider = Gtk.CssProvider.new()
        self.provider.load_from_data(CSS_TRANSPARENT.encode())

        if self.display:
            Gtk.StyleContext.add_provider_for_display(
                self.display, self.provider, Gtk.STYLE_PROVIDER_PRIORITY_USER
            )
        else:
            raise ValueError("Failed to get display")

    def add_custom_style(self, css_content: str):
        """添加自定义样式"""
        if self.provider:
            current_css = CSS_TRANSPARENT + "\n" + css_content
            self.provider.load_from_data(current_css.encode())
