from __future__ import annotations

from typing import Callable, Protocol

from waydroid_helper.controller.widgets.base.edit_controls import (
    EditControlAction,
    EditControls,
    EditableControlHost,
)


class EditInteractionHost(EditableControlHost, Protocol):
    SETTINGS_PANEL_AUTO_HIDE: bool

    def queue_draw(self) -> None: ...
    def set_cursor_from_name(self, cursor_name: str) -> None: ...
    def set_cursor(self, cursor) -> None: ...


class EditControlInteraction:
    """Translate edit-control input into actions and widget UI feedback."""

    def __init__(
        self,
        edit_controls: EditControls,
        on_delete: Callable[[EditInteractionHost], None],
        on_settings: Callable[[EditInteractionHost, bool], None],
    ):
        self._edit_controls = edit_controls
        self._on_delete = on_delete
        self._on_settings = on_settings

    def handle_click(
        self,
        host: EditInteractionHost,
        x: int | float,
        y: int | float,
    ) -> bool:
        action = self._edit_controls.action_at(host, x, y)
        if action == EditControlAction.DELETE:
            self._on_delete(host)
            return True

        if action == EditControlAction.SETTINGS:
            self._on_settings(host, host.SETTINGS_PANEL_AUTO_HIDE)
            return True

        return False

    def handle_motion(
        self,
        host: EditInteractionHost,
        x: int | float,
        y: int | float,
    ) -> None:
        if self._edit_controls.update_hover(host, x, y):
            host.queue_draw()

        if self._edit_controls.has_hover():
            host.set_cursor_from_name("pointer")
        else:
            host.set_cursor(None)

    def handle_leave(self, host: EditInteractionHost) -> None:
        if self._edit_controls.clear_hover():
            host.queue_draw()

        host.set_cursor(None)
