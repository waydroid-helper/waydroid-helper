#!/usr/bin/env python3
"""Dynamic context menu UI."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from gettext import gettext as _
from typing import Any, Protocol

import gi
from gi.repository import Gdk, Gtk

from waydroid_helper.controller.ui.layout_file_actions import LayoutFileActions
from waydroid_helper.util.log import logger

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")


class WidgetSource(Protocol):
    def iter_widgets(self) -> Iterable[Any]: ...


class ContextMenuHost(Protocol):
    workspace_manager: WidgetSource

    def create_widget_at_position(self, widget: Any, x: int, y: int) -> None: ...

    def attach_widget_at_position(self, widget: Any, x: float, y: float) -> None: ...

    def on_clear_widgets(self, button: Gtk.Button | None) -> None: ...

    def begin_swipe_placement(self, widget: Any) -> None: ...


class WidgetFactoryView(Protocol):
    widget_classes: dict[str, type[Any]]

    def get_available_types(self) -> list[str]: ...

    def get_widget_metadata(self, widget_type: str) -> dict[str, Any]: ...

    def create_widget(self, widget_type: str, **kwargs: Any) -> Any | None: ...

    def reload_widgets(self) -> None: ...

    def print_discovered_widgets(self) -> None: ...


class WidgetLayoutOperations(Protocol):
    def save_layout(self, file_path: str, widgets: Iterable[Any]) -> None: ...

    def load_layout(
        self,
        file_path: str,
        widget_factory: WidgetFactoryView,
        clear_widgets: Callable[[], None],
        create_widget_at_position: Callable[[Any, int, int], None],
    ) -> int: ...


EMBEDDED_CONTROL_ICONS = {
    "singleclick": "mapping-tap-symbolic",
    "repeatedclick": "mapping-repeat-tap-symbolic",
    "triggerslider": "mapping-trigger-slider-symbolic",
    "dualstagetrigger": "mapping-dual-stage-symbolic",
    "swipe": "mapping-swipe-symbolic",
    "directionalpad": "mapping-d-pad-symbolic",
    "analogstick": "mapping-left-stick-symbolic",
    "rightstick": "mapping-right-stick-symbolic",
    "aim": "find-location-symbolic",
    "fire": "mapping-fire-symbolic",
    "scroll": "mapping-scroll-symbolic",
    "pinch": "mapping-pinch-symbolic",
    "rightclicktowalk": "mapping-right-click-symbolic",
    "macro": "mapping-macro-symbolic",
    "recordedaction": "mapping-recorded-action-symbolic",
    "gamepadskillcasting": "mapping-cast-symbolic",
    "skillcasting": "mapping-cast-symbolic",
}


class ContextMenuManager:
    """Builds the context popover and delegates non-UI work to services."""

    def __init__(
        self,
        parent_window: ContextMenuHost,
        layout_service: WidgetLayoutOperations,
        file_actions: LayoutFileActions,
        anchor=None,
    ):
        self.parent_window = parent_window
        self.layout_service = layout_service
        self.file_actions = file_actions
        self.anchor = anchor or parent_window
        self._popover: "Gtk.Popover | None" = None
        self._main_box: "Gtk.Box | None" = None
        self._flow_box: "Gtk.FlowBox | None" = None
        self._tool_flow: "Gtk.FlowBox | None" = None

    def show_widget_creation_menu(
        self, x: int, y: int, widget_factory: WidgetFactoryView
    ):
        if self._popover is None:
            self._create_popover()

        self._update_menu_content(x, y, widget_factory)

        rect = Gdk.Rectangle()
        rect.x = int(x)
        rect.y = int(y)
        rect.width = 1
        rect.height = 1
        self._popover.set_pointing_to(rect)
        self._popover.popup()

    def _create_popover(self) -> None:
        self._popover = Gtk.Popover()
        self._popover.set_parent(self.anchor)
        self._popover.set_has_arrow(False)
        self._popover.set_autohide(True)

        self._main_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        self._popover.set_child(self._main_box)

        scrolled = Gtk.ScrolledWindow()
        scrolled.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
        scrolled.set_max_content_height(300)
        scrolled.set_max_content_width(400)
        scrolled.set_propagate_natural_height(True)
        scrolled.set_propagate_natural_width(True)
        self._main_box.append(scrolled)

        self._flow_box = Gtk.FlowBox()
        self._flow_box.set_orientation(Gtk.Orientation.HORIZONTAL)
        self._flow_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self._flow_box.set_column_spacing(4)
        self._flow_box.set_row_spacing(4)
        self._flow_box.set_margin_top(8)
        self._flow_box.set_margin_bottom(8)
        self._flow_box.set_margin_start(8)
        self._flow_box.set_margin_end(8)
        self._flow_box.set_min_children_per_line(2)
        self._flow_box.set_max_children_per_line(4)
        scrolled.set_child(self._flow_box)

        if getattr(self.parent_window, "embedded", False):
            return

        separator = Gtk.Separator(orientation=Gtk.Orientation.HORIZONTAL)
        separator.set_margin_top(4)
        separator.set_margin_bottom(4)
        self._main_box.append(separator)

        tool_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        tool_box.set_margin_top(4)
        tool_box.set_margin_bottom(8)
        tool_box.set_margin_start(8)
        tool_box.set_margin_end(8)
        self._main_box.append(tool_box)

        self._tool_flow = Gtk.FlowBox()
        self._tool_flow.set_orientation(Gtk.Orientation.HORIZONTAL)
        self._tool_flow.set_selection_mode(Gtk.SelectionMode.NONE)
        self._tool_flow.set_column_spacing(4)
        self._tool_flow.set_row_spacing(4)
        self._tool_flow.set_min_children_per_line(3)
        self._tool_flow.set_max_children_per_line(5)
        tool_box.append(self._tool_flow)

    def _clear_flow_box(self, flow_box: "Gtk.FlowBox | None") -> None:
        if flow_box is None:
            return
        child = flow_box.get_first_child()
        while child:
            next_child = child.get_next_sibling()
            flow_box.remove(child)
            child = next_child

    def _update_menu_content(
        self, x: int, y: int, widget_factory: WidgetFactoryView
    ) -> None:
        self._clear_flow_box(self._flow_box)
        self._clear_flow_box(self._tool_flow)

        if self._flow_box is None or self._popover is None:
            return

        self._populate_widget_buttons(x, y, widget_factory)
        if not getattr(self.parent_window, "embedded", False):
            self._populate_tool_buttons(widget_factory)

    def _populate_widget_buttons(
        self, x: int, y: int, widget_factory: WidgetFactoryView
    ) -> None:
        filtered_types = []
        for widget_type in widget_factory.get_available_types():
            widget_class = widget_factory.widget_classes.get(widget_type)
            if getattr(self.parent_window, "embedded", False):
                from waydroid_helper.controller.app.mapping_profiles import (
                    supports_control,
                )

                if not supports_control(self.parent_window.profiles.kind, widget_type):
                    continue
            if getattr(widget_class, "EMBEDDED_ONLY", False) and not getattr(
                self.parent_window, "embedded", False
            ):
                continue
            if widget_class and getattr(
                widget_class,
                "ALLOW_CONTEXT_MENU_CREATION",
                True,
            ):
                filtered_types.append(widget_type)

        if self._flow_box is None:
            return

        if not filtered_types:
            label = Gtk.Label(label=_("No widgets found"))
            label.set_margin_top(20)
            label.set_margin_bottom(20)
            self._flow_box.append(label)
            return

        for widget_type in sorted(filtered_types):
            metadata = widget_factory.get_widget_metadata(widget_type)
            display_name = metadata.get("name", widget_type.title())
            button = Gtk.Button(label=str(display_name))
            if getattr(self.parent_window, "embedded", False):
                if (getattr(widget_factory.widget_classes[widget_type], "REQUIRES_ANALOG_TRIGGER", False)
                        and not self.parent_window.gamepad.available_triggers):
                    button.set_sensitive(False)
                    button.set_tooltip_text(_("Requires a controller with analog triggers"))
                content = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
                image = Gtk.Image.new_from_icon_name(
                    EMBEDDED_CONTROL_ICONS.get(widget_type, "input-gaming-symbolic")
                )
                image.set_pixel_size(24)
                content.append(image)
                content.append(
                    Gtk.Label(
                        label=str(display_name),
                        wrap=True,
                        justify=Gtk.Justification.CENTER,
                    )
                )
                button.set_child(content)
                button.add_css_class("flat")
                button.set_size_request(82, 54)
            else:
                button.set_size_request(100, 40)
            button.connect(
                "clicked",
                lambda btn, wtype=widget_type: [
                    self._create_widget_callback(wtype, x, y, widget_factory),
                    self._popover.popdown() if self._popover else None,
                ],
            )
            self._flow_box.append(button)

    def _populate_tool_buttons(self, widget_factory: WidgetFactoryView) -> None:
        if self._tool_flow is None:
            return

        tool_items = [
            (_("Refresh widgets"), lambda: self._refresh_widgets(widget_factory)),
            (_("Clear all"), self._clear_all_widgets),
            (_("Save layout"), self.save_layout),
            (_("Load layout"), lambda: self.load_layout(widget_factory)),
        ]

        for label, callback in tool_items:
            button = Gtk.Button(label=label)
            button.set_size_request(70, 35)
            button.connect(
                "clicked",
                lambda btn, cb=callback: [
                    cb(),
                    self._popover.popdown() if self._popover else None,
                ],
            )
            self._tool_flow.append(button)

    def _create_widget_callback(
        self, widget_type: str, x: int, y: int, widget_factory: WidgetFactoryView
    ) -> None:
        try:
            widget = widget_factory.create_widget(widget_type, x=x, y=y)
            if widget:
                if hasattr(widget, "set_recorded_path"):
                    self.parent_window.begin_swipe_placement(widget)
                    return
                if getattr(self.parent_window, "embedded", False):
                    width, height = (
                        self.parent_window.screen_geometry.get_host_resolution()
                    )
                    x = round(max(0, min(x - widget.width / 2, width - widget.width)))
                    y = round(
                        max(0, min(y - widget.height / 2, height - widget.height))
                    )
                self.parent_window.create_widget_at_position(widget, x, y)
                if getattr(self.parent_window, "embedded", False):
                    from waydroid_helper.controller.app import widget_capabilities

                    self.parent_window.workspace_manager.clear_all_selections()
                    widget_capabilities.set_selected(widget, True)
                    widget.grab_focus()
        except Exception:
            logger.exception("Error creating %s widget", widget_type)

    def _refresh_widgets(self, widget_factory: WidgetFactoryView) -> None:
        widget_factory.reload_widgets()
        widget_factory.print_discovered_widgets()

    def _clear_all_widgets(self) -> None:
        self.parent_window.on_clear_widgets(None)

    def save_layout(self) -> None:
        self.file_actions.save_layout(
            lambda path: self.layout_service.save_layout(
                path,
                self.parent_window.workspace_manager.iter_widgets(),
            )
        )

    def load_layout(self, widget_factory: WidgetFactoryView) -> None:
        self.file_actions.load_layout(
            lambda path: self.open_layout(path, widget_factory)
        )

    def open_layout(self, path: str, widget_factory: WidgetFactoryView) -> int:
        return self.layout_service.load_layout(
            path,
            widget_factory,
            lambda: self.parent_window.on_clear_widgets(None),
            self.parent_window.attach_widget_at_position,
        )
