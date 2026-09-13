#!/usr/bin/env python3
"""GTK controller wiring and input dispatch for TransparentWindow."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from typing import TYPE_CHECKING

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")

from gi.repository import Gdk, Gtk

from waydroid_helper.controller.app import widget_capabilities as capabilities
from waydroid_helper.controller.app.mode_controller import ModeController
from waydroid_helper.controller.core.event_bus import Event, EventType
from waydroid_helper.controller.core.handler.event_handlers import InputEventType

if TYPE_CHECKING:
    from waydroid_helper.controller.app.input_event_factory import GtkInputEventFactory
    from waydroid_helper.controller.app.workspace_manager import WorkspaceManager
    from waydroid_helper.controller.core.event_bus import EventBus
    from waydroid_helper.controller.core.handler.event_handlers import (
        InputEventHandlerChain,
    )


@dataclass(frozen=True)
class WindowInputRouterDependencies:
    """Explicit collaborators required by GTK input routing.

    Keeping this dependency object separate from TransparentWindow prevents the
    router from reading arbitrary window internals. The composition root decides
    how UI actions map to application services and supplies only those actions.
    """

    host: Gtk.Widget
    get_current_mode: Callable[[], str]
    switch_mode: Callable[[str], bool]
    toggle_widget_transparency: Callable[[], bool]
    clear_selections: Callable[[], None]
    show_widget_creation_menu: Callable[[float, float], None]
    mode_controller: ModeController
    input_event_factory: "GtkInputEventFactory"
    event_handler_chain: "InputEventHandlerChain"
    event_bus: "EventBus"
    workspace_manager: "WorkspaceManager"


class WindowInputRouter:
    """Keeps GTK event controller callbacks out of the window object."""

    def __init__(self, dependencies: WindowInputRouterDependencies) -> None:
        self._dependencies = dependencies

    def install(self) -> None:
        key_controller = Gtk.EventControllerKey.new()
        key_controller.connect("key-pressed", self.on_global_key_press)
        key_controller.connect("key-released", self.on_global_key_release)
        self._dependencies.host.add_controller(key_controller)

        scroll_controller = Gtk.EventControllerScroll.new(
            flags=Gtk.EventControllerScrollFlags.BOTH_AXES
        )
        scroll_controller.connect("scroll-begin", self.on_window_mouse_scroll)
        scroll_controller.connect("scroll", self.on_window_mouse_scroll)
        scroll_controller.connect("scroll-end", self.on_window_mouse_scroll)
        self._dependencies.host.add_controller(scroll_controller)

        click_controller = Gtk.EventControllerLegacy()
        click_controller.connect("event", self.on_window_mouse_event)
        self._dependencies.host.add_controller(click_controller)

        click_edit_controller = Gtk.GestureClick()
        click_edit_controller.set_button(0)
        click_edit_controller.connect("pressed", self.on_window_mouse_pressed)
        click_edit_controller.connect("released", self.on_window_mouse_released)
        self._dependencies.host.add_controller(click_edit_controller)

        motion_controller = Gtk.EventControllerMotion.new()
        motion_controller.connect("motion", self.on_window_mouse_motion)
        self._dependencies.host.add_controller(motion_controller)

        zoom_controller = Gtk.GestureZoom()
        zoom_controller.connect(
            "begin", partial(self.on_window_mouse_zoom, status="begin")
        )
        zoom_controller.connect(
            "scale-changed",
            partial(self.on_window_mouse_zoom, status="scale-changed"),
        )
        zoom_controller.connect("end", partial(self.on_window_mouse_zoom, status="end"))
        self._dependencies.host.add_controller(zoom_controller)

    def on_window_mouse_event(self, controller, event):
        if self._dependencies.get_current_mode() != ModeController.MAPPING_MODE:
            return False

        input_event = self._dependencies.input_event_factory.create_mouse_button_event(
            controller,
            event,
        )
        if input_event is None:
            return False

        return bool(self._dependencies.event_handler_chain.process_event(input_event))

    def on_window_mouse_pressed(self, controller, n_press, x, y):
        if self._dependencies.get_current_mode() == ModeController.MAPPING_MODE:
            return False

        button = controller.get_current_button()
        if button == Gdk.BUTTON_SECONDARY:
            widget_at_position = self._dependencies.workspace_manager.get_widget_at_position(
                x, y
            )
            if not widget_at_position:
                self._dependencies.show_widget_creation_menu(x, y)
                return None

            local_x, local_y = self._dependencies.workspace_manager.global_to_local_coords(
                widget_at_position,
                x,
                y,
            )
            capabilities.notify_right_click(widget_at_position, local_x, local_y)
            return None

        if button == Gdk.BUTTON_PRIMARY:
            self._dependencies.workspace_manager.handle_primary_press(n_press, x, y)

    def on_window_mouse_motion(self, controller, x, y):
        if self._dependencies.get_current_mode() == ModeController.MAPPING_MODE:
            input_event = self._dependencies.input_event_factory.create_mouse_motion_event(
                controller,
                x,
                y,
            )
            if input_event is None:
                return False

            self._dependencies.event_bus.emit(
                Event(EventType.MOUSE_MOTION, self._dependencies.host, input_event)
            )
            self._dependencies.event_handler_chain.process_event(input_event)
            return True

        self._dependencies.workspace_manager.handle_pointer_motion(x, y)

    def on_window_mouse_scroll(
        self,
        controller: Gtk.EventControllerScroll,
        dx: float | None = None,
        dy: float | None = None,
    ):
        if self._dependencies.get_current_mode() == ModeController.MAPPING_MODE:
            input_event = self._dependencies.input_event_factory.create_scroll_event(
                controller,
                dx,
                dy,
            )
            self._dependencies.event_handler_chain.process_event(input_event)

    def on_window_mouse_zoom(self, controller, zoom, status: str):
        input_event = self._dependencies.input_event_factory.create_zoom_event(
            controller,
            zoom,
            status,
        )
        self._dependencies.event_handler_chain.process_event(input_event)

    def on_window_mouse_released(self, controller, n_press, x, y):
        if self._dependencies.get_current_mode() == ModeController.MAPPING_MODE:
            return False
        self._dependencies.workspace_manager.handle_pointer_release()

    def on_global_key_press(self, controller, keyval, keycode, state):
        current_mode = self._dependencies.get_current_mode()
        if self._dependencies.mode_controller.is_mode_switch_key(keyval):
            self._dependencies.switch_mode(
                self._dependencies.mode_controller.toggle(current_mode)
            )
            return True

        if self._is_mapping_transparency_toggle_key(keyval):
            self._dependencies.toggle_widget_transparency()
            return True

        if current_mode == ModeController.MAPPING_MODE:
            input_event = self._dependencies.input_event_factory.create_key_event(
                InputEventType.KEY_PRESS,
                controller,
                keyval,
                keycode,
                state,
            )
            if input_event is not None:
                handled = self._dependencies.event_handler_chain.process_event(input_event)
                if handled:
                    return True

        if keyval == Gdk.KEY_Escape:
            if current_mode == ModeController.EDIT_MODE:
                self._dependencies.clear_selections()
            return True

        if current_mode == ModeController.EDIT_MODE and keyval == Gdk.KEY_Delete:
            self._dependencies.workspace_manager.delete_selected_widgets()
            return True

        return False

    def on_global_key_release(self, controller, keyval, keycode, state):
        if self._dependencies.get_current_mode() != ModeController.MAPPING_MODE:
            return False

        if self._is_mapping_transparency_toggle_key(keyval):
            return True

        input_event = self._dependencies.input_event_factory.create_key_event(
            InputEventType.KEY_RELEASE,
            controller,
            keyval,
            keycode,
            state,
        )
        if input_event is not None:
            handled = self._dependencies.event_handler_chain.process_event(input_event)
            if handled:
                return True

        return False

    def _is_mapping_transparency_toggle_key(self, keyval: int) -> bool:
        return (
            self._dependencies.get_current_mode() == ModeController.MAPPING_MODE
            and keyval == Gdk.KEY_F12
        )
