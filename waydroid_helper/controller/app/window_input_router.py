#!/usr/bin/env python3
"""GTK controller wiring and input dispatch for TransparentWindow."""

from __future__ import annotations

from functools import partial

from gi.repository import Gdk, Gtk

from waydroid_helper.controller.app import widget_capabilities as capabilities
from waydroid_helper.controller.core.event_bus import Event, EventType
from waydroid_helper.controller.core.handler.event_handlers import InputEventType


class WindowInputRouter:
    """Keeps GTK event controller callbacks out of the window object."""

    def __init__(self, window) -> None:
        self.window = window

    def install(self) -> None:
        key_controller = Gtk.EventControllerKey.new()
        key_controller.connect("key-pressed", self.on_global_key_press)
        key_controller.connect("key-released", self.on_global_key_release)
        self.window.add_controller(key_controller)

        scroll_controller = Gtk.EventControllerScroll.new(
            flags=Gtk.EventControllerScrollFlags.BOTH_AXES
        )
        scroll_controller.connect("scroll-begin", self.on_window_mouse_scroll)
        scroll_controller.connect("scroll", self.on_window_mouse_scroll)
        scroll_controller.connect("scroll-end", self.on_window_mouse_scroll)
        self.window.add_controller(scroll_controller)

        click_controller = Gtk.EventControllerLegacy()
        click_controller.connect("event", self.on_window_mouse_event)
        self.window.add_controller(click_controller)

        click_edit_controller = Gtk.GestureClick()
        click_edit_controller.set_button(0)
        click_edit_controller.connect("pressed", self.on_window_mouse_pressed)
        click_edit_controller.connect("released", self.on_window_mouse_released)
        self.window.add_controller(click_edit_controller)

        motion_controller = Gtk.EventControllerMotion.new()
        motion_controller.connect("motion", self.on_window_mouse_motion)
        self.window.add_controller(motion_controller)

        zoom_controller = Gtk.GestureZoom()
        zoom_controller.connect(
            "begin", partial(self.on_window_mouse_zoom, status="begin")
        )
        zoom_controller.connect(
            "scale-changed",
            partial(self.on_window_mouse_zoom, status="scale-changed"),
        )
        zoom_controller.connect("end", partial(self.on_window_mouse_zoom, status="end"))
        self.window.add_controller(zoom_controller)

    def on_window_mouse_event(self, controller, event):
        if self.window.current_mode != self.window.MAPPING_MODE:
            return False

        input_event = self.window.input_event_factory.create_mouse_button_event(
            controller,
            controller.get_current_event(),
        )
        if input_event is None:
            return False

        return bool(self.window.event_handler_chain.process_event(input_event))

    def on_window_mouse_pressed(self, controller, n_press, x, y):
        if self.window.current_mode == self.window.MAPPING_MODE:
            return False

        button = controller.get_current_button()
        if button == Gdk.BUTTON_SECONDARY:
            widget_at_position = self.window.workspace_manager.get_widget_at_position(
                x, y
            )
            if not widget_at_position:
                self.window.menu_manager.show_widget_creation_menu(
                    x,
                    y,
                    self.window.widget_factory,
                )
                return None

            local_x, local_y = self.window.workspace_manager.global_to_local_coords(
                widget_at_position,
                x,
                y,
            )
            capabilities.notify_right_click(widget_at_position, local_x, local_y)
            return None

        if button == Gdk.BUTTON_PRIMARY:
            self.window.workspace_manager.handle_primary_press(n_press, x, y)

    def on_window_mouse_motion(self, controller, x, y):
        if self.window.current_mode == self.window.MAPPING_MODE:
            input_event = self.window.input_event_factory.create_mouse_motion_event(
                controller,
                x,
                y,
            )
            if input_event is None:
                return False

            self.window.event_bus.emit(
                Event(EventType.MOUSE_MOTION, self.window, input_event)
            )
            self.window.event_handler_chain.process_event(input_event)
            return True

        self.window.workspace_manager.handle_pointer_motion(x, y)

    def on_window_mouse_scroll(
        self,
        controller: Gtk.EventControllerScroll,
        dx: float | None = None,
        dy: float | None = None,
    ):
        if self.window.current_mode == self.window.MAPPING_MODE:
            input_event = self.window.input_event_factory.create_scroll_event(
                controller,
                dx,
                dy,
            )
            self.window.event_handler_chain.process_event(input_event)

    def on_window_mouse_zoom(self, controller, zoom, status: str):
        input_event = self.window.input_event_factory.create_zoom_event(
            controller,
            zoom,
            status,
        )
        self.window.event_handler_chain.process_event(input_event)

    def on_window_mouse_released(self, controller, n_press, x, y):
        if self.window.current_mode == self.window.MAPPING_MODE:
            return False
        self.window.workspace_manager.handle_pointer_release()

    def on_global_key_press(self, controller, keyval, keycode, state):
        if self.window.mode_controller.is_mode_switch_key(keyval):
            self.window.switch_mode(
                self.window.mode_controller.toggle(self.window.current_mode)
            )
            return True

        if self.window.current_mode == self.window.MAPPING_MODE:
            input_event = self.window.input_event_factory.create_key_event(
                InputEventType.KEY_PRESS,
                controller,
                keyval,
                keycode,
                state,
            )
            if input_event is not None:
                handled = self.window.event_handler_chain.process_event(input_event)
                if handled:
                    return True

        if keyval == Gdk.KEY_Escape:
            if self.window.current_mode == self.window.EDIT_MODE:
                self.window.clear_all_selections()
            return True

        if self.window.current_mode == self.window.EDIT_MODE and keyval == Gdk.KEY_Delete:
            self.window.workspace_manager.delete_selected_widgets()
            return True

        return False

    def on_global_key_release(self, controller, keyval, keycode, state):
        if self.window.current_mode != self.window.MAPPING_MODE:
            return False

        input_event = self.window.input_event_factory.create_key_event(
            InputEventType.KEY_RELEASE,
            controller,
            keyval,
            keycode,
            state,
        )
        if input_event is not None:
            handled = self.window.event_handler_chain.process_event(input_event)
            if handled:
                return True

        return False
