from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True)
class WidgetGeometry:
    x: float
    y: float
    width: int
    height: int


class ModeLayoutHost(Protocol):
    x: int
    y: int
    width: int
    height: int
    mapping_mode: bool
    mapping_start_x: float
    mapping_start_y: float
    MAPPING_MODE_WIDTH: int
    MAPPING_MODE_HEIGHT: int

    def get_parent(self): ...
    def set_size_request(self, width: int, height: int) -> None: ...
    def queue_draw(self) -> None: ...


class WidgetModeLayout:
    """Apply edit-mode and mapping-mode geometry to a widget host.

    BaseWidget owns the domain state, while this collaborator owns the GTK
    layout side effects: parent movement, requested size, optional content size,
    and redraw scheduling.
    """

    def set_mapping_mode(self, host: ModeLayoutHost, mapping_mode: bool) -> bool:
        if host.mapping_mode == mapping_mode:
            return False

        host.mapping_mode = mapping_mode
        geometry = self._mapping_geometry(host) if mapping_mode else self._edit_geometry(host)
        self._apply_geometry(host, geometry)
        host.queue_draw()
        return True

    def get_widget_bounds(self, host: ModeLayoutHost) -> tuple[int, int, int, int]:
        parent = host.get_parent()
        if parent is None:
            return 0, 0, host.width, host.height

        x, y = parent.get_child_position(host)
        width = host.get_allocated_width()
        height = host.get_allocated_height()
        return x, y, width, height

    def _mapping_geometry(self, host: ModeLayoutHost) -> WidgetGeometry:
        return WidgetGeometry(
            x=host.mapping_start_x,
            y=host.mapping_start_y,
            width=host.MAPPING_MODE_WIDTH,
            height=host.MAPPING_MODE_HEIGHT,
        )

    def _edit_geometry(self, host: ModeLayoutHost) -> WidgetGeometry:
        return WidgetGeometry(
            x=host.x,
            y=host.y,
            width=host.width,
            height=host.height,
        )

    def _apply_geometry(self, host: ModeLayoutHost, geometry: WidgetGeometry) -> None:
        parent = host.get_parent()
        if parent is not None:
            parent.move(host, geometry.x, geometry.y)

        host.set_size_request(geometry.width, geometry.height)
        self._set_optional_content_size(host, geometry)

    def _set_optional_content_size(
        self,
        host: ModeLayoutHost,
        geometry: WidgetGeometry,
    ) -> None:
        set_content_width = getattr(host, "set_content_width", None)
        if set_content_width is not None:
            set_content_width(geometry.width)

        set_content_height = getattr(host, "set_content_height", None)
        if set_content_height is not None:
            set_content_height(geometry.height)
