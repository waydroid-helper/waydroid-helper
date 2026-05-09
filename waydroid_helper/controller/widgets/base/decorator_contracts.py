#!/usr/bin/env python3
"""Explicit behavior contracts installed by widget decorators."""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from waydroid_helper.controller.core.key_system import KeyCombination


class WidgetDecoratorBehavior(ABC):
    """Marker base for behavior objects owned by widget decorators."""


class EditableWidgetBehavior(WidgetDecoratorBehavior):
    """Behavior contract for widgets that support key-capture editing."""

    @abstractmethod
    def should_keep_editing_on_click(self, x: float, y: float) -> bool:
        ...

    @abstractmethod
    def cancel_editing(self) -> None:
        ...

    @abstractmethod
    def get_captured_keys(self) -> set["KeyCombination"]:
        ...


class ResizableWidgetBehavior(WidgetDecoratorBehavior):
    """Behavior contract for widgets that support edit-mode resizing."""

    @abstractmethod
    def check_resize_direction(self, x: float, y: float) -> str | None:
        ...

    @abstractmethod
    def start_resize(self, x: float, y: float, resize_direction: str) -> None:
        ...

    @abstractmethod
    def is_resizing(self) -> bool:
        ...

    @abstractmethod
    def on_resize_release(self) -> None:
        ...

    @abstractmethod
    def handle_resize_motion(self, global_x: float, global_y: float) -> None:
        ...
