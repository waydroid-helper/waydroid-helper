#!/usr/bin/env python3
"""Registers key mappings exposed by controller widgets."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from waydroid_helper.controller.app import widget_capabilities as capabilities

if TYPE_CHECKING:
    from waydroid_helper.controller.core.key_system import KeyCombination


RegisterKeyMapping = Callable[[Any, "KeyCombination"], bool]


class WidgetMappingRegistrar:
    """Translate widget-declared mappings into key mapping subscriptions.

    The window owns placement and lifecycle wiring. This registrar owns the
    policy for discovering whether a widget exposes many directional mappings
    or traditional ``final_keys`` mappings, keeping those widget-shape details
    out of the window.
    """

    def __init__(self, register_key_mapping: RegisterKeyMapping):
        self._register_key_mapping = register_key_mapping

    def register_widget(self, widget: Any) -> int:
        key_mappings = capabilities.get_all_key_mappings(widget)
        if key_mappings is not None:
            return self._register_multi_key_widget(widget, key_mappings)

        return self._register_single_key_widget(widget)

    def _register_multi_key_widget(self, widget: Any, key_mappings) -> int:
        registered_count = 0
        for key_combination in key_mappings:
            if self._register_key_mapping(widget, key_combination):
                registered_count += 1
        return registered_count

    def _register_single_key_widget(self, widget: Any) -> int:
        registered_count = 0
        for key_combination in capabilities.get_final_key_mappings(widget):
            if self._register_key_mapping(widget, key_combination):
                registered_count += 1
                capabilities.set_text_if_empty(widget, str(key_combination))
        return registered_count
