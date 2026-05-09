from __future__ import annotations

from waydroid_helper.controller.app.widget_mapping_registrar import (
    WidgetMappingRegistrar,
)
from waydroid_helper.controller.core.key_system import Key, KeyCombination, KeyType


KEY_A = Key("A", 65, KeyType.CHARACTER)
KEY_B = Key("B", 66, KeyType.CHARACTER)
COMBO_A = KeyCombination([KEY_A])
COMBO_B = KeyCombination([KEY_B])


class SingleKeyWidget:
    def __init__(self, text: str = ""):
        self.final_keys = {COMBO_A}
        self.text = text

    def get_layout_key_mappings(self):
        return set(self.final_keys)

    def set_text_if_empty(self, text: str):
        if self.text:
            return False
        self.text = text
        return True


class MultiKeyWidget:
    def get_all_key_mappings(self):
        return {COMBO_A: "left", COMBO_B: "right"}


def test_register_single_key_widget_updates_empty_display_text():
    registered: list[tuple[object, KeyCombination]] = []
    widget = SingleKeyWidget()
    registrar = WidgetMappingRegistrar(
        lambda target, key_combination: registered.append(
            (target, key_combination)
        ) or True
    )

    assert registrar.register_widget(widget) == 1
    assert registered == [(widget, COMBO_A)]
    assert widget.text == str(COMBO_A)


def test_register_single_key_widget_preserves_existing_display_text():
    widget = SingleKeyWidget(text="Custom")
    registrar = WidgetMappingRegistrar(lambda target, key_combination: True)

    assert registrar.register_widget(widget) == 1
    assert widget.text == "Custom"


def test_register_multi_key_widget_registers_each_declared_mapping():
    registered: list[KeyCombination] = []
    widget = MultiKeyWidget()
    registrar = WidgetMappingRegistrar(
        lambda target, key_combination: registered.append(key_combination) or True
    )

    assert registrar.register_widget(widget) == 2
    assert registered == [COMBO_A, COMBO_B]


def test_register_widget_returns_only_successful_subscriptions():
    widget = SingleKeyWidget()
    registrar = WidgetMappingRegistrar(lambda target, key_combination: False)

    assert registrar.register_widget(widget) == 0
    assert widget.text == ""
