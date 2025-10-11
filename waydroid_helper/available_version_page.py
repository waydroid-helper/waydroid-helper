import asyncio
from enum import IntEnum
from functools import partial
from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gettext import gettext as _

from gi.repository import Adw, GObject, Gtk

from waydroid_helper.compat_widget import (HeaderBar, MessageDialog,
                                           NavigationPage, Spinner,
                                           ToolbarView)
from waydroid_helper.tools import PackageManager
from waydroid_helper.util import Task, logger

if TYPE_CHECKING:
    from waydroid_helper.tools.extensions_manager import PackageInfo, ValidationResult


class AvailableRow(Adw.ActionRow):
    class State(IntEnum):
        UNINSTALLED = 0
        INSTALLING = 1
        INSTALLED = 2

    def __init__(self, name: str, version: str, installed: bool):
        super().__init__()
        self.set_title(title=f"{name}-{version}")

        button_size = 36

        # We'll manage subtitle text directly instead of widgets
        # for better integration with ActionRow's native subtitle area

        self.delete_button: Gtk.Button = Gtk.Button.new()
        self.delete_button.set_valign(align=Gtk.Align.CENTER)
        self.delete_button.set_icon_name("edit-delete-symbolic")
        self.delete_button.add_css_class("destructive-action")
        self.delete_button.set_size_request(button_size, button_size)
        self.add_suffix(self.delete_button)

        self.install_button: Gtk.Button = Gtk.Button.new()
        self.install_button.add_css_class("suggested-action")
        self.install_button.set_valign(align=Gtk.Align.CENTER)
        self.install_button.set_icon_name("document-save-symbolic")
        self.install_button.set_size_request(button_size, button_size)
        self.add_suffix(self.install_button)

        self.spinner: Spinner = Spinner()
        self.spinner.set_size_request(button_size, button_size)
        self.spinner.set_valign(align=Gtk.Align.CENTER)
        self.add_suffix(self.spinner)

        if installed:
            self.set_installation_state(self.State.INSTALLED)
        else:
            self.set_installation_state(self.State.UNINSTALLED)

    def set_installation_state(self, state: State):
        if state == self.State.INSTALLED:
            self.install_button.hide()
            self.delete_button.show()
            self.spinner.hide()
        elif state == self.State.UNINSTALLED:
            self.install_button.show()
            self.delete_button.hide()
            self.spinner.hide()
        elif state == self.State.INSTALLING:
            self.install_button.hide()
            self.delete_button.hide()
            self.spinner.show()

    def set_validation_errors(self, arch_error: bool = False, android_version_error: bool = False):
        """Set validation errors as colored subtitle text and disable row if needed"""
        subtitle_parts = []
        
        if arch_error:
            # Red colored text for architecture error
            subtitle_parts.append('<span color="#e01b24" size="small" weight="bold">⚠️ ' + _("Incompatible Arch") + '</span>')
        if android_version_error:
            # Orange colored text for android version error  
            subtitle_parts.append('<span color="#f57c00" size="small" weight="bold">⚠️ ' + _("Incompatible Android") + '</span>')
            
        if subtitle_parts:
            # Join multiple errors and set as subtitle with markup
            subtitle_markup = ' • '.join(subtitle_parts)
            self.set_subtitle(subtitle_markup)
            # Disable the entire row if there are validation errors
            self.set_sensitive(False)
            self.install_button.set_sensitive(False)
            self.delete_button.set_sensitive(False)
        else:
            # Clear subtitle if no errors
            self.set_subtitle("")
            self.set_sensitive(True)
            self.install_button.set_sensitive(True)
            self.delete_button.set_sensitive(True)


# class CircularProgressBar(Gtk.DrawingArea):
#     def __init__(self):
#         super().__init__()
#         self.fraction = 0.0
#         self.set_content_width(40)
#         self.set_content_height(40)
#         self.set_draw_func(self.draw)
#         self.accent_color: Gdk.RGBA = None

#     def __init_accent_color(self):
#         if adw_version >= "10600":

#             def on_accent_color_changed(style_manager):
#                 accent_color = self.style_manager.get_accent_color()
#                 self.accent_color = accent_color.to_rgba(accent_color)
#                 self.queue_draw()

#             self.style_manager = self.get_root().get_application().get_style_manager()
#             on_accent_color_changed(None, None)
#             self.style_manager.connect("notify::accent-color", on_accent_color_changed)
#         else:
#             style_context = self.get_style_context()
#             self.accent_color = style_context.lookup_color("accent_bg_color")[1]

#     def set_fraction(self, fraction):
#         self.fraction = fraction
#         self.queue_draw()

#     def draw(self, area, cr, width, height):
#         if self.accent_color is None:
#             self.__init_accent_color()

#         center_x = width / 2
#         center_y = height / 2
#         radius = min(width, height) / 2 - 5

#         cr.set_line_width(4)
#         cr.set_source_rgb(0.8, 0.8, 0.8)
#         cr.arc(center_x, center_y, radius, 0, 2 * math.pi)
#         cr.stroke()

#         Gdk.cairo_set_source_rgba(cr, self.accent_color)
#         cr.arc(
#             center_x,
#             center_y,
#             radius,
#             -math.pi / 2,
#             (2 * self.fraction - 0.5) * math.pi,
#         )
#         cr.stroke()


"""
AdwNavigationView：
若直接 push 而没有 add, 在 pop 之后页面会自动销毁。
但是如果 AdwNavigationPage 的派生类中信号连接了回调函数，则不会自动销毁，必须要手动解除后才会被销毁
"""


class AvailableVersionPage(NavigationPage):
    __gtype_name__: str = "AvailableVersionPage"
    extension_manager: PackageManager
    _task: Task = Task()
    page: Adw.PreferencesPage

    # AdwLeafletView
    # if NAVIGATION_PAGE == "AdwLeafletPage":
    #     back_button = Gtk.Template.Child()

    def __init__(
        self, ext_versions: list["PackageInfo"], extension_manager: PackageManager
    ):
        super().__init__(title=_("Available Versions"))
        self.extension_manager = extension_manager
        ext_versions = sorted(
            ext_versions,
            key=lambda x: x["version"],
            reverse=True,
        )
        adw_preferences_group = Adw.PreferencesGroup.new()
        self.page = Adw.PreferencesPage.new()
        self.page.add(group=adw_preferences_group)

        adw_header_bar = HeaderBar()
        adw_tool_bar_view = ToolbarView.new()
        adw_tool_bar_view.add_top_bar(adw_header_bar)

        adw_tool_bar_view.set_content(self.page)

        self.set_child(adw_tool_bar_view)

        self.rows: dict[str, AvailableRow] = {}
        self.lock: asyncio.Lock = asyncio.Lock()

        for version in ext_versions:
            installed = self.extension_manager.is_installed(
                version["name"], version["version"]
            )
            adw_action_row = AvailableRow(
                version["name"], version["version"], installed
            )
            
            # Check validation errors
            arch_validation = self.extension_manager.check_arch(version["name"], version["version"])
            android_validation = self.extension_manager.check_android_version(version["name"], version["version"])
            
            # Set validation error labels and disable if needed
            adw_action_row.set_validation_errors(
                arch_error=not arch_validation.is_valid,
                android_version_error=not android_validation.is_valid
            )
            
            adw_action_row.delete_button.connect(
                "clicked",
                partial(
                    self.on_delete_button_clicked,
                    name=version["name"],
                    version=version["version"],
                ),
            )
            adw_action_row.install_button.connect(
                "clicked",
                partial(
                    self.on_install_button_clicked,
                    name=version["name"],
                    version=version["version"],
                ),
            )
            adw_preferences_group.add(child=adw_action_row)
            self.rows[f"{version['name']}-{version['version']}"] = adw_action_row

    def on_installation_started(
        self, obj: GObject.Object, name: str, version: str
    ) -> None:
        pass
        # self.rows[f"{name}-{version}"].set_installation_state(
        #     AvailableRow.State.INSTALLING
        # )

    def on_installation_completed(
        self, obj: GObject.Object, name: str, version: str
    ) -> None:
        self.rows[f"{name}-{version}"].set_installation_state(
            AvailableRow.State.INSTALLED
        )
        dialog = MessageDialog(
            _("Installation Complete"),
            _("{0} has been successfully installed.").format(f"{name}-{version}"),
            self.get_root(),
            True,
        )
        dialog.add_response(Gtk.ResponseType.OK, _("OK"))
        dialog.present()
    
    def on_uninstallation_started(
        self, obj: GObject.Object, name: str, version: str
    ) -> None:
        pass

    def on_uninstallation_completed(
        self, obj: GObject.Object, name: str, version: str
    ) -> None:
        self.rows[f"{name}-{version}"].set_installation_state(
            AvailableRow.State.UNINSTALLED
        )
        dialog = MessageDialog(
            _("Uninstallation Complete"),
            _("{0} has been successfully uninstalled.").format(f"{name}-{version}"),
            self.get_root(),
            True,
        )
        dialog.add_response(Gtk.ResponseType.OK, _("OK"))
        dialog.present()

    async def show_dialog(self, title: str, body: str) -> bool:
        dialog = MessageDialog(
            heading=title,
            body=body,
            parent=self.get_root(),
        )
        dialog.add_response(Gtk.ResponseType.CANCEL, _("Cancel"))
        dialog.add_response(Gtk.ResponseType.OK, _("OK"))
        dialog.set_response_appearance(Gtk.ResponseType.OK, "suggested-action")
        dialog.set_response_appearance(Gtk.ResponseType.CANCEL, "destructive-action")
        dialog.set_default_response(Gtk.ResponseType.OK)
        # 使用 asyncio.Future 等待用户响应
        future:asyncio.Future[bool] = asyncio.Future()

        def on_response(dialog:MessageDialog, response:Gtk.ResponseType|str):
            if (
                response == Gtk.ResponseType.OK.value_nick
                or response == Gtk.ResponseType.OK
            ):
                future.set_result(True)
            else:
                future.set_result(False)

        dialog.connect("response", on_response) # pyright:ignore[reportUnknownMemberType]
        dialog.present()

        return await future

    async def show_validation_error(self, validation_result: "ValidationResult") -> bool:
        if validation_result.is_valid:
            return True
            
        dialog = MessageDialog(
            heading=_("Installation Validation Failed"),
            body=validation_result.error_message,
            parent=self.get_root(),
        )
        dialog.add_response(Gtk.ResponseType.OK, _("OK"))
        dialog.present()
        return False
    

    async def __install(self, name: str, version: str) -> None:
        installation_successful = False
        try:
            # Spinner
            self.rows[f"{name}-{version}"].set_installation_state(
                AvailableRow.State.INSTALLING
            )
            async with self.lock:
                arch_check = self.extension_manager.check_arch(name, version)
                if not await self.show_validation_error(arch_check):
                    return
                
                android_version_check = self.extension_manager.check_android_version(name, version)
                if not await self.show_validation_error(android_version_check):
                    return
                
                conflicts = self.extension_manager.check_conflicts(
                    name=name, version=version
                )
                if await self.show_dialog(
                    _("Extension Installation"),
                    _("Do you want to install") + " " + name,
                ):
                    if conflicts:
                        if await self.show_dialog(
                            _("Extension Conflict"),
                            _("Do you want to uninstall the conflicting extensions")
                            + " "
                            + ",".join(conflicts),
                        ):
                            await self.extension_manager.remove_packages(conflicts)
                        else:
                            return
                    await self.extension_manager.install_package(
                        name=name, version=version
                    )
                    installation_successful = True
        except Exception as e:
            logger.error(str(e))
            dialog = MessageDialog(
                heading=_("Installation Failed"), body=str(e), parent=self.get_root()
            )
            dialog.add_response(Gtk.ResponseType.OK, _("OK"))
            dialog.present()
        finally:
            if not installation_successful:
                self.rows[f"{name}-{version}"].set_installation_state(
                    AvailableRow.State.UNINSTALLED
                )

    async def __uninstall(self, name:str, version:str):
        uninstall_successful = False
        try:
            self.rows[f"{name}-{version}"].set_installation_state(
                AvailableRow.State.INSTALLING
            )
            if await self.show_dialog(
                _("Uninstall Confirmation"),
                _("Do you want to uninstall") + " " + name,
            ):
                await self.extension_manager.remove_package(name)
                uninstall_successful = True
        except Exception as e:
            self.rows[f"{name}-{version}"].set_installation_state(
                AvailableRow.State.INSTALLED
            )
            logger.error(e)
            dialog = MessageDialog(
                heading=_("Uninstallation Failed"), body=str(e), parent=self.get_root()
            )
            dialog.add_response(Gtk.ResponseType.OK, _("OK"))
            dialog.present()
        finally:
            if not uninstall_successful:
                self.rows[f"{name}-{version}"].set_installation_state(
                    AvailableRow.State.INSTALLED
                )

    def on_install_button_clicked(self, button: Gtk.Button, name:str, version:str):
        self._task.create_task(self.__install(name, version))

    def on_delete_button_clicked(self, button: Gtk.Button, name:str, version:str):
        self._task.create_task(self.__uninstall(name, version))
