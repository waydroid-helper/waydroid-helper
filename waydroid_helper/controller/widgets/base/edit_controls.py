from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum, auto
from typing import Any, Protocol


class EditControlAction(Enum):
    NONE = auto()
    DELETE = auto()
    SETTINGS = auto()


class EditableControlHost(Protocol):
    width: int
    height: int
    is_selected: bool
    mapping_mode: bool

    def get_delete_button_bounds(self) -> tuple[int, int, int, int]: ...
    def get_settings_button_bounds(self) -> tuple[int, int, int, int]: ...


@dataclass
class EditControlHoverState:
    delete: bool = False
    settings: bool = False


class EditControls:
    """Own edit-mode chrome hit testing, hover state, and drawing.

    BaseWidget still exposes the historical button-bound APIs so subclasses can
    override placement. This collaborator keeps the common edit controls from
    leaking into every widget's domain behavior.
    """

    BUTTON_SIZE = 16

    def __init__(self):
        self.hover = EditControlHoverState()

    def default_delete_button_bounds(self, width: int, height: int) -> tuple[int, int, int, int]:
        return self._bounds_at_angle(width, height, -math.pi / 4)

    def default_settings_button_bounds(self, width: int, height: int) -> tuple[int, int, int, int]:
        return self._bounds_at_angle(width, height, math.pi / 4)

    def hit_test_delete(self, host: EditableControlHost, x: int | float, y: int | float) -> bool:
        return self._is_point_in_button(host.get_delete_button_bounds(), x, y)

    def hit_test_settings(self, host: EditableControlHost, x: int | float, y: int | float) -> bool:
        return self._is_point_in_button(host.get_settings_button_bounds(), x, y)

    def action_at(
        self,
        host: EditableControlHost,
        x: int | float,
        y: int | float,
    ) -> EditControlAction:
        if not self.is_active(host):
            return EditControlAction.NONE

        if self.hit_test_delete(host, x, y):
            return EditControlAction.DELETE

        if self.hit_test_settings(host, x, y):
            return EditControlAction.SETTINGS

        return EditControlAction.NONE

    def update_hover(
        self,
        host: EditableControlHost,
        x: int | float,
        y: int | float,
    ) -> bool:
        if not self.is_active(host):
            return self.clear_hover()

        return self._set_hover(
            delete=self.hit_test_delete(host, x, y),
            settings=self.hit_test_settings(host, x, y),
        )

    def clear_hover(self) -> bool:
        return self._set_hover(delete=False, settings=False)

    def has_hover(self) -> bool:
        return self.hover.delete or self.hover.settings

    def is_active(self, host: EditableControlHost) -> bool:
        return host.is_selected and not host.mapping_mode

    def draw(self, host: EditableControlHost, cr: Any) -> None:
        if not self.is_active(host):
            return

        self.draw_delete_button(host, cr)
        self.draw_settings_button(host, cr)

    def draw_delete_button(self, host: EditableControlHost, cr: Any) -> None:
        if host.mapping_mode:
            return

        x, y, w, h = host.get_delete_button_bounds()

        cr.set_source_rgba(1, 1, 1, 0.9)
        cr.arc(x + w / 2, y + h / 2, w / 2, 0, 2 * math.pi)
        cr.fill()

        if self.hover.delete:
            cr.set_source_rgba(1.0, 0.2, 0.2, 0.9)
            cr.arc(x + w / 2, y + h / 2, w / 2, 0, 2 * math.pi)
            cr.fill()

        if self.hover.delete:
            cr.set_source_rgba(1, 1, 1, 1)
        else:
            cr.set_source_rgba(0, 0, 0, 0.7)
        cr.set_line_width(2)
        padding = 4
        cr.move_to(x + padding, y + padding)
        cr.line_to(x + w - padding, y + h - padding)
        cr.move_to(x + w - padding, y + padding)
        cr.line_to(x + padding, y + h - padding)
        cr.stroke()

    def draw_settings_button(self, host: EditableControlHost, cr: Any) -> None:
        if host.mapping_mode:
            return

        x, y, w, h = host.get_settings_button_bounds()
        center_x, center_y = x + w / 2, y + h / 2

        cr.set_source_rgba(1, 1, 1, 0.9)
        cr.arc(center_x, center_y, w / 2, 0, 2 * math.pi)
        cr.fill()

        if self.hover.settings:
            cr.set_source_rgba(0.2, 0.6, 1.0, 0.9)
            cr.arc(center_x, center_y, w / 2, 0, 2 * math.pi)
            cr.fill()

        if self.hover.settings:
            cr.set_source_rgba(1, 1, 1, 1)
        else:
            cr.set_source_rgba(0.2, 0.2, 0.2, 0.8)

        num_teeth = 6
        outer_radius = w / 2 - 2
        inner_radius = outer_radius * 0.6
        hole_radius = outer_radius * 0.4

        cr.set_line_width(1.5)

        for i in range(num_teeth):
            angle = i * (2 * math.pi / num_teeth)
            start_angle = angle - math.pi / num_teeth / 2
            end_angle = angle + math.pi / num_teeth / 2

            x1 = center_x + outer_radius * math.cos(start_angle)
            y1 = center_y + outer_radius * math.sin(start_angle)
            x2 = center_x + outer_radius * math.cos(end_angle)
            y2 = center_y + outer_radius * math.sin(end_angle)
            x3 = center_x + inner_radius * math.cos(end_angle)
            y3 = center_y + inner_radius * math.sin(end_angle)
            x4 = center_x + inner_radius * math.cos(start_angle)
            y4 = center_y + inner_radius * math.sin(start_angle)

            cr.new_path()
            cr.move_to(x1, y1)
            cr.line_to(x2, y2)
            cr.line_to(x3, y3)
            cr.line_to(x4, y4)
            cr.close_path()
            cr.fill()

        cr.new_path()
        cr.arc(center_x, center_y, inner_radius, 0, 2 * math.pi)
        cr.fill()

        cr.save()
        if self.hover.settings:
            cr.set_source_rgba(0.2, 0.6, 1.0, 1.0)
        else:
            cr.set_source_rgba(1, 1, 1, 1.0)

        cr.new_path()
        cr.arc(center_x, center_y, hole_radius, 0, 2 * math.pi)
        cr.fill()
        cr.restore()

    def _set_hover(self, delete: bool, settings: bool) -> bool:
        changed = self.hover.delete != delete or self.hover.settings != settings
        self.hover.delete = delete
        self.hover.settings = settings
        return changed

    def _bounds_at_angle(self, width: int, height: int, angle: float) -> tuple[int, int, int, int]:
        center_x = width / 2
        center_y = height / 2
        radius = min(width, height) / 2
        button_center_x = center_x + radius * math.cos(angle)
        button_center_y = center_y + radius * math.sin(angle)
        x = button_center_x - self.BUTTON_SIZE / 2
        y = button_center_y - self.BUTTON_SIZE / 2
        return (int(x), int(y), self.BUTTON_SIZE, self.BUTTON_SIZE)

    def _is_point_in_button(
        self,
        bounds: tuple[int, int, int, int],
        x: int | float,
        y: int | float,
    ) -> bool:
        bx, by, bw, bh = bounds
        center_x = bx + bw / 2
        center_y = by + bh / 2
        radius = bw / 2
        distance = math.sqrt((x - center_x) ** 2 + (y - center_y) ** 2)
        return distance <= radius
