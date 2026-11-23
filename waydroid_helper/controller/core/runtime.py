#!/usr/bin/env python3
"""Runtime context objects shared by one controller window.

The controller may host multiple windows in one process, so runtime state must
be instance-owned instead of hidden behind module globals.  This module keeps
that mutable state explicit and injectable.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Protocol

from waydroid_helper.controller.core.event_bus import EventBus
from waydroid_helper.controller.core.key_system import KeyCombination, KeyRegistry
from waydroid_helper.controller.core.utils import PointerIdManager
from waydroid_helper.util.log import logger

if TYPE_CHECKING:
    from waydroid_helper.controller.core.handler.event_handlers import (
        InputEvent,
        InputEventType,
    )


class WidgetInputEventFactory(Protocol):
    """Input normalization operations required by editable widgets.

    The protocol lives in the core runtime boundary so widget code can consume
    normalized input without importing the GTK application adapter that
    implements these operations.
    """

    def create_key_event(
        self,
        event_type: "InputEventType | str",
        controller: Any,
        keyval: int,
        keycode: int,
        state: int,
    ) -> "InputEvent | None": ...

    def create_scroll_event(
        self, controller: Any, dx: float, dy: float
    ) -> "InputEvent": ...

    def create_mouse_capture_event(
        self,
        event_type: "InputEventType | str",
        controller: Any,
        n_press: int,
        x: float,
        y: float,
    ) -> "InputEvent | None": ...


class WidgetKeyMappingService(Protocol):
    """Mapping operations used by widgets and decorator-owned behavior."""

    def subscribe(
        self,
        target: Any,
        key_combination: KeyCombination,
        condition: Callable[[], bool] | None = None,
        required_states: list[str] | None = None,
        reentrant: bool | None = None,
    ) -> bool: ...

    def unsubscribe(self, target: Any) -> bool: ...

    def unsubscribe_key(
        self,
        target: Any,
        key_combination: KeyCombination,
    ) -> bool: ...

    def get_target_reentrant(self, target: Any) -> bool: ...


class PointerInputOwnership:
    """Coordinate exclusive ownership of host pointer input.

    Relative-pointer components such as Aim and Fire translate host mouse
    motion into Android finger events. While one of them owns the pointer, the
    default mouse handler must not also translate the same GTK event stream into
    ``PointerId.MOUSE`` events. Mixing those two streams can produce a mouse
    MOVE without a preceding mouse DOWN while a finger is already active.

    Ownership is intentionally instance-scoped and identity-based: all widgets
    in one controller window share this object through ControllerRuntimeContext,
    while separate windows remain independent.
    """

    def __init__(self) -> None:
        self._owner: Any | None = None

    def acquire(self, owner: Any) -> bool:
        if self._owner is None:
            self._owner = owner
            logger.debug(
                "Pointer input ownership acquired by %s",
                type(owner).__name__,
            )
            return True

        if self._owner is owner:
            return True

        logger.warning(
            "Pointer input ownership is already held by %s; %s cannot acquire it",
            type(self._owner).__name__,
            type(owner).__name__,
        )
        return False

    def release(self, owner: Any) -> bool:
        if self._owner is not owner:
            if self._owner is not None:
                logger.warning(
                    "%s attempted to release pointer input owned by %s",
                    type(owner).__name__,
                    type(self._owner).__name__,
                )
            return False

        self._owner = None
        logger.debug(
            "Pointer input ownership released by %s",
            type(owner).__name__,
        )
        return True

    def transfer(self, current_owner: Any, next_owner: Any) -> bool:
        """Atomically hand pointer routing to another component.

        Aim and Fire rebuild the compositor's relative-pointer constraint during
        a handoff, but the host pointer remains logically captured throughout
        that operation. Replacing the owner without passing through ``None``
        prevents default mouse injection and cursor restoration from observing a
        false gap between the two physical locks.
        """
        if self._owner is not current_owner:
            logger.warning(
                "%s cannot transfer pointer input owned by %s",
                type(current_owner).__name__,
                self.owner_name(),
            )
            return False

        self._owner = next_owner
        logger.debug(
            "Pointer input ownership transferred from %s to %s",
            type(current_owner).__name__,
            type(next_owner).__name__,
        )
        return True

    def blocks_default_mouse_input(self) -> bool:
        return self._owner is not None

    def owner_name(self) -> str | None:
        if self._owner is None:
            return None
        return type(self._owner).__name__


@dataclass
class ScreenGeometry:
    """Per-controller screen dimensions used for host and device scaling."""

    width: int = 0
    height: int = 0
    host_width: int = 0
    host_height: int = 0
    _missing_device_resolution_logged: bool = field(default=False, init=False, repr=False)

    def set_resolution(self, width: int, height: int) -> None:
        self.width = width
        self.height = height

    def get_resolution(self) -> tuple[int, int]:
        return self.width, self.height

    def set_host_resolution(self, width: int, height: int) -> None:
        self.host_width = width
        self.host_height = height

    def get_host_resolution(self) -> tuple[int, int]:
        return self.host_width, self.host_height

    def get_device_resolution_for_client(
        self, client_width: int, client_height: int
    ) -> tuple[int, int]:
        if self.width > 0 and self.height > 0:
            return self.width, self.height

        if not self._missing_device_resolution_logged:
            logger.warning(
                "Device resolution not set for this controller context; "
                "using client resolution %sx%s.",
                client_width,
                client_height,
            )
            self._missing_device_resolution_logged = True

        return client_width, client_height


@dataclass(frozen=True)
class DefaultHandlerRuntimeConfig:
    """Snapshot of persisted defaults used by the default input handler."""

    keyboard_inject_mode: str = "mixed"
    mouse_natural_scroll: bool = True
    mouse_hover: bool = False


@dataclass(frozen=True)
class ControllerRuntimeContext:
    """Complete per-window dependency set shared by controller objects.

    Every widget is created from this context. Requiring the full dependency
    set prevents widgets from constructing private runtime state or discovering
    application services through their GTK root window.
    """

    event_bus: EventBus
    screen_geometry: ScreenGeometry
    pointer_id_manager: PointerIdManager
    key_registry: KeyRegistry
    input_event_factory: WidgetInputEventFactory
    key_mapping_service: WidgetKeyMappingService
    is_edit_mode: Callable[[], bool]
    pointer_input_ownership: PointerInputOwnership = field(
        default_factory=PointerInputOwnership
    )
    default_handler_config: DefaultHandlerRuntimeConfig = field(
        default_factory=DefaultHandlerRuntimeConfig
    )
