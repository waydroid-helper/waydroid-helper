from __future__ import annotations

import pytest

from waydroid_helper.controller.widgets.decorators.resize_geometry import (
    ResizeGeometryCalculator,
    ResizeSnapshot,
    ResizeStrategy,
)


def test_resize_hit_test_reports_edges_and_corners():
    geometry = ResizeGeometryCalculator()

    assert geometry.hit_test(98, 98, 100, 100) == "se"
    assert geometry.hit_test(2, 98, 100, 100) == "sw"
    assert geometry.hit_test(50, 2, 100, 100) == "n"
    assert geometry.hit_test(50, 50, 100, 100) is None


def test_normal_resize_preserves_legacy_fixed_minimums():
    geometry = ResizeGeometryCalculator()
    snapshot = ResizeSnapshot(
        width=80,
        height=60,
        x=10,
        y=20,
        min_width=120,
        min_height=90,
    )

    result = geometry.calculate("w", 60, 0, snapshot, ResizeStrategy.NORMAL)

    assert result.width == 50
    assert result.height == 60
    assert result.x == 40
    assert result.y == 20


def test_center_resize_keeps_center_position():
    geometry = ResizeGeometryCalculator()
    snapshot = ResizeSnapshot(
        width=100,
        height=100,
        x=10,
        y=20,
        min_width=20,
        min_height=20,
    )

    result = geometry.calculate("e", 50, 0, snapshot, ResizeStrategy.CENTER)

    assert result.width == 150
    assert result.height == 150
    assert result.x == pytest.approx(-15)
    assert result.y == pytest.approx(-5)


def test_symmetric_resize_expands_around_center():
    geometry = ResizeGeometryCalculator()
    snapshot = ResizeSnapshot(
        width=100,
        height=80,
        x=10,
        y=20,
        min_width=20,
        min_height=20,
    )

    result = geometry.calculate("se", 10, 5, snapshot, ResizeStrategy.SYMMETRIC)

    assert result.width == 120
    assert result.height == 90
    assert result.x == 0
    assert result.y == 15
