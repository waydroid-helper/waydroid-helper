#!/usr/bin/env python3
"""Batch widget opacity policy for mapping mode visibility shortcuts."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from waydroid_helper.controller.app import widget_capabilities as capabilities


class WidgetTransparencyController:
    """Own transparent/normal widget state independently of input routing.

    Mapping mode owns the shortcut, but opacity is a cross-widget presentation
    concern. Keeping the state here prevents the window and input router from
    growing knowledge about how each existing or newly-created widget should be
    updated.
    """

    NORMAL_OPACITY = 1.0
    TRANSPARENT_OPACITY = 0.0

    def __init__(self, iter_widgets: Callable[[], Iterable[object]]) -> None:
        self._iter_widgets = iter_widgets
        self._transparent = False

    @property
    def is_transparent(self) -> bool:
        return self._transparent

    def toggle(self) -> bool:
        self._transparent = not self._transparent
        self.apply_to_all()
        return self._transparent

    def restore_normal(self) -> bool:
        if not self._transparent:
            return False
        self._transparent = False
        self.apply_to_all()
        return True

    def apply_to_widget(self, widget: object) -> bool:
        return capabilities.set_opacity(widget, self._current_opacity())

    def apply_to_all(self) -> int:
        updated_count = 0
        for widget in self._iter_widgets():
            if self.apply_to_widget(widget):
                updated_count += 1
        return updated_count

    def _current_opacity(self) -> float:
        if self._transparent:
            return self.TRANSPARENT_OPACITY
        return self.NORMAL_OPACITY
