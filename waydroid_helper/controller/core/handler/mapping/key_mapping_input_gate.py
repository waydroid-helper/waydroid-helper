#!/usr/bin/env python3
"""Pause key mapping while Android reports editable input focus."""

from __future__ import annotations

from waydroid_helper.controller.core.event_bus import Event, EventBus, EventType
from waydroid_helper.controller.core.handler.event_handlers import (
    InputEvent,
    InputEventSource,
    InputEventType,
)
from waydroid_helper.controller.core.input_state import AndroidInputState
from waydroid_helper.util.log import logger

from .key_mapping_event_handler import KeyMappingEventHandler
from .key_mapping_manager import KeyMappingManager


class KeyMappingInputStateGate:
    """Owns the policy for Android text input temporarily disabling mappings."""

    def __init__(
        self,
        event_bus: EventBus,
        key_mapping_handler: KeyMappingEventHandler,
        key_mapping_manager: KeyMappingManager,
    ) -> None:
        self.event_bus = event_bus
        self.key_mapping_handler = key_mapping_handler
        self.key_mapping_manager = key_mapping_manager
        self._is_input_active = False
        event_bus.subscribe(
            EventType.ANDROID_INPUT_STATE_CHANGED,
            self._on_android_input_state_changed,
            subscriber=self,
        )

    def _on_android_input_state_changed(
        self, event: Event[AndroidInputState | bool]
    ) -> None:
        input_state = event.data
        is_input_active = (
            input_state.is_input_active
            if isinstance(input_state, AndroidInputState)
            else bool(input_state)
        )
        if self._is_input_active == is_input_active:
            return

        self._is_input_active = is_input_active
        if is_input_active:
            release_event = InputEvent(
                event_type=InputEventType.KEY_RELEASE,
                source=InputEventSource.ANDROID_ACCESSIBILITY,
            )
            self.key_mapping_manager.release_all_triggered_mappings(release_event)
            # Widgets such as Aim own pointer locks, timers, and async state that
            # can outlive the mapping manager's pressed-key table. Broadcast a
            # source-neutral cancellation event before pausing key mappings so
            # every stateful component can release touches and clear local state.
            self.event_bus.emit(
                Event(EventType.COMPONENT_CANCEL_TRIGGER_STATE, self, release_event)
            )
            self.key_mapping_handler.set_enabled(False)
            logger.info("Android input focus active; key mapping paused")
            return

        self.key_mapping_handler.set_enabled(True)
        logger.info("Android input focus inactive; key mapping resumed")

    @property
    def is_input_active(self) -> bool:
        return self._is_input_active
