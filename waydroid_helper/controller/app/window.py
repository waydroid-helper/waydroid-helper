#!/usr/bin/env python3
"""Transparent controller window composition root."""

from __future__ import annotations

import asyncio
import math
import signal
from gettext import gettext as _
from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")

from gi.events import GLibEventLoopPolicy
from gi.repository import Adw, Gdk, GLib, GObject, Gtk

from waydroid_helper.compat_widget import PropertyAnimationTarget
from waydroid_helper.config.models import RootConfig
from waydroid_helper.controller.app.input_event_factory import (
    GdkKeySymbolResolver,
    GtkInputEventFactory,
)
from waydroid_helper.controller.app.input_state_lifecycle import (
    AndroidInputStateLifecycleService,
)
from waydroid_helper.controller.app.mode_controller import ModeController
from waydroid_helper.controller.app.scrcpy_lifecycle import ScrcpyLifecycleService
from waydroid_helper.controller.app.widget_layout_service import WidgetLayoutService
from waydroid_helper.controller.app.widget_mapping_registrar import (
    WidgetMappingRegistrar,
)
from waydroid_helper.controller.app.widget_settings_popover import (
    WidgetSettingsPopoverPresenter,
)
from waydroid_helper.controller.app.widget_transparency_controller import (
    WidgetTransparencyController,
)
from waydroid_helper.controller.app.window_input_router import WindowInputRouter
from waydroid_helper.controller.app.workspace_manager import WorkspaceManager
from waydroid_helper.controller.core import (
    ControllerRuntimeContext,
    DefaultHandlerRuntimeConfig,
    Event,
    EventBus,
    EventType,
    KeyCombination,
    KeyRegistry,
    ScreenGeometry,
    Server,
)
from waydroid_helper.controller.core.constants import APP_TITLE
from waydroid_helper.controller.core.handler import (
    DefaultEventHandler,
    InputEventHandlerChain,
    KeyMappingEventHandler,
    KeyMappingInputStateGate,
    KeyMappingManager,
)
from waydroid_helper.controller.core.input_state_server import AndroidInputStateServer
from waydroid_helper.controller.core.utils import PointerIdManager
from waydroid_helper.controller.ui.layout_file_actions import LayoutFileActions
from waydroid_helper.controller.ui.menus import ContextMenuManager
from waydroid_helper.controller.ui.styles import StyleManager
from waydroid_helper.controller.widgets.factory import WidgetFactory
from waydroid_helper.util import AdbHelper, logger

if TYPE_CHECKING:
    from waydroid_helper.controller.widgets.base import BaseWidget


Adw.init()


class CircleOverlay(Gtk.DrawingArea):
    """Circular overlay for drawing skill release range indicators."""

    def __init__(self):
        super().__init__()
        self.circle_data: dict | None = None
        self.set_draw_func(self._draw_circle, None)

    def set_circle_data(self, data):
        self.circle_data = data
        self.queue_draw()

    def _draw_circle(self, widget, cr, width, height, user_data):
        if not self.circle_data:
            return

        radius_world = float(self.circle_data.get("circle_radius", 5.0) or 5.0)
        tilt_deg = float(self.circle_data.get("tilt_angle", 45.0) or 45.0)
        fov_deg = float(self.circle_data.get("camera_fov", 36.0) or 36.0)
        origin_x_ratio = float(self.circle_data.get("origin_x", 50.0) or 50.0) / 100.0
        origin_y_ratio = float(self.circle_data.get("origin_y", 50.0) or 50.0) / 100.0

        if width <= 0 or height <= 0 or radius_world <= 0:
            return

        origin_sx = origin_x_ratio * width
        origin_sy = origin_y_ratio * height
        if fov_deg <= 0 or fov_deg >= 180:
            fov_deg = 36.0
        focal = (height / 2.0) / math.tan(math.radians(fov_deg) / 2.0)
        tilt_rad = math.radians(tilt_deg)
        cam_dist = 13.66

        def world_to_screen(wx: float, wz: float) -> tuple[float, float] | None:
            depth = cam_dist + wz * math.cos(tilt_rad)
            if depth <= 1e-3:
                return None
            sx = origin_sx + wx * focal / depth
            sy = origin_sy - wz * math.sin(tilt_rad) * focal / depth
            return sx, sy

        points: list[tuple[float, float]] = []
        for i in range(241):
            t = 2.0 * math.pi * i / 240
            projected = world_to_screen(
                radius_world * math.cos(t),
                radius_world * math.sin(t),
            )
            if projected is not None:
                points.append(projected)

        if len(points) < 3:
            return

        cr.set_source_rgba(0.6, 0.6, 0.6, 0.8)
        cr.set_line_width(3)
        first_x, first_y = points[0]
        cr.move_to(first_x, first_y)
        for x, y in points[1:]:
            cr.line_to(x, y)
        cr.close_path()
        cr.stroke()

        center_sp = world_to_screen(0.0, 0.0)
        if center_sp is not None:
            cx, cy = center_sp
            cr.set_source_rgba(0.5, 0.5, 0.5, 0.9)
            cr.arc(cx, cy, 4, 0, 2 * math.pi)
            cr.fill()


class TransparentWindow(Adw.Window):
    """Transparent controller window."""

    EDIT_MODE = ModeController.EDIT_MODE
    MAPPING_MODE = ModeController.MAPPING_MODE

    current_mode = GObject.Property(
        type=str,
        default=EDIT_MODE,
        nick="Current Mode",
        blurb="The current operating mode (edit or mapping)",
    )

    def __init__(self, app, display_name: str):
        super().__init__(application=app)
        self._is_closing = False

        if self.get_display().get_name() != display_name:
            display = Gdk.Display.open(display_name)
            if display:
                self.set_display(display)
            else:
                raise ValueError("Failed to open display")

        self.connect("close-request", self._on_close_request)
        self.set_title(APP_TITLE)

        overlay = Gtk.Overlay.new()
        self.set_content(overlay)

        self.fixed = Gtk.Fixed.new()
        self.fixed.set_name("mapping-widget")
        overlay.set_child(self.fixed)

        self.event_bus = EventBus()
        self.screen_geometry = ScreenGeometry()
        self.pointer_id_manager = PointerIdManager()
        self.key_registry = KeyRegistry(GdkKeySymbolResolver())
        self.config = RootConfig()
        # Handlers receive an immutable snapshot so controller input processing
        # stays independent from the persistence backend and from live UI state.
        default_handler_config = DefaultHandlerRuntimeConfig(
            keyboard_inject_mode=self.config.default_handler.keyboard_inject_mode,
            mouse_natural_scroll=self.config.default_handler.mouse_natural_scroll,
            mouse_hover=self.config.default_handler.mouse_hover,
        )
        self.runtime_context = ControllerRuntimeContext(
            event_bus=self.event_bus,
            screen_geometry=self.screen_geometry,
            pointer_id_manager=self.pointer_id_manager,
            key_registry=self.key_registry,
            default_handler_config=default_handler_config,
        )

        self._setup_notification_overlay(overlay)

        self.widget_factory = WidgetFactory(self.runtime_context)
        self.style_manager = StyleManager(self.get_display())
        self.workspace_manager = WorkspaceManager(self, self.fixed, self.event_bus)
        self.widget_transparency_controller = WidgetTransparencyController(
            self.workspace_manager.iter_widgets
        )
        self.layout_service = WidgetLayoutService(self.runtime_context)
        self.layout_file_actions = LayoutFileActions(self)
        self.menu_manager = ContextMenuManager(
            self,
            self.layout_service,
            self.layout_file_actions,
        )

        self.circle_overlay = CircleOverlay()
        self.circle_overlay.set_can_target(False)
        overlay.add_overlay(self.circle_overlay)

        self.settings_popover_presenter = WidgetSettingsPopoverPresenter(
            self,
            self.event_bus,
        )
        self.event_bus.subscribe(
            EventType.SETTINGS_WIDGET,
            self._on_widget_settings_requested,
            subscriber=self,
        )
        self.event_bus.subscribe(
            EventType.WIDGET_SELECTION_OVERLAY,
            self._on_widget_selection_overlay,
            subscriber=self,
        )

        self.input_event_factory = GtkInputEventFactory(self, self.key_registry)
        self.key_mapping_manager = KeyMappingManager(self.event_bus)
        self.widget_mapping_registrar = WidgetMappingRegistrar(
            self.register_widget_key_mapping
        )
        self.event_handler_chain = InputEventHandlerChain()
        self.key_mapping_handler = KeyMappingEventHandler(self.key_mapping_manager)
        self.key_mapping_input_gate = KeyMappingInputStateGate(
            self.event_bus,
            self.key_mapping_handler,
            self.key_mapping_manager,
        )
        self.default_handler = DefaultEventHandler(self.runtime_context)
        self.event_handler_chain.add_handler(self.key_mapping_handler)
        self.event_handler_chain.add_handler(self.default_handler)

        self.adb_helper = AdbHelper()
        self.server = Server("0.0.0.0", 10721, self.event_bus)
        self.scrcpy_lifecycle = ScrcpyLifecycleService(
            self.server,
            self.adb_helper,
            self.screen_geometry,
        )
        self.input_state_server = AndroidInputStateServer(self.event_bus)
        self.input_state_lifecycle = AndroidInputStateLifecycleService(
            self.input_state_server,
            self.adb_helper,
        )

        self.mode_controller = ModeController(
            window=self,
            event_bus=self.event_bus,
            iter_widgets=self.workspace_manager.iter_widgets,
            clear_selections=self.clear_all_selections,
            restore_widget_opacity=self.restore_all_widgets_opacity,
            notify=self.show_notification,
        )
        self.connect("notify::current-mode", self._on_mode_changed)

        self.setup_window()
        self.input_router = WindowInputRouter(self)
        self.input_router.install()
        GLib.idle_add(self.show_notification, _("Edit Mode (F1: Switch Mode)"))

    def _setup_notification_overlay(self, overlay: Gtk.Overlay) -> None:
        self.notification_label = Gtk.Label.new("")
        self.notification_label.set_name("mode-notification-label")

        self.notification_box = Gtk.Box()
        self.notification_box.set_name("mode-notification-box")
        self.notification_box.set_halign(Gtk.Align.CENTER)
        self.notification_box.set_valign(Gtk.Align.START)
        self.notification_box.set_margin_top(60)
        self.notification_box.append(self.notification_label)
        self.notification_box.set_opacity(0.0)
        self.notification_box.set_can_target(False)
        overlay.add_overlay(self.notification_box)

    def _on_widget_selection_overlay(self, event):
        overlay_data = event.data
        if overlay_data["action"] == "show":
            self.circle_overlay.set_circle_data(overlay_data)
        elif overlay_data["action"] == "hide":
            self.circle_overlay.set_circle_data(None)

    def _on_widget_settings_requested(self, event: "Event[bool]") -> None:
        self.settings_popover_presenter.show(event.source, event.data)

    def _on_close_request(self, window):
        async def close():
            await self.cleanup_input_state()
            await self.close_server()
            await self.cleanup_scrcpy()

        asyncio.create_task(close())
        return False

    async def close_server(self) -> None:
        await self.scrcpy_lifecycle.close_server()

    async def cleanup_scrcpy(self) -> None:
        await self.scrcpy_lifecycle.cleanup()

    async def cleanup_input_state(self) -> None:
        await self.input_state_lifecycle.cleanup()

    def setup_window(self) -> None:
        self.realize()
        self.set_decorated(False)
        self.maximize()
        self.set_name("transparent-window")

    def do_size_allocate(self, width: int, height: int, baseline: int):
        Adw.Window().do_size_allocate(self, width, height, baseline)
        host_width, host_height = self.screen_geometry.get_host_resolution()
        if self.is_maximized() and host_width == 0 and host_height == 0:
            width = self.get_allocated_width()
            height = self.get_allocated_height()

            self.set_default_size(width, height)
            self.set_size_request(width, height)
            self.screen_geometry.set_host_resolution(width, height)
            self.fixed.set_size_request(width, height)
            self.set_resizable(False)
            logger.info("Window maximized: %s x %s", width, height)

    def fixed_put(self, widget, x, y) -> None:
        self.fixed.put(widget, x, y)
        widget.x = x
        widget.y = y

    def fixed_move(self, widget, x, y) -> None:
        self.fixed.move(widget, x, y)
        widget.x = x
        widget.y = y

    def clear_all_selections(self) -> None:
        self.workspace_manager.clear_all_selections()

    def set_all_widgets_mapping_mode(self, mapping_mode: bool) -> None:
        for child in self.workspace_manager.iter_widgets():
            child.set_mapping_mode(mapping_mode)

    def toggle_all_widgets_transparency(self) -> bool:
        is_transparent = self.widget_transparency_controller.toggle()
        if is_transparent:
            self.show_notification(_("Widgets Transparent (F12: Toggle Widgets)"))
        else:
            self.show_notification(_("Widgets Normal (F12: Toggle Widgets)"))
        return is_transparent

    def restore_all_widgets_opacity(self) -> bool:
        return self.widget_transparency_controller.restore_normal()

    def create_widget_at_position(self, widget: "BaseWidget", x: int, y: int) -> None:
        self.fixed_put(widget, x, y)
        self.widget_mapping_registrar.register_widget(widget)
        self.widget_transparency_controller.apply_to_widget(widget)

    def on_clear_widgets(self, button: Gtk.Button | None) -> None:
        widgets_to_delete = list(self.workspace_manager.iter_widgets())
        for widget in widgets_to_delete:
            self.workspace_manager.delete_specific_widget(widget)
        self.workspace_manager.clear_interaction_state()

    def delete_selected_widgets(self) -> None:
        self.workspace_manager.delete_selected_widgets()

    def show_notification(self, text: str) -> None:
        self.notification_label.set_label(text)

        if (
            hasattr(self, "_notification_fade_out_timer")
            and self._notification_fade_out_timer > 0
        ):
            GLib.source_remove(self._notification_fade_out_timer)
        if hasattr(self, "_notification_animation"):
            self._notification_animation.reset()

        self.notification_box.set_opacity(0)
        animation_target = PropertyAnimationTarget(self.notification_box, "opacity")
        self._notification_animation = Adw.TimedAnimation.new(
            self.notification_box,
            0.0,
            1.0,
            300,
            animation_target,
        )
        self._notification_animation.set_easing(Adw.Easing.LINEAR)
        self._notification_animation.play()
        self._notification_fade_out_timer = GLib.timeout_add(
            1500,
            self._fade_out_notification,
        )

    def _fade_out_notification(self):
        animation_target = PropertyAnimationTarget(self.notification_box, "opacity")
        self._notification_animation = Adw.TimedAnimation.new(
            self.notification_box,
            1.0,
            0.0,
            500,
            animation_target,
        )
        self._notification_animation.set_easing(Adw.Easing.LINEAR)
        self._notification_animation.play()
        self._notification_fade_out_timer = 0
        return GLib.SOURCE_REMOVE

    def _on_mode_changed(self, widget, pspec) -> None:
        self.mode_controller.apply_mode(self.current_mode)

    def switch_mode(self, new_mode: str) -> bool:
        if new_mode not in [self.EDIT_MODE, self.MAPPING_MODE]:
            return False
        if self.current_mode == new_mode:
            return True
        self.set_property("current-mode", new_mode)
        return True

    def register_widget_key_mapping(
        self,
        widget,
        key_combination: KeyCombination,
    ) -> bool:
        return self.key_mapping_manager.subscribe(widget, key_combination)

    def unregister_widget_key_mapping(self, widget) -> bool:
        return self.key_mapping_manager.unsubscribe(widget)

    def unregister_single_widget_key_mapping(
        self,
        widget,
        key_combination: KeyCombination,
    ) -> bool:
        return self.key_mapping_manager.unsubscribe_key(widget, key_combination)

    def get_widget_key_mapping(self, widget) -> list[KeyCombination]:
        return self.key_mapping_manager.get_subscriptions(widget)

    def print_key_mappings(self) -> None:
        self.key_mapping_manager.print_mappings()

    def clear_all_key_mappings(self):
        return self.key_mapping_manager.clear()

    def get_key_mapping_size(self):
        return self._key_mapping_width, self._key_mapping_height


class KeyMapper(Adw.Application):
    def __init__(self, display_name: str):
        sanitized_display = (
            display_name.replace(":", "_").replace("/", "_").replace("-", "_")
        )
        super().__init__(
            application_id=(
                "com.jaoushingan.WaydroidHelper.KeyMapper."
                f"{sanitized_display}"
            )
        )
        self.display_name = display_name
        self.window = None

    def do_activate(self):
        self.window = TransparentWindow(self, self.display_name)
        self.window.present()
        GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal.SIGTERM, self.on_sigterm)

    async def _do_shutdown(self) -> None:
        if self.window:
            self.window.on_clear_widgets(None)
            await self.window.cleanup_input_state()
            await self.window.close_server()
            await self.window.cleanup_scrcpy()
        self.quit()

    def on_sigterm(self):
        asyncio.create_task(self._do_shutdown())
        return True


def create_keymapper(display_name: str):
    asyncio.set_event_loop_policy(
        GLibEventLoopPolicy()  # pyright:ignore[reportUnknownArgumentType]
    )
    app = KeyMapper(display_name)
    app.run()
