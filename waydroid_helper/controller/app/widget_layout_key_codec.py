#!/usr/bin/env python3
"""Encode and decode widget key mappings in layout files."""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable

from waydroid_helper.controller.core.key_system import Key, KeyCombination, KeyRegistry


@runtime_checkable
class KeyLayoutProvider(Protocol):
    def get_layout_key_mappings(self) -> set[KeyCombination]:
        ...


@runtime_checkable
class DirectionalKeyLayoutProvider(Protocol):
    def get_layout_direction_keys(self) -> dict[str, KeyCombination | None]:
        ...


class WidgetLayoutKeyCodec:
    """Keeps layout key mapping shape out of UI menu code."""

    DIRECTIONAL_PAD_TYPE = "directionalpad"
    DIRECTION_KEYS_FIELD = "direction_keys"
    DEFAULT_KEYS_FIELD = "default_keys"
    DIRECTIONS = ("up", "down", "left", "right")

    def __init__(self, key_registry: KeyRegistry):
        self._key_registry = key_registry

    def serialize_key_combination(
        self, key_combination: KeyCombination | None
    ) -> list[str]:
        if not key_combination:
            return []
        return [str(key) for key in key_combination.keys]

    def deserialize_key_combination(
        self, key_names: list[str]
    ) -> KeyCombination | None:
        keys: list[Key] = []
        for key_name in key_names:
            key = self._key_registry.deserialize_key(key_name)
            if key:
                keys.append(key)
        return KeyCombination(keys) if keys else None

    def serialize_widget_keys(self, widget_type: str, widget: Any) -> dict[str, Any]:
        if widget_type == self.DIRECTIONAL_PAD_TYPE:
            return self._serialize_directional_pad_keys(widget)

        if not isinstance(widget, KeyLayoutProvider):
            return {}

        default_keys = widget.get_layout_key_mappings()
        if not default_keys:
            return {}

        return {
            self.DEFAULT_KEYS_FIELD: [
                self.serialize_key_combination(key_combination)
                for key_combination in default_keys
            ]
        }

    def apply_widget_keys_to_create_kwargs(
        self,
        widget_type: str,
        widget_data: dict[str, Any],
        create_kwargs: dict[str, Any],
    ) -> None:
        if widget_type == self.DIRECTIONAL_PAD_TYPE:
            self._apply_directional_pad_keys(widget_data, create_kwargs)
            return

        default_keys = []
        for key_names in widget_data.get(self.DEFAULT_KEYS_FIELD, []):
            key_combination = self.deserialize_key_combination(key_names)
            if key_combination:
                default_keys.append(key_combination)
        create_kwargs[self.DEFAULT_KEYS_FIELD] = default_keys

    def _serialize_directional_pad_keys(self, widget: Any) -> dict[str, Any]:
        if not isinstance(widget, DirectionalKeyLayoutProvider):
            return {}

        direction_keys = widget.get_layout_direction_keys()
        if not direction_keys:
            return {}

        return {
            self.DIRECTION_KEYS_FIELD: {
                direction: self.serialize_key_combination(
                    direction_keys.get(direction)
                )
                for direction in self.DIRECTIONS
            }
        }

    def _apply_directional_pad_keys(
        self,
        widget_data: dict[str, Any],
        create_kwargs: dict[str, Any],
    ) -> None:
        direction_data = widget_data.get(self.DIRECTION_KEYS_FIELD)
        if not direction_data:
            return

        create_kwargs[self.DIRECTION_KEYS_FIELD] = {
            direction: self.deserialize_key_combination(
                direction_data.get(direction, [])
            )
            for direction in self.DIRECTIONS
        }
