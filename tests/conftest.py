from __future__ import annotations

import importlib.machinery
import sys
import types
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CONTROLLER_DIR = ROOT / "waydroid_helper" / "controller"

if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


class DummyLogger:
    def __getattr__(self, name: str):
        def log_noop(*args, **kwargs):
            return None

        return log_noop


def install_package_stub(name: str, path: Path | None = None) -> types.ModuleType:
    module = types.ModuleType(name)
    module.__package__ = name
    module.__spec__ = importlib.machinery.ModuleSpec(
        name, loader=None, is_package=True
    )
    if path is not None:
        module.__path__ = [str(path)]
    sys.modules[name] = module
    return module


# The controller package imports the GTK window from __init__.py. Unit tests for
# the mapping core should not create application windows, start log listener
# processes, or depend on a display server, so the package hierarchy is stubbed
# before test modules import controller internals.
import waydroid_helper

controller_pkg = install_package_stub(
    "waydroid_helper.controller", CONTROLLER_DIR
)
core_pkg = install_package_stub(
    "waydroid_helper.controller.core", CONTROLLER_DIR / "core"
)
handler_pkg = install_package_stub(
    "waydroid_helper.controller.core.handler",
    CONTROLLER_DIR / "core" / "handler",
)
mapping_pkg = install_package_stub(
    "waydroid_helper.controller.core.handler.mapping",
    CONTROLLER_DIR / "core" / "handler" / "mapping",
)
util_pkg = install_package_stub("waydroid_helper.util")
log_module = types.ModuleType("waydroid_helper.util.log")
log_module.logger = DummyLogger()

sys.modules["waydroid_helper.util.log"] = log_module

setattr(waydroid_helper, "controller", controller_pkg)
setattr(waydroid_helper, "util", util_pkg)
setattr(controller_pkg, "core", core_pkg)
setattr(core_pkg, "handler", handler_pkg)
setattr(handler_pkg, "mapping", mapping_pkg)
setattr(util_pkg, "log", log_module)

from waydroid_helper.controller.core.event_bus import Event, EventBus, EventType
from waydroid_helper.controller.core.key_system import KeyCombination, KeyRegistry
from waydroid_helper.controller.core.runtime import (
    ControllerRuntimeContext,
    DefaultHandlerRuntimeConfig,
    ScreenGeometry,
)
from waydroid_helper.controller.core.utils import PointerIdManager, is_point_in_rect
from waydroid_helper.controller.core.handler.event_handlers import (
    EventHandlerPriority,
    InputEvent,
    InputEventHandler,
    InputEventHandlerChain,
    InputEventSource,
    InputEventType,
    InputModifierState,
)
from waydroid_helper.controller.core.handler.mapping.key_mapping_manager import (
    KeyMappingManager,
    KeyMappingTarget,
)

setattr(core_pkg, "Event", Event)
setattr(core_pkg, "EventBus", EventBus)
setattr(core_pkg, "EventType", EventType)
setattr(core_pkg, "KeyCombination", KeyCombination)
setattr(core_pkg, "KeyRegistry", KeyRegistry)
setattr(core_pkg, "ControllerRuntimeContext", ControllerRuntimeContext)
setattr(core_pkg, "DefaultHandlerRuntimeConfig", DefaultHandlerRuntimeConfig)
setattr(core_pkg, "ScreenGeometry", ScreenGeometry)
setattr(core_pkg, "PointerIdManager", PointerIdManager)
setattr(core_pkg, "is_point_in_rect", is_point_in_rect)

setattr(handler_pkg, "EventHandlerPriority", EventHandlerPriority)
setattr(handler_pkg, "InputEvent", InputEvent)
setattr(handler_pkg, "InputEventHandler", InputEventHandler)
setattr(handler_pkg, "InputEventHandlerChain", InputEventHandlerChain)
setattr(handler_pkg, "InputEventSource", InputEventSource)
setattr(handler_pkg, "InputEventType", InputEventType)
setattr(handler_pkg, "InputModifierState", InputModifierState)
setattr(handler_pkg, "KeyMappingManager", KeyMappingManager)
setattr(handler_pkg, "KeyMappingTarget", KeyMappingTarget)
setattr(mapping_pkg, "KeyMappingManager", KeyMappingManager)
setattr(mapping_pkg, "KeyMappingTarget", KeyMappingTarget)
