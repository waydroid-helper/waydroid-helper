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

from gi.repository import Adw, Gtk, GObject  # type: ignore
from gettext import gettext as _
from typing import TYPE_CHECKING

from waydroid_helper.compat_widget.dialog import Dialog
from waydroid_helper.compat_widget.header_bar import HeaderBar
from waydroid_helper.config import get_cage_config

if TYPE_CHECKING:
    from waydroid_helper.config.models import CageConfigModel


class KeyMappingPreferenceDialog(Dialog):
    
    def __init__(
        self,
        title: str | None = None,
        parent: Gtk.Window | None = None,
        **kwargs
    ):
        super().__init__(
            title=title or _("Key Mapping Preferences"),
            parent=parent,
            content_width=600,
            content_height=400,
            **kwargs
        )
        
        # 获取配置模型
        self.cage_config: CageConfigModel = get_cage_config()
        self.enable_switch: Gtk.Switch
        self.opacity_scale: Gtk.Scale
        self.size_spinbutton: Gtk.SpinButton
        
        self._setup_ui()
        self._setup_signals()
        self._setup_bindings()
        
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
        
        # Cage 设置组
        cage_group = self._create_cage_group()
        preferences_page.add(cage_group)
        
        return preferences_page
        
    def _create_cage_group(self):
        """创建 Cage 设置组"""
        group = Adw.PreferencesGroup.new()
        group.set_title(_("Cage Settings"))
        group.set_description(_("Configure cage functionality"))
        
        # 启用 Cage 开关
        enable_row = Adw.ActionRow.new()
        enable_row.set_title(_("Enable Cage"))
        enable_row.set_subtitle(_("Enable or disable cage functionality"))
        
        self.enable_switch = Gtk.Switch.new()
        self.enable_switch.set_valign(Gtk.Align.CENTER)
        enable_row.add_suffix(self.enable_switch)
        enable_row.set_activatable_widget(self.enable_switch)
        
        group.add(enable_row)
        
        # Cage 透明度滑块
        opacity_row = Adw.ActionRow.new()
        opacity_row.set_title(_("Cage Opacity"))
        opacity_row.set_subtitle(_("Adjust the opacity of cage overlay"))
        
        self.opacity_scale = Gtk.Scale.new_with_range(Gtk.Orientation.HORIZONTAL, 0.0, 1.0, 0.1)
        self.opacity_scale.set_hexpand(True)
        self.opacity_scale.set_size_request(200, -1)
        opacity_row.add_suffix(self.opacity_scale)
        
        group.add(opacity_row)
        
        # Cage 大小调整
        size_row = Adw.ActionRow.new()
        size_row.set_title(_("Cage Size"))
        size_row.set_subtitle(_("Adjust the size of cage in pixels"))
        
        self.size_spinbutton = Gtk.SpinButton.new_with_range(10, 1000, 10)
        self.size_spinbutton.set_valign(Gtk.Align.CENTER)
        size_row.add_suffix(self.size_spinbutton)
        
        group.add(size_row)
        
        return group
        
    def _setup_signals(self):
        """设置信号连接"""
        # 这里可以添加信号连接，比如保存设置等
        pass
        
    def _setup_bindings(self):
        """设置数据绑定 - 使用 GTK 双向绑定"""
        # 使用 GTK 内置的双向绑定
        self.cage_config.bind_property(
            "enabled", 
            self.enable_switch, 
            "active",
            GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.BIDIRECTIONAL
        )
        
        self.cage_config.bind_property(
            "opacity", 
            self.opacity_scale.get_adjustment(), 
            "value",
            GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.BIDIRECTIONAL
        )
        
        self.cage_config.bind_property(
            "size", 
            self.size_spinbutton.get_adjustment(), 
            "value",
            GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.BIDIRECTIONAL
        )
        
    def _on_cancel_clicked(self, button):
        """取消按钮点击事件"""
        self.close()
        
    def _on_confirm_clicked(self, button):
        """确认按钮点击事件"""
        # 双向绑定已经自动同步了值，直接保存
        if self.cage_config.save_to_file():
            print(f"配置已保存 - Cage enabled: {self.cage_config.get_property('enabled')}, opacity: {self.cage_config.get_property('opacity')}, size: {self.cage_config.get_property('size')}")
        else:
            print("配置保存失败!")
        
        self.close()
