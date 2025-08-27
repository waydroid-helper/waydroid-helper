# pyright: reportCallIssue=false
# pyright: reportUnknownVariableType=false
# pyright: reportAny=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false

from gettext import gettext as _
from typing import cast
import asyncio

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GObject, Gtk

from waydroid_helper.controller import TransparentWindow
from waydroid_helper.infobar import InfoBar
from waydroid_helper.shared_folder import SharedFoldersWidget
from waydroid_helper.util import Task, logger
from waydroid_helper.util.subprocess_manager import SubprocessManager
from waydroid_helper.waydroid import Waydroid
from waydroid_helper.compat_widget import NavigationPage, HeaderBar, ToolbarView, ADW_VERSION
from waydroid_helper.compat_widget.message_dialog import MessageDialog
import os


class InstanceDetailPage(NavigationPage):
    __gtype_name__: str = "InstanceDetailPage"

    def __init__(self, waydroid: Waydroid, navigation_view, props_page, extensions_page, **kwargs):
        super().__init__(title=_("Instance Details"), **kwargs)

        self.waydroid = waydroid
        self._navigation_view = navigation_view
        self._props_page = props_page
        self._extensions_page = extensions_page
        self._task: Task = Task()
        self._key_mapping_window: TransparentWindow | None = None
        self._app: Gtk.Application | None = None

        # Create main content - 简单的ViewStack，不重复window.py的复杂结构
        self._create_simple_content()

        # Connect to waydroid state changes
        self.waydroid.connect("notify::state", self._on_waydroid_state_changed)
        
    def _create_simple_content(self):
        """创建正确的内容结构 - 必须有 ToolbarView 和 HeaderBar"""
        # 创建 ToolbarView - 这是必需的，否则没有窗口装饰
        toolbar_view = ToolbarView.new()

        # 创建 HeaderBar - 这是必需的，否则没有标题栏
        header_bar = HeaderBar()

        # 创建ViewStack
        self.view_stack = Adw.ViewStack.new()

        # 添加详情标签页
        details_tab = self._create_details_tab()
        details_page = self.view_stack.add_titled(details_tab, "details", _("Details"))
        details_page.set_icon_name("info-symbolic")

        # 添加设置标签页
        settings_page = self.view_stack.add_titled(self._props_page, "settings", _("Settings"))
        settings_page.set_icon_name("system-symbolic")

        # 添加扩展标签页
        extensions_page = self.view_stack.add_titled(self._extensions_page, "extensions", _("Extensions"))
        extensions_page.set_icon_name("addon-symbolic")

        # 监听页面变化，控制刷新按钮
        self.view_stack.connect("notify::visible-child", self._on_page_changed)

        # 设置ViewSwitcher到HeaderBar
        if ADW_VERSION >= (1, 4, 0):
            view_switcher = Adw.ViewSwitcher.new()
            view_switcher.set_policy(Adw.ViewSwitcherPolicy.WIDE)
            view_switcher.set_stack(self.view_stack)
            header_bar.set_title_widget(view_switcher)
        else:
            header_bar.set_property("centering-policy", Adw.CenteringPolicy.STRICT)
            view_switcher_title = Adw.ViewSwitcherTitle.new()
            view_switcher_title.set_stack(self.view_stack)
            view_switcher_title.set_title(_("Instance Details"))
            header_bar.set_title_widget(view_switcher_title)
            self._view_switcher_title = view_switcher_title

        # 添加HeaderBar到ToolbarView
        toolbar_view.add_top_bar(header_bar)

        # 创建刷新按钮但先不添加到HeaderBar
        self._create_refresh_button_only()
        self._header_bar = header_bar

        # 连接信号，在页面被推入导航栈后添加刷新按钮
        self.connect("notify::root", self._on_detail_root_changed)

        # 创建ViewSwitcherBar用于窄屏
        view_switcher_bar = Adw.ViewSwitcherBar.new()
        view_switcher_bar.set_stack(self.view_stack)

        # 设置响应式行为
        if ADW_VERSION < (1, 4, 0):
            if hasattr(self, '_view_switcher_title'):
                self._view_switcher_title.bind_property(
                    "title-visible",
                    view_switcher_bar,
                    "reveal",
                    GObject.BindingFlags.SYNC_CREATE,
                )

        toolbar_view.add_bottom_bar(view_switcher_bar)

        # 新版本的断点机制 - 响应式设计
        if ADW_VERSION >= (1, 4, 0):
            # 需要添加到窗口级别，延迟到页面被添加到窗口后
            self._setup_breakpoint_data = {
                'view_switcher_bar': view_switcher_bar,
                'header_bar': header_bar
            }
            self.connect("notify::root", self._on_root_changed)

        # 设置内容
        toolbar_view.set_content(self.view_stack)
        self.set_child(toolbar_view)

    def _create_refresh_button(self, header_bar):
        """创建刷新按钮并添加到HeaderBar"""
        self.refresh_button = Gtk.Button()
        self.refresh_button.set_tooltip_text(_("Click to refresh extension list"))
        self.refresh_button.add_css_class("image-button")

        self.refresh_btn_stack = Gtk.Stack.new()
        self.refresh_btn_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)

        # 图标状态
        icon_box = Gtk.Box.new(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        icon_box.append(Gtk.Image.new_from_icon_name("view-refresh-symbolic"))
        self.refresh_btn_stack.add_named(name="icon", child=icon_box)

        # 加载状态
        from waydroid_helper.compat_widget import Spinner
        self.refresh_btn_stack.add_named(name="spin", child=Spinner())

        self.refresh_button.set_child(self.refresh_btn_stack)
        self.refresh_button.connect("clicked", self._on_refresh_button_clicked)

        # 初始状态：隐藏刷新按钮
        self.refresh_button.set_visible(False)

        # 添加到HeaderBar左边，在返回按钮右边
        header_bar.pack_start(self.refresh_button)

    def _create_refresh_button_only(self):
        """只创建刷新按钮，不添加到HeaderBar"""
        self.refresh_button = Gtk.Button()
        self.refresh_button.set_tooltip_text(_("Click to refresh extension list"))
        self.refresh_button.add_css_class("image-button")

        self.refresh_btn_stack = Gtk.Stack.new()
        self.refresh_btn_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)

        # 图标状态
        icon_box = Gtk.Box.new(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        icon_box.append(Gtk.Image.new_from_icon_name("view-refresh-symbolic"))
        self.refresh_btn_stack.add_named(name="icon", child=icon_box)

        # 加载状态
        from waydroid_helper.compat_widget import Spinner
        self.refresh_btn_stack.add_named(name="spin", child=Spinner())

        self.refresh_button.set_child(self.refresh_btn_stack)
        self.refresh_button.connect("clicked", self._on_refresh_button_clicked)

        # 初始状态：隐藏刷新按钮
        self.refresh_button.set_visible(False)

    def _on_detail_root_changed(self, widget, param):
        """当页面被推入导航栈时，添加刷新按钮"""
        if self.get_root() and hasattr(self, '_header_bar') and hasattr(self, 'refresh_button'):
            self._header_bar.pack_start(self.refresh_button)



    def _on_page_changed(self, stack, pspec):
        """处理页面切换，控制刷新按钮显示"""
        current_page = stack.get_visible_child()

        # 只在扩展页面显示刷新按钮
        if hasattr(self, 'refresh_button'):
            if current_page == self._extensions_page:
                self.refresh_button.set_visible(True)
            else:
                self.refresh_button.set_visible(False)

    def _on_refresh_button_clicked(self, button):
        """处理刷新按钮点击"""
        asyncio.create_task(self._refresh_extensions_page(button))
        
    async def _refresh_extensions_page(self, button):
        """刷新扩展页面"""
        stack = button.get_child()
        if isinstance(stack, Gtk.Stack):
            stack.set_visible_child_name("spin")

        await self._extensions_page.refresh()

        if isinstance(stack, Gtk.Stack):
            stack.set_visible_child_name("icon")
        
    def _create_details_tab(self):
        """创建详情标签页，包含共享文件夹、按键映射和缓存管理"""
        box = Gtk.Box.new(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Create preferences page
        prefs_page = Adw.PreferencesPage.new()

        # 共享文件夹组
        shared_folders_widget = SharedFoldersWidget()
        prefs_page.add(shared_folders_widget)

        # 按键映射组
        key_mapping_group = self._create_key_mapping_group()
        prefs_page.add(key_mapping_group)

        # 缓存管理组
        cache_management_group = self._create_cache_management_group()
        prefs_page.add(cache_management_group)

        # Google Play 服务组
        google_play_group = self._create_google_play_group()
        prefs_page.add(google_play_group)

        # InfoBar for shared folders
        self.infobar: InfoBar = InfoBar(
            label=_("Restart the systemd user service immediately"),
            ok_callback=lambda *_: shared_folders_widget.restart_service(),
        )
        shared_folders_widget.connect(
            "updated", lambda _: self.infobar.set_reveal_child(True)
        )

        box.append(prefs_page)
        box.append(self.infobar)
        return box
        
    def _create_key_mapping_group(self):
        """创建按键映射组"""
        group = Adw.PreferencesGroup.new()
        group.set_title(_("Key Mapper"))

        # 按键映射行
        key_mapping_row = Adw.ActionRow.new()
        key_mapping_row.set_title(_("Key Mapping Window"))
        key_mapping_row.set_subtitle(_("Manage key mapping overlay window for game control"))

        # 创建按钮容器
        button_box = Gtk.Box.new(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        
        # 设置按钮（左边）
        self.key_mapping_settings_button = Gtk.Button.new()
        self.key_mapping_settings_button.add_css_class("flat")
        self.key_mapping_settings_button.set_size_request(40, 40)
        self.key_mapping_settings_button.connect("clicked", self.on_key_mapping_settings_clicked)
        
        # 添加系统设置图标
        settings_icon = Gtk.Image.new_from_icon_name("applications-system-symbolic")
        self.key_mapping_settings_button.set_child(settings_icon)
        self.key_mapping_settings_button.set_tooltip_text(_("Key Mapping Settings"))
        
        # 切换按钮（右边）
        self.key_mapping_toggle_button = Gtk.Button.new_with_label(_("Open"))
        self.key_mapping_toggle_button.set_sensitive(False)
        self.key_mapping_toggle_button.add_css_class("suggested-action")
        self.key_mapping_toggle_button.set_size_request(160, 40)  # 统一宽度
        self.key_mapping_toggle_button.connect("clicked", self.on_key_mapping_toggle_clicked)

        # 将按钮添加到容器中
        button_box.append(self.key_mapping_settings_button)
        button_box.append(self.key_mapping_toggle_button)
        
        key_mapping_row.add_suffix(button_box)
        group.add(key_mapping_row)

        return group

    def _create_cache_management_group(self):
        """创建缓存管理组"""
        group = Adw.PreferencesGroup.new()
        group.set_title(_("Cache Management"))

        # 清除缓存行
        clear_cache_row = Adw.ActionRow.new()
        clear_cache_row.set_title(_("Clear Package Cache"))
        clear_cache_row.set_subtitle(_("Fix startup issues after installing GApps or microG"))

        # 清除缓存按钮
        self.clear_cache_button = Gtk.Button.new_with_label(_("Clear Cache"))
        self.clear_cache_button.add_css_class("destructive-action")
        self.clear_cache_button.set_size_request(160, 40)  # 统一宽度
        self.clear_cache_button.connect("clicked", self.on_clear_cache_clicked)

        clear_cache_row.add_suffix(self.clear_cache_button)
        group.add(clear_cache_row)

        return group

    def set_app(self, app: Gtk.Application):
        """设置应用实例"""
        self._app = app
        self._update_key_mapping_buttons()

    def _on_root_changed(self, widget, param):
        """当页面被添加到窗口时设置断点"""
        root = self.get_root()
        if root and hasattr(self, '_setup_breakpoint_data') and hasattr(root, 'add_breakpoint'):
            data = self._setup_breakpoint_data

            breakpoint_condition = Adw.BreakpointCondition.new_length(
                type=Adw.BreakpointConditionLengthType.MAX_WIDTH,
                value=550,
                unit=Adw.LengthUnit.PX,
            )
            break_point = Adw.Breakpoint.new(condition=breakpoint_condition)
            none_value = GObject.Value()
            none_value.init(GObject.TYPE_OBJECT)
            none_value.set_object(None)

            break_point.add_setters(
                objects=[data['view_switcher_bar'], data['header_bar']],
                names=["reveal", "title-widget"],
                values=[True, none_value],
            )
            root.add_breakpoint(breakpoint=break_point)

            # 清理数据，避免重复添加
            del self._setup_breakpoint_data

    def _on_waydroid_state_changed(self, w, param):
        """Waydroid状态变化时更新按键映射按钮"""
        self._update_key_mapping_buttons()
        
    def _update_key_mapping_buttons(self):
        """Update key mapping button status"""
        try:
            if self._key_mapping_window and self._key_mapping_window.is_visible():
                # 窗口已打开，显示关闭按钮
                self.key_mapping_toggle_button.set_label(_("Close"))
                self.key_mapping_toggle_button.remove_css_class("suggested-action")
                self.key_mapping_toggle_button.add_css_class("destructive-action")
                self.key_mapping_toggle_button.set_sensitive(True)
            else:
                # 窗口未打开，显示打开按钮
                self.key_mapping_toggle_button.set_label(_("Open"))
                self.key_mapping_toggle_button.remove_css_class("destructive-action")
                self.key_mapping_toggle_button.add_css_class("suggested-action")
                self.key_mapping_toggle_button.set_sensitive(True)
        except Exception as e:
            logger.error(f"Update key mapping button status failed: {e}")
            self.key_mapping_toggle_button.set_label(_("Open"))
            self.key_mapping_toggle_button.remove_css_class("destructive-action")
            self.key_mapping_toggle_button.add_css_class("suggested-action")
            self.key_mapping_toggle_button.set_sensitive(True)

    def on_key_mapping_toggle_clicked(self, button: Gtk.Button):
        """Toggle key mapping window"""
        try:
            if self._key_mapping_window and self._key_mapping_window.is_visible():
                # 窗口已打开，关闭它
                logger.info("Close key mapping window")
                self._key_mapping_window.close()
                logger.info("Key mapping window close request sent")
            else:
                # 窗口未打开，打开它
                logger.info("Open key mapping window")
                if self._app:
                    self._key_mapping_window = TransparentWindow(self._app)
                    self._key_mapping_window.connect("close-request", self._on_key_mapping_window_closed)
                    self._key_mapping_window.present()
                    self._update_key_mapping_buttons()
                    logger.info("Key mapping window opened")

                    # Minimize the main window
                    root = self.get_root()
                    root = cast(Gtk.ApplicationWindow, root)
                    if root and hasattr(root, 'minimize'):
                        root.minimize()
                        logger.info("Main window minimized")
                else:
                    logger.error("Cannot get application instance")
        except Exception as e:
            logger.error(f"Toggle key mapping window failed: {e}")
            self._key_mapping_window = None
            self._update_key_mapping_buttons()

    def on_key_mapping_settings_clicked(self, button: Gtk.Button):
        """Open key mapping preferences dialog"""
        try:
            from waydroid_helper.key_mapping_preference_dialog import KeyMappingPreferenceDialog
            
            # 获取父窗口
            parent_window = self.get_root()
            
            # 创建设置对话框
            settings_dialog = KeyMappingPreferenceDialog(
                title=_("Key Mapping Preferences"),
                parent=parent_window
            )
            
            # 显示对话框
            settings_dialog.present()
            
            logger.info("Key mapping preferences dialog opened")
            
        except Exception as e:
            logger.error(f"Failed to open key mapping preferences dialog: {e}")
            # 显示错误消息
            from waydroid_helper.compat_widget.message_dialog import MessageDialog
            
            error_dialog = MessageDialog(
                heading=_("Error"),
                body=_("Failed to open key mapping preferences dialog:\n\n{0}").format(str(e)),
                parent=self.get_root()
            )
            error_dialog.add_response(Gtk.ResponseType.OK, _("OK"))
            error_dialog.set_default_response(Gtk.ResponseType.OK)
            error_dialog.present()

    def _on_key_mapping_window_closed(self, window):
        """Callback when key mapping window is closed"""
        logger.info("Key mapping window closed")
        self._key_mapping_window = None
        self._update_key_mapping_buttons()
        return False

    def on_clear_cache_clicked(self, button: Gtk.Button):
        """Handle clear cache button click"""
        logger.info("Clear package cache button clicked")
        self._show_clear_cache_confirmation(button)

    def _show_clear_cache_confirmation(self, button: Gtk.Button):
        """Show confirmation dialog before clearing cache"""
        dialog = MessageDialog(
            heading=_("Clear Package Cache"),
            body=_("This will clear Waydroid package cache files to fix startup issues after installing GApps or microG.\n\nA backup will be created before clearing. Do you want to continue?"),
            parent=self.get_root()
        )

        dialog.add_response(Gtk.ResponseType.CANCEL, _("Cancel"))
        dialog.add_response(Gtk.ResponseType.OK, _("Clear Cache"))
        dialog.set_response_appearance(Gtk.ResponseType.OK, "destructive-action")
        dialog.set_default_response(Gtk.ResponseType.CANCEL)

        dialog.connect("response", self._on_confirmation_response, button)
        dialog.present()

    def _on_confirmation_response(self, dialog, response, button: Gtk.Button):
        """Handle confirmation dialog response"""
        # 处理不同类型的响应，参考 available_version_page.py 的实现
        if (response == Gtk.ResponseType.OK.value_nick or
            response == Gtk.ResponseType.OK):
            logger.info("User confirmed cache clearing")
            self._task.create_task(self._clear_package_cache(button))
        else:
            logger.info("User cancelled cache clearing")

    async def _clear_package_cache(self, button: Gtk.Button):
        """Clear Waydroid package cache"""
        try:
            # 禁用按钮防止重复点击
            button.set_sensitive(False)
            button.set_label(_("Clearing..."))

            # 获取waydroid-cli路径
            cli_path = os.environ.get('WAYDROID_CLI_PATH')
            if not cli_path:
                logger.error("WAYDROID_CLI_PATH environment variable not set")
                self._show_cache_clear_result(False, _("WAYDROID_CLI_PATH not found"))
                return

            # 构建命令
            command = f"{cli_path} clear_package_cache"

            # 执行命令
            subprocess_manager = SubprocessManager()
            result = await subprocess_manager.run(command, shell=False)

            logger.info(f"Clear cache command result: {result}")

            if result["returncode"] == 0:
                # 从输出中提取备份文件路径
                backup_path = self._extract_backup_path(result["stdout"])
                self._show_cache_clear_result(True, _("Package cache cleared successfully"), backup_path)
            else:
                self._show_cache_clear_result(False, f"Error: {result['stderr']}")

        except Exception as e:
            logger.error(f"Failed to clear package cache: {e}")
            self._show_cache_clear_result(False, str(e))
        finally:
            # 恢复按钮状态
            button.set_sensitive(True)
            button.set_label(_("Clear Cache"))

    def _extract_backup_path(self, stdout: str) -> str:
        """Extract backup file path from command output"""
        try:
            # 查找 "Creating backup: " 行
            lines = stdout.split('\n')
            for line in lines:
                if "Creating backup:" in line:
                    # 提取文件名，例如 "Creating backup: ../package_cache_backup_1755763729.tar.gz"
                    backup_filename = line.split("Creating backup: ")[1].strip()
                    # 构建完整路径
                    data_dir = os.path.expanduser("~/.local/share/waydroid/data")
                    if backup_filename.startswith("../"):
                        backup_path = os.path.join(data_dir, backup_filename[3:])  # 去掉 "../"
                    else:
                        backup_path = os.path.join(data_dir, "system", backup_filename)
                    return backup_path
        except Exception as e:
            logger.error(f"Failed to extract backup path: {e}")
        return ""

    def _show_cache_clear_result(self, success: bool, message: str, backup_path: str = ""):
        """Show cache clear operation result"""
        if success:
            logger.info(f"Cache clear success: {message}")
            # 显示成功对话框，包含备份位置信息
            heading = _("Cache Cleared Successfully")
            if backup_path:
                body = _("Package cache has been cleared successfully.\n\nBackup saved to:\n{0}").format(backup_path)
            else:
                body = _("Package cache has been cleared successfully.")
        else:
            logger.error(f"Cache clear failed: {message}")
            # 显示失败对话框
            heading = _("Cache Clear Failed")
            body = _("Failed to clear package cache:\n\n{0}").format(message)

        dialog = MessageDialog(
            heading=heading,
            body=body,
            parent=self.get_root()
        )

        dialog.add_response(Gtk.ResponseType.OK, _("OK"))
        dialog.set_default_response(Gtk.ResponseType.OK)

        dialog.present()

    def _create_google_play_group(self):
        """创建 Google Play 服务组"""
        group = Adw.PreferencesGroup.new()
        group.set_title(_("Google Play Services"))

        # GSF ID Retriever row
        gsf_id_row = Adw.ActionRow.new()
        gsf_id_row.set_title(_("GSF ID Retriever"))
        gsf_id_row.set_subtitle(_("Retrieve Google Services Framework ID for Google Play registration"))

        # GSF ID Retriever button
        self.gsf_id_button = Gtk.Button.new_with_label(_("Retrieve GSF ID"))
        self.gsf_id_button.add_css_class("suggested-action")
        self.gsf_id_button.set_size_request(160, 40)
        self.gsf_id_button.connect("clicked", self._on_gsf_id_button_clicked)

        gsf_id_row.add_suffix(self.gsf_id_button)
        group.add(gsf_id_row)

        return group

    def _on_gsf_id_button_clicked(self, button):
        """Handle GSF ID Retriever button click"""
        from .gsf_retriever import GSFIDRetrieverDialog
        parent_window = self.get_root()
        if parent_window:
            retriever = GSFIDRetrieverDialog(parent_window, self.waydroid)
            retriever.present()
