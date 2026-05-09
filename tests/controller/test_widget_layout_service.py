from __future__ import annotations

import json

from waydroid_helper.controller.app.widget_layout_service import WidgetLayoutService
from waydroid_helper.controller.core.event_bus import EventBus
from waydroid_helper.controller.core.key_system import Key, KeyCombination, KeyRegistry, KeyType
from waydroid_helper.controller.core.runtime import (
    ControllerRuntimeContext,
    ScreenGeometry,
)
from waydroid_helper.controller.core.utils import PointerIdManager
from waydroid_helper.controller.widgets.base import BaseWidget


KEY_A = Key("A", 65, KeyType.CHARACTER)
COMBO_A = KeyCombination([KEY_A])


class FakeConfigManager:
    def __init__(self, configs=None):
        self.configs = configs or {}
        self.deserialized = None

    def serialize(self):
        return self.configs

    def deserialize(self, data):
        self.deserialized = data


class FakeWidget:
    def __init__(self, text="", config=None):
        self.x = 10
        self.y = 20
        self.width = 30
        self.height = 40
        self.text = text
        self.final_keys = {COMBO_A}
        self.config_manager = FakeConfigManager(config)

    def get_layout_key_mappings(self):
        return set(self.final_keys)

    def get_config_manager(self):
        return self.config_manager


class FakeFactory:
    def __init__(self):
        self.created_kwargs = []
        self.created_widgets = []

    def create_widget(self, widget_type, **kwargs):
        widget = FakeWidget(text=kwargs.get("text", ""))
        self.created_kwargs.append((widget_type, kwargs))
        self.created_widgets.append(widget)
        return widget


def make_service():
    screen_geometry = ScreenGeometry()
    screen_geometry.set_host_resolution(200, 300)
    return WidgetLayoutService(
        ControllerRuntimeContext(
            event_bus=EventBus(),
            screen_geometry=screen_geometry,
            pointer_id_manager=PointerIdManager(),
            key_registry=KeyRegistry(),
        )
    )


def test_widget_layout_service_serializes_widgets():
    service = make_service()
    widget = FakeWidget(text="Tap", config={"enabled": {"value": True}})

    layout = service.serialize_layout([widget])

    assert layout["version"] == BaseWidget.WIDGET_VERSION
    assert layout["screen_resolution"] == {"width": 200, "height": 300}
    assert layout["widgets"][0]["default_keys"] == [["A"]]
    assert layout["widgets"][0]["config"] == {"enabled": {"value": True}}


def test_widget_layout_service_loads_scaled_macro_layout(tmp_path):
    service = make_service()
    factory = FakeFactory()
    created_positions = []
    cleared = []
    layout_path = tmp_path / "layout.json"
    layout_path.write_text(
        json.dumps(
            {
                "version": BaseWidget.WIDGET_VERSION,
                "screen_resolution": {"width": 100, "height": 100},
                "widgets": [
                    {
                        "type": "macro",
                        "x": 5,
                        "y": 7,
                        "width": 20,
                        "height": 30,
                        "text": "Macro",
                        "default_keys": [["A"]],
                        "config": {
                            "macro_command": {"value": "click 10,20"}
                        },
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    count = service.load_layout(
        str(layout_path),
        factory,
        lambda: cleared.append(True),
        lambda widget, x, y: created_positions.append((widget, x, y)),
    )

    assert count == 1
    assert cleared == [True]
    assert created_positions[0][1:] == (10, 21)
    assert factory.created_kwargs[0][1]["width"] == 40
    assert factory.created_kwargs[0][1]["height"] == 90
    assert factory.created_widgets[0].config_manager.deserialized == {
        "macro_command": {"value": "click 20,60"}
    }
