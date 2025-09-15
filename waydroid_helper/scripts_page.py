# pyright: reportCallIssue=false
# pyright: reportUnknownVariableType=false
# pyright: reportAny=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false

from gettext import gettext as _
import os
import gi

from waydroid_helper.util import logger

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Vte", "3.91")

from gi.repository import Adw, GObject, Gtk, Vte, GLib, Pango, Gdk
from waydroid_helper.compat_widget.message_dialog import MessageDialog
from waydroid_helper.compat_widget.header_bar import HeaderBar
from waydroid_helper.compat_widget.dialog import Dialog


class ScriptItem(Adw.ActionRow):
    """脚本项组件"""
    __gtype_name__: str = "ScriptItem"
    
    def __init__(self, script_name: str, script_path: str, description: str = ""):
        super().__init__()
        self.script_name = script_name
        self.script_path = script_path
        self.description = description
        
        self.set_title(script_name)
        if description:
            self.set_subtitle(description)
        
        # 创建按钮容器
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        
        # 信息按钮
        self.info_button = Gtk.Button()
        self.info_button.add_css_class("flat")
        self.info_button.set_size_request(40, 40)
        info_icon = Gtk.Image.new_from_icon_name("info-symbolic")
        self.info_button.set_child(info_icon)
        self.info_button.set_tooltip_text(_("View Script Info"))
        
        # 运行按钮 - 使用播放图标
        self.run_button = Gtk.Button()
        self.run_button.add_css_class("flat")
        self.run_button.set_size_request(40, 40)
        play_icon = Gtk.Image.new_from_icon_name("media-playback-start-symbolic")
        self.run_button.set_child(play_icon)
        self.run_button.set_tooltip_text(_("Run Script"))
        
        button_box.append(self.info_button)
        button_box.append(self.run_button)
        
        self.add_suffix(button_box)


class ScriptsListWidget(Adw.PreferencesPage):
    """脚本列表组件"""
    __gtype_name__: str = "ScriptsListWidget"
    
    def __init__(self):
        super().__init__()
        
        # 创建脚本组
        self.waydroid_group = Adw.PreferencesGroup()
        self.waydroid_group.set_title(_("Waydroid Scripts"))
        self.waydroid_group.set_description(_("Built-in Waydroid management scripts"))
        
        # 创建系统组
        self.system_group = Adw.PreferencesGroup()
        self.system_group.set_title(_("System Scripts"))
        self.system_group.set_description(_("System information and diagnostic scripts"))
        
        # 添加示例脚本
        self._add_sample_scripts()
        
        # 添加组到页面
        self.add(self.waydroid_group)
        self.add(self.system_group)
    
    def _add_sample_scripts(self):
        """添加示例脚本"""
        # Waydroid 相关脚本
        waydroid_scripts = [
            ("waydroid-info", "/usr/bin/waydroid", _("Show Waydroid system information")),
            ("waydroid-logs", "/usr/bin/waydroid", _("View Waydroid logs")),
            ("waydroid-status", "/usr/bin/waydroid", _("Check Waydroid status")),
        ]
        
        for name, path, desc in waydroid_scripts:
            script_item = ScriptItem(name, path, desc)
            self.waydroid_group.add(script_item)
            # 存储脚本项引用以便后续连接事件
            if not hasattr(self, '_script_items'):
                self._script_items = []
            self._script_items.append(script_item)
        
        # 系统相关脚本
        system_scripts = [
            ("system-info", "/bin/bash", _("Show system information")),
            ("network-check", "/bin/bash", _("Check network connectivity")),
            ("disk-usage", "/bin/bash", _("Check disk usage")),
        ]
        
        for name, path, desc in system_scripts:
            script_item = ScriptItem(name, path, desc)
            self.system_group.add(script_item)
            # 存储脚本项引用以便后续连接事件
            if not hasattr(self, '_script_items'):
                self._script_items = []
            self._script_items.append(script_item)


class TerminalWidget(Gtk.Box):
    """VTE 终端组件"""
    __gtype_name__: str = "TerminalWidget"
    
    __gsignals__ = {
        "shell-ready": (GObject.SignalFlags.RUN_FIRST, None, ())
    }
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        
        self.terminal = Vte.Terminal.new()
        self.terminal.set_font(Pango.FontDescription("Monospace 12"))
        
        # 启用一些有用的终端功能
        self.terminal.set_scroll_on_output(True)
        self.terminal.set_scroll_on_keystroke(True)
        
        # 设置复制粘贴功能
        self.setup_copy_paste()
        
        self.append(self.terminal)
        
        # 启动 shell
        self._spawn_shell()
        
        # 跟随系统暗/亮模式
        self._setup_theme_colors()
    
    def _spawn_shell(self):
        """启动 shell"""
        shell = os.environ.get("SHELL", "/bin/bash")
        
        def on_spawn(term, res, user_data):
            try:
                # Shell 启动成功，发送信号通知
                self.emit("shell-ready")
            except GLib.Error as e:
                logger.error(f"Terminal spawn failed: {e}")
        
        # 使用 spawn_async 的正确参数顺序
        self.terminal.spawn_async(
            Vte.PtyFlags.DEFAULT,  # pty_flags
            os.path.expanduser("~"),  # working_directory
            [shell],  # argv
            None,  # envv
            GLib.SpawnFlags.DEFAULT,  # spawn_flags
            None,  # child_setup
            None,  # child_setup_data
            -1,  # timeout
            None,  # cancellable
            on_spawn,  # callback
            (),  # user_data
        )
    
    def _setup_theme_colors(self):
        """设置主题颜色"""
        style_manager = Adw.StyleManager.get_default()
        
        def update_colors():
            if style_manager.get_dark():
                fg = Gdk.RGBA(1, 1, 1, 1)  # 白字
                bg = Gdk.RGBA(0, 0, 0, 1)  # 黑底
            else:
                fg = Gdk.RGBA(0, 0, 0, 1)  # 黑字
                bg = Gdk.RGBA(1, 1, 1, 1)  # 白底
            self.terminal.set_colors(foreground=fg, background=bg, palette=[])
        
        update_colors()
        _ = style_manager.connect("notify::dark", lambda *a: update_colors())
    
    def setup_copy_paste(self):
        """设置复制粘贴功能"""
        # 创建快捷键控制器
        shortcut_controller = Gtk.ShortcutController()
        
        # 创建复制快捷键 Ctrl+Shift+C
        copy_shortcut = Gtk.Shortcut.new(
            trigger=Gtk.ShortcutTrigger.parse_string("<Ctrl><Shift>c"),
            action=Gtk.CallbackAction.new(self.on_copy_shortcut, None)
        )
        shortcut_controller.add_shortcut(copy_shortcut)
        
        # 创建粘贴快捷键 Ctrl+Shift+V
        paste_shortcut = Gtk.Shortcut.new(
            trigger=Gtk.ShortcutTrigger.parse_string("<Ctrl><Shift>v"),
            action=Gtk.CallbackAction.new(self.on_paste_shortcut, None)
        )
        shortcut_controller.add_shortcut(paste_shortcut)
        
        self.terminal.add_controller(shortcut_controller)
    
    def on_copy_shortcut(self, *args):
        """处理复制快捷键"""
        if self.terminal.get_has_selection():
            self.terminal.copy_clipboard()
            return True
        return False
    
    def on_paste_shortcut(self, *args):
        """处理粘贴快捷键"""
        self.terminal.paste_clipboard()
        return True
    
    def run_command(self, command: str):
        """在终端中运行命令"""
        # 使用 feed_child 方法发送命令到子进程执行
        # 需要发送命令字符串加上换行符
        self.terminal.feed_child((command + '\n').encode())


class TerminalWindow(Dialog):
    """独立的终端窗口"""
    __gtype_name__: str = "TerminalWindow"
    
    def __init__(self, script_name: str, parent_window=None):
        # 创建主容器
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        
        # 创建头部栏
        self.header_bar = HeaderBar()
        title_label = Gtk.Label(label=f"Terminal - {script_name}")
        self.header_bar.set_title_widget(title_label)
        
        # 添加头部栏到主容器
        main_box.append(self.header_bar)
        
        # 创建终端组件
        self.terminal_widget = TerminalWidget()
        main_box.append(self.terminal_widget)
        
        # 调用父类构造函数
        super().__init__(
            title=f"Terminal - {script_name}",
            content_widget=main_box,
            parent=parent_window,
            modal=False,
            content_height=600,
            content_width=800
        )
        
        # 存储命令，等待 shell 准备好后执行
        self._pending_command = None
        
        # 设置窗口图标（如果有的话）
        try:
            self.set_icon_name("utilities-terminal")
        except:
            pass
    
    def set_command(self, command: str):
        """设置要执行的命令"""
        self._pending_command = command
        # 连接 shell-ready 信号
        _ = self.terminal_widget.connect("shell-ready", self._on_shell_ready)
    
    def _on_shell_ready(self, terminal_widget):
        """Shell 准备好后执行命令"""
        if self._pending_command:
            terminal_widget.run_command(self._pending_command)
            logger.debug(f"Running script: {self._pending_command}")
            self._pending_command = None


class ScriptsPage(Gtk.Box):
    """脚本页面主组件"""
    __gtype_name__: str = "ScriptsPage"
    
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        
        # 只显示脚本列表
        self.scripts_list_widget = ScriptsListWidget()
        self.append(self.scripts_list_widget)
        
        # 连接脚本按钮事件
        self._connect_script_events()
    
    def _connect_script_events(self):
        """连接脚本按钮事件"""
        # 遍历所有脚本项并连接事件
        for script_item in self.scripts_list_widget._script_items:
            # 连接运行按钮事件
            _ = script_item.run_button.connect("clicked", 
                lambda btn, item=script_item: self._on_run_script(item))
            # 连接信息按钮事件
            _ = script_item.info_button.connect("clicked", 
                lambda btn, item=script_item: self._on_show_script_info(item))
    
    def _on_run_script(self, script_item: ScriptItem):
        """运行脚本"""
        try:
            # 根据脚本类型生成不同的命令
            if "waydroid" in script_item.script_name:
                if "info" in script_item.script_name:
                    command = "waydroid info"
                elif "logs" in script_item.script_name:
                    command = "waydroid log"
                elif "status" in script_item.script_name:
                    command = "waydroid status"
                else:
                    command = f"waydroid {script_item.script_name.replace('waydroid-', '')}"
            elif "system-info" in script_item.script_name:
                command = "uname -a && lsb_release -a"
            elif "network-check" in script_item.script_name:
                command = "ping -c 3 8.8.8.8"
            elif "disk-usage" in script_item.script_name:
                command = "df -h"
            else:
                command = f"{script_item.script_path} --help"
            
            # 创建并显示终端窗口
            terminal_window = TerminalWindow(script_item.script_name, parent_window=self.get_root())
            terminal_window.present()
            
            # 设置要执行的命令，等待 shell 准备好后自动执行
            terminal_window.set_command(command)
        except Exception as e:
            logger.error(f"Failed to run script {script_item.script_name}: {e}")
    
    def _on_show_script_info(self, script_item: ScriptItem):
        """显示脚本信息"""
        try:
            info_text = f"Script: {script_item.script_name}\n"
            info_text += f"Path: {script_item.script_path}\n"
            info_text += f"Description: {script_item.description}"
            
            dialog = MessageDialog(
                heading=_("Script Information"),
                body=info_text,
                parent=None,  # 暂时设为 None，避免类型错误
            )
            dialog.add_response(Gtk.ResponseType.OK, _("OK"))
            dialog.set_default_response(Gtk.ResponseType.OK)
            dialog.present()
        except Exception as e:
            logger.error(f"Failed to show script info: {e}")
