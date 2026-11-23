from __future__ import annotations

from dataclasses import dataclass

from waydroid_helper.controller.widgets.base.edit_controls import EditControls
from waydroid_helper.controller.widgets.base.edit_interaction import EditControlInteraction


@dataclass
class FakeHost:
    width: int = 100
    height: int = 100
    is_selected: bool = True
    mapping_mode: bool = False
    SETTINGS_PANEL_AUTO_HIDE: bool = False
    delete_bounds: tuple[int, int, int, int] = (0, 0, 16, 16)
    settings_bounds: tuple[int, int, int, int] = (84, 84, 16, 16)

    def __post_init__(self):
        self.queue_draw_calls = 0

    def get_delete_button_bounds(self):
        return self.delete_bounds

    def get_settings_button_bounds(self):
        return self.settings_bounds

    def queue_draw(self):
        self.queue_draw_calls += 1


def test_edit_interaction_emits_delete_and_settings_events():
    host = FakeHost(SETTINGS_PANEL_AUTO_HIDE=True)
    actions: list[tuple[str, object, object]] = []
    interaction = EditControlInteraction(
        EditControls(),
        on_delete=lambda action_host: actions.append(("delete", action_host, action_host)),
        on_settings=lambda action_host, auto_hide: actions.append(
            ("settings", action_host, auto_hide)
        ),
    )

    assert interaction.handle_click(host, 8, 8) is True
    assert interaction.handle_click(host, 92, 92) is True
    assert interaction.handle_click(host, 50, 50) is False

    assert actions == [
        ("delete", host, host),
        ("settings", host, True),
    ]


def test_edit_interaction_redraws_when_hover_changes():
    controls = EditControls()
    host = FakeHost()
    interaction = EditControlInteraction(
        controls,
        on_delete=lambda action_host: None,
        on_settings=lambda action_host, auto_hide: None,
    )

    interaction.handle_motion(host, 8, 8)

    assert host.queue_draw_calls == 1

    interaction.handle_motion(host, 50, 50)

    assert host.queue_draw_calls == 2

    interaction.handle_motion(host, 50, 50)

    assert host.queue_draw_calls == 2


def test_edit_interaction_clears_hover_on_leave():
    controls = EditControls()
    host = FakeHost()
    interaction = EditControlInteraction(
        controls,
        on_delete=lambda action_host: None,
        on_settings=lambda action_host, auto_hide: None,
    )

    interaction.handle_motion(host, 8, 8)
    interaction.handle_leave(host)

    assert controls.has_hover() is False
    assert host.queue_draw_calls == 2
