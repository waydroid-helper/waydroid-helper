#!/usr/bin/env python3
"""Widget settings popover presentation."""

from __future__ import annotations

import asyncio
from gettext import gettext as _

from gi.repository import Gdk, Gtk

from waydroid_helper.controller.core.event_bus import Event, EventBus, EventType


class WidgetSettingsPopoverPresenter:
    """Builds and tears down widget settings popovers."""

    def __init__(self, window, event_bus: EventBus) -> None:
        self.window = window
        self.event_bus = event_bus

    def show(self, widget, autohide: bool) -> None:
        popover = Gtk.Popover()
        popover.set_autohide(autohide)

        if not autohide:
            self._install_modal_mask(popover, widget)
        else:
            self._install_autohide_workaround(popover, widget)

        popover.set_parent(self.window)
        self._populate_content(popover, widget)
        self._point_to_settings_button(popover, widget)
        popover.popup()

    def _install_modal_mask(self, popover: Gtk.Popover, widget) -> None:
        overlay = self.window.get_content()
        if not isinstance(overlay, Gtk.Overlay):
            return

        mask_layer = Gtk.Box()
        mask_layer.set_hexpand(True)
        mask_layer.set_vexpand(True)
        mask_layer.set_name("mask-layer")
        mask_layer.set_visible(False)
        mask_layer.set_cursor_from_name("default")
        mask_layer.set_can_target(True)
        mask_layer.set_focusable(True)

        click_controller = Gtk.GestureClick()
        click_controller.set_button(0)

        def on_mask_clicked(controller, n_press, x, y):
            self.event_bus.emit(
                Event(EventType.MASK_CLICKED, self.window, {"x": int(x), "y": int(y)})
            )
            controller.set_state(Gtk.EventSequenceState.CLAIMED)
            return True

        click_controller.connect("pressed", on_mask_clicked)
        click_controller.connect("released", lambda c, n, x, y: True)
        mask_layer.add_controller(click_controller)

        disabled_controllers = self._disable_window_controllers()
        overlay.add_overlay(mask_layer)
        mask_layer.set_visible(True)
        mask_layer.grab_focus()

        async def on_popover_closed_with_mask(p):
            self._restore_window_controllers(disabled_controllers)
            if mask_layer.get_parent():
                overlay.remove_overlay(mask_layer)

            widget.get_config_manager().clear_ui_references()
            p.unparent()

        popover.connect(
            "closed",
            lambda p: asyncio.create_task(on_popover_closed_with_mask(p)),
        )

    def _disable_window_controllers(self):
        disabled_controllers = []
        for controller in self.window.observe_controllers():
            if isinstance(
                controller,
                (
                    Gtk.EventControllerKey,
                    Gtk.GestureClick,
                    Gtk.EventControllerMotion,
                    Gtk.EventControllerScroll,
                ),
            ):
                original_state = controller.get_propagation_phase()
                controller.set_propagation_phase(Gtk.PropagationPhase.NONE)
                disabled_controllers.append((controller, original_state))
        return disabled_controllers

    def _restore_window_controllers(self, disabled_controllers) -> None:
        for controller, original_state in disabled_controllers:
            controller.set_propagation_phase(original_state)

    def _install_autohide_workaround(self, popover: Gtk.Popover, widget) -> None:
        def workaround_popover_auto_hide(controller, n_press, x, y):
            if popover.get_visible() and popover.get_autohide():
                if x < 0 or y < 0 or x > popover.get_width() or y > popover.get_height():
                    popover.popdown()

        click_controller = Gtk.GestureClick()
        click_controller.connect("pressed", workaround_popover_auto_hide)
        popover.add_controller(click_controller)

        def on_popover_closed(p):
            widget.get_config_manager().clear_ui_references()
            p.unparent()
            self.window.queue_draw()

        popover.connect("closed", on_popover_closed)

    def _populate_content(self, popover: Gtk.Popover, widget) -> None:
        main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        main_box.set_size_request(250, -1)
        popover.set_child(main_box)

        title_label = Gtk.Label()
        title_label.set_markup(f"<b>{widget.WIDGET_NAME} {_('Settings')}</b>")
        title_label.set_halign(Gtk.Align.CENTER)
        main_box.append(title_label)

        config_manager = widget.get_config_manager()
        if not config_manager.configs:
            main_box.append(Gtk.Label(label=_("This widget has no settings.")))
            return

        main_box.append(config_manager.create_ui_panel())
        confirm_button = Gtk.Button(label=_("OK"), halign=Gtk.Align.END)
        confirm_button.add_css_class("suggested-action")

        def on_confirm_clicked(btn):
            config_manager.emit("confirmed")
            popover.popdown()

        confirm_button.connect("clicked", on_confirm_clicked)
        main_box.append(confirm_button)

    def _point_to_settings_button(self, popover: Gtk.Popover, widget) -> None:
        settings_button_rect = Gdk.Rectangle()
        bounds = widget.get_settings_button_bounds()
        settings_button_rect.x = bounds[0] + widget.x
        settings_button_rect.y = bounds[1] + widget.y
        settings_button_rect.width = bounds[2]
        settings_button_rect.height = bounds[3]
        popover.set_pointing_to(settings_button_rect)
        popover.set_position(Gtk.PositionType.BOTTOM)
