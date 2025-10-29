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
from typing import Any
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
    def __init__(self, script_dir: Path, config: dict[str, Any]):
        self.script_dir = script_dir
        self.name = config.get("name", script_dir.name)
        self.description = config.get("description", "")
        self.command = config.get("command", "")
        self.entry_file = config.get("entry_file", "run.sh")
        self.author = config.get("author", "")
        
        self.entry_path = script_dir / self.entry_file
        self.config_file = script_dir / "script.json"
    
    def is_valid(self) -> bool:
        return (
            self.config_file.exists() and 
            self.entry_path.exists() and
            self.entry_path.is_file()
        )
    
    def get_executable_path(self) -> str | None:
        if self.entry_path.exists() and self.entry_path.is_file():
            if not os.access(self.entry_path, os.X_OK):
                try:
                    current_mode = self.entry_path.stat().st_mode
                    self.entry_path.chmod(current_mode | stat.S_IEXEC)
                except Exception as e:
                    logger.warning(f"Failed to make script executable: {e}")
            return str(self.entry_path)
        return None


class ScriptLoader:
    
    def __init__(self):
        default_dir = Path("/usr/share") / os.environ.get("PROJECT_NAME", "waydroid-helper")
        data_dir = os.getenv("PKGDATADIR", default_dir)
        self.script_dir = Path(data_dir) / "data" / "scripts"
        self.scripts: dict[str, ScriptInfo] = {}
    
    def load_scripts(self) -> dict[str, ScriptInfo]:
        self.scripts.clear()
        
        if not self.script_dir.exists():
            logger.info(f"Script directory does not exist: {self.script_dir}")
            return self.scripts
        
        try:
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
    
    def get_all_scripts(self) -> list[ScriptInfo]:
        return list(self.scripts.values())


class ScriptItem(Adw.ActionRow):
    __gtype_name__: str = "ScriptItem"
    
    def __init__(self, script_info: ScriptInfo):
        super().__init__()
        self.script_info = script_info
        
        self.set_title(script_info.name)
        if script_info.description:
            self.set_subtitle(script_info.description)
        
        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        
        self.info_button = Gtk.Button()
        self.info_button.add_css_class("flat")
        self.info_button.set_size_request(40, 40)
        info_icon = Gtk.Image.new_from_icon_name("info-symbolic")
        self.info_button.set_child(info_icon)
        self.info_button.set_tooltip_text(_("View Script Info"))
        
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
    __gtype_name__: str = "ScriptsListWidget"
    
    def __init__(self):
        super().__init__()
        
        self.script_loader = ScriptLoader()
        
        self._script_items: list[ScriptItem] = []
        
        self._groups: dict[str, Adw.PreferencesGroup] = {}
        
        self._load_scripts()
    
    def _load_scripts(self):
        for group in self._groups.values():
            self.remove(group)
        self._groups.clear()
        self._script_items.clear()
        
        scripts = self.script_loader.load_scripts()
        if not scripts:
            self._add_no_scripts_message()
            return
        
        all_scripts = self.script_loader.get_all_scripts()
        
        group = Adw.PreferencesGroup()
        group.set_title(_("Available Scripts"))
        
        for script_info in all_scripts:
            script_item = ScriptItem(script_info)
            group.add(script_item)
            self._script_items.append(script_item)
        
        self._groups["all"] = group
        self.add(group)
    
    def _add_no_scripts_message(self):
        group = Adw.PreferencesGroup()
        group.set_title(_("No Scripts Found"))
        
        info_row = Adw.ActionRow()
        info_row.set_title(_("No scripts found in the scripts directory"))
        info_row.set_subtitle(_("Create script folders in: {script_dir}").format(
            script_dir=self.script_loader.script_dir
        ))
        
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
        self._load_scripts()
        parent = self.get_parent()
        if parent and hasattr(parent, '_connect_script_events'):
            parent._connect_script_events()
    
    def refresh_scripts(self):
        self._on_refresh_scripts(None)


class TerminalWidget(Gtk.Box):
    __gtype_name__: str = "TerminalWidget"
    
    __gsignals__ = {
        "shell-ready": (GObject.SignalFlags.RUN_FIRST, None, ())
    }
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        
        self.terminal = Vte.Terminal.new()
        self.terminal.set_font(Pango.FontDescription("Monospace 12"))
        
        self.terminal.set_scroll_on_output(True)
        self.terminal.set_scroll_on_keystroke(True)
        
        self.setup_copy_paste()
        
        self.append(self.terminal)
        
        self._setup_theme_colors()
    
    def _setup_theme_colors(self):
        style_manager = Adw.StyleManager.get_default()
        
        def update_colors():
            # Ensure explicit RGBA objects and avoid passing an empty palette,
            # which can cause foreground color to be ignored in some runtimes (e.g. AppImage)
            fg = Gdk.RGBA()
            bg = Gdk.RGBA()
            if style_manager.get_dark():
                fg.red, fg.green, fg.blue, fg.alpha = 1.0, 1.0, 1.0, 1.0  # white text
                bg.red, bg.green, bg.blue, bg.alpha = 0.0, 0.0, 0.0, 1.0  # black background
            else:
                fg.red, fg.green, fg.blue, fg.alpha = 0.0, 0.0, 0.0, 1.0  # black text
                bg.red, bg.green, bg.blue, bg.alpha = 1.0, 1.0, 1.0, 1.0  # white background

            # Pass palette=None so VTE doesn't override our explicit foreground color
            self.terminal.set_colors(foreground=fg, background=bg, palette=None)
        
        update_colors()
        _ = style_manager.connect("notify::dark", lambda *a: update_colors())
    
    def setup_copy_paste(self):
        shortcut_controller = Gtk.ShortcutController()
        
        copy_shortcut = Gtk.Shortcut.new(
            trigger=Gtk.ShortcutTrigger.parse_string("<Ctrl><Shift>c"),
            action=Gtk.CallbackAction.new(self.on_copy_shortcut, None)
        )
        shortcut_controller.add_shortcut(copy_shortcut)
        
        paste_shortcut = Gtk.Shortcut.new(
            trigger=Gtk.ShortcutTrigger.parse_string("<Ctrl><Shift>v"),
            action=Gtk.CallbackAction.new(self.on_paste_shortcut, None)
        )
        shortcut_controller.add_shortcut(paste_shortcut)
        
        self.terminal.add_controller(shortcut_controller)
    
    def on_copy_shortcut(self, *args):
        if self.terminal.get_has_selection():
            self.terminal.copy_clipboard()
            return True
        return False
    
    def on_paste_shortcut(self, *args):
        self.terminal.paste_clipboard()
        return True
    
    def run_command(self, command: str):
        completion_msg = _("Script execution completed. You can close this window.")
        full_command = f"clear; {command}; echo '{completion_msg}'; exit"
        shell = os.environ.get("SHELL", "/bin/bash")

        env_vars = os.environ.copy()
        env_vars["PATH"] = f"/usr/bin:/bin:{os.environ.get('PATH','')}"
        env_vars["LD_LIBRARY_PATH"] = ""
        env_vars["LD_PRELOAD"] = ""
        env_vars["PYTHONPATH"] = ""
        env_vars["PYTHONHOME"] = ""
        env_vars["SHELL"] = shell

        env_list = [f"{k}={v}" for k, v in env_vars.items()]

        # Spawn a non-interactive shell to execute the command so the command itself is not echoed
        self.terminal.spawn_async(
            Vte.PtyFlags.DEFAULT,
            os.path.expanduser("~"),
            [shell, "-c", full_command],
            env_list,
            GLib.SpawnFlags.DEFAULT,
            None,
            None,
            -1,
            None,
            None,
            (),
        )


class TerminalWindow(Dialog):
    __gtype_name__: str = "TerminalWindow"
    
    def __init__(self, script_name: str, parent_window=None):
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        
        self.header_bar = HeaderBar()
        title_label = Gtk.Label(label=f"Terminal - {script_name}")
        self.header_bar.set_title_widget(title_label)
        
        main_box.append(self.header_bar)
        
        self.terminal_widget = TerminalWidget()
        main_box.append(self.terminal_widget)
        
        super().__init__(
            title=f"Terminal - {script_name}",
            content_widget=main_box,
            parent=parent_window,
            modal=True,
            content_height=600,
            content_width=800
        )
        
        self._pending_command = None
        
        try:
            self.set_icon_name("utilities-terminal")
        except:
            pass
    
    def set_command(self, command: str):
        self._pending_command = command
        self.terminal_widget.run_command(self._pending_command)
        logger.debug(f"Running script: {self._pending_command}")
        self._pending_command = None
    
class ScriptsPage(Gtk.Box):
    __gtype_name__: str = "ScriptsPage"
    
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        
        self.scripts_list_widget = ScriptsListWidget()
        self.append(self.scripts_list_widget)
        
        self._connect_script_events()
    
    def _connect_script_events(self):
        for script_item in self.scripts_list_widget._script_items:
            _ = script_item.run_button.connect("clicked", 
                lambda btn, item=script_item: self._on_run_script(item))
            _ = script_item.info_button.connect("clicked", 
                lambda btn, item=script_item: self._on_show_script_info(item))
    
    def _on_run_script(self, script_item: ScriptItem):
        try:
            script_info = script_item.script_info
            
            executable_path = script_info.get_executable_path()
            if not executable_path:
                logger.error(f"Script executable not found: {script_info.entry_path}")
                self._show_error_dialog(_("Script Error"), 
                    _("Script executable not found: {}").format(script_info.entry_path))
                return
            
            if script_info.command:
                command = script_info.command
            else:
                command = executable_path
            
            terminal_window = TerminalWindow(script_info.name, parent_window=self.get_root())
            terminal_window.present()
            
            terminal_window.set_command(command)
            
        except Exception as e:
            logger.error(f"Failed to run script {script_item.script_info.name}: {e}")
            self._show_error_dialog(_("Script Error"), 
                _("Failed to run script: {}").format(str(e)))
    
    def _on_show_script_info(self, script_item: ScriptItem):
        try:
            script_info = script_item.script_info
            
            info_text = f"Script: {script_info.name}\n"
            info_text += f"Description: {script_info.description}\n"
            info_text += f"Author: {script_info.author}\n"
            info_text += f"Entry File: {script_info.entry_file}\n"
            info_text += f"Script Directory: {script_info.script_dir}\n"
            
            if script_info.command:
                info_text += f"Command: {script_info.command}\n"
            
            dialog = MessageDialog(
                heading=_("Script Information"),
                body=info_text,
                parent=self.get_root(),
            )
            dialog.add_response(Gtk.ResponseType.OK, _("OK"))
            dialog.set_default_response(Gtk.ResponseType.OK)
            dialog.present()
            
        except Exception as e:
            logger.error(f"Failed to show script info: {e}")
            self._show_error_dialog(_("Error"), 
                _("Failed to show script info: {}").format(str(e)))
    
    def _show_error_dialog(self, title: str, message: str):
        dialog = MessageDialog(
            heading=title,
            body=message,
            parent=None,
        )
        dialog.add_response(Gtk.ResponseType.OK, _("OK"))
        dialog.set_default_response(Gtk.ResponseType.OK)
        dialog.present()
    
    def refresh_scripts(self):
        self.scripts_list_widget.refresh_scripts()
        self._connect_script_events()
