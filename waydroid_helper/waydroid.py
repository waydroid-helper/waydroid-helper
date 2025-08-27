# pyright: reportAny=false
# pyright: reportAttributeAccessIssue=false,reportUnknownArgumentType=false,reportUnknownMemberType=false

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

import os
from typing import Any

from gi.repository import GLib, GObject

from waydroid_helper.util import SubprocessError, SubprocessManager, Task, logger

CONFIG_PATH = os.environ.get("WAYDROID_CONFIG", "/var/lib/waydroid/waydroid.cfg")

# Import new architecture components
from waydroid_helper.model_controller import ModelController
from waydroid_helper.models import SessionState, ModelState

# Compatibility aliases for existing code
WaydroidState = SessionState
PropsState = ModelState


# 有一说一, 将来直接通过 app_process 跑一个 java 服务器比 subprocess 更好
class PersistPropsCompat(GObject.Object):
    """Compatibility wrapper for persist properties"""

    state = GObject.Property(type=object)

    def __init__(self, controller: ModelController):
        super().__init__()
        self._controller: ModelController = controller
        self.set_property("state", PropsState.UNINITIALIZED)

        # Bind to model state - use GLib.idle_add to ensure proper initialization
        GLib.idle_add(self._setup_state_binding)

        # Set up property bindings for all persist properties
        self._setup_property_bindings()

    def _setup_state_binding(self):
        """Set up state binding after initialization"""
        _ = self._controller.property_model.bind_property(
            "state",
            self,
            "state",
            GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.BIDIRECTIONAL,
        )

    def _setup_property_bindings(self):
        """Set up property bindings - simplified approach"""
        # Instead of dynamic GObject properties, we'll handle property access
        # through get_property/set_property overrides
        pass

    def get_property(self, property_name: str) -> Any:
        """Get property value from model"""
        if property_name == "state":
            return super().get_property(property_name)

        return self._controller.property_model.get_property(property_name)

    def set_property(self, property_name: str, value: Any):
        """Set property value in model"""
        if property_name == "state":
            super().set_property(property_name, value)
            return

        self._controller.property_model.set_property(property_name, value)

    async def fetch(self):
        """Fetch properties (compatibility method)"""
        # This is handled automatically by the controller
        pass

    async def reset(self):
        """Reset properties (compatibility method)"""
        await self._controller.reset_persist_properties()

    async def save(self, name: str):
        """Save a property (compatibility method)"""
        await self._controller.save_persist_property(name)

    async def refresh(self, name: str):
        """Refresh a property from Waydroid (compatibility method)"""
        return await self._controller.refresh_persist_property(name)


class PrivilegedPropsCompat(GObject.Object):
    """Compatibility wrapper for privileged properties"""

    state = GObject.Property(type=object)
    android_version = GObject.Property(type=str, default="")

    def __init__(self, controller: ModelController):
        super().__init__()
        self._controller = controller
        self.set_property("state", PropsState.UNINITIALIZED)

        # Bind to model states - use GLib.idle_add to ensure proper initialization
        GLib.idle_add(self._setup_state_binding)

        # Set up property bindings for all privileged properties
        self._setup_property_bindings()

    def _setup_state_binding(self):
        """Set up state binding after initialization"""
        # Privileged props bind to privileged_state, not the main state
        _ = self._controller.property_model.bind_property(
            "privileged-state",
            self,
            "state",
            GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.BIDIRECTIONAL,
        )
        _ = self._controller.session_model.bind_property(
            "android-version",
            self,
            "android_version",
            GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.BIDIRECTIONAL,
        )

    def _setup_property_bindings(self):
        """Set up property bindings - simplified approach"""
        # Instead of dynamic GObject properties, we'll handle property access
        # through get_property/set_property overrides
        pass

    def get_property(self, property_name: str) -> Any:
        """Get property value from model"""
        if property_name in ("state", "android_version"):
            return super().get_property(property_name)

        return self._controller.property_model.get_property(property_name)

    def set_property(self, property_name: str, value: Any):
        """Set property value in model"""
        if property_name in ("state", "android_version"):
            super().set_property(property_name, value)
            return

        self._controller.property_model.set_property(property_name, value)

    def set_device_info(self, data: dict[str, Any]):
        """Set device info (compatibility method)"""
        self._controller._task.create_task(self._controller.set_device_info(data))

    async def fetch(self):
        """Fetch properties (compatibility method)"""
        # This is handled automatically by the controller
        pass

    async def reset(self):
        """Reset properties (compatibility method)"""
        await self._controller.reset_privileged_properties()

    async def save(self):
        """Save properties (compatibility method)"""
        success = await self._controller.save_all_privileged_properties()
        if success:
            return await self._controller.upgrade(offline=True)
        return False

    async def restore(self):
        """Restore properties (compatibility method)"""
        await self._controller.restore_privileged_properties()


class WaydroidPropsCompat(GObject.Object):
    """Compatibility wrapper for waydroid config properties"""

    state = GObject.Property(type=object)

    def __init__(self, controller: ModelController):
        super().__init__()
        self._controller: ModelController = controller

        # Connect to model changes
        _ = self._controller.property_model.bind_property(
            "waydroid-state",
            self,
            "state",
            GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.BIDIRECTIONAL,
        )

    def set_property(self, property_name: str, value: Any):
        """Set property value in model"""
        if property_name == "state":
            super().set_property(property_name, value)
            return

        self._controller.property_model.set_property(property_name, value)

    # Compatibility methods for accessing properties
    def get_property(self, property_name: str):
        if property_name in ("state"):
            return super().get_property(property_name)

        return self._controller.property_model.get_property(property_name)


class WaydroidCompat(GObject.Object):
    """
    Compatibility wrapper for the old Waydroid class.

    This class provides the same interface as the original Waydroid class
    but uses the new clean architecture internally. This allows for
    incremental migration of the codebase.
    """

    state: WaydroidState = GObject.Property(  # pyright: ignore[reportAssignmentType]
        type=object
    )

    def __init__(self) -> None:
        super().__init__()

        # Initialize the new architecture
        self._controller = ModelController()

        # Set up property bindings for compatibility
        self._setup_compatibility_bindings()

        self._persist_props_compat: PersistPropsCompat = PersistPropsCompat(
            self._controller
        )
        self._privileged_props_compat: PrivilegedPropsCompat = PrivilegedPropsCompat(
            self._controller
        )
        self._waydroid_props_compat: WaydroidPropsCompat = WaydroidPropsCompat(
            self._controller
        )

        # Initialize state
        self.set_property("state", WaydroidState.LOADING)

    def _setup_compatibility_bindings(self):
        """Set up bindings between new models and old interface"""
        # Bind session state
        _ = self._controller.session_model.bind_property(
            "state",
            self,
            "state",
            GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.BIDIRECTIONAL,
        )

    # Compatibility properties
    @property
    def persist_props(self):
        """Compatibility property for persist props"""
        return self._persist_props_compat

    @property
    def privileged_props(self):
        """Compatibility property for privileged props"""
        return self._privileged_props_compat

    @property
    def waydroid_props(self):
        """Compatibility property for waydroid config props"""
        return self._waydroid_props_compat

    # Session management methods (delegate to controller)
    async def start_session(self):
        """Start Waydroid session"""
        return await self._controller.start_session()

    async def stop_session(self):
        """Stop Waydroid session"""
        return await self._controller.stop_session()

    async def restart_session(self):
        """Restart Waydroid session"""
        return await self._controller.restart_session()

    async def show_full_ui(self):
        """Show Waydroid full UI"""
        return await self._controller.show_full_ui()

    async def upgrade(self, offline: bool = False) -> bool:
        """Upgrade Waydroid"""
        return await self._controller.upgrade(offline)

    # Property management methods (delegate to controller)
    async def reset_persist_props(self):
        """Reset persist properties"""
        return await self._controller.reset_persist_properties()

    async def reset_privileged_props(self):
        """Reset privileged properties"""
        return await self._controller.reset_privileged_properties()

    async def save_persist_prop(self, name: str):
        """Save a persist property"""
        return await self._controller.save_persist_property(name)

    async def refresh_persist_prop(self, name: str):
        """Refresh a persist property from Waydroid"""
        return await self._controller.refresh_persist_property(name)

    async def save_privileged_props(self):
        """Save privileged properties"""
        success = await self._controller.save_all_privileged_properties()
        if success:
            return await self._controller.upgrade(offline=True)
        return False

    async def restore_privileged_props(self):
        """Restore privileged properties"""
        return await self._controller.restore_privileged_properties()

    async def save_waydroid_props(self, upgrade: bool = False):
        """Save waydroid config properties"""
        success = await self._controller.save_all_waydroid_properties()
        if success and upgrade:
            logger.debug("Upgrade waydroid config properties")
            return await self._controller.upgrade(offline=True)
        return success

    async def reset_waydroid_props(self):
        """Reset waydroid config properties"""
        return await self._controller.reset_waydroid_properties()

    async def restore_waydroid_props(self):
        """Restore waydroid config properties"""
        return await self._controller.restore_waydroid_properties()

    async def set_extension_props(self, pairs: dict[str, Any]):
        """Set extension properties"""
        return await self._controller.set_extension_properties(pairs)

    async def remove_extension_props(self, keys: list[str]):
        """Remove extension properties"""
        return await self._controller.remove_extension_properties(keys)

    def get_android_version(self):
        """Get Android version"""
        return self._controller.session_model.get_property("android_version")

    # State management methods
    def reset_persist_props_state(self):
        """Reset persist props state (compatibility)"""
        # This is handled automatically by the new architecture
        pass

    def reset_privileged_props_state(self):
        """Reset privileged props state (compatibility)"""
        # This is handled automatically by the new architecture
        pass

    def reset_waydroid_props_state(self):
        """Reset waydroid props state (compatibility)"""
        # This is handled automatically by the new architecture
        pass

    async def retry_load_privileged_properties(self):
        """Retry loading privileged properties (public interface)"""
        return await self._controller._load_privileged_properties_with_retry()

    async def retry_load_waydroid_properties(self):
        """Retry loading waydroid properties (public interface)"""
        return await self._controller._load_waydroid_properties_with_retry()

    def bind(
        self,
        source_property: str,
        target: GObject.Object,
        target_property: str,
        flags: GObject.BindingFlags = GObject.BindingFlags.DEFAULT,
        transform_to=None,
        transform_from=None,
        user_data=None,
    ) -> GObject.Binding:
        return self._controller.property_model.bind_property(
            source_property,
            target,
            target_property,
            flags,
            transform_to,
            transform_from,
            user_data,
        )


# Create alias for backward compatibility
Waydroid = WaydroidCompat
