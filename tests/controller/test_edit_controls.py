from __future__ import annotations

from dataclasses import dataclass

from waydroid_helper.controller.widgets.base.edit_controls import (
    EditControlAction,
    EditControls,
)


@dataclass
class FakeHost:
    width: int = 100
    height: int = 100
    is_selected: bool = True
    mapping_mode: bool = False
    delete_bounds: tuple[int, int, int, int] = (0, 0, 16, 16)
    settings_bounds: tuple[int, int, int, int] = (84, 84, 16, 16)

    def get_delete_button_bounds(self):
        return self.delete_bounds

    def get_settings_button_bounds(self):
        return self.settings_bounds


def test_edit_controls_resolve_action_from_host_button_bounds():
    controls = EditControls()
    host = FakeHost()

    assert controls.action_at(host, 8, 8) is EditControlAction.DELETE
    assert controls.action_at(host, 92, 92) is EditControlAction.SETTINGS
    assert controls.action_at(host, 50, 50) is EditControlAction.NONE


def test_edit_controls_are_inactive_when_unselected_or_mapping():
    controls = EditControls()
    host = FakeHost(is_selected=False)

    assert controls.action_at(host, 8, 8) is EditControlAction.NONE

    host.is_selected = True
    host.mapping_mode = True

    assert controls.action_at(host, 8, 8) is EditControlAction.NONE


def test_edit_controls_track_hover_changes_and_clear_state():
    controls = EditControls()
    host = FakeHost()

    assert controls.update_hover(host, 8, 8) is True
    assert controls.hover.delete is True
    assert controls.hover.settings is False
    assert controls.has_hover() is True

    assert controls.update_hover(host, 8, 8) is False

    assert controls.update_hover(host, 92, 92) is True
    assert controls.hover.delete is False
    assert controls.hover.settings is True

    assert controls.clear_hover() is True
    assert controls.has_hover() is False
    assert controls.clear_hover() is False
