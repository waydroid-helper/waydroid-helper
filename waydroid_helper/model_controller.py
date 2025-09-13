# pyright: reportAny=false
# pyright: reportAttributeAccessIssue=false,reportUnknownArgumentType=false,reportUnknownMemberType=false

"""
Controller Layer for Waydroid Helper

This module implements the controller that coordinates between the model layer
and SDK layer, providing a clean interface for the view layer.
"""

import asyncio
from typing import Any

from gi.repository import GLib, GObject

from waydroid_helper.util import Task, logger
from waydroid_helper.models import (
    PropertyCategory,
    PropertyModel,
    SessionModel,
    ModelState,
    SessionState,
)
from waydroid_helper.sdk import WaydroidSDK, PropertyManager, ConfigManager


class ModelController(GObject.Object):
    """
    Controller that coordinates between models and SDK.

    This controller:
    - Manages the lifecycle of models
    - Coordinates operations between models and SDK
    - Provides a clean interface for the view layer
    - Handles async operations and error handling
    """

    def __init__(self):
        super().__init__()

        # Initialize models
        self.property_model = PropertyModel()
        self.session_model = SessionModel()

        # Initialize SDK components
        self.waydroid_sdk = WaydroidSDK()
        self.property_manager = PropertyManager()
        self.config_manager = ConfigManager()

        # Task management
        self._task = Task()
        self._status_update_lock = asyncio.Lock()
        self._monitoring_started = False

        # Defer async initialization until event loop is available
        GLib.idle_add(self._start_status_monitoring)

    def _start_status_monitoring(self):
        """Start periodic monitoring of Waydroid status"""
        if self._monitoring_started:
            return False

        self._monitoring_started = True

        # Initial status check
        self._task.create_task(self._initial_status_check())

        # Schedule periodic updates every 2 seconds
        GLib.timeout_add_seconds(2, self._schedule_status_update)

        # Schedule periodic ERROR state recovery checks every 10 seconds
        GLib.timeout_add_seconds(10, self._schedule_error_recovery)

        return False  # Don't repeat this idle callback

    async def _initial_status_check(self):
        """Initial status check with forced property loading"""
        try:
            current_state = await self.waydroid_sdk.get_session_status()

            # Set initial session state
            self.session_model.set_session_state(current_state)

            # Force load privileged and waydroid properties if waydroid is initialized
            if current_state in (SessionState.STOPPED, SessionState.RUNNING):
                await self._load_privileged_properties()
                await self._load_waydroid_properties()
                await self._load_android_version()

            # Load persist properties if session is running
            if current_state == SessionState.RUNNING:
                await self._load_persist_properties()

        except Exception as e:
            logger.error(f"Failed initial status check: {e}")

    def _schedule_status_update(self) -> bool:
        """Schedule a status update task"""
        # self._task.create_task(self._update_session_status())
        asyncio.create_task(self._update_session_status())
        return True  # Continue the timeout

    def _schedule_error_recovery(self) -> bool:
        """Schedule an error recovery check"""
        # self._task.create_task(self._handle_error_state_recovery())
        asyncio.create_task(self._handle_error_state_recovery())
        return True  # Continue the timeout

    async def _update_session_status(self):
        """Update session status and load properties if needed"""
        async with self._status_update_lock:
            try:
                new_state = await self.waydroid_sdk.get_session_status()
                old_state = self.session_model.get_property("state")

                # Only log significant state changes
                if old_state != new_state:
                    logger.debug(
                        f"Session state transition: {old_state} -> {new_state}"
                    )

                # Update session state
                self.session_model.set_session_state(new_state)

                _ = await self.refresh_persist_property("boot-completed")

                # Handle state transitions
                await self._handle_session_state_transition(old_state, new_state)

            except Exception as e:
                logger.error(f"Failed to update session status: {e}")

    async def _handle_session_state_transition(
        self, old_state: SessionState, new_state: SessionState
    ):
        """Handle session state transitions and load/unload properties accordingly"""

        # When session becomes running, load persist properties
        if new_state == SessionState.RUNNING and old_state != SessionState.RUNNING:
            await self._load_persist_properties()
            # Also load Android version if coming from UNINITIALIZED
            if old_state == SessionState.UNINITIALIZED:
                await self._load_android_version()
                await self._load_privileged_properties()
                await self._load_waydroid_properties()

        # When session stops, reset persist props state but keep privileged props
        elif new_state == SessionState.STOPPED and old_state == SessionState.RUNNING:
            self.property_model.set_property("state", ModelState.UNINITIALIZED)
            # privileged_state remains READY

        # When Waydroid becomes initialized (stopped), load privileged and waydroid properties
        elif (
            new_state == SessionState.STOPPED
            and old_state == SessionState.UNINITIALIZED
        ):
            await self._load_privileged_properties_with_retry()
            await self._load_waydroid_properties_with_retry()
            await self._load_android_version()

        # When waydroid becomes completely uninitialized, reset all states
        elif new_state == SessionState.UNINITIALIZED:
            self.property_model.set_property("state", ModelState.UNINITIALIZED)
            self.property_model.set_property(
                "privileged-state", ModelState.UNINITIALIZED
            )
            self.property_model.set_property("waydroid-state", ModelState.UNINITIALIZED)

        # Handle ERROR state recovery - retry loading if states are in ERROR
        await self._handle_error_state_recovery()

    async def _load_persist_properties(self):
        """Load persist properties from Waydroid"""
        self.property_model.set_property("state", ModelState.LOADING)

        try:
            property_values = await self.property_manager.get_all_persist_properties(
                self.property_model.get_persist_properties()
            )

            for prop_name, raw_value in property_values.items():
                self.property_model.set_property_raw_value(prop_name, raw_value)

            self.property_model.set_property("state", ModelState.READY)

        except Exception as e:
            logger.error(f"Failed to load persist properties: {e}")
            self.property_model.set_property("state", ModelState.ERROR)
            raise

    async def _load_privileged_properties(self):
        """Load privileged properties from config"""
        self.property_model.set_property("privileged-state", ModelState.LOADING)

        try:
            if not self.config_manager.load_config():
                raise Exception("Failed to load config")

            property_values = self.config_manager.get_all_privileged_properties(
                self.property_model.get_privileged_properties()
            )

            for prop_name, raw_value in property_values.items():
                self.property_model.set_property_raw_value(prop_name, raw_value)

            self.property_model.set_property("privileged-state", ModelState.READY)

        except Exception as e:
            logger.error(f"Failed to load privileged properties: {e}")
            self.property_model.set_property("privileged-state", ModelState.ERROR)
            # Don't raise - allow other operations to continue

    async def _load_waydroid_properties(self):
        """Load waydroid config properties from [waydroid] section"""
        self.property_model.set_property("waydroid-state", ModelState.LOADING)

        try:
            if not self.config_manager.load_config():
                raise Exception("Failed to load config")

            property_values = self.config_manager.get_all_waydroid_properties(
                self.property_model.get_waydroid_properties()
            )

            for prop_name, raw_value in property_values.items():
                self.property_model.set_property_raw_value(prop_name, raw_value)

            self.property_model.set_property("waydroid-state", ModelState.READY)

        except Exception as e:
            logger.error(f"Failed to load waydroid properties: {e}")
            self.property_model.set_property("waydroid-state", ModelState.ERROR)
            # Don't raise - allow other operations to continue

    async def _load_privileged_properties_with_retry(self, max_retries: int = 3):
        """Load privileged properties with retry mechanism"""
        for attempt in range(max_retries):
            try:
                await self._load_privileged_properties()
                return  # Success, exit retry loop
            except Exception as e:
                logger.warning(
                    f"Attempt {attempt + 1}/{max_retries} to load privileged properties failed: {e}"
                )
                if attempt < max_retries - 1:
                    # Wait before retry (exponential backoff)
                    await asyncio.sleep(2**attempt)
                else:
                    logger.error(
                        f"Failed to load privileged properties after {max_retries} attempts"
                    )

    async def _load_waydroid_properties_with_retry(self, max_retries: int = 3):
        """Load waydroid properties with retry mechanism"""
        for attempt in range(max_retries):
            try:
                await self._load_waydroid_properties()
                return  # Success, exit retry loop
            except Exception as e:
                logger.warning(
                    f"Attempt {attempt + 1}/{max_retries} to load waydroid properties failed: {e}"
                )
                if attempt < max_retries - 1:
                    # Wait before retry (exponential backoff)
                    await asyncio.sleep(2**attempt)
                else:
                    logger.error(
                        f"Failed to load waydroid properties after {max_retries} attempts"
                    )

    async def _handle_error_state_recovery(self):
        """Handle recovery from ERROR states by retrying failed operations"""
        # Check if privileged properties are in ERROR state and retry
        privileged_state = self.property_model.get_property("privileged-state")
        if privileged_state == ModelState.ERROR:
            logger.info("Attempting to recover from privileged properties ERROR state")
            await self._load_privileged_properties_with_retry(max_retries=2)

        # Check if waydroid properties are in ERROR state and retry
        waydroid_state = self.property_model.get_property("waydroid-state")
        if waydroid_state == ModelState.ERROR:
            logger.info("Attempting to recover from waydroid properties ERROR state")
            await self._load_waydroid_properties_with_retry(max_retries=2)

    async def _load_android_version(self):
        """Load Android version from config"""
        try:
            android_version = await self.config_manager.get_android_version()
            self.session_model.set_property("android_version", android_version)
        except Exception as e:
            logger.error(f"Failed to load Android version: {e}")

    # Public API for view layer

    async def save_persist_property(self, property_name: str) -> bool:
        """Save a single persist property"""
        try:
            raw_value = self.property_model.get_property_raw_value(property_name)
            nick = self.property_model.find_property(property_name).get_nick()

            logger.info(f"Saved persist property {property_name} = {raw_value}")
            return await self.property_manager.set_persist_property(nick, raw_value)

        except Exception as e:
            logger.error(f"Failed to save persist property {property_name}: {e}")
            return False

    async def refresh_persist_property(self, property_name: str) -> bool:
        """Refresh a single persist property from Waydroid"""
        try:
            # Get current value from Waydroid
            nick = self.property_model.find_property(property_name).get_nick()
            raw_value = await self.property_manager.get_persist_property(nick)

            self.property_model.set_property_raw_value(property_name, raw_value)

            logger.debug(f"Refreshed persist property {property_name} = {raw_value}")
            return True

        except Exception as e:
            logger.error(f"Failed to refresh persist property {property_name}: {e}")
            return False

    async def save_all_privileged_properties(self) -> bool:
        """Save all privileged properties to config file"""
        try:
            # Prepare all privileged properties for saving
            privileged_props = self.property_model.get_privileged_properties()
            properties_to_save = {}

            for prop in privileged_props:
                nick = prop.get_nick()
                raw_value = self.property_model.get_property_raw_value(prop.get_name())
                properties_to_save[nick] = raw_value

            # Set all properties in config
            self.config_manager.set_multiple_privileged_properties(properties_to_save)

            # Save config file
            success = await self.config_manager.save_config()

            return success

        except Exception as e:
            logger.error(f"Failed to save privileged properties: {e}")
            return False

    async def reset_persist_properties(self) -> bool:
        """Reset all persist properties to defaults"""
        self.property_model.set_property("state", ModelState.LOADING)
        try:
            persist_props = self.property_model.get_persist_properties()

            # Reset in model
            self.property_model.reset_to_defaults(PropertyCategory.PERSIST)

            # Save all persist properties
            tasks = []
            for prop in persist_props:
                task = self.save_persist_property(prop.get_name())
                tasks.append(task)

            results = await asyncio.gather(*tasks, return_exceptions=True)
            self.property_model.set_property("state", ModelState.READY)

            # Check if all succeeded
            return all(
                result is True
                for result in results
                if not isinstance(result, Exception)
            )

        except Exception as e:
            logger.error(f"Failed to reset persist properties: {e}")
            self.property_model.set_property("state", ModelState.ERROR)
            return False

    async def reset_privileged_properties(self) -> bool:
        """Reset all privileged properties to defaults"""
        self.property_model.set_property("privileged-state", ModelState.LOADING)
        try:
            self.property_model.reset_to_defaults(PropertyCategory.PRIVILEGED)

            props = self.property_model.get_privileged_properties()
            for prop in props:
                self.config_manager.set_privileged_property(prop.get_nick(), "")

            success = await self.config_manager.save_config()
            if success:
                return await self.upgrade(offline=True)

            self.property_model.set_property("privileged-state", ModelState.READY)
            return success

        except Exception as e:
            logger.error(f"Failed to reset privileged properties: {e}")
            self.property_model.set_property("privileged-state", ModelState.ERROR)
            return False

    async def save_all_waydroid_properties(self) -> bool:
        """Save all waydroid config properties to [waydroid] section"""
        try:
            # Prepare all waydroid properties for saving
            waydroid_props = self.property_model.get_waydroid_properties()
            properties_to_save = {}

            for prop in waydroid_props:
                nick = prop.get_nick()
                raw_value = self.property_model.get_property_raw_value(prop.get_name())
                properties_to_save[nick] = raw_value

            # Set all properties in config
            self.config_manager.set_multiple_waydroid_properties(properties_to_save)

            # Save config file
            success = await self.config_manager.save_config()

            if success:
                # Trigger restart container to apply changes
                await self.waydroid_sdk.stop_session(wait=True)
                await self.waydroid_sdk.restart_container(wait=True)

            return success

        except Exception as e:
            logger.error(f"Failed to save waydroid properties: {e}")
            return False

    async def reset_waydroid_properties(self) -> bool:
        """Reset all waydroid config properties to defaults"""
        self.property_model.set_property("waydroid-state", ModelState.LOADING)
        try:
            self.property_model.reset_to_defaults(PropertyCategory.WAYDROID)

            props = self.property_model.get_waydroid_properties()
            for prop in props:
                nick = prop.get_nick()
                raw_value = self.property_model.get_property_raw_value(prop.get_name())
                self.config_manager.set_waydroid_property(nick, raw_value)

            success = await self.config_manager.save_config()
            if success:
                return await self.upgrade(offline=True)

            self.property_model.set_property("waydroid-state", ModelState.READY)
            return success

        except Exception as e:
            logger.error(f"Failed to reset waydroid properties: {e}")
            self.property_model.set_property("waydroid-state", ModelState.ERROR)
            return False

    async def restore_privileged_properties(self) -> bool:
        """Restore privileged properties from saved config"""
        self.property_model.set_property("privileged-state", ModelState.LOADING)
        try:
            # Reload config from file
            if not self.config_manager.load_config():
                return False

            # Reload properties into model
            await self._load_privileged_properties()

            self.property_model.set_property("privileged-state", ModelState.READY)
            return True

        except Exception as e:
            logger.error(f"Failed to restore privileged properties: {e}")
            self.property_model.set_property("privileged-state", ModelState.ERROR)
            return False

    async def restore_waydroid_properties(self) -> bool:
        """Restore waydroid config properties from saved config"""
        self.property_model.set_property("waydroid-state", ModelState.LOADING)
        try:
            # Reload config from file
            if not self.config_manager.load_config():
                self.property_model.set_property("privileged-state", ModelState.ERROR)
                return False

            # Reload properties into model
            await self._load_waydroid_properties()

            self.property_model.set_property("waydroid-state", ModelState.READY)
            return True

        except Exception as e:
            logger.error(f"Failed to restore waydroid properties: {e}")
            self.property_model.set_property("waydroid-state", ModelState.ERROR)
            return False

    async def set_device_info(self, device_properties: dict[str, Any]) -> bool:
        """Set device information properties"""
        try:
            # Update model
            for prop_name, value in device_properties.items():
                # Convert property names (e.g., "ro.product.brand" -> "ro_product_brand")
                model_prop_name = prop_name.replace(".", "_")
                _ = self.property_model.set_property_raw_value(model_prop_name, value)
            self.config_manager.set_multiple_privileged_properties(device_properties)
            return True

        except Exception as e:
            logger.error(f"Failed to set device info: {e}")
            return False

    async def set_extension_properties(self, properties: dict[str, Any]) -> bool:
        """Set extension properties"""
        try:
            # Set properties in config
            self.config_manager.set_multiple_privileged_properties(properties)

            success = await self.config_manager.save_config()

            return success

        except Exception as e:
            logger.error(f"Failed to set extension properties: {e}")
            return False

    async def remove_extension_properties(self, property_keys: list[str]) -> bool:
        """Remove extension properties"""
        try:
            # Remove properties from config
            empty_properties = {key: "" for key in property_keys}
            self.config_manager.set_multiple_privileged_properties(empty_properties)

            success = await self.config_manager.save_config()

            return success

        except Exception as e:
            logger.error(f"Failed to remove extension properties: {e}")
            return False

    # Session management

    async def start_session(self) -> bool:
        """Start Waydroid session"""
        return await self.waydroid_sdk.start_session()

    async def stop_session(self) -> bool:
        """Stop Waydroid session"""
        return await self.waydroid_sdk.stop_session()

    async def restart_session(self) -> bool:
        """Restart Waydroid session"""
        return await self.waydroid_sdk.restart_session()

    async def show_full_ui(self) -> bool:
        """Show Waydroid full UI"""
        return await self.waydroid_sdk.show_full_ui()

    async def upgrade(self, offline: bool = False) -> bool:
        """Upgrade Waydroid"""
        success = await self.waydroid_sdk.upgrade(offline)
        await self._load_privileged_properties_with_retry()
        await self._load_waydroid_properties_with_retry()
        return success
