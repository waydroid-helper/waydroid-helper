#!/usr/bin/env python3
"""State machine for editable widget key capture sessions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

from waydroid_helper.controller.core.key_system import Key, KeyCombination
from waydroid_helper.util.log import logger

if TYPE_CHECKING:
    from waydroid_helper.controller.widgets.base.base_widget import (
        BaseWidget,
        EditableRegion,
    )


CAPTURE_HINT_TEXT = "Press keys to capture"


@dataclass(slots=True)
class EditableFinishResult:
    """Describes mapping side effects requested when editing finishes."""

    region: "EditableRegion | None" = None
    original_keys: set[KeyCombination] | None = None
    register_widget_mappings: bool = False


class EditableCaptureSession:
    """Owns key-capture state independent from GTK event wiring."""

    def __init__(self, max_keys: int) -> None:
        self.max_keys = max_keys
        self.is_editing = False
        self.original_text = ""
        self.current_edit_region: EditableRegion | None = None
        self.original_keys: set[KeyCombination] = set()
        self.realtime_keys: set[Key] = set()

    def should_keep_editing_on_click(
        self,
        widget: "BaseWidget",
        x: float,
        y: float,
    ) -> bool:
        if not self.is_editing:
            return False

        logger.debug(
            "Query if should keep editing: position(%.1f, %.1f), editing: %s",
            x,
            y,
            self.is_editing,
        )

        if self.current_edit_region:
            clicked_region = widget.get_region_at_position(x, y)
            logger.debug(
                "Current edit region: %s, clicked region: %s",
                self.current_edit_region["id"],
                clicked_region["id"] if clicked_region else "None",
            )
            if clicked_region and clicked_region["id"] == self.current_edit_region["id"]:
                logger.debug("Clicked current edit region %s, keep editing", clicked_region["id"])
                return True

            logger.debug("Clicked other region, should exit editing")
            return False

        logger.debug("Traditional editing mode, clicked widget internal, should keep editing")
        return True

    def begin_widget_editing(self, widget: "BaseWidget") -> bool:
        if self.is_editing:
            return False

        logger.debug("Start key capture: '%s'", widget.text)

        self.is_editing = True
        self.current_edit_region = None
        self.original_text = widget.text or ""
        self.original_keys = set(widget.final_keys)
        self.realtime_keys = set()

        if not widget.final_keys and not self.original_text:
            widget.text = CAPTURE_HINT_TEXT
            logger.debug("Show capture hint text")

        return True

    def begin_region_editing(
        self,
        widget: "BaseWidget",
        region: "EditableRegion",
    ) -> bool:
        if self.is_editing:
            return False

        logger.debug(
            "Start region key capture: %s (%s)",
            region["name"],
            region["id"],
        )

        self.is_editing = True
        self.current_edit_region = region
        self.original_keys = set(region["get_keys"]())
        self.original_text = widget.text
        self.realtime_keys = set()
        return True

    def capture_key(self, widget: "BaseWidget", key: Key) -> None:
        if len(self.realtime_keys) >= self.max_keys:
            removed_key = next(iter(self.realtime_keys))
            self.realtime_keys.remove(removed_key)
            logger.debug("Real-time set is full, remove oldest key: %s", removed_key)

        self.realtime_keys.add(key)
        logger.debug(
            "Add key to real-time set: %s, current real-time set: %s",
            key,
            [str(k) for k in self.realtime_keys],
        )
        self._update_final_capture(widget)

    def release_key(self, widget: "BaseWidget", key: Key) -> bool:
        if key not in self.realtime_keys:
            return False

        self.realtime_keys.remove(key)
        logger.debug(
            "Remove key from real-time set: %s, current real-time set: %s",
            key,
            [str(k) for k in self.realtime_keys],
        )
        self._update_display(widget)
        return True

    def remove_last_final_key(self, widget: "BaseWidget") -> KeyCombination | None:
        if not widget.final_keys:
            return None

        removed_combination = widget.final_keys.pop()
        self._update_display(widget)
        logger.debug("Delete key combination: %s", removed_combination)
        return removed_combination

    def finish(
        self,
        widget: "BaseWidget",
        apply_changes: bool = True,
    ) -> EditableFinishResult | None:
        if not self.is_editing:
            return None

        self.is_editing = False
        if self.current_edit_region:
            return self._finish_region_editing(widget, apply_changes)
        return self._finish_widget_editing(widget, apply_changes)

    def _finish_region_editing(
        self,
        widget: "BaseWidget",
        apply_changes: bool,
    ) -> EditableFinishResult:
        region = self.current_edit_region
        original_keys = set(self.original_keys)

        if region is not None:
            if not apply_changes:
                logger.debug("Cancel region %s key capture", region["id"])
                region["set_keys"](set(original_keys))
            else:
                logger.debug("Region %s key capture completed", region["id"])

        self.current_edit_region = None
        self.original_keys = set()
        self.realtime_keys = set()
        widget.queue_draw()

        if apply_changes and region is not None:
            return EditableFinishResult(region=region, original_keys=original_keys)
        return EditableFinishResult()

    def _finish_widget_editing(
        self,
        widget: "BaseWidget",
        apply_changes: bool,
    ) -> EditableFinishResult:
        current_text = widget.text
        register_widget_mappings = False

        if not apply_changes:
            logger.debug(
                "Cancel key capture: '%s' -> '%s'",
                current_text,
                self.original_text,
            )
            widget.text = self.original_text
            widget.final_keys = self.original_keys.copy()
        else:
            logger.debug(
                "Key capture completed: '%s' -> '%s'",
                self.original_text,
                current_text,
            )
            logger.debug("Final captured keys: %s", widget.final_keys)

            if not widget.final_keys and current_text == CAPTURE_HINT_TEXT:
                widget.text = ""
                logger.debug("No keys captured, restore empty text")

            register_widget_mappings = bool(widget.final_keys)

        self.realtime_keys = set()
        widget.queue_draw()
        return EditableFinishResult(register_widget_mappings=register_widget_mappings)

    def _update_final_capture(self, widget: "BaseWidget") -> None:
        if self.realtime_keys:
            current_combination = KeyCombination(list(self.realtime_keys))

            if self.current_edit_region:
                self.current_edit_region["set_keys"]({current_combination})
                logger.debug(
                    "Update region %s keys: %s",
                    self.current_edit_region["id"],
                    current_combination,
                )
            else:
                widget.final_keys = {current_combination}
                logger.debug("Update final capture: %s", current_combination)

        self._update_display(widget)

    def _update_display(self, widget: "BaseWidget") -> None:
        if widget.final_keys:
            first_combination = next(iter(widget.final_keys))
            widget.text = str(first_combination)
        elif self.is_editing:
            widget.text = CAPTURE_HINT_TEXT
        else:
            widget.text = ""
