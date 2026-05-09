#!/usr/bin/env python3
"""Key mapping registration support for editable widgets."""

from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from waydroid_helper.util.log import logger

if TYPE_CHECKING:
    from gi.repository import Gtk
    from waydroid_helper.controller.core.key_system import KeyCombination
    from waydroid_helper.controller.widgets.base.base_widget import EditableRegion


class EditableKeyMappingRegistrar:
    """Keeps window key-mapping collaboration out of the GTK decorator.

    EditableDecorator owns GTK controllers and capture flow. This helper owns
    the cross-component mapping side effects, so missing window services and
    subscription failures are logged in one place instead of being silently
    swallowed by the decorator.
    """

    def __init__(
        self,
        widget: Any,
        get_toplevel_window: Callable[[], "Gtk.Window | None"],
    ) -> None:
        self._widget = widget
        self._get_toplevel_window = get_toplevel_window

    def update_global_mapping(self) -> None:
        """Refresh mappings after deleting the current captured key."""
        try:
            key_mapping_manager = self._get_key_mapping_manager()
            if key_mapping_manager is None:
                logger.warning(
                    "Skip global mapping update for %s: no key mapping manager",
                    type(self._widget).__name__,
                )
                return

            key_mapping_manager.unsubscribe(self._widget)

            if self._widget.final_keys:
                for key_combination in self._widget.final_keys:
                    key_mapping_manager.subscribe(self._widget, key_combination)
                    logger.debug(f"Update global mapping: {key_combination}")
            else:
                logger.debug("Clear global mapping (no keys)")

        except Exception:
            logger.exception("Error updating global mapping")

    def register_widget_mappings(self) -> None:
        """Register the final keys captured by a single-region widget."""
        try:
            key_mapping_manager = self._get_key_mapping_manager()
            if key_mapping_manager is None:
                logger.warning(
                    "Skip key mapping registration for %s: no key mapping manager",
                    type(self._widget).__name__,
                )
                return

            key_mapping_manager.unsubscribe(self._widget)

            for key_combination in self._widget.final_keys:
                success = key_mapping_manager.subscribe(
                    self._widget,
                    key_combination,
                )
                if success:
                    reentrant = key_mapping_manager.get_target_reentrant(self._widget)
                    logger.debug(
                        "Successfully register key mapping: %s -> %s "
                        "(reentrant=%s)",
                        key_combination,
                        type(self._widget).__name__,
                        reentrant,
                    )
                else:
                    logger.debug(f"Failed to register key mapping: {key_combination}")

        except Exception:
            logger.exception("Error registering key mapping")

    def register_region_mappings(
        self,
        region: "EditableRegion",
        original_keys: set["KeyCombination"],
    ) -> None:
        """Replace old region-specific subscriptions with current keys."""
        try:
            key_mapping_manager = self._get_key_mapping_manager()
            if key_mapping_manager is None:
                logger.warning(
                    "Skip region key mapping registration for %s: "
                    "no key mapping manager",
                    type(self._widget).__name__,
                )
                return

            for old_key_combination in original_keys:
                key_mapping_manager.unsubscribe_key(self._widget, old_key_combination)
                logger.debug(
                    "Cancel region %s old key mapping: %s",
                    region["id"],
                    old_key_combination,
                )

            current_keys = region["get_keys"]()
            if not current_keys:
                logger.debug(
                    "Region %s has no keys, skip mapping registration",
                    region["id"],
                )
                return

            for key_combination in current_keys:
                success = key_mapping_manager.subscribe(
                    self._widget,
                    key_combination,
                )
                if success:
                    reentrant = key_mapping_manager.get_target_reentrant(self._widget)
                    logger.debug(
                        "Successfully register region key mapping: %s -> %s[%s] "
                        "(reentrant=%s)",
                        key_combination,
                        type(self._widget).__name__,
                        region["id"],
                        reentrant,
                    )
                else:
                    logger.debug(
                        "Failed to register region key mapping: %s",
                        key_combination,
                    )

        except Exception:
            logger.exception("Error registering region key mapping")

    def _get_key_mapping_manager(self):
        window = self._get_toplevel_window()
        if window is None:
            return None
        try:
            return window.key_mapping_manager
        except AttributeError:
            logger.warning(
                "Top-level window %s has no key_mapping_manager",
                type(window).__name__,
            )
            return None
