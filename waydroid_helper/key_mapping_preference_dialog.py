# pyright: reportUnknownMemberType=false
# pyright: reportUnknownParameterType=false
# pyright: reportMissingParameterType=false
# pyright: reportRedeclaration=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportAny=false
# pyright: reportCallIssue=false
# pyright: reportMissingSuperCall=false
# pyright: reportGeneralTypeIssues=false
# pyright: reportUntypedBaseClass=false

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk
from gettext import gettext as _

from waydroid_helper.compat_widget.dialog import Dialog
from waydroid_helper.compat_widget.header_bar import HeaderBar


class KeyMappingPreferenceDialog(Dialog):
    
    def __init__(
        self,
        title: str = _("Key Mapping Preferences"),
        parent: Gtk.Window | None = None,
        **kwargs
    ):
        super().__init__(
            title=title,
            parent=parent,
            content_width=600,
            content_height=500,
            **kwargs
        )
        
        self._setup_ui()
        self._setup_signals()
        
    def _setup_ui(self):
        """设置用户界面"""
        # 创建主容器
        main_box = Gtk.Box.new(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        
        # 创建 HeaderBar
        header_bar = self._create_header_bar()
        main_box.append(header_bar)
        
        # 创建 AdwPreferencesPage
        preferences_page = self._create_preferences_page()
        main_box.append(preferences_page)
        
        # 设置内容
        self.set_content(main_box)
        
    def _create_header_bar(self):
        """创建 HeaderBar，包含取消和确认按钮"""
        header_bar = HeaderBar()
        
        # 左侧取消按钮
        cancel_button = Gtk.Button.new_with_label(_("Cancel"))
        cancel_button.add_css_class("text-button")
        cancel_button.connect("clicked", self._on_cancel_clicked)
        header_bar.pack_start(cancel_button)
        
        # 右侧确认按钮
        confirm_button = Gtk.Button.new_with_label(_("Confirm"))
        confirm_button.add_css_class("suggested-action")
        confirm_button.connect("clicked", self._on_confirm_clicked)
        header_bar.pack_end(confirm_button)
        
        return header_bar
        
    def _create_preferences_page(self):
        """创建 AdwPreferencesPage"""
        preferences_page = Adw.PreferencesPage.new()
        
        # 按键映射设置组
        key_mapping_group = self._create_key_mapping_group()
        preferences_page.add(key_mapping_group)
        
        # 游戏控制设置组
        game_control_group = self._create_game_control_group()
        preferences_page.add(game_control_group)
        
        # 高级设置组
        advanced_group = self._create_advanced_group()
        preferences_page.add(advanced_group)
        
        return preferences_page
        
    def _create_key_mapping_group(self):
        """创建按键映射设置组"""
        group = Adw.PreferencesGroup.new()
        group.set_title(_("Key Mapping Settings"))
        group.set_description(_("Configure key mapping behavior and appearance"))
        
        # 启用按键映射开关
        enable_row = Adw.ActionRow.new()
        enable_row.set_title(_("Enable Key Mapping"))
        enable_row.set_subtitle(_("Enable or disable key mapping functionality"))
        
        self.enable_switch = Gtk.Switch.new()
        self.enable_switch.set_active(True)
        self.enable_switch.set_valign(Gtk.Align.CENTER)
        enable_row.add_suffix(self.enable_switch)
        enable_row.set_activatable_widget(self.enable_switch)
        
        group.add(enable_row)
        
        # 透明度设置
        opacity_row = Adw.ActionRow.new()
        opacity_row.set_title(_("Window Opacity"))
        opacity_row.set_subtitle(_("Set the transparency level of the key mapping window"))
        
        self.opacity_scale = Gtk.Scale.new_with_range(
            Gtk.Orientation.HORIZONTAL, 0.1, 1.0, 0.1
        )
        self.opacity_scale.set_value(0.8)
        self.opacity_scale.set_digits(1)
        self.opacity_scale.set_size_request(150, -1)
        opacity_row.add_suffix(self.opacity_scale)
        
        group.add(opacity_row)
        
        # 按键映射文件路径
        config_path_row = Adw.ActionRow.new()
        config_path_row.set_title(_("Configuration File"))
        config_path_row.set_subtitle(_("Path to key mapping configuration file"))
        
        self.config_path_entry = Gtk.Entry.new()
        self.config_path_entry.set_text("~/.config/waydroid/key_mapping.json")
        self.config_path_entry.set_editable(False)
        self.config_path_entry.set_size_request(200, -1)
        
        browse_button = Gtk.Button.new_with_label(_("Browse"))
        browse_button.add_css_class("text-button")
        browse_button.connect("clicked", self._on_browse_config_path)
        
        path_box = Gtk.Box.new(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        path_box.append(self.config_path_entry)
        path_box.append(browse_button)
        
        config_path_row.add_suffix(path_box)
        group.add(config_path_row)
        
        return group
        
    def _create_game_control_group(self):
        """创建游戏控制设置组"""
        group = Adw.PreferencesGroup.new()
        group.set_title(_("Game Control Settings"))
        group.set_description(_("Configure game-specific control options"))
        
        # 自动隐藏开关
        auto_hide_row = Adw.ActionRow.new()
        auto_hide_row.set_title(_("Auto-hide on Game Focus"))
        auto_hide_row.set_subtitle(_("Automatically hide key mapping window when game gains focus"))
        
        self.auto_hide_switch = Gtk.Switch.new()
        self.auto_hide_switch.set_active(False)
        self.auto_hide_switch.set_valign(Gtk.Align.CENTER)
        auto_hide_row.add_suffix(self.auto_hide_switch)
        auto_hide_row.set_activatable_widget(self.auto_hide_switch)
        
        group.add(auto_hide_row)
        
        # 热键设置
        hotkey_row = Adw.ActionRow.new()
        hotkey_row.set_title(_("Toggle Hotkey"))
        hotkey_row.set_subtitle(_("Keyboard shortcut to show/hide key mapping window"))
        
        self.hotkey_entry = Gtk.Entry.new()
        self.hotkey_entry.set_text("F12")
        self.hotkey_entry.set_size_request(100, -1)
        hotkey_row.add_suffix(self.hotkey_entry)
        
        group.add(hotkey_row)
        
        # 默认位置
        position_row = Adw.ActionRow.new()
        position_row.set_title(_("Default Position"))
        position_row.set_subtitle(_("Default position of the key mapping window"))
        
        self.position_combo = Gtk.ComboBoxText.new()
        self.position_combo.append("top-left", _("Top Left"))
        self.position_combo.append("top-right", _("Top Right"))
        self.position_combo.append("bottom-left", _("Bottom Left"))
        self.position_combo.append("bottom-right", _("Bottom Right"))
        self.position_combo.append("center", _("Center"))
        self.position_combo.set_active_id("top-right")
        self.position_combo.set_size_request(120, -1)
        
        position_row.add_suffix(self.position_combo)
        group.add(position_row)
        
        return group
        
    def _create_advanced_group(self):
        """创建高级设置组"""
        group = Adw.PreferencesGroup.new()
        group.set_title(_("Advanced Settings"))
        group.set_description(_("Advanced configuration options"))
        
        # 调试模式开关
        debug_row = Adw.ActionRow.new()
        debug_row.set_title(_("Debug Mode"))
        debug_row.set_subtitle(_("Enable debug logging for key mapping operations"))
        
        self.debug_switch = Gtk.Switch.new()
        self.debug_switch.set_active(False)
        self.debug_switch.set_valign(Gtk.Align.CENTER)
        debug_row.add_suffix(self.debug_switch)
        debug_row.set_activatable_widget(self.debug_switch)
        
        group.add(debug_row)
        
        # 重置按钮
        reset_row = Adw.ActionRow.new()
        reset_row.set_title(_("Reset to Defaults"))
        reset_row.set_subtitle(_("Reset all settings to their default values"))
        
        reset_button = Gtk.Button.new_with_label(_("Reset"))
        reset_button.add_css_class("destructive-action")
        reset_button.connect("clicked", self._on_reset_clicked)
        reset_button.set_size_request(80, -1)
        
        reset_row.add_suffix(reset_button)
        group.add(reset_row)
        
        return group
        
    def _setup_signals(self):
        """设置信号连接"""
        # 这里可以添加信号连接，比如保存设置等
        
    def _on_cancel_clicked(self, button):
        """取消按钮点击事件"""
        self.close()
        
    def _on_confirm_clicked(self, button):
        """确认按钮点击事件"""
        # 保存设置
        self._save_settings()
        # 关闭对话框
        self.close()
        
    def _on_browse_config_path(self, button):
        """浏览配置文件路径"""
        # 这里可以实现文件选择对话框
        pass
        
    def _on_reset_clicked(self, button):
        """重置设置按钮点击事件"""
        # 显示确认对话框
        from waydroid_helper.compat_widget.message_dialog import MessageDialog
        
        dialog = MessageDialog(
            heading=_("Reset to Defaults"),
            body=_("Are you sure you want to reset all settings to their default values? This action cannot be undone."),
            parent=self
        )
        
        dialog.add_response(Gtk.ResponseType.NO, _("No"))
        dialog.add_response(Gtk.ResponseType.YES, _("Yes"))
        dialog.set_response_appearance(Gtk.ResponseType.YES, "destructive-action")
        dialog.set_default_response(Gtk.ResponseType.NO)
        
        dialog.connect("response", self._on_reset_response)
        dialog.present()
        
    def _on_reset_response(self, dialog, response):
        """处理重置确认对话框的响应"""
        if (response == Gtk.ResponseType.YES.value_nick or
            response == Gtk.ResponseType.YES):
            self._reset_to_defaults()
            
    def _save_settings(self):
        """保存设置"""
        # 这里实现保存设置的逻辑
        settings = {
            "enable_key_mapping": self.enable_switch.get_active(),
            "opacity": self.opacity_scale.get_value(),
            "config_path": self.config_path_entry.get_text(),
            "auto_hide": self.auto_hide_switch.get_active(),
            "hotkey": self.hotkey_entry.get_text(),
            "default_position": self.position_combo.get_active_id(),
            "debug_mode": self.debug_switch.get_active()
        }
        
        # 保存到配置文件或数据库
        print(f"Saving settings: {settings}")
        
    def _reset_to_defaults(self):
        """重置为默认设置"""
        self.enable_switch.set_active(True)
        self.opacity_scale.set_value(0.8)
        self.config_path_entry.set_text("~/.config/waydroid/key_mapping.json")
        self.auto_hide_switch.set_active(False)
        self.hotkey_entry.set_text("F12")
        self.position_combo.set_active_id("top-right")
        self.debug_switch.set_active(False)
