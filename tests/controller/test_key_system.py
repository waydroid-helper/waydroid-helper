from __future__ import annotations

from waydroid_helper.controller.core.key_system import (
    KeyRegistry,
    KeyType,
    STANDARD_KEY_SYMBOLS,
)


class FakeSymbolResolver:
    def __init__(self):
        self.names_by_code = {65421: "KP_Enter"}
        self.codes_by_name = {"KP_Enter": 65421}

    def name_from_code(self, code: int) -> str | None:
        return self.names_by_code.get(code)

    def code_from_name(self, name: str) -> int | None:
        return self.codes_by_name.get(name)


def test_key_registry_registers_standard_keys_without_toolkit_imports():
    registry = KeyRegistry()

    ctrl = registry.get_by_name("Ctrl_L")
    up = registry.get_by_name("Up")

    assert ctrl is not None
    assert ctrl.keyval == STANDARD_KEY_SYMBOLS["Ctrl_L"]
    assert ctrl.key_type == KeyType.MODIFIER
    assert up is not None
    assert up.keyval == STANDARD_KEY_SYMBOLS["Up"]
    assert up.key_type == KeyType.FUNCTION


def test_key_registry_uses_symbol_resolver_for_unknown_key_codes():
    registry = KeyRegistry(FakeSymbolResolver())

    key = registry.create_from_keyval(65421)

    assert key is not None
    assert key.name == "KP_Enter"
    assert key.keyval == 65421
    assert key.key_type == KeyType.SPECIAL


def test_key_registry_deserializes_dynamic_symbol_with_resolver():
    registry = KeyRegistry(FakeSymbolResolver())

    key = registry.deserialize_key("KP_Enter")

    assert key is not None
    assert key.name == "KP_Enter"
    assert key.keyval == 65421
    assert registry.get_by_name("KP_Enter") == key
