from __future__ import annotations

from waydroid_helper.controller.core.event_bus import Event, EventBus, EventType
from waydroid_helper.controller.widgets.config import (
    ConfigManager,
    ConfigWidgetRegistry,
    create_textarea_config,
)


class FakeWidget:
    def __init__(self):
        self.unparent_calls = 0

    def unparent(self):
        self.unparent_calls += 1


def test_config_widget_registry_owns_event_bus_subscription_cleanup():
    bus = EventBus()
    registry = ConfigWidgetRegistry(bus)
    widget = FakeWidget()
    calls: list[str] = []

    bus.subscribe(
        EventType.CUSTOM,
        lambda event: calls.append(event.data),
        subscriber=widget,
    )
    registry.bind("macro_command", widget)

    bus.emit(Event(EventType.CUSTOM, object(), "before-clear"))
    registry.clear()
    bus.emit(Event(EventType.CUSTOM, object(), "after-clear"))

    assert calls == ["before-clear"]
    assert widget.unparent_calls == 1
    assert registry.widgets == {}


def test_textarea_config_gets_event_bus_from_manager_and_keeps_visibility():
    bus = EventBus()
    manager = ConfigManager(bus)
    config = create_textarea_config(
        key="macro_command",
        label="Macro Command",
        visible=False,
    )

    assert config.event_bus is None

    manager.add_config(config)

    assert config.event_bus is bus
    assert config.visible is False
