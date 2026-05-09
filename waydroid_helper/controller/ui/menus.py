#!/usr/bin/env python3
"""Dynamic context menu UI."""

from __future__ import annotations

from gettext import gettext as _
from typing import TYPE_CHECKING

import gi
from gi.repository import Gdk, Gtk

from waydroid_helper.controller.app.widget_layout_service import WidgetLayoutService
from waydroid_helper.controller.ui.layout_file_actions import LayoutFileActions
from waydroid_helper.util.log import logger

gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")

if TYPE_CHECKING:
    from waydroid_helper.controller.app.window import TransparentWindow
    from waydroid_helper.controller.widgets.factory import WidgetFactory


class ContextMenuManager:
    """Builds the context popover and delegates non-UI work to services."""

    def __init__(
        self,
        parent_window: "TransparentWindow",
        layout_service: WidgetLayoutService,
        file_actions: LayoutFileActions,
    ):
        self.parent_window = parent_window
        self.layout_service = layout_service
        self.file_actions = file_actions
        self._popover: "Gtk.Popover | None" = None
        self._main_box: "Gtk.Box | None" = None
        self._flow_box: "Gtk.FlowBox | None" = None
        self._tool_flow: "Gtk.FlowBox | None" = None

    def show_widget_creation_menu(
        self, x: int, y: int, widget_factory: "WidgetFactory"
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
        self._popover.set_parent(self.parent_window)
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
        self, x: int, y: int, widget_factory: "WidgetFactory"
    ) -> None:
        self._clear_flow_box(self._flow_box)
        self._clear_flow_box(self._tool_flow)

        if self._flow_box is None or self._tool_flow is None or self._popover is None:
            return

        self._populate_widget_buttons(x, y, widget_factory)
        self._populate_tool_buttons(widget_factory)

    def _populate_widget_buttons(
        self, x: int, y: int, widget_factory: "WidgetFactory"
    ) -> None:
        filtered_types = []
        for widget_type in widget_factory.get_available_types():
            widget_class = widget_factory.widget_classes.get(widget_type)
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
            button.set_size_request(100, 40)
            button.connect(
                "clicked",
                lambda btn, wtype=widget_type: [
                    self._create_widget_callback(wtype, x, y, widget_factory),
                    self._popover.popdown() if self._popover else None,
                ],
            )
            self._flow_box.append(button)

    def _populate_tool_buttons(self, widget_factory: "WidgetFactory") -> None:
        if self._tool_flow is None:
            return

        tool_items = [
            (_("Refresh widgets"), lambda: self._refresh_widgets(widget_factory)),
            (_("Clear all"), self._clear_all_widgets),
            (_("Save layout"), self._save_layout),
            (_("Load layout"), lambda: self._load_layout(widget_factory)),
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
        self, widget_type: str, x: int, y: int, widget_factory: "WidgetFactory"
    ) -> None:
        try:
            widget = widget_factory.create_widget(widget_type, x=x, y=y)
            if widget:
                self.parent_window.create_widget_at_position(widget, x, y)
        except Exception:
            logger.exception("Error creating %s widget", widget_type)

    def _refresh_widgets(self, widget_factory: "WidgetFactory") -> None:
        widget_factory.reload_widgets()
        widget_factory.print_discovered_widgets()

    def _clear_all_widgets(self) -> None:
        self.parent_window.on_clear_widgets(None)

    def _save_layout(self) -> None:
        self.file_actions.save_layout(
            lambda path: self.layout_service.save_layout(
                path,
                self.parent_window.workspace_manager.iter_widgets(),
            )
        )

    def _load_layout(self, widget_factory: "WidgetFactory") -> None:
        self.file_actions.load_layout(
            lambda path: self.layout_service.load_layout(
                path,
                widget_factory,
                lambda: self.parent_window.on_clear_widgets(None),
                self.parent_window.create_widget_at_position,
            )
        )
