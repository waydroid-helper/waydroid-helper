#!/usr/bin/env python3
"""
GSF ID Generator - 优雅极简版本
"""

import os
import gi
import asyncio
from typing import TYPE_CHECKING

from waydroid_helper.util.log import logger
from waydroid_helper.util.subprocess_manager import SubprocessManager

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Gtk, Adw, GLib

from gettext import gettext as _
from .compat_widget import dialog, MessageDialog, Spinner
from .models import SessionState
from .util.state_waiter import wait_for_state


if TYPE_CHECKING:
    from waydroid_helper.waydroid import Waydroid

class GSFIDRetrieverDialog(dialog.Dialog):

    def __init__(self, parent_window, waydroid_instance: "Waydroid"):
        super().__init__(
            title="GSF ID Retriever",
            parent=parent_window,
            modal=True,
        )

        self._subprocess_manager = SubprocessManager()
        self.gsf_id = None
        self.waydroid = waydroid_instance
        self._current_task = None  # 添加任务引用
        self._build_ui()

    def _build_ui(self):

        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        main_box.set_valign(Gtk.Align.FILL)

        self.set_content(main_box)

        self.stack = Gtk.Stack()
        self.stack.set_transition_type(Gtk.StackTransitionType.SLIDE_LEFT_RIGHT)
        self.stack.set_transition_duration(300)
        self.stack.set_vexpand(True)
        self.stack.set_valign(Gtk.Align.START)
        main_box.append(self.stack)

        self._create_pages()
        self.stack.set_visible_child_name("start")

    def _create_pages(self):
        start_page = self._create_start_page()
        self.stack.add_named(start_page, "start")

        # 进行中页面 - 阶段1
        progress_page1 = self._create_progress_page("Retrieving GSF ID, please wait...")
        self.stack.add_named(progress_page1, "progress1")

        # 错误页面
        error_page = self._create_error_page()
        self.stack.add_named(error_page, "error")

        # 完成页面
        complete_page = self._create_complete_page()
        self.stack.add_named(complete_page, "complete")

    def _create_start_page(self):
        """Minimal, official-style start page (English)"""
        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        container.set_halign(Gtk.Align.CENTER)
        container.set_valign(Gtk.Align.CENTER)

        desc = Gtk.Label(
            label=_(
                "Obtain your Google Services Framework (GSF) Android ID for device registration."
            )
        )
        desc.set_halign(Gtk.Align.CENTER)
        desc.set_wrap(True)
        desc.set_max_width_chars(50)
        container.append(desc)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        button_box.set_halign(Gtk.Align.CENTER)
        button_box.set_margin_top(8)
        container.append(button_box)

        cancel_btn = Gtk.Button(label=_("Cancel"))
        cancel_btn.set_size_request(100, 36)
        cancel_btn.connect("clicked", lambda b: self.close())
        button_box.append(cancel_btn)

        start_btn = Gtk.Button(label=_("Retrieve"))
        start_btn.add_css_class("suggested-action")
        start_btn.set_size_request(100, 36)
        start_btn.connect("clicked", self._on_start)
        button_box.append(start_btn)

        return container

    def _create_progress_page(self, status_text):
        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        container.set_halign(Gtk.Align.CENTER)
        container.set_valign(Gtk.Align.CENTER)

        spinner = Spinner()
        spinner.set_spinning(True)
        spinner.set_size_request(32, 32)
        spinner.set_halign(Gtk.Align.CENTER)
        container.append(spinner)

        status_label = Gtk.Label(label=status_text)
        status_label.set_halign(Gtk.Align.CENTER)
        status_label.set_wrap(True)
        status_label.set_max_width_chars(40)
        container.append(status_label)

        cancel_btn = Gtk.Button(label=_("Cancel"))
        cancel_btn.set_size_request(100, 36)
        cancel_btn.set_halign(Gtk.Align.CENTER)
        cancel_btn.set_margin_top(8)
        cancel_btn.connect("clicked", self._on_cancel)
        container.append(cancel_btn)

        return container

    def _create_complete_page(self):
        """Minimal, official-style complete page (English, with browser button)"""
        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        container.set_halign(Gtk.Align.CENTER)
        container.set_valign(Gtk.Align.CENTER)

        success_msg = Gtk.Label(label=_("GSF ID Retrieved"))
        success_msg.add_css_class("title-3")
        success_msg.set_halign(Gtk.Align.CENTER)
        container.append(success_msg)

        id_frame = Gtk.Frame()
        id_frame.set_margin_start(8)
        id_frame.set_margin_end(8)
        container.append(id_frame)

        self.id_display = Gtk.Label()
        self.id_display.set_selectable(True)
        self.id_display.set_halign(Gtk.Align.CENTER)
        self.id_display.set_margin_top(8)
        self.id_display.set_margin_bottom(8)
        self.id_display.set_margin_start(12)
        self.id_display.set_margin_end(12)
        id_frame.set_child(self.id_display)

        # 添加提示信息
        info_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        info_box.set_margin_start(8)
        info_box.set_margin_end(8)
        container.append(info_box)

        info_label = Gtk.Label(
            label=_("After registration, please clear data for Google Play Services and Google Play Store, then wait for a while.")
        )
        info_label.set_halign(Gtk.Align.CENTER)
        info_label.set_wrap(True)
        info_label.set_max_width_chars(60)
        info_label.add_css_class("dim-label")
        info_box.append(info_label)

        # 添加清理数据按钮
        clear_btn = Gtk.Button(label=_("Clear Package Data"))
        clear_btn.set_size_request(140, 36)
        clear_btn.connect("clicked", self._on_clear_data)
        clear_btn.set_halign(Gtk.Align.CENTER)
        container.append(clear_btn)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        button_box.set_halign(Gtk.Align.CENTER)
        button_box.set_margin_top(8)
        container.append(button_box)

        copy_btn = Gtk.Button(label=_("Copy"))
        copy_btn.set_size_request(90, 36)
        copy_btn.connect("clicked", self._on_copy)
        button_box.append(copy_btn)

        browser_btn = Gtk.Button(label=_("Open registration page"))
        browser_btn.set_size_request(140, 36)
        browser_btn.connect("clicked", self._on_register)
        button_box.append(browser_btn)

        close_btn = Gtk.Button(label=_("Done"))
        close_btn.set_size_request(90, 36)
        close_btn.connect("clicked", lambda b: self.close())
        button_box.append(close_btn)

        return container

    def _create_error_page(self):
        container = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=16)
        container.set_halign(Gtk.Align.CENTER)
        container.set_valign(Gtk.Align.CENTER)

        icon = Gtk.Image.new_from_icon_name("dialog-error")
        icon.set_pixel_size(48)
        icon.set_halign(Gtk.Align.CENTER)
        container.append(icon)

        error_title = Gtk.Label(label=_("Error"))
        error_title.add_css_class("title-3")
        error_title.set_halign(Gtk.Align.CENTER)
        container.append(error_title)

        self.error_message = Gtk.Label()
        self.error_message.set_halign(Gtk.Align.CENTER)
        self.error_message.set_wrap(True)
        self.error_message.set_max_width_chars(50)
        self.error_message.set_justify(Gtk.Justification.CENTER)
        container.append(self.error_message)

        button_box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        button_box.set_halign(Gtk.Align.CENTER)
        button_box.set_margin_top(8)
        container.append(button_box)

        retry_btn = Gtk.Button(label=_("Retry"))
        retry_btn.set_size_request(100, 36)
        retry_btn.connect("clicked", self._on_retry)
        button_box.append(retry_btn)

        close_btn = Gtk.Button(label=_("Close"))
        close_btn.set_size_request(100, 36)
        close_btn.connect("clicked", lambda b: self.close())
        button_box.append(close_btn)

        return container

    def _on_retry(self, button):
        """重试操作"""
        self.stack.set_visible_child_name("start")

    def _on_start(self, button):
        """Start the async GSF ID generation process"""
        self._current_task = asyncio.create_task(self._async_retrieve())

    async def _async_retrieve(self):
        self.stack.set_visible_child_name("progress1")

        try:
            await self.waydroid.start_session()
            success = await wait_for_state(
                self.waydroid, SessionState.RUNNING, timeout=30.0
            )

            if not success:
                raise Exception(_("Timeout waiting for Waydroid to start"))

            logger.debug("Waydroid started")

            success = await wait_for_state(
                self.waydroid._controller.property_model,
                target_state=True,
                state_property="boot-completed",
                timeout=60,
            )

            logger.debug("Waydroid booted")

            if not success:
                raise Exception(_("Timeout waiting for Waydroid to boot"))

            # 尝试获取 GSF ID，最多重试30秒
            start_time = asyncio.get_event_loop().time()
            timeout = 30.0
            
            while True:
                cli_path = os.environ.get("WAYDROID_CLI_PATH")
                result = await self._subprocess_manager.run(
                    command=f"pkexec {cli_path} get_android_id",
                    shell=False
                )
                logger.info(result["stdout"])
                logger.warning(result["stderr"])
                
                # 检查 stdout 是否包含 android_id| 格式的字符串
                stdout = result["stdout"]
                if "android_id|" in stdout:
                    # 提取 android_id 后面的值
                    lines = stdout.strip().split('\n')
                    for line in lines:
                        if line.startswith("android_id|"):
                            self.gsf_id = line.split("|", 1)[1]
                            logger.info(f"Successfully retrieved GSF ID: {self.gsf_id}")
                            break
                    else:
                        # 如果没找到，继续重试
                        continue
                    
                    # 成功获取到 GSF ID
                    self.id_display.set_text(self.gsf_id)
                    self.stack.set_visible_child_name("complete")
                    return
                
                # 检查是否超时
                elapsed_time = asyncio.get_event_loop().time() - start_time
                if elapsed_time >= timeout:
                    raise Exception(_("Timeout: Failed to retrieve GSF ID after 30 seconds"))
                
                # 等待1秒后重试
                await asyncio.sleep(1.0)

        except asyncio.CancelledError:
            return
        except Exception as e:
            await self._show_error(f"Error retrieving GSF ID: {str(e)}")
        finally:
            self._current_task = None

    async def _show_error(self, message: str):
        self.error_message.set_text(message)
        self.stack.set_visible_child_name("error")

    def _on_cancel(self, button):
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()

        self.close()

    def _on_cancel_response(self, dialog, response):
        if response == "yes" or response == Gtk.ResponseType.OK:
            if self._current_task and not self._current_task.done():
                self._current_task.cancel()

            self.close()
        else:
            dialog.close()

    def _on_register(self, button):
        import webbrowser

        webbrowser.open("https://www.google.com/android/uncertified/")

    def _on_copy(self, button):
        if self.gsf_id:
            clipboard = self.get_clipboard()
            clipboard.set(self.gsf_id)

            dialog = MessageDialog(
                heading=_("Copied"),
                body=_("GSF ID copied to clipboard!"),
                parent=self.get_root(),
            )
            dialog.add_response(Gtk.ResponseType.OK, "OK")
            dialog.set_default_response(Gtk.ResponseType.OK)
            dialog.present()

    def _on_clear_data(self, button):
        """清理 Google Play Services 和 Google Play Store 的数据"""
        # 禁用按钮防止重复点击
        button.set_sensitive(False)
        button.set_label(_("Clearing..."))
        
        # 创建异步任务来清理数据
        self._current_task = asyncio.create_task(self._async_clear_data(button))

    async def _async_clear_data(self, button):
        """异步清理包数据"""
        try:
            # 需要清理的包名列表
            packages_to_clear = [
                "com.google.android.gms",      # Google Play Services
                "com.android.vending"          # Google Play Store
            ]
            
            cli_path = os.environ.get("WAYDROID_CLI_PATH")
            
            # 逐个清理包数据
            for package in packages_to_clear:
                logger.info(f"Clearing data for package: {package}")
                result = await self._subprocess_manager.run(
                    command=f"pkexec {cli_path} clear_package_data {package}",
                    shell=False
                )
                logger.info(f"Clear result for {package}: {result['stdout']}")
                if result["stderr"]:
                    logger.warning(f"Clear stderr for {package}: {result['stderr']}")
            
            # 清理完成，恢复按钮状态
            button.set_sensitive(True)
            button.set_label(_("Clear Package Data"))
            
            # 显示成功消息
            dialog = MessageDialog(
                heading=_("Success"),
                body=_("Package data cleared successfully! Please wait for a while before using Google services."),
                parent=self.get_root(),
            )
            dialog.add_response(Gtk.ResponseType.OK, "OK")
            dialog.set_default_response(Gtk.ResponseType.OK)
            dialog.present()
            
        except Exception as e:
            logger.error(f"Error clearing package data: {str(e)}")
            
            # 恢复按钮状态
            button.set_sensitive(True)
            button.set_label(_("Clear Package Data"))
            
            # 显示错误消息
            dialog = MessageDialog(
                heading=_("Error"),
                body=_("Failed to clear package data: {error}").format(error=str(e)),
                parent=self.get_root(),
            )
            dialog.add_response(Gtk.ResponseType.OK, "OK")
            dialog.set_default_response(Gtk.ResponseType.OK)
            dialog.present()
        finally:
            self._current_task = None

    def close(self):
        if self._current_task and not self._current_task.done():
            self._current_task.cancel()
        super().close()
