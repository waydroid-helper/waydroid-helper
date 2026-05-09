#!/usr/bin/env python3
"""Pure geometry helpers for resizable widget decorators."""

from __future__ import annotations

from dataclasses import dataclass
from enum import IntEnum


class ResizeStrategy(IntEnum):
    """Resize strategies supported by the edit-mode resize decorator."""

    NORMAL = 0
    CENTER = 1
    SYMMETRIC = 2


@dataclass(frozen=True, slots=True)
class ResizeSnapshot:
    """Widget geometry captured when a resize gesture starts."""

    width: float
    height: float
    x: float
    y: float
    min_width: float
    min_height: float


@dataclass(frozen=True, slots=True)
class ResizeResult:
    """Widget geometry produced by a resize calculation."""

    width: float
    height: float
    x: float
    y: float


class ResizeGeometryCalculator:
    """Computes resize hit targets and new bounds without GTK state."""

    BORDER = 8
    FALLBACK_MIN_WIDTH = 50
    FALLBACK_MIN_HEIGHT = 30

    def hit_test(
        self,
        x: float,
        y: float,
        width: float,
        height: float,
    ) -> str | None:
        left_edge = x <= self.BORDER
        right_edge = x >= width - self.BORDER
        top_edge = y <= self.BORDER
        bottom_edge = y >= height - self.BORDER

        if bottom_edge and right_edge:
            return "se"
        if bottom_edge and left_edge:
            return "sw"
        if top_edge and right_edge:
            return "ne"
        if top_edge and left_edge:
            return "nw"
        if right_edge:
            return "e"
        if left_edge:
            return "w"
        if bottom_edge:
            return "s"
        if top_edge:
            return "n"

        return None

    def calculate(
        self,
        resize_direction: str,
        global_dx: float,
        global_dy: float,
        snapshot: ResizeSnapshot,
        strategy: ResizeStrategy,
    ) -> ResizeResult:
        if strategy == ResizeStrategy.CENTER:
            return self._calculate_center(resize_direction, global_dx, global_dy, snapshot)
        if strategy == ResizeStrategy.SYMMETRIC:
            return self._calculate_symmetric(
                resize_direction,
                global_dx,
                global_dy,
                snapshot,
            )
        return self._calculate_normal(resize_direction, global_dx, global_dy, snapshot)

    def _calculate_normal(
        self,
        resize_direction: str,
        global_dx: float,
        global_dy: float,
        snapshot: ResizeSnapshot,
    ) -> ResizeResult:
        new_width = snapshot.width
        new_height = snapshot.height
        new_x = snapshot.x
        new_y = snapshot.y
        min_width = self.FALLBACK_MIN_WIDTH
        min_height = self.FALLBACK_MIN_HEIGHT

        if "e" in resize_direction:
            new_width = max(min_width, snapshot.width + global_dx)
        elif "w" in resize_direction:
            new_width = max(min_width, snapshot.width - global_dx)
            new_x = snapshot.x + global_dx
            if new_width == min_width:
                new_x = snapshot.x + snapshot.width - min_width

        if "s" in resize_direction:
            new_height = max(min_height, snapshot.height + global_dy)
        elif "n" in resize_direction:
            new_height = max(min_height, snapshot.height - global_dy)
            new_y = snapshot.y + global_dy
            if new_height == min_height:
                new_y = snapshot.y + snapshot.height - min_height

        return ResizeResult(new_width, new_height, new_x, new_y)

    def _calculate_center(
        self,
        resize_direction: str,
        global_dx: float,
        global_dy: float,
        snapshot: ResizeSnapshot,
    ) -> ResizeResult:
        center_x = snapshot.x + snapshot.width / 2
        center_y = snapshot.y + snapshot.height / 2
        scale_factor = self._axis_scale_factor(
            resize_direction,
            global_dx,
            global_dy,
            snapshot,
        )

        scale_factor = max(
            scale_factor,
            snapshot.min_width / snapshot.width,
            snapshot.min_height / snapshot.height,
        )

        new_width = max(self.FALLBACK_MIN_WIDTH, snapshot.width * scale_factor)
        new_height = max(self.FALLBACK_MIN_HEIGHT, snapshot.height * scale_factor)
        new_x = center_x - new_width / 2
        new_y = center_y - new_height / 2
        return ResizeResult(new_width, new_height, new_x, new_y)

    def _calculate_symmetric(
        self,
        resize_direction: str,
        global_dx: float,
        global_dy: float,
        snapshot: ResizeSnapshot,
    ) -> ResizeResult:
        new_width = snapshot.width
        new_height = snapshot.height
        new_x = snapshot.x
        new_y = snapshot.y
        min_width = self.FALLBACK_MIN_WIDTH
        min_height = self.FALLBACK_MIN_HEIGHT

        if "e" in resize_direction or "w" in resize_direction:
            width_change = global_dx if "e" in resize_direction else -global_dx
            new_width = max(min_width, snapshot.width + width_change * 2)
            width_diff = new_width - snapshot.width
            new_x = snapshot.x - width_diff / 2

        if "s" in resize_direction or "n" in resize_direction:
            height_change = global_dy if "s" in resize_direction else -global_dy
            new_height = max(min_height, snapshot.height + height_change * 2)
            height_diff = new_height - snapshot.height
            new_y = snapshot.y - height_diff / 2

        return ResizeResult(new_width, new_height, new_x, new_y)

    def _axis_scale_factor(
        self,
        resize_direction: str,
        global_dx: float,
        global_dy: float,
        snapshot: ResizeSnapshot,
    ) -> float:
        scale_factor = 1.0

        if "e" in resize_direction:
            scale_factor = self._safe_ratio(snapshot.width + global_dx, snapshot.width)
        elif "w" in resize_direction:
            scale_factor = self._safe_ratio(snapshot.width - global_dx, snapshot.width)
        elif "s" in resize_direction:
            scale_factor = self._safe_ratio(snapshot.height + global_dy, snapshot.height)
        elif "n" in resize_direction:
            scale_factor = self._safe_ratio(snapshot.height - global_dy, snapshot.height)

        if len(resize_direction) == 2:
            scale_factor_x = 1.0
            scale_factor_y = 1.0

            if "e" in resize_direction:
                scale_factor_x = self._safe_ratio(
                    snapshot.width + global_dx,
                    snapshot.width,
                )
            elif "w" in resize_direction:
                scale_factor_x = self._safe_ratio(
                    snapshot.width - global_dx,
                    snapshot.width,
                )

            if "s" in resize_direction:
                scale_factor_y = self._safe_ratio(
                    snapshot.height + global_dy,
                    snapshot.height,
                )
            elif "n" in resize_direction:
                scale_factor_y = self._safe_ratio(
                    snapshot.height - global_dy,
                    snapshot.height,
                )

            if abs(scale_factor_x - 1.0) > abs(scale_factor_y - 1.0):
                scale_factor = scale_factor_x
            else:
                scale_factor = scale_factor_y

        return scale_factor

    def _safe_ratio(self, numerator: float, denominator: float) -> float:
        if denominator <= 0:
            return 1.0
        return numerator / denominator
