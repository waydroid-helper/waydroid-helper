# pyright: reportCallIssue=false
# pyright: reportUnknownVariableType=false
# pyright: reportAny=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false

from gettext import gettext as _
import os
import json
import stat
from pathlib import Path
from typing import Dict, List, Optional, Any
import gi

from waydroid_helper.util import logger

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Vte", "3.91")

from gi.repository import Adw, GObject, Gtk, Vte, GLib, Pango, Gdk
from waydroid_helper.compat_widget.message_dialog import MessageDialog
from waydroid_helper.compat_widget.header_bar import HeaderBar
from waydroid_helper.compat_widget.dialog import Dialog


class ScriptInfo:
    """脚本信息数据类"""
    def __init__(self, script_dir: Path, config: Dict[str, Any]):
        self.script_dir = script_dir
        self.name = config.get("name", script_dir.name)
        self.description = config.get("description", "")
        self.category = config.get("category", "other")
        self.command = config.get("command", "")
        self.entry_file = config.get("entry_file", "run.sh")
        self.icon = config.get("icon", "utilities-terminal")
        self.author = config.get("author", "")
        self.version = config.get("version", "1.0")
        
        # 构建完整路径
        self.entry_path = script_dir / self.entry_file
        self.config_file = script_dir / "script.json"
    
    def is_valid(self) -> bool:
        """检查脚本是否有效"""
        return (
            self.config_file.exists() and 
            self.entry_path.exists() and
            self.entry_path.is_file()
        )
    
    def get_executable_path(self) -> Optional[str]:
        """获取可执行文件路径"""
        if self.entry_path.exists() and self.entry_path.is_file():
            # 检查文件是否可执行
            if not os.access(self.entry_path, os.X_OK):
                # 尝试添加执行权限
                try:
                    current_mode = self.entry_path.stat().st_mode
                    self.entry_path.chmod(current_mode | stat.S_IEXEC)
                except Exception as e:
                    logger.warning(f"Failed to make script executable: {e}")
            return str(self.entry_path)
        return None


class ScriptLoader:
    """脚本加载器"""
    
    def __init__(self):
        self.script_dir = Path(GLib.get_user_data_dir()) / os.getenv("PROJECT_NAME", "waydroid-helper") / "scripts"
        self.scripts: Dict[str, ScriptInfo] = {}
    
    def load_scripts(self) -> Dict[str, ScriptInfo]:
        """加载所有脚本"""
        self.scripts.clear()
        
        if not self.script_dir.exists():
            logger.info(f"Script directory does not exist: {self.script_dir}")
            return self.scripts
        
        try:
            # 遍历脚本目录
            for script_folder in self.script_dir.iterdir():
                if not script_folder.is_dir():
                    continue
                
                config_file = script_folder / "script.json"
                if not config_file.exists():
                    logger.warning(f"Script {script_folder.name} missing script.json")
                    continue
                
                try:
                    with open(config_file, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                    
                    script_info = ScriptInfo(script_folder, config)
                    if script_info.is_valid():
                        self.scripts[script_info.name] = script_info
                        logger.debug(f"Loaded script: {script_info.name}")
                    else:
                        logger.warning(f"Invalid script: {script_folder.name}")
                        
                except json.JSONDecodeError as e:
                    logger.error(f"Invalid JSON in {config_file}: {e}")
                except Exception as e:
                    logger.error(f"Failed to load script {script_folder.name}: {e}")
        
        except Exception as e:
            logger.error(f"Failed to scan script directory: {e}")
        
        return self.scripts
    
    def get_scripts_by_category(self) -> Dict[str, List[ScriptInfo]]:
        """按分类获取脚本"""
        categories: Dict[str, List[ScriptInfo]] = {}
        
        for script_info in self.scripts.values():
            category = script_info.category
            if category not in categories:
                categories[category] = []
            categories[category].append(script_info)
        
        return categories


class ScriptItem(Adw.ActionRow):
    """脚本项组件"""
    __gtype_name__: str = "ScriptItem"
    
    def __init__(self, script_info: ScriptInfo):
        super().__init__()
        self.script_info = script_info
        
        self.set_title(script_info.name)
        if script_info.description:
            self.set_subtitle(script_info.description)
        
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
        
        # 初始化脚本加载器
        self.script_loader = ScriptLoader()
        
        # 存储脚本项引用
        self._script_items: List[ScriptItem] = []
        
        # 存储分组
        self._groups: Dict[str, Adw.PreferencesGroup] = {}
        
        # 加载脚本
        self._load_scripts()
    
    def _load_scripts(self):
        """加载并显示脚本"""
        # 清除现有内容
        for group in self._groups.values():
            self.remove(group)
        self._groups.clear()
        self._script_items.clear()
        
        # 加载脚本
        scripts = self.script_loader.load_scripts()
        if not scripts:
            self._add_no_scripts_message()
            return
        
        # 按分类组织脚本
        categories = self.script_loader.get_scripts_by_category()
        
        # 预定义分类标题和描述
        category_info = {
            "waydroid": (_("Waydroid Scripts"), _("Waydroid management and diagnostic scripts")),
            "system": (_("System Scripts"), _("System information and diagnostic scripts")),
            "network": (_("Network Scripts"), _("Network connectivity and diagnostic scripts")),
            "development": (_("Development Scripts"), _("Development and debugging tools")),
            "other": (_("Other Scripts"), _("Miscellaneous scripts")),
        }
        
        # 创建分组
        for category, scripts_in_category in categories.items():
            title, description = category_info.get(category, (category.title(), ""))
            
            group = Adw.PreferencesGroup()
            group.set_title(title)
            group.set_description(description)
            
            # 添加脚本项到分组
            for script_info in scripts_in_category:
                script_item = ScriptItem(script_info)
                group.add(script_item)
                self._script_items.append(script_item)
            
            self._groups[category] = group
            self.add(group)
    
    def _add_no_scripts_message(self):
        """添加无脚本时的提示信息"""
        group = Adw.PreferencesGroup()
        group.set_title(_("No Scripts Found"))
        
        # 创建提示行
        info_row = Adw.ActionRow()
        info_row.set_title(_("No scripts found in the scripts directory"))
        info_row.set_subtitle(_("Create script folders in: {script_dir}").format(
            script_dir=self.script_loader.script_dir
        ))
        
        # 添加刷新按钮
        refresh_button = Gtk.Button()
        refresh_button.add_css_class("flat")
        refresh_button.set_size_request(40, 40)
        refresh_icon = Gtk.Image.new_from_icon_name("view-refresh-symbolic")
        refresh_button.set_child(refresh_icon)
        refresh_button.set_tooltip_text(_("Refresh Scripts"))
        refresh_button.connect("clicked", self._on_refresh_scripts)
        info_row.add_suffix(refresh_button)
        
        group.add(info_row)
        self._groups["empty"] = group
        self.add(group)
    
    def _on_refresh_scripts(self, button=None):
        """刷新脚本列表"""
        self._load_scripts()
        # 通知父组件重新连接事件
        parent = self.get_parent()
        if parent and hasattr(parent, '_connect_script_events'):
            parent._connect_script_events()
    
    def refresh_scripts(self):
        """公共方法：刷新脚本列表"""
        self._on_refresh_scripts(None)


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
            script_info = script_item.script_info
            
            # 获取可执行文件路径
            executable_path = script_info.get_executable_path()
            if not executable_path:
                logger.error(f"Script executable not found: {script_info.entry_path}")
                self._show_error_dialog(_("Script Error"), 
                    _("Script executable not found: {}").format(script_info.entry_path))
                return
            
            # 构建命令
            if script_info.command:
                # 使用配置中指定的命令
                command = script_info.command
            else:
                # 直接执行脚本文件
                command = executable_path
            
            # 创建并显示终端窗口
            terminal_window = TerminalWindow(script_info.name, parent_window=self.get_root())
            terminal_window.present()
            
            # 设置要执行的命令，等待 shell 准备好后自动执行
            terminal_window.set_command(command)
            
        except Exception as e:
            logger.error(f"Failed to run script {script_item.script_info.name}: {e}")
            self._show_error_dialog(_("Script Error"), 
                _("Failed to run script: {}").format(str(e)))
    
    def _on_show_script_info(self, script_item: ScriptItem):
        """显示脚本信息"""
        try:
            script_info = script_item.script_info
            
            info_text = f"Script: {script_info.name}\n"
            info_text += f"Description: {script_info.description}\n"
            info_text += f"Category: {script_info.category}\n"
            info_text += f"Author: {script_info.author}\n"
            info_text += f"Version: {script_info.version}\n"
            info_text += f"Entry File: {script_info.entry_file}\n"
            info_text += f"Script Directory: {script_info.script_dir}\n"
            
            if script_info.command:
                info_text += f"Command: {script_info.command}\n"
            
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
            self._show_error_dialog(_("Error"), 
                _("Failed to show script info: {}").format(str(e)))
    
    def _show_error_dialog(self, title: str, message: str):
        """显示错误对话框"""
        dialog = MessageDialog(
            heading=title,
            body=message,
            parent=None,
        )
        dialog.add_response(Gtk.ResponseType.OK, _("OK"))
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.present()
    
    def refresh_scripts(self):
        """公共方法：刷新脚本列表"""
        self.scripts_list_widget.refresh_scripts()
        self._connect_script_events()
