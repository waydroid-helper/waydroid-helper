#!/usr/bin/env python3
"""Runtime context objects shared by one controller window.

The controller may host multiple windows in one process, so runtime state must
be instance-owned instead of hidden behind module globals.  This module keeps
that mutable state explicit and injectable.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from waydroid_helper.controller.core.event_bus import EventBus
from waydroid_helper.controller.core.key_system import KeyRegistry
from waydroid_helper.controller.core.utils import PointerIdManager
from waydroid_helper.util.log import logger


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
                "falling back to client resolution %sx%s.",
                client_width,
                client_height,
            )
            self._missing_device_resolution_logged = True

        return client_width, client_height


@dataclass(frozen=True)
class DefaultHandlerRuntimeConfig:
    """Snapshot of persisted defaults used by the fallback input handler."""

    keyboard_inject_mode: str = "mixed"
    mouse_natural_scroll: bool = True
    mouse_hover: bool = False


@dataclass(frozen=True)
class ControllerRuntimeContext:
    """Explicit dependencies shared by widgets, handlers, and app services."""

    event_bus: EventBus
    screen_geometry: ScreenGeometry
    pointer_id_manager: PointerIdManager
    key_registry: KeyRegistry
    default_handler_config: DefaultHandlerRuntimeConfig = field(
        default_factory=DefaultHandlerRuntimeConfig
    )
