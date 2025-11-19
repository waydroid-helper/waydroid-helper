# pyright: reportCallIssue=false
# pyright: reportUnknownVariableType=false
# pyright: reportAny=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false

import dis
from gettext import gettext as _
import multiprocessing
from typing import cast
import asyncio

import gi

from waydroid_helper.util.state_waiter import wait_for_state

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GObject, Gtk

from waydroid_helper.controller.app.window import create_keymapper
from waydroid_helper.infobar import InfoBar
from waydroid_helper.shared_folder import SharedFoldersWidget
from waydroid_helper.util import Task, logger
from waydroid_helper.util.subprocess_manager import SubprocessManager
from waydroid_helper.waydroid import Waydroid, WaydroidState
from waydroid_helper.compat_widget import (
    NavigationPage,
    HeaderBar,
    ToolbarView,
    ADW_VERSION,
)
from waydroid_helper.compat_widget.message_dialog import MessageDialog
from waydroid_helper.props_page import PropsPage
from waydroid_helper.extensions_page import ExtensionsPage
from waydroid_helper.scripts_page import ScriptsPage
import os
from waydroid_helper.config.models import RootConfig


class InstanceDetailPage(NavigationPage):
    __gtype_name__: str = "InstanceDetailPage"

    def __init__(
        self, waydroid: Waydroid, navigation_view, config: RootConfig, **kwargs
    ):
        super().__init__(title=_("Instance Details"), **kwargs)

        self.waydroid = waydroid
        self._navigation_view = navigation_view
        self.config = config
        self._task: Task = Task()
        self._app: Gtk.Application | None = None

        # Use lazy loading for page instances
        self._props_page = None
        self._extensions_page = None
        self._scripts_page = None
        self._pages_created = False

        # Create main content first - this is lightweight
        self._create_simple_content()

        # 页面显示后开始预加载其他页面
        self.connect("notify::root", self._on_page_added_to_window)

        self.keymapper_proc = None

    def _ensure_pages_created(self):
        """延迟创建页面实例，只在需要时创建"""
        if not self._pages_created:
            # 开始异步创建页面
            self._create_pages_async()

    def _create_pages_async(self):
        from gi.repository import GLib

        def create_pages():
            self._props_page = PropsPage(self.waydroid)
            self._extensions_page = ExtensionsPage(
                self.waydroid, navigation_view=self._navigation_view
            )
            self._scripts_page = ScriptsPage()
            self._pages_created = True

            self._replace_placeholder_with_real_pages()
            return False

        GLib.idle_add(create_pages)

    def _on_page_added_to_window(self, widget, param):
        if self.get_root() and not self._pages_created:
            from gi.repository import GLib

            GLib.timeout_add(200, self._start_preload)

    def _start_preload(self):
        if not self._pages_created:
            self._ensure_pages_created()
        return False

    def _add_placeholder_pages(self):
        from waydroid_helper.compat_widget import Spinner

        settings_placeholder = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            valign=Gtk.Align.CENTER,
            halign=Gtk.Align.CENTER,
        )
        settings_placeholder.set_spacing(12)
        settings_spinner = Spinner()
        settings_label = Gtk.Label(label=_("Loading Settings..."))
        settings_placeholder.append(settings_spinner)
        settings_placeholder.append(settings_label)

        settings_page = self.view_stack.add_titled(
            settings_placeholder, "settings", _("Settings")
        )
        settings_page.set_icon_name("system-symbolic")

        # 创建扩展页面占位符
        extensions_placeholder = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            valign=Gtk.Align.CENTER,
            halign=Gtk.Align.CENTER,
        )
        extensions_placeholder.set_spacing(12)
        extensions_spinner = Spinner()
        extensions_label = Gtk.Label(label=_("Loading Extensions..."))
        extensions_placeholder.append(extensions_spinner)
        extensions_placeholder.append(extensions_label)

        extensions_page = self.view_stack.add_titled(
            extensions_placeholder, "extensions", _("Extensions")
        )
        extensions_page.set_icon_name("addon-symbolic")

        # 创建脚本页面占位符
        scripts_placeholder = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            valign=Gtk.Align.CENTER,
            halign=Gtk.Align.CENTER,
        )
        scripts_placeholder.set_spacing(12)
        scripts_spinner = Spinner()
        scripts_label = Gtk.Label(label=_("Loading Scripts..."))
        scripts_placeholder.append(scripts_spinner)
        scripts_placeholder.append(scripts_label)

        scripts_page = self.view_stack.add_titled(
            scripts_placeholder, "scripts", _("Scripts")
        )
        scripts_page.set_icon_name("utilities-terminal-symbolic")

    def _replace_placeholder_with_real_pages(self):
        """将占位符替换为真实页面"""
        if self._props_page and self._extensions_page and self._scripts_page:
            # 移除旧的占位符页面
            old_settings = self.view_stack.get_child_by_name("settings")
            old_extensions = self.view_stack.get_child_by_name("extensions")
            old_scripts = self.view_stack.get_child_by_name("scripts")

            if old_settings:
                self.view_stack.remove(old_settings)
            if old_extensions:
                self.view_stack.remove(old_extensions)
            if old_scripts:
                self.view_stack.remove(old_scripts)

            # 添加真实页面
            settings_page = self.view_stack.add_titled(
                self._props_page, "settings", _("Settings")
            )
            settings_page.set_icon_name("system-symbolic")

            extensions_page = self.view_stack.add_titled(
                self._extensions_page, "extensions", _("Extensions")
            )
            extensions_page.set_icon_name("addon-symbolic")

            scripts_page = self.view_stack.add_titled(
                self._scripts_page, "scripts", _("Scripts")
            )
            scripts_page.set_icon_name("utilities-terminal-symbolic")

    def _create_simple_content(self):
        toolbar_view = ToolbarView.new()
        header_bar = HeaderBar()

        self.view_stack = Adw.ViewStack.new()

        details_tab = self._create_details_tab()
        details_page = self.view_stack.add_titled(details_tab, "details", _("Details"))
        details_page.set_icon_name("info-symbolic")

        self._add_placeholder_pages()

        self.view_stack.connect("notify::visible-child", self._on_page_changed)

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

        toolbar_view.add_top_bar(header_bar)

        self._create_refresh_button_only()
        self._header_bar = header_bar

        self.connect("notify::root", self._on_detail_root_changed)

        view_switcher_bar = Adw.ViewSwitcherBar.new()
        view_switcher_bar.set_stack(self.view_stack)

        if ADW_VERSION < (1, 4, 0):
            if hasattr(self, "_view_switcher_title"):
                self._view_switcher_title.bind_property(
                    "title-visible",
                    view_switcher_bar,
                    "reveal",
                    GObject.BindingFlags.SYNC_CREATE,
                )

        toolbar_view.add_bottom_bar(view_switcher_bar)

        if ADW_VERSION >= (1, 4, 0):
            self._setup_breakpoint_data = {
                "view_switcher_bar": view_switcher_bar,
                "header_bar": header_bar,
            }
            self.connect("notify::root", self._on_root_changed)

        toolbar_view.set_content(self.view_stack)
        self.set_child(toolbar_view)

    def _create_refresh_button(self, header_bar):
        self.refresh_button = Gtk.Button()
        self.refresh_button.set_tooltip_text(_("Click to refresh extension list"))
        self.refresh_button.add_css_class("image-button")

        self.refresh_btn_stack = Gtk.Stack.new()
        self.refresh_btn_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)

        icon_box = Gtk.Box.new(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        icon_box.append(Gtk.Image.new_from_icon_name("view-refresh-symbolic"))
        self.refresh_btn_stack.add_named(name="icon", child=icon_box)

        from waydroid_helper.compat_widget import Spinner

        self.refresh_btn_stack.add_named(name="spin", child=Spinner())

        self.refresh_button.set_child(self.refresh_btn_stack)
        self.refresh_button.connect("clicked", self._on_refresh_button_clicked)

        self.refresh_button.set_visible(False)

        header_bar.pack_start(self.refresh_button)

    def _create_refresh_button_only(self):
        self.refresh_button = Gtk.Button()
        self.refresh_button.set_tooltip_text(_("Click to refresh extension list"))
        self.refresh_button.add_css_class("image-button")

        self.refresh_btn_stack = Gtk.Stack.new()
        self.refresh_btn_stack.set_transition_type(Gtk.StackTransitionType.CROSSFADE)

        icon_box = Gtk.Box.new(orientation=Gtk.Orientation.HORIZONTAL, spacing=0)
        icon_box.append(Gtk.Image.new_from_icon_name("view-refresh-symbolic"))
        self.refresh_btn_stack.add_named(name="icon", child=icon_box)

        from waydroid_helper.compat_widget import Spinner

        self.refresh_btn_stack.add_named(name="spin", child=Spinner())

        self.refresh_button.set_child(self.refresh_btn_stack)
        self.refresh_button.connect("clicked", self._on_refresh_button_clicked)

        self.refresh_button.set_visible(False)

    def _on_detail_root_changed(self, widget, param):
        if (
            self.get_root()
            and hasattr(self, "_header_bar")
            and hasattr(self, "refresh_button")
        ):
            self._header_bar.pack_start(self.refresh_button)

    def _on_page_changed(self, stack, pspec):
        current_page = stack.get_visible_child()

        current_page_name = stack.get_visible_child_name()
        if current_page_name in ["settings", "extensions", "scripts"] and not self._pages_created:
            self._ensure_pages_created()

        if hasattr(self, "refresh_button"):
            if current_page == self._extensions_page:
                self.refresh_button.set_visible(True)
            else:
                self.refresh_button.set_visible(False)

    def _on_refresh_button_clicked(self, button):
        asyncio.create_task(self._refresh_extensions_page(button))

    async def _refresh_extensions_page(self, button):
        if not self._pages_created:
            self._ensure_pages_created()

        stack = button.get_child()
        if isinstance(stack, Gtk.Stack):
            stack.set_visible_child_name("spin")

        if self._extensions_page:
            await self._extensions_page.refresh()

        if isinstance(stack, Gtk.Stack):
            stack.set_visible_child_name("icon")

    def _create_details_tab(self):
        box = Gtk.Box.new(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # Create preferences page
        prefs_page = Adw.PreferencesPage.new()

        shared_folders_widget = SharedFoldersWidget()
        prefs_page.add(shared_folders_widget)

        key_mapping_group = self._create_key_mapping_group()
        prefs_page.add(key_mapping_group)

        google_play_group = self._create_google_play_group()
        prefs_page.add(google_play_group)

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
        group = Adw.PreferencesGroup.new()
        group.set_title(_("Key Mapper"))

        key_mapping_row = Adw.ActionRow.new()
        key_mapping_row.set_title(_("Key Mapping Window"))
        key_mapping_row.set_subtitle(
            _("Manage key mapping overlay window for game control")
        )

        button_box = Gtk.Box.new(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        self.key_mapping_settings_button = Gtk.Button.new()
        self.key_mapping_settings_button.add_css_class("flat")
        self.key_mapping_settings_button.set_size_request(40, 40)
        self.key_mapping_settings_button.connect(
            "clicked", self.on_key_mapping_settings_clicked
        )

        settings_icon = Gtk.Image.new_from_icon_name("applications-system-symbolic")
        self.key_mapping_settings_button.set_child(settings_icon)
        self.key_mapping_settings_button.set_tooltip_text(_("Key Mapping Settings"))

        self.key_mapping_toggle_button = Gtk.Button.new_with_label(_("Open"))
        self.key_mapping_toggle_button.set_sensitive(False)
        self.key_mapping_toggle_button.add_css_class("suggested-action")
        self.key_mapping_toggle_button.set_size_request(160, 40)  # 统一宽度
        self.key_mapping_toggle_button.connect(
            "clicked", self.on_key_mapping_toggle_clicked
        )

        button_box.append(self.key_mapping_settings_button)
        button_box.append(self.key_mapping_toggle_button)

        key_mapping_row.add_suffix(button_box)
        group.add(key_mapping_row)

        return group

    def set_app(self, app: Gtk.Application):
        self._app = app
        self._update_key_mapping_buttons()

    def _on_root_changed(self, widget, param):
        root = self.get_root()
        if (
            root
            and hasattr(self, "_setup_breakpoint_data")
            and hasattr(root, "add_breakpoint")
        ):
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
                objects=[data["view_switcher_bar"], data["header_bar"]],
                names=["reveal", "title-widget"],
                values=[True, none_value],
            )
            root.add_breakpoint(breakpoint=break_point)

            del self._setup_breakpoint_data

    def _update_key_mapping_buttons(self):
        """Update key mapping button status"""
        try:
            if self.keymapper_proc and self.keymapper_proc.is_alive():
                self.key_mapping_toggle_button.set_label(_("Close"))
                self.key_mapping_toggle_button.remove_css_class("suggested-action")
                self.key_mapping_toggle_button.add_css_class("destructive-action")
                self.key_mapping_toggle_button.set_sensitive(True)
            else:
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
            if self.keymapper_proc and self.keymapper_proc.is_alive():
                logger.debug("Close key mapping window")
                # 显示关闭确认对话框
                asyncio.create_task(self._show_close_key_mapping_dialog(button))
            else:
                logger.debug("Open key mapping window")

                asyncio.create_task(self._open_key_mapping_window(button))

        except Exception as e:
            logger.error(f"Toggle key mapping window failed: {e}")
            self.keymapper_proc = None
            self._update_key_mapping_buttons()

    async def _show_close_key_mapping_dialog(self, button: Gtk.Button) -> None:
        """显示关闭按键映射器确认对话框"""
        future: asyncio.Future[str] = asyncio.Future()

        def on_response(dialog, response):
            if response == Gtk.ResponseType.CANCEL.value_nick or response == Gtk.ResponseType.CANCEL:
                future.set_result("cancel")
            elif response == Gtk.ResponseType.OK.value_nick or response == Gtk.ResponseType.OK:
                future.set_result("keymapper_only")
            elif response == Gtk.ResponseType.YES.value_nick or response == Gtk.ResponseType.YES:
                future.set_result("stop_session")

        dialog = MessageDialog(
            heading=_("Close Key Mapping Window"),
            body=_("Choose how to close the key mapping window"),
            parent=self.get_root(),
        )

        dialog.add_response(Gtk.ResponseType.CANCEL, _("Cancel"))
        dialog.add_response(Gtk.ResponseType.OK, _("Close Key Mapping Only"))
        dialog.add_response(Gtk.ResponseType.YES, _("Close and Stop Session"))
        dialog.set_response_appearance(Gtk.ResponseType.YES, "destructive-action")
        dialog.set_default_response(Gtk.ResponseType.OK)

        dialog.connect("response", on_response)
        dialog.present()

        result = await future
        
        if result == "cancel":
            return
        elif result == "keymapper_only":
            # 只关闭按键映射器
            self.keymapper_proc.terminate()
            logger.debug("Key mapping window close request sent")
        elif result == "stop_session":
            # 关闭按键映射器并停止 waydroid session
            self.keymapper_proc.terminate()
            logger.debug("Key mapping window close request sent")
            
            # 停止 waydroid session
            try:
                await self.waydroid.stop_session()
                logger.debug("Waydroid session stopped")
            except Exception as e:
                logger.error(f"Failed to stop Waydroid session: {e}")

    async def _show_cage_session_warning(self) -> bool:
        """显示 cage 会话警告对话框"""
        future: asyncio.Future[bool] = asyncio.Future()

        def on_response(dialog, response):
            if (
                response == Gtk.ResponseType.OK.value_nick
                or response == Gtk.ResponseType.OK
            ):
                future.set_result(True)
            else:
                future.set_result(False)

        dialog = MessageDialog(
            heading=_("Session Will Be Stopped"),
            body=_(
                "Cage is enabled and Waydroid session is running. Opening the key mapping window will stop the current session.\n\nDo you want to continue?"
            ),
            parent=self.get_root(),
        )

        dialog.add_response(Gtk.ResponseType.CANCEL, _("Cancel"))
        dialog.add_response(Gtk.ResponseType.OK, _("Continue"))
        dialog.set_response_appearance(Gtk.ResponseType.OK, "destructive-action")
        dialog.set_default_response(Gtk.ResponseType.CANCEL)

        dialog.connect("response", on_response)
        dialog.present()

        return await future

    async def _open_key_mapping_window(self, button: Gtk.Button):
        """打开按键映射窗口"""
        button.set_sensitive(False)
        try:
            # 检查 cage 是否启用且 waydroid 已启动完成
            if self.config.cage.get_property("enabled"):
                if (
                    self.waydroid.persist_props.get_property("boot_completed")
                    or self.waydroid.state == WaydroidState.RUNNING
                ):
                    # 显示确认对话框
                    if not await self._show_cage_session_warning():
                        return
                    await self.waydroid.stop_session()
                    await wait_for_state(self.waydroid, WaydroidState.STOPPED)
                    await asyncio.sleep(1)

                from waydroid_helper.util.subprocess_manager import SubprocessManager
                sm = SubprocessManager()
                width = self.config.cage.window_width
                height = self.config.cage.window_height
                logic_width = self.config.cage.logical_width
                logic_height = self.config.cage.logical_height
                socket_name = self.config.cage.socket_name
                scale = self.config.cage.scale/100
                refresh_rate = self.config.cage.refresh_rate
                hide_titlebar_flag = "--hide-titlebar" if self.config.cage.hide_titlebar else ""
                confine_pointer_flag = "--confine-pointer" if self.config.cage.confine_pointer else ""
                await sm.run(
                    f"{self.config.cage.executable_path} -W {width} -H {height} -w {logic_width} -h {logic_height} -S {socket_name} --scale {scale} --refresh-rate {refresh_rate} {hide_titlebar_flag} {confine_pointer_flag} -- waydroid show-full-ui",
                    flag=True,
                    wait=False,
                )

                await wait_for_state(
                    self.waydroid._controller.property_model,
                    target_state=True,
                    state_property="boot-completed",
                    timeout=60,
                )

            # 直接打开窗口
            if self._app:
                if self.config.cage.enabled:
                    display_name = self.config.cage.socket_name
                else:
                    display_name = self.get_display().get_name()
                self.keymapper_proc = multiprocessing.get_context('spawn').Process(target=create_keymapper,
                                                                    args=(display_name,), name=f"KeyMapper-{display_name}")
                self.keymapper_proc.start()

                async def watch_process(p):
                    loop = asyncio.get_running_loop()
                    await loop.run_in_executor(None, p.join)
                    self._on_key_mapping_window_closed()

                asyncio.create_task(watch_process(self.keymapper_proc)) 

                self._update_key_mapping_buttons()
                logger.debug("Key mapping window opened")

            else:
                logger.error("Cannot get application instance")
            
            root = self.get_root()
            root = cast(Gtk.ApplicationWindow, root)
            if root and hasattr(root, "minimize"):
                root.minimize()
                logger.debug("Main window minimized")
        except Exception as e:
            logger.error(f"Failed to open key mapping window: {e}")
            self.keymapper_proc = None
            self._update_key_mapping_buttons()
            error_dialog = MessageDialog(
                heading=_("Error"),
                body=_("Failed to open key mapping window:\n\n{0}").format(str(e)),
                parent=self.get_root(),
            )
            error_dialog.add_response(Gtk.ResponseType.OK, _("OK"))
            error_dialog.set_default_response(Gtk.ResponseType.OK)
            error_dialog.present()
        finally:
            button.set_sensitive(True)

    def on_key_mapping_settings_clicked(self, button: Gtk.Button):
        """Open key mapping preferences dialog"""
        try:
            from waydroid_helper.key_mapping_preference_dialog import (
                KeyMappingPreferenceDialog,
            )

            parent_window = self.get_root()

            settings_dialog = KeyMappingPreferenceDialog(
                title=_("Key Mapping Preferences"),
                parent=parent_window,
                config=self.config,
            )

            settings_dialog.present()

        except Exception as e:
            logger.error(f"Failed to open key mapping preferences dialog: {e}")
            from waydroid_helper.compat_widget.message_dialog import MessageDialog

            error_dialog = MessageDialog(
                heading=_("Error"),
                body=_("Failed to open key mapping preferences dialog:\n\n{0}").format(
                    str(e)
                ),
                parent=self.get_root(),
            )
            error_dialog.add_response(Gtk.ResponseType.OK, _("OK"))
            error_dialog.set_default_response(Gtk.ResponseType.OK)
            error_dialog.present()

    def _on_key_mapping_window_closed(self):
        """Callback when key mapping window is closed"""
        logger.debug("Key mapping window closed")
        self.keymapper_proc = None
        self._update_key_mapping_buttons()

    def _create_google_play_group(self):
        group = Adw.PreferencesGroup.new()
        group.set_title(_("Google Play Services"))

        gsf_id_row = Adw.ActionRow.new()
        gsf_id_row.set_title(_("GSF ID Retriever"))
        gsf_id_row.set_subtitle(
            _("Retrieve Google Services Framework ID for Google Play registration")
        )

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
