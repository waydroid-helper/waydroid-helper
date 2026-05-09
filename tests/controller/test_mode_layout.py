from __future__ import annotations

from dataclasses import dataclass

from waydroid_helper.controller.widgets.base.mode_layout import WidgetModeLayout


class FakeParent:
    def __init__(self):
        self.moves: list[tuple[object, float, float]] = []
        self.position = (3, 4)

    def move(self, widget, x, y):
        self.moves.append((widget, x, y))
        self.position = (x, y)

    def get_child_position(self, widget):
        return self.position


@dataclass
class FakeWidget:
    x: int = 10
    y: int = 20
    width: int = 120
    height: int = 80
    mapping_mode: bool = False
    mapping_start_x: float = 45
    mapping_start_y: float = 55
    MAPPING_MODE_WIDTH: int = 30
    MAPPING_MODE_HEIGHT: int = 40
    parent: FakeParent | None = None

    def __post_init__(self):
        self.size_requests: list[tuple[int, int]] = []
        self.content_widths: list[int] = []
        self.content_heights: list[int] = []
        self.queue_draw_calls = 0
        self.allocated_width = self.width
        self.allocated_height = self.height

    def get_parent(self):
        return self.parent

    def set_size_request(self, width: int, height: int):
        self.size_requests.append((width, height))
        self.allocated_width = width
        self.allocated_height = height

    def set_content_width(self, width: int):
        self.content_widths.append(width)

    def set_content_height(self, height: int):
        self.content_heights.append(height)

    def get_allocated_width(self):
        return self.allocated_width

    def get_allocated_height(self):
        return self.allocated_height

    def queue_draw(self):
        self.queue_draw_calls += 1


def test_widget_mode_layout_enters_mapping_mode_geometry():
    parent = FakeParent()
    widget = FakeWidget(parent=parent)
    layout = WidgetModeLayout()

    assert layout.set_mapping_mode(widget, True) is True

    assert widget.mapping_mode is True
    assert parent.moves == [(widget, 45, 55)]
    assert widget.size_requests == [(30, 40)]
    assert widget.content_widths == [30]
    assert widget.content_heights == [40]
    assert widget.queue_draw_calls == 1


def test_widget_mode_layout_restores_edit_mode_geometry():
    parent = FakeParent()
    widget = FakeWidget(parent=parent, mapping_mode=True)
    layout = WidgetModeLayout()

    assert layout.set_mapping_mode(widget, False) is True

    assert widget.mapping_mode is False
    assert parent.moves == [(widget, 10, 20)]
    assert widget.size_requests == [(120, 80)]
    assert widget.content_widths == [120]
    assert widget.content_heights == [80]
    assert widget.queue_draw_calls == 1


def test_widget_mode_layout_noops_when_mode_is_unchanged():
    parent = FakeParent()
    widget = FakeWidget(parent=parent)
    layout = WidgetModeLayout()

    assert layout.set_mapping_mode(widget, False) is False

    assert parent.moves == []
    assert widget.size_requests == []
    assert widget.queue_draw_calls == 0


def test_widget_mode_layout_reads_parent_bounds_and_falls_back_without_parent():
    parent = FakeParent()
    widget = FakeWidget(parent=parent)
    layout = WidgetModeLayout()

    layout.set_mapping_mode(widget, True)

    assert layout.get_widget_bounds(widget) == (45, 55, 30, 40)

    widget.parent = None

    assert layout.get_widget_bounds(widget) == (0, 0, 120, 80)
