from __future__ import annotations

from waydroid_helper.controller.core.event_bus import (
    Event,
    EventBus,
    EventType,
)


def test_event_bus_dispatches_by_priority_then_subscription_order():
    bus = EventBus()
    calls: list[str] = []

    bus.subscribe(EventType.CUSTOM, lambda event: calls.append("low"), priority=0)
    bus.subscribe(EventType.CUSTOM, lambda event: calls.append("high"), priority=10)
    bus.subscribe(EventType.CUSTOM, lambda event: calls.append("high-second"), priority=10)

    bus.emit(Event(EventType.CUSTOM, object(), None))

    assert calls == ["high", "high-second", "low"]


def test_event_bus_filter_and_unsubscribe_by_subscriber():
    bus = EventBus()
    subscriber = object()
    calls: list[str] = []

    bus.subscribe(
        EventType.CUSTOM,
        lambda event: calls.append(event.data),
        filter=lambda event: event.data == "accepted",
        subscriber=subscriber,
    )

    bus.emit(Event(EventType.CUSTOM, object(), "ignored"))
    bus.emit(Event(EventType.CUSTOM, object(), "accepted"))
    removed = bus.unsubscribe_by_subscriber(subscriber)
    bus.emit(Event(EventType.CUSTOM, object(), "accepted"))

    assert calls == ["accepted"]
    assert removed == 1


def test_event_bus_continues_after_handler_error():
    bus = EventBus()
    calls: list[str] = []

    def failing_handler(event):
        calls.append("failing")
        raise RuntimeError("boom")

    bus.subscribe(EventType.CUSTOM, failing_handler)
    bus.subscribe(EventType.CUSTOM, lambda event: calls.append("after"))

    bus.emit(Event(EventType.CUSTOM, object(), None))

    assert calls == ["failing", "after"]


def test_event_bus_dispatches_only_to_matching_event_type():
    bus = EventBus()
    calls: list[str] = []

    bus.subscribe(EventType.CUSTOM, lambda event: calls.append(event.data))
    bus.subscribe(EventType.MODE_CHANGED, lambda event: calls.append("wrong"))

    bus.emit(Event(EventType.CUSTOM, object(), "payload"))

    assert calls == ["payload"]
