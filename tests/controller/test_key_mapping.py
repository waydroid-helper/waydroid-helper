from __future__ import annotations

import asyncio

import pytest

from waydroid_helper.controller.core.event_bus import Event, EventBus, EventType
from waydroid_helper.controller.core.handler.event_handlers import (
    EventHandlerPriority,
    InputEvent,
    InputEventHandler,
    InputEventHandlerChain,
    InputEventSource,
    InputEventType,
)
from waydroid_helper.controller.core.handler.mapping.key_mapping_event_handler import (
    KeyMappingEventHandler,
)
from waydroid_helper.controller.core.handler.mapping.key_mapping_input_gate import (
    KeyMappingInputStateGate,
)
from waydroid_helper.controller.core.handler.mapping.key_mapping_manager import (
    KeyMappingManager,
)
from waydroid_helper.controller.core.input_state import AndroidInputState
from waydroid_helper.controller.core.key_system import Key, KeyCombination, KeyType
from waydroid_helper.controller.widgets.components.aim import Aim, AimState


KEY_A = Key("A", 65, KeyType.CHARACTER)
KEY_B = Key("B", 66, KeyType.CHARACTER)
KEY_CTRL = Key("Ctrl_L", 65507, KeyType.MODIFIER)
MOUSE_RIGHT = Key("Mouse_Right", -3, KeyType.MOUSE)


class MappingTarget:
    IS_REENTRANT = False

    def __init__(self, trigger_result: bool = True, release_result: bool = True):
        self.trigger_result = trigger_result
        self.release_result = release_result
        self.triggered: list[tuple[KeyCombination | None, InputEvent | None]] = []
        self.released: list[tuple[KeyCombination | None, InputEvent | None]] = []

    def on_key_triggered(
        self,
        key_combination: KeyCombination | None = None,
        event: InputEvent | None = None,
    ) -> bool:
        self.triggered.append((key_combination, event))
        return self.trigger_result

    def on_key_released(
        self,
        key_combination: KeyCombination | None = None,
        event: InputEvent | None = None,
    ) -> bool:
        self.released.append((key_combination, event))
        return self.release_result


class ReentrantMappingTarget(MappingTarget):
    IS_REENTRANT = True


class SpyDefaultHandler(InputEventHandler):
    def __init__(self):
        super().__init__(EventHandlerPriority.LOWEST)
        self.events: list[InputEvent] = []

    def can_handle(self, event: InputEvent) -> bool:
        return True

    def handle_event(self, event: InputEvent) -> bool:
        self.events.append(event)
        return True


class FakeTask:
    def __init__(self, done: bool = False):
        self._done = done
        self.cancelled = False

    def done(self) -> bool:
        return self._done

    def cancel(self) -> None:
        self.cancelled = True


class NoPointerManager:
    def get_allocated_id(self, widget):
        return None


@pytest.fixture
def event_bus():
    bus = EventBus()
    yield bus
    bus.clear()


@pytest.fixture
def manager(event_bus):
    return KeyMappingManager(event_bus)


def key_event(event_type: InputEventType, key: Key) -> InputEvent:
    return InputEvent(event_type=event_type, key=key)


def mouse_event(event_type: InputEventType, key: Key, button: int) -> InputEvent:
    return InputEvent(event_type=event_type, key=key, button=button)


def combo(*keys: Key) -> KeyCombination:
    return KeyCombination(list(keys))


def test_mapping_hit_consumes_event_before_default_handler(manager):
    target = MappingTarget()
    manager.subscribe(target, combo(KEY_A))

    chain = InputEventHandlerChain()
    chain.add_handler(KeyMappingEventHandler(manager))
    default_handler = SpyDefaultHandler()
    chain.add_handler(default_handler)

    event = key_event(InputEventType.KEY_PRESS, KEY_A)

    assert chain.process_event(event) is True
    assert target.triggered == [(combo(KEY_A), event)]
    assert default_handler.events == []


def test_unmapped_event_falls_through_to_default_handler(manager):
    target = MappingTarget()
    manager.subscribe(target, combo(KEY_A))

    chain = InputEventHandlerChain()
    chain.add_handler(KeyMappingEventHandler(manager))
    default_handler = SpyDefaultHandler()
    chain.add_handler(default_handler)

    event = key_event(InputEventType.KEY_PRESS, KEY_B)

    assert chain.process_event(event) is True
    assert target.triggered == []
    assert default_handler.events == [event]


def test_key_combination_triggers_when_all_keys_are_pressed(manager):
    target = MappingTarget()
    key_combination = combo(KEY_CTRL, KEY_A)
    manager.subscribe(target, key_combination)

    assert manager.handle_key_press(key_event(InputEventType.KEY_PRESS, KEY_CTRL)) is False

    press_a = key_event(InputEventType.KEY_PRESS, KEY_A)
    assert manager.handle_key_press(press_a) is True
    assert target.triggered == [(key_combination, press_a)]


def test_key_release_calls_release_callback_for_triggered_mapping(manager):
    target = MappingTarget()
    key_combination = combo(KEY_A)
    manager.subscribe(target, key_combination)

    manager.handle_key_press(key_event(InputEventType.KEY_PRESS, KEY_A))
    release_a = key_event(InputEventType.KEY_RELEASE, KEY_A)

    assert manager.handle_key_release(release_a) is True
    assert target.released == [(key_combination, release_a)]


def test_non_reentrant_mapping_consumes_repeat_without_retriggering(manager):
    target = MappingTarget()
    manager.subscribe(target, combo(KEY_A))

    first_press = key_event(InputEventType.KEY_PRESS, KEY_A)
    repeat_press = key_event(InputEventType.KEY_PRESS, KEY_A)

    assert manager.handle_key_press(first_press) is True
    assert manager.handle_key_press(repeat_press) is True
    assert target.triggered == [(combo(KEY_A), first_press)]


def test_reentrant_mapping_retriggers_on_repeat_press(manager):
    target = ReentrantMappingTarget()
    manager.subscribe(target, combo(KEY_A))

    first_press = key_event(InputEventType.KEY_PRESS, KEY_A)
    repeat_press = key_event(InputEventType.KEY_PRESS, KEY_A)

    assert manager.handle_key_press(first_press) is True
    assert manager.handle_key_press(repeat_press) is True
    assert target.triggered == [
        (combo(KEY_A), first_press),
        (combo(KEY_A), repeat_press),
    ]


def test_mouse_button_mapping_uses_same_trigger_and_release_flow(manager):
    target = MappingTarget()
    key_combination = combo(MOUSE_RIGHT)
    manager.subscribe(target, key_combination)

    press = mouse_event(InputEventType.MOUSE_PRESS, MOUSE_RIGHT, button=3)
    release = mouse_event(InputEventType.MOUSE_RELEASE, MOUSE_RIGHT, button=3)

    assert manager.handle_key_press(press) is True
    assert manager.handle_key_release(release) is True
    assert target.triggered == [(key_combination, press)]
    assert target.released == [(key_combination, release)]


def test_unsubscribe_removes_target_mapping(manager):
    target = MappingTarget()
    manager.subscribe(target, combo(KEY_A))

    assert manager.unsubscribe(target) is True
    assert manager.handle_key_press(key_event(InputEventType.KEY_PRESS, KEY_A)) is False
    assert target.triggered == []


def test_macro_events_are_normalized_into_mapping_input_events(event_bus, manager):
    target = MappingTarget()
    key_combination = combo(KEY_A)
    manager.subscribe(target, key_combination)

    event_bus.emit(Event(EventType.MACRO_KEY_PRESSED, object(), KEY_A))
    event_bus.emit(Event(EventType.MACRO_KEY_RELEASED, object(), KEY_A))

    assert len(target.triggered) == 1
    assert len(target.released) == 1
    assert target.triggered[0][0] == key_combination
    assert target.released[0][0] == key_combination
    assert target.triggered[0][1].source == InputEventSource.MACRO
    assert target.released[0][1].source == InputEventSource.MACRO


def test_macro_mapping_events_are_scoped_to_their_event_bus_instance():
    bus_a = EventBus()
    bus_b = EventBus()
    manager_a = KeyMappingManager(bus_a)
    manager_b = KeyMappingManager(bus_b)
    target_a = MappingTarget()
    target_b = MappingTarget()

    manager_a.subscribe(target_a, combo(KEY_A))
    manager_b.subscribe(target_b, combo(KEY_A))

    try:
        bus_a.emit(Event(EventType.MACRO_KEY_PRESSED, object(), KEY_A))

        assert len(target_a.triggered) == 1
        assert target_b.triggered == []
    finally:
        bus_a.clear()
        bus_b.clear()


def test_android_input_gate_releases_mappings_and_cancels_component_state(
    event_bus, manager
):
    target = MappingTarget()
    manager.subscribe(target, combo(KEY_A))
    key_mapping_handler = KeyMappingEventHandler(manager)
    gate = KeyMappingInputStateGate(event_bus, key_mapping_handler, manager)
    cancel_events: list[InputEvent] = []
    event_bus.subscribe(
        EventType.COMPONENT_CANCEL_TRIGGER_STATE,
        lambda event: cancel_events.append(event.data),
    )

    manager.handle_key_press(key_event(InputEventType.KEY_PRESS, KEY_A))
    event_bus.emit(
        Event(
            EventType.ANDROID_INPUT_STATE_CHANGED,
            object(),
            AndroidInputState(is_input_active=True, reason="test"),
        )
    )

    assert gate.is_input_active is True
    assert key_mapping_handler.enabled is False
    assert len(target.released) == 1
    assert target.released[0][1].source == InputEventSource.ANDROID_ACCESSIBILITY
    assert len(cancel_events) == 1
    assert cancel_events[0].source == InputEventSource.ANDROID_ACCESSIBILITY


def test_android_input_gate_pauses_only_mapping_handler(event_bus, manager):
    target = MappingTarget()
    manager.subscribe(target, combo(KEY_A))
    key_mapping_handler = KeyMappingEventHandler(manager)
    default_handler = SpyDefaultHandler()
    chain = InputEventHandlerChain()
    chain.add_handler(key_mapping_handler)
    chain.add_handler(default_handler)
    KeyMappingInputStateGate(event_bus, key_mapping_handler, manager)

    event_bus.emit(Event(EventType.ANDROID_INPUT_STATE_CHANGED, object(), True))
    press_a = key_event(InputEventType.KEY_PRESS, KEY_A)

    assert chain.process_event(press_a) is True
    assert target.triggered == []
    assert default_handler.events == [press_a]

    event_bus.emit(Event(EventType.ANDROID_INPUT_STATE_CHANGED, object(), False))
    press_a_after_resume = key_event(InputEventType.KEY_PRESS, KEY_A)

    assert chain.process_event(press_a_after_resume) is True
    assert target.triggered == [(combo(KEY_A), press_a_after_resume)]


def test_aim_cancels_reentrant_state_when_component_cancel_event_arrives(monkeypatch):
    aim = Aim.__new__(Aim)
    aim._state = AimState.AIMING
    aim._current_pos = None
    aim.pointer_id_manager = NoPointerManager()
    running_task = FakeTask()
    created_task = FakeTask()
    aim._aim_task = running_task

    def fake_create_task(coro):
        coro.close()
        return created_task

    monkeypatch.setattr(asyncio, "create_task", fake_create_task)

    Aim._handle_component_cancel_trigger_state(
        aim,
        Event(
            EventType.COMPONENT_CANCEL_TRIGGER_STATE,
            object(),
            InputEvent(
                event_type=InputEventType.KEY_RELEASE,
                source=InputEventSource.ANDROID_ACCESSIBILITY,
            ),
        ),
    )

    assert running_task.cancelled is True
    assert aim._aim_task is created_task
