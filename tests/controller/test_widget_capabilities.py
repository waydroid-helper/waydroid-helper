from __future__ import annotations

from waydroid_helper.controller.app import widget_capabilities as capabilities
from waydroid_helper.controller.core.key_system import Key, KeyCombination, KeyType


class CapabilityWidget:
    def __init__(self):
        self.is_selected = False
        self.mapping_mode = False
        self.clicked: list[tuple[float, float]] = []
        self.double_clicked: list[tuple[float, float]] = []
        self.right_clicked: list[tuple[float, float]] = []
        self.resize_started: list[tuple[float, float, str]] = []
        self.resize_motion: list[tuple[float, float]] = []
        self.resize_released = False
        self.deleted = False
        self.text = ""
        self._skip_delayed_bring_to_front = False

    def set_selected(self, selected: bool):
        self.is_selected = selected

    def set_mapping_mode(self, mapping_mode: bool):
        self.mapping_mode = mapping_mode

    def on_widget_clicked(self, x, y):
        self.clicked.append((x, y))

    def on_widget_double_clicked(self, x, y):
        self.double_clicked.append((x, y))

    def on_widget_right_clicked(self, x, y):
        self.right_clicked.append((x, y))

    def should_keep_editing_on_click(self, x, y):
        return x < 10 and y < 10

    def supports_editing_interaction(self):
        return True

    def check_resize_direction(self, x, y):
        return "se" if x > 90 and y > 90 else None

    def supports_resizing(self):
        return True

    def start_resize(self, x, y, resize_direction):
        self.resize_started.append((x, y, resize_direction))

    def handle_resize_motion(self, global_x, global_y):
        self.resize_motion.append((global_x, global_y))

    def on_resize_release(self):
        self.resize_released = True

    def get_widget_bounds(self):
        return (1, 2, 100, 80)

    def on_delete(self):
        self.deleted = True

    def get_layout_key_mappings(self):
        return getattr(self, "final_keys", set())

    def set_text_if_empty(self, text: str):
        if self.text:
            return False
        self.text = text
        return True

    def mark_skip_delayed_bring_to_front(self):
        self._skip_delayed_bring_to_front = True

    def should_skip_delayed_bring_to_front(self):
        return self._skip_delayed_bring_to_front

    def clear_skip_delayed_bring_to_front(self):
        self._skip_delayed_bring_to_front = False


def test_widget_capability_adapter_invokes_supported_operations():
    widget = CapabilityWidget()

    assert capabilities.set_selected(widget, True) is True
    assert capabilities.is_selected(widget) is True
    assert capabilities.set_mapping_mode(widget, True) is True
    assert widget.mapping_mode is True
    assert capabilities.notify_click(widget, 1, 2) is True
    assert capabilities.notify_double_click(widget, 3, 4) is True
    assert capabilities.notify_right_click(widget, 5, 6) is True
    assert capabilities.should_keep_editing_on_click(widget, 5, 5) is True
    assert capabilities.supports_editing_interaction(widget) is True
    assert capabilities.check_resize_direction(widget, 95, 95) == "se"
    assert capabilities.start_resize(widget, 7, 8, "se") is True
    assert capabilities.handle_resize_motion(widget, 9, 10) is True
    assert capabilities.notify_resize_release(widget) is True
    assert capabilities.get_widget_bounds(widget) == (1, 2, 100, 80)
    assert capabilities.notify_delete(widget) is True

    assert widget.clicked == [(1, 2)]
    assert widget.double_clicked == [(3, 4)]
    assert widget.right_clicked == [(5, 6)]
    assert widget.resize_started == [(7, 8, "se")]
    assert widget.resize_motion == [(9, 10)]
    assert widget.resize_released is True
    assert widget.deleted is True


def test_widget_capability_adapter_handles_unsupported_operations():
    widget = object()

    assert capabilities.set_selected(widget, True) is False
    assert capabilities.is_selected(widget) is False
    assert capabilities.set_mapping_mode(widget, True) is False
    assert capabilities.notify_click(widget, 1, 2) is False
    assert capabilities.notify_double_click(widget, 1, 2) is False
    assert capabilities.notify_right_click(widget, 1, 2) is False
    assert capabilities.should_keep_editing_on_click(widget, 1, 2) is False
    assert capabilities.supports_editing_interaction(widget) is False
    assert capabilities.check_resize_direction(widget, 1, 2) is None
    assert capabilities.start_resize(widget, 1, 2, "se") is False
    assert capabilities.handle_resize_motion(widget, 1, 2) is False
    assert capabilities.notify_resize_release(widget) is False
    assert capabilities.get_widget_bounds(widget) is None
    assert capabilities.notify_delete(widget) is False


def test_mapping_helpers_normalize_single_and_multi_key_widgets():
    key = Key("A", 65, KeyType.CHARACTER)
    combination = KeyCombination([key])

    class MultiMappingWidget:
        def get_all_key_mappings(self):
            return {combination: "up"}

    class SingleMappingWidget:
        def __init__(self):
            self.final_keys = {combination}
            self.text = ""

        def get_layout_key_mappings(self):
            return set(self.final_keys)

        def set_text_if_empty(self, text: str):
            if self.text:
                return False
            self.text = text
            return True

    single = SingleMappingWidget()

    assert capabilities.get_all_key_mappings(MultiMappingWidget()) == {
        combination: "up"
    }
    assert capabilities.get_final_key_mappings(single) == {combination}
    assert capabilities.set_text_if_empty(single, "A") is True
    assert single.text == "A"
    assert capabilities.set_text_if_empty(single, "B") is False
    assert single.text == "A"


def test_skip_delayed_bring_to_front_flag_is_centralized():
    widget = CapabilityWidget()

    assert capabilities.should_skip_delayed_bring_to_front(widget) is False

    capabilities.mark_skip_delayed_bring_to_front(widget)
    assert capabilities.should_skip_delayed_bring_to_front(widget) is True

    capabilities.clear_skip_delayed_bring_to_front(widget)
    assert capabilities.should_skip_delayed_bring_to_front(widget) is False
