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
        self.held_keys: dict[Key, None] = {}

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
        self.held_keys.clear()

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
        widget.capture_preview = None
        self.held_keys.clear()
        return True

    def capture_key(self, widget: "BaseWidget", key: Key) -> None:
        kind = getattr(widget, "profile_kind", None)
        if kind and key.name.startswith("Pad_") != (kind == "gamepad"):
            return
        if key in self.held_keys:
            return  # Auto-repeat does not start a new chord.

        # Track all physical presses until their releases. For a bounded
        # chord, keep the first held prefix and the newest input. A one-key
        # direction cell therefore takes just the newest key, while Ctrl,
        # Shift, M in a two-key cell displays Ctrl+M.
        prefix = list(self.held_keys)[: self.max_keys - 1]
        self.held_keys[key] = None
        combination = KeyCombination([*prefix, key])
        if self.current_edit_region is not None:
            widget.capture_preview = combination
        else:
            widget.final_keys = {combination}
            self._update_display(widget)

    def release_key(self, widget: "BaseWidget", key: Key) -> EditableFinishResult | None:
        if key not in self.held_keys:
            return None
        del self.held_keys[key]
        if self.current_edit_region is not None and not self.held_keys:
            return self._commit_region_chord(widget)
        return None

    def _commit_region_chord(self, widget: "BaseWidget") -> EditableFinishResult | None:
        """Accept one gesture without taking focus away from its keycap.

        A paired control may move a binding from its opposite row. Only
        publish the complete chord, never an intermediate modifier. A later
        press in this same field starts a replacement for that binding.
        """
        region = self.current_edit_region
        combo = widget.capture_preview
        widget.capture_preview = None
        if region is None or combo is None:
            return None
        previous = set(region["get_keys"]())
        if previous == {combo}:
            return None
        region["set_keys"]({combo})
        self._update_display(widget)
        return EditableFinishResult(region=region, original_keys=previous)

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
        result = self._commit_region_chord(widget) if apply_changes else None
        widget.capture_preview = None
        self.current_edit_region = None
        self.original_keys.clear()
        self.held_keys.clear()
        widget.queue_draw()
        return result or EditableFinishResult()

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

        self.held_keys.clear()
        widget.queue_draw()
        return EditableFinishResult(register_widget_mappings=register_widget_mappings)

    def _update_display(self, widget: "BaseWidget") -> None:
        if widget.final_keys:
            first_combination = next(iter(widget.final_keys))
            widget.text = first_combination.display_text
        elif self.is_editing:
            widget.text = CAPTURE_HINT_TEXT
        else:
            widget.text = ""
