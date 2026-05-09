#!/usr/bin/env python3
"""Shared draw overlay hook for widget decorators."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any


DrawOverlay = Callable[[Any, int, int], None]


@dataclass
class DecoratorDrawOverlayRegistry:
    """Installs one draw wrapper and runs registered overlay callbacks."""

    widget: Any
    overlays: list[DrawOverlay] = field(default_factory=list)

    def add(self, draw_overlay: DrawOverlay) -> None:
        self.overlays.append(draw_overlay)


def add_decorator_draw_overlay(widget: Any, draw_overlay: DrawOverlay) -> None:
    try:
        registry = widget._decorator_draw_overlay_registry
    except AttributeError:
        registry = None

    if not isinstance(registry, DecoratorDrawOverlayRegistry):
        registry = DecoratorDrawOverlayRegistry(widget)
        original_draw = widget.draw_func

        def master_draw_func(widget_instance, cr, width, height, user_data):
            original_draw(widget_instance, cr, width, height, user_data)
            for overlay in registry.overlays:
                overlay(cr, width, height)

        widget._decorator_draw_overlay_registry = registry
        widget.set_draw_func(master_draw_func, None)

    registry.add(draw_overlay)
