from __future__ import annotations

from waydroid_helper.controller.core.key_system import Key, KeyCombination, KeyType
from waydroid_helper.controller.widgets.decorators.editable_session import (
    CAPTURE_HINT_TEXT,
    EditableCaptureSession,
)


class FakeEditableWidget:
    def __init__(self):
        self.text = ""
        self.final_keys: set[KeyCombination] = set()
        self.queue_draw_calls = 0
        self.regions = []

    def queue_draw(self):
        self.queue_draw_calls += 1

    def get_region_at_position(self, x, y):
        for region in self.regions:
            rx, ry, rw, rh = region["bounds"]
            if rx <= x <= rx + rw and ry <= y <= ry + rh:
                return region
        return None


def make_key(name: str, keycode: int) -> Key:
    return Key(name, keycode, KeyType.CHARACTER)


def test_widget_capture_cancel_restores_original_text_and_keys():
    widget = FakeEditableWidget()
    original = KeyCombination([make_key("A", 65)])
    widget.text = "A"
    widget.final_keys = {original}
    session = EditableCaptureSession(max_keys=1)

    assert session.begin_widget_editing(widget) is True
    session.capture_key(widget, make_key("B", 66))

    assert widget.text == "B"
    assert widget.final_keys != {original}

    result = session.finish(widget, apply_changes=False)

    assert result is not None
    assert widget.text == "A"
    assert widget.final_keys == {original}
    assert session.is_editing is False


def test_widget_capture_hint_is_cleared_when_no_key_is_captured():
    widget = FakeEditableWidget()
    session = EditableCaptureSession(max_keys=1)

    assert session.begin_widget_editing(widget) is True
    assert widget.text == CAPTURE_HINT_TEXT

    result = session.finish(widget, apply_changes=True)

    assert result is not None
    assert result.register_widget_mappings is False
    assert widget.text == ""


def test_region_capture_returns_mapping_side_effect_request():
    widget = FakeEditableWidget()
    original = KeyCombination([make_key("W", 87)])
    region_keys = {original}
    region = {
        "id": "up",
        "name": "Up",
        "bounds": (0, 0, 50, 50),
        "get_keys": lambda: set(region_keys),
        "set_keys": lambda keys: region_keys.clear() or region_keys.update(keys),
    }
    widget.regions = [region]
    session = EditableCaptureSession(max_keys=1)

    assert session.begin_region_editing(widget, region) is True
    session.capture_key(widget, make_key("I", 73))
    result = session.finish(widget, apply_changes=True)

    assert result is not None
    assert result.region is region
    assert result.original_keys == {original}
    assert session.is_editing is False


def test_keep_editing_only_for_current_region():
    widget = FakeEditableWidget()
    region = {
        "id": "default",
        "name": "Default",
        "bounds": (0, 0, 10, 10),
        "get_keys": lambda: set(),
        "set_keys": lambda keys: None,
    }
    widget.regions = [region]
    session = EditableCaptureSession(max_keys=1)

    session.begin_region_editing(widget, region)

    assert session.should_keep_editing_on_click(widget, 5, 5) is True
    assert session.should_keep_editing_on_click(widget, 20, 20) is False


def test_release_commits_each_chord_without_blurring_its_field():
    widget = FakeEditableWidget()
    region = dict(id="tap", name="Tap", get_keys=lambda: widget.final_keys,
                  set_keys=lambda keys: setattr(widget, "final_keys", keys))
    session = EditableCaptureSession(2)
    session.begin_region_editing(widget, region)
    j, k, x = [make_key(name, ord(name)) for name in "JKX"]
    for key in (j, k):
        session.capture_key(widget, key)
        assert session.release_key(widget, key).region is region
        assert session.is_editing and widget.final_keys == {KeyCombination([key])}

    session.capture_key(widget, j)
    session.capture_key(widget, k)
    session.capture_key(widget, x)
    session.capture_key(widget, j)  # OS repeat must not replace the pending chord.
    for key in (k, x):
        assert session.release_key(widget, key) is None
    assert session.release_key(widget, j).original_keys == {KeyCombination([k])}
    assert widget.final_keys == {KeyCombination([j, x])}
    assert session.finish(widget).region is None  # Already registered on release.


def test_single_input_region_uses_last_new_press_until_focus_moves():
    widget = FakeEditableWidget()
    region = dict(id="up", name="Up", get_keys=lambda: widget.final_keys,
                  set_keys=lambda keys: setattr(widget, "final_keys", keys))
    session = EditableCaptureSession(1)
    session.begin_region_editing(widget, region)
    ctrl, y = Key("Ctrl_L", 0xffe3, KeyType.MODIFIER), make_key("Y", 89)
    session.capture_key(widget, ctrl)
    session.capture_key(widget, y)
    session.release_key(widget, y)
    session.capture_key(widget, ctrl)  # Repeat of the held prefix.
    session.finish(widget)
    assert widget.final_keys == {KeyCombination([y])}
