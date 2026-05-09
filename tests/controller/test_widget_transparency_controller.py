from __future__ import annotations

from waydroid_helper.controller.app.widget_transparency_controller import (
    WidgetTransparencyController,
)


class FakeWidget:
    def __init__(self):
        self.opacity_history: list[float] = []

    def set_opacity(self, opacity: float):
        self.opacity_history.append(opacity)


def test_widget_transparency_controller_toggles_all_widgets_between_hidden_and_normal():
    widgets = [FakeWidget(), FakeWidget()]
    controller = WidgetTransparencyController(lambda: iter(widgets))

    assert controller.toggle() is True
    assert controller.is_transparent is True
    assert [widget.opacity_history for widget in widgets] == [[0.0], [0.0]]

    assert controller.toggle() is False
    assert controller.is_transparent is False
    assert [widget.opacity_history for widget in widgets] == [[0.0, 1.0], [0.0, 1.0]]


def test_widget_transparency_controller_restores_normal_once_and_updates_new_widgets():
    widgets = [FakeWidget()]
    controller = WidgetTransparencyController(lambda: iter(widgets))

    controller.toggle()
    new_widget = FakeWidget()

    assert controller.apply_to_widget(new_widget) is True
    assert new_widget.opacity_history == [0.0]
    assert controller.restore_normal() is True
    assert controller.restore_normal() is False
    assert widgets[0].opacity_history == [0.0, 1.0]
