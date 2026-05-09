#!/usr/bin/env python3
"""Typed widget capability contracts used by app-layer managers."""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, Protocol, runtime_checkable

if TYPE_CHECKING:
    from waydroid_helper.controller.core.key_system import KeyCombination


ResizeDirection = str
WidgetBounds = tuple[int, int, int, int]


@runtime_checkable
class SelectableWidget(Protocol):
    is_selected: bool

    def set_selected(self, selected: bool) -> None:
        ...


@runtime_checkable
class MappingModeWidget(Protocol):
    def set_mapping_mode(self, mapping_mode: bool) -> None:
        ...


@runtime_checkable
class OpacityWidget(Protocol):
    def set_opacity(self, opacity: float) -> None:
        ...


@runtime_checkable
class ContextMenuTarget(Protocol):
    def on_widget_right_clicked(self, x: float, y: float) -> None:
        ...


@runtime_checkable
class ClickableWidget(Protocol):
    def on_widget_clicked(self, x: float, y: float) -> None:
        ...


@runtime_checkable
class DoubleClickableWidget(Protocol):
    def on_widget_double_clicked(self, x: float, y: float) -> None:
        ...


@runtime_checkable
class EditableInteractionWidget(Protocol):
    def supports_editing_interaction(self) -> bool:
        ...

    def should_keep_editing_on_click(self, x: float, y: float) -> bool:
        ...


@runtime_checkable
class ResizableWidget(Protocol):
    def supports_resizing(self) -> bool:
        ...


@runtime_checkable
class ResizeHitTestWidget(ResizableWidget, Protocol):
    def check_resize_direction(self, x: float, y: float) -> ResizeDirection | None:
        ...


@runtime_checkable
class ResizeSessionWidget(ResizableWidget, Protocol):
    def start_resize(self, x: float, y: float, resize_direction: ResizeDirection) -> None:
        ...

    def handle_resize_motion(self, global_x: float, global_y: float) -> None:
        ...


@runtime_checkable
class ResizeReleaseWidget(ResizableWidget, Protocol):
    def on_resize_release(self) -> None:
        ...


@runtime_checkable
class BoundedWidget(Protocol):
    def get_widget_bounds(self) -> WidgetBounds:
        ...


@runtime_checkable
class DeletableWidget(Protocol):
    def on_delete(self) -> None:
        ...


@runtime_checkable
class MultiKeyMappingWidget(Protocol):
    def get_all_key_mappings(self) -> Mapping["KeyCombination", Any]:
        ...


@runtime_checkable
class LayoutKeyMappingWidget(Protocol):
    def get_layout_key_mappings(self) -> set["KeyCombination"]:
        ...


@runtime_checkable
class DisplayTextWidget(Protocol):
    text: str

    def set_text_if_empty(self, text: str) -> bool:
        ...


@runtime_checkable
class BringToFrontGuardWidget(Protocol):
    def mark_skip_delayed_bring_to_front(self) -> None:
        ...

    def should_skip_delayed_bring_to_front(self) -> bool:
        ...

    def clear_skip_delayed_bring_to_front(self) -> None:
        ...


def set_selected(widget: Any, selected: bool) -> bool:
    if not isinstance(widget, SelectableWidget):
        return False
    widget.set_selected(selected)
    return True


def is_selected(widget: Any) -> bool:
    if not isinstance(widget, SelectableWidget):
        return False
    return bool(widget.is_selected)


def set_mapping_mode(widget: Any, mapping_mode: bool) -> bool:
    if not isinstance(widget, MappingModeWidget):
        return False
    widget.set_mapping_mode(mapping_mode)
    return True


def set_opacity(widget: Any, opacity: float) -> bool:
    if not isinstance(widget, OpacityWidget):
        return False
    widget.set_opacity(opacity)
    return True


def notify_right_click(widget: Any, x: float, y: float) -> bool:
    if not isinstance(widget, ContextMenuTarget):
        return False
    widget.on_widget_right_clicked(x, y)
    return True


def notify_click(widget: Any, x: float, y: float) -> bool:
    if not isinstance(widget, ClickableWidget):
        return False
    widget.on_widget_clicked(x, y)
    return True


def notify_double_click(widget: Any, x: float, y: float) -> bool:
    if not isinstance(widget, DoubleClickableWidget):
        return False
    widget.on_widget_double_clicked(x, y)
    return True


def should_keep_editing_on_click(widget: Any, x: float, y: float) -> bool:
    if not isinstance(widget, EditableInteractionWidget):
        return False
    if not widget.supports_editing_interaction():
        return False
    return bool(widget.should_keep_editing_on_click(x, y))


def supports_editing_interaction(widget: Any) -> bool:
    if not isinstance(widget, EditableInteractionWidget):
        return False
    return widget.supports_editing_interaction()


def check_resize_direction(
    widget: Any, x: float, y: float
) -> ResizeDirection | None:
    if not isinstance(widget, ResizeHitTestWidget):
        return None
    if not widget.supports_resizing():
        return None
    return widget.check_resize_direction(x, y)


def start_resize(
    widget: Any, x: float, y: float, resize_direction: ResizeDirection
) -> bool:
    if not isinstance(widget, ResizeSessionWidget):
        return False
    if not widget.supports_resizing():
        return False
    widget.start_resize(x, y, resize_direction)
    return True


def handle_resize_motion(widget: Any, global_x: float, global_y: float) -> bool:
    if not isinstance(widget, ResizeSessionWidget):
        return False
    if not widget.supports_resizing():
        return False
    widget.handle_resize_motion(global_x, global_y)
    return True


def notify_resize_release(widget: Any) -> bool:
    if not isinstance(widget, ResizeReleaseWidget):
        return False
    if not widget.supports_resizing():
        return False
    widget.on_resize_release()
    return True


def get_widget_bounds(widget: Any) -> WidgetBounds | None:
    if not isinstance(widget, BoundedWidget):
        return None
    return widget.get_widget_bounds()


def notify_delete(widget: Any) -> bool:
    if not isinstance(widget, DeletableWidget):
        return False
    widget.on_delete()
    return True


def get_all_key_mappings(widget: Any) -> Mapping["KeyCombination", Any] | None:
    if not isinstance(widget, MultiKeyMappingWidget):
        return None
    return widget.get_all_key_mappings()


def get_final_key_mappings(widget: Any) -> set["KeyCombination"]:
    if not isinstance(widget, LayoutKeyMappingWidget):
        return set()
    return widget.get_layout_key_mappings()


def set_text_if_empty(widget: Any, text: str) -> bool:
    if not isinstance(widget, DisplayTextWidget):
        return False
    return widget.set_text_if_empty(text)


def mark_skip_delayed_bring_to_front(widget: Any) -> None:
    if isinstance(widget, BringToFrontGuardWidget):
        widget.mark_skip_delayed_bring_to_front()


def should_skip_delayed_bring_to_front(widget: Any) -> bool:
    if not isinstance(widget, BringToFrontGuardWidget):
        return False
    return widget.should_skip_delayed_bring_to_front()


def clear_skip_delayed_bring_to_front(widget: Any) -> None:
    if isinstance(widget, BringToFrontGuardWidget):
        widget.clear_skip_delayed_bring_to_front()
