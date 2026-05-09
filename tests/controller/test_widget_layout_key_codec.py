from __future__ import annotations

from waydroid_helper.controller.app.widget_layout_key_codec import WidgetLayoutKeyCodec
from waydroid_helper.controller.core.key_system import Key, KeyCombination, KeyRegistry, KeyType


KEY_A = Key("A", 65, KeyType.CHARACTER)
KEY_B = Key("B", 66, KeyType.CHARACTER)
KEY_C = Key("C", 67, KeyType.CHARACTER)
COMBO_A = KeyCombination([KEY_A])
COMBO_B = KeyCombination([KEY_B])
COMBO_C = KeyCombination([KEY_C])


class SingleKeyWidget:
    final_keys = {COMBO_A, COMBO_B}

    def get_layout_key_mappings(self):
        return set(self.final_keys)


class DirectionalPadWidget:
    direction_keys = {
        "up": COMBO_A,
        "down": COMBO_B,
        "left": COMBO_C,
        "right": None,
    }

    def get_layout_direction_keys(self):
        return dict(self.direction_keys)


def test_serializes_and_deserializes_key_combination_names():
    codec = WidgetLayoutKeyCodec(KeyRegistry())

    serialized = codec.serialize_key_combination(COMBO_A)

    assert serialized == ["A"]
    assert codec.deserialize_key_combination(serialized) == COMBO_A
    assert codec.serialize_key_combination(None) == []
    assert codec.deserialize_key_combination([]) is None


def test_serializes_default_widget_keys_without_ui_shape_leakage():
    codec = WidgetLayoutKeyCodec(KeyRegistry())
    data = codec.serialize_widget_keys("singleclick", SingleKeyWidget())

    assert sorted(data["default_keys"]) == [["A"], ["B"]]


def test_serializes_directional_pad_keys():
    codec = WidgetLayoutKeyCodec(KeyRegistry())
    data = codec.serialize_widget_keys("directionalpad", DirectionalPadWidget())

    assert data == {
        "direction_keys": {
            "up": ["A"],
            "down": ["B"],
            "left": ["C"],
            "right": [],
        }
    }


def test_applies_default_keys_to_create_kwargs():
    codec = WidgetLayoutKeyCodec(KeyRegistry())
    kwargs: dict[str, object] = {}

    codec.apply_widget_keys_to_create_kwargs(
        "singleclick",
        {"default_keys": [["A"], ["B"]]},
        kwargs,
    )

    assert kwargs["default_keys"] == [COMBO_A, COMBO_B]


def test_applies_directional_pad_keys_to_create_kwargs():
    codec = WidgetLayoutKeyCodec(KeyRegistry())
    kwargs: dict[str, object] = {}

    codec.apply_widget_keys_to_create_kwargs(
        "directionalpad",
        {
            "direction_keys": {
                "up": ["A"],
                "down": ["B"],
                "left": ["C"],
                "right": [],
            }
        },
        kwargs,
    )

    assert kwargs["direction_keys"] == {
        "up": COMBO_A,
        "down": COMBO_B,
        "left": COMBO_C,
        "right": None,
    }
