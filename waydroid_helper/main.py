# pyright: reportUnknownVariableType=false,reportMissingImports=false

from gi.repository import Adw, Gio, GLib, GObject, Gtk
from gi.events import GLibEventLoopPolicy
import sys
import os
import asyncio
from typing import Callable

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")


Adw.init()

GLIB_VERSION = GLib.MAJOR_VERSION, GLib.MINOR_VERSION, GLib.MICRO_VERSION

if GLIB_VERSION >= (2, 74, 0):
    flags = Gio.ApplicationFlags.DEFAULT_FLAGS
else:
    flags = Gio.ApplicationFlags.FLAGS_NONE


class WaydroidHelperApplication(Adw.Application):
    """The main application singleton class."""

    def __init__(self, version: str):
        super().__init__(application_id="com.jaoushingan.WaydroidHelper", flags=flags)
        self.version = version

        self.logger = None

        self.add_main_option(
            "log-level",
            ord("l"),  # Using 'l' as a short name
            GLib.OptionFlags.NONE,
            GLib.OptionArg.STRING,
            "Set the logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
            "LEVEL",
        )

        self.create_action(
            "quit",
            # pyright: ignore[reportUnknownArgumentType]
            lambda *_: self.quit(),
            ["<primary>q"],
        )
        self.create_action("about", self.on_about_action)
        self.create_action("preferences", self.on_preferences_action)

    def do_activate(self):
        """Called when the application is activated.

        We raise the application's main window, creating it if
        necessary.
        """

        uid = os.getuid()
        if uid == 0:
            from waydroid_helper.compat_widget import MessageDialog
            win = Adw.ApplicationWindow(application=self)
            def dialog_response(
                dialog: MessageDialog, response: Gtk.ResponseType | str
            ):
                win.close()

            dialog = MessageDialog(
                parent=win, heading="Error", body="Cannot run as root user!"
            )
            dialog.add_response(Gtk.ResponseType.OK, "OK")
            dialog.connect(  # pyright: ignore[reportUnknownMemberType]
                "response", dialog_response
            )
            win.present()
            dialog.present()

        else:
            win = self.props.active_window
            if not win: 
                from waydroid_helper.util.log import logger
                from .window import WaydroidHelperWindow

                self.logger = logger
                win = WaydroidHelperWindow(application=self)
            win.present()

    def on_about_action(self, widget: Gtk.Widget, _: GObject.Object):
        """Callback for the app.about action."""
        about = Adw.AboutWindow(
            transient_for=self.props.active_window,
            application_name="waydroid-helper",
            application_icon="com.jaoushingan.WaydroidHelper",
            developer_name="rikka",
            version=self.version,
            developers=["rikka"],
            copyright="© 2024 rikka",
        )
        about.present()

    def on_preferences_action(self, widget: Gtk.Widget, _: GObject.Object):
        """Callback for the app.preferences action."""
        self.logger.info("app.preferences action activated")

    def create_action(
        self,
        name: str,
        callback: Callable[[Gtk.Widget, GObject.Object], None],
        shortcuts: list[str] | None = None,
    ):
        """Add an application action.

        Args:
            name: the name of the action
            callback: the function to be called when the action is
              activated
            shortcuts: an optional list of accelerators
        """
        action = Gio.SimpleAction.new(name, None)
        action.connect("activate", callback)
        self.add_action(action)
        if shortcuts:
            self.set_accels_for_action(f"app.{name}", shortcuts)

    def do_shutdown(self):
        """应用程序关闭时的清理工作"""
        sys.stderr.write("Application is shutting down...\n")

        try:
            # 清理所有multiprocessing子进程（主要是KeyMapper等）
            self._cleanup_child_processes()

            # 清理日志系统
            self._cleanup_logging_system()

            sys.stderr.write("Cleanup resources completed\n")
        except Exception as e:
            sys.stderr.write(f"Cleanup resources failed: {e}\n")

        # 调用父类的shutdown方法
        Adw.Application.do_shutdown(self)

    def _cleanup_logging_system(self):
        """清理日志系统资源"""
        try:
            from waydroid_helper.util import log
            log.cleanup_logging()
        except Exception as e:
            sys.stderr.write(f"Cleanup logging system failed: {e}\n")

    def _cleanup_child_processes(self):
        """清理所有子进程"""
        import multiprocessing

        try:
            # 获取当前所有活跃的子进程
            active_children = multiprocessing.active_children()
            if active_children:
                sys.stderr.write(
                    f"Found {len(active_children)} active child processes, cleaning up...\n")

                for child in active_children:
                    try:
                        if child.is_alive():
                            sys.stderr.write(
                                f"Terminate process: {child.name} (PID: {child.pid})\n")
                            child.terminate()
                    except Exception as e:
                        sys.stderr.write(
                            f"Terminate process {child.name} failed: {e}\n")

                # 给进程一点时间正常退出
                import time
                time.sleep(0.1)

                # 强制杀死仍然存活的进程
                for child in active_children:
                    try:
                        if child.is_alive():
                            sys.stderr.write(
                                f"Force kill process: {child.name} (PID: {child.pid})\n")
                            child.kill()
                    except Exception:
                        pass

        except Exception as e:
            sys.stderr.write(f"Cleanup child processes failed: {e}\n")


def main(version: str):
    """The application's entry point."""
    asyncio.set_event_loop_policy(
        GLibEventLoopPolicy()  # pyright:ignore[reportUnknownArgumentType]
    )

    import multiprocessing
    multiprocessing.set_start_method("spawn", force=True)

    app = WaydroidHelperApplication(version)
    return app.run(sys.argv)
