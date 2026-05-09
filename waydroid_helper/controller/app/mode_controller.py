#!/usr/bin/env python3
"""Controller mode transitions."""

from __future__ import annotations

from gettext import gettext as _
from typing import Callable, Iterable

from gi.repository import Gdk

from waydroid_helper.controller.app import widget_capabilities as capabilities
from waydroid_helper.controller.core.constants import APP_TITLE
from waydroid_helper.controller.core.event_bus import Event, EventBus, EventType


class ModeController:
    """Applies mode-specific UI and widget state changes."""

    EDIT_MODE = "edit"
    MAPPING_MODE = "mapping"

    def __init__(
        self,
        *,
        window,
        event_bus: EventBus,
        iter_widgets: Callable[[], Iterable[object]],
        clear_selections: Callable[[], None],
        restore_widget_opacity: Callable[[], bool],
        notify: Callable[[str], None],
    ) -> None:
        self.window = window
        self.event_bus = event_bus
        self.iter_widgets = iter_widgets
        self.clear_selections = clear_selections
        self.restore_widget_opacity = restore_widget_opacity
        self.notify = notify

    def apply_mode(self, new_mode: str) -> None:
        mapping_mode = new_mode == self.MAPPING_MODE
        for child in self.iter_widgets():
            capabilities.set_mapping_mode(child, mapping_mode)

        if new_mode == self.MAPPING_MODE:
            self.clear_selections()
            self.notify(_("Mapping Mode (F1: Switch Mode)"))
            self.window.set_title(f"{APP_TITLE} - Mapping Mode (F1: Switch Mode)")
            self.window.set_cursor_from_name("default")
            return

        self.restore_widget_opacity()
        self.notify(_("Edit Mode (F1: Switch Mode)"))
        self.window.set_title(f"{APP_TITLE} - Edit Mode (F1: Switch Mode)")
        self.event_bus.emit(Event(EventType.EXIT_STARING, self.window, None))

    def toggle(self, current_mode: str) -> str:
        return self.MAPPING_MODE if current_mode == self.EDIT_MODE else self.EDIT_MODE

    def is_mode_switch_key(self, keyval: int) -> bool:
        return keyval == Gdk.KEY_F1
