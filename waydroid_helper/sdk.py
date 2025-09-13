# pyright: reportAny=false
# pyright: reportAttributeAccessIssue=false,reportUnknownArgumentType=false,reportUnknownMemberType=false

"""
Clean SDK Layer for Waydroid Helper

This module implements a clean SDK that handles Waydroid operations without
managing state or emitting events. It's a pure interface to Waydroid functionality.
"""

import asyncio
import configparser
import copy
import os
from typing import Any, Dict, List, Optional, Tuple

from gi.repository import GLib
from gi.repository.GObject import ParamSpec

from waydroid_helper.util import SubprocessError, SubprocessManager, logger
from waydroid_helper.models import SessionState

class WaydroidSDK:
    """
    Pure Waydroid SDK that handles session management.
    
    This SDK:
    - Provides clean interfaces to Waydroid operations
    - Returns results without managing state
    - Has no knowledge of models or UI
    """
    
    def __init__(self):
        self._subprocess = SubprocessManager()
    
    async def get_session_status(self) -> SessionState:
        """Get current Waydroid session status"""
        try:
            result = await self._subprocess.run("waydroid status", shell=False)
            output = result["stdout"]
            
            if "WayDroid is not initialized" in output:
                return SessionState.UNINITIALIZED
            elif "Session:\tRUNNING" in output:
                return SessionState.RUNNING
            elif "Session:\tSTOPPED" in output:
                return SessionState.STOPPED
            else:
                return SessionState.LOADING
                
        except SubprocessError as e:
            logger.error(f"Failed to get Waydroid status: {e}")
            return SessionState.UNINITIALIZED
    
    async def start_session(self, wait: bool = False) -> bool:
        """Start Waydroid session"""
        try:
            await self._subprocess.run("waydroid session start", flag=True, wait=wait, shell=False)
            return True
        except SubprocessError as e:
            logger.error(f"Failed to start Waydroid session: {e}")
            return False
    
    async def stop_session(self, wait: bool = False) -> bool:
        """Stop Waydroid session"""
        try:
            await self._subprocess.run("waydroid session stop", flag=True, wait=wait, shell=False)
            return True
        except SubprocessError as e:
            logger.error(f"Failed to stop Waydroid session: {e}")
            return False
    
    async def restart_session(self) -> bool:
        """Restart Waydroid session"""
        stop_success = await self.stop_session()
        if not stop_success:
            return False
        
        # Wait a moment for the session to fully stop
        await asyncio.sleep(1)
        
        return await self.start_session()
    
    async def show_full_ui(self) -> bool:
        """Show Waydroid full UI"""
        try:
            await self._subprocess.run("waydroid show-full-ui", flag=True, wait=False, shell=False)
            return True
        except SubprocessError as e:
            logger.error(f"Failed to show Waydroid full UI: {e}")
            return False
    
    async def restart_container(self, wait: bool = False) -> bool:
        """"""
        try:
            await self._subprocess.run(f"pkexec {os.environ['WAYDROID_CLI_PATH']} restart_container", flag=True, wait=wait, shell=False)
            return True
        except SubprocessError as e:
            logger.error(f"Failed to restart Waydroid container: {e}")
            return False
    
    async def upgrade(self, offline: bool = False) -> bool:
        """Upgrade Waydroid"""
        try:
            if offline:
                cmd = f"pkexec {os.environ['WAYDROID_CLI_PATH']} upgrade -o"
            else:
                cmd = f"pkexec {os.environ['WAYDROID_CLI_PATH']} upgrade"
            
            await self._subprocess.run(cmd, flag=True, shell=False)
            return True
        except SubprocessError as e:
            logger.error(f"Failed to upgrade Waydroid: {e}")
            return False


class PropertyManager:
    """
    Manager for Waydroid properties.
    
    This manager:
    - Handles both persist properties (via waydroid prop) and privileged properties (via config)
    - Provides clean interfaces for property operations
    - Returns results without managing state
    """
    
    def __init__(self):
        self._subprocess = SubprocessManager()
    
    async def get_persist_property(self, property_nick: str) -> str:
        """Get a persist property value using waydroid prop get"""
        try:
            result = await self._subprocess.run(f"waydroid prop get {property_nick}", shell=False, timeout=10)
            output = result["stdout"].replace(
                "[gbinder] Service manager /dev/binder has appeared", ""
            ).strip().split("\n")[-1]
            return output
        except SubprocessError as e:
            logger.error(f"Failed to get persist property {property_nick}: {e}")
            return ""
    
    async def set_persist_property(self, property_nick: str, value: str) -> bool:
        """Set a persist property value using waydroid prop set"""
        try:
            await self._subprocess.run(f'waydroid prop set {property_nick} "{value}"', shell=False)
            return True
        except SubprocessError as e:
            logger.error(f"Failed to set persist property {property_nick}: {e}")
            return False
    
    async def get_all_persist_properties(self, param_specs: list[ParamSpec]) -> dict[str, str]:
        """Get all persist properties in parallel"""
        if not param_specs:
            return {}

        async def get_prop(p: ParamSpec):
            try:
                result = await self._subprocess.run(f"waydroid prop get {p.get_nick()}", shell=False, timeout=10)
                output = result["stdout"].replace(
                    "[gbinder] Service manager /dev/binder has appeared", ""
                ).strip().split("\n")[-1]
                return (p.get_name(), output)
            except Exception as e:
                logger.warning(f"Failed to get property {p.get_name()}: {e}")
                return (p.get_name(), "")

        tasks = [get_prop(p) for p in param_specs]
        results = await asyncio.gather(*tasks)
        return dict(results)


class ConfigManager:
    """
    Manager for Waydroid configuration files.
    
    This manager:
    - Handles privileged properties that require config file modification
    - Provides clean interfaces for config operations
    - Returns results without managing state
    """
    
    def __init__(self):
        self._subprocess: SubprocessManager = SubprocessManager()
        self._config_cache: configparser.ConfigParser | None = None
    
    def load_config(self, config_path: str = "/var/lib/waydroid/waydroid.cfg") -> bool:
        """Load Waydroid configuration file with improved error handling"""
        try:
            # Check if config file exists
            if not os.path.exists(config_path):
                logger.warning(f"Config file does not exist: {config_path}")
                # Try to create a minimal config
                return self._create_minimal_config()

            # Check if config file is readable
            if not os.access(config_path, os.R_OK):
                logger.error(f"Config file is not readable: {config_path}")
                return False

            self._config_cache = configparser.ConfigParser()
            self._config_cache.read(config_path)

            # Verify config has required sections
            if not self._config_cache.has_section("properties"):
                logger.warning("Config missing [properties] section, adding it")
                self._config_cache.add_section("properties")

            if not self._config_cache.has_section("waydroid"):
                logger.warning("Config missing [waydroid] section, adding it")
                self._config_cache.add_section("waydroid")

            return True
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            # Try to create a minimal config as fallback
            return self._create_minimal_config()

    def _create_minimal_config(self) -> bool:
        """Create a minimal configuration as fallback"""
        try:
            logger.info("Creating minimal configuration as fallback")
            self._config_cache = configparser.ConfigParser()
            self._config_cache.add_section("properties")
            self._config_cache.add_section("waydroid")
            # Add some default waydroid settings
            self._config_cache.set("waydroid", "images_path", "/var/lib/waydroid/images")
            return True
        except Exception as e:
            logger.error(f"Failed to create minimal config: {e}")
            return False
    
    def get_privileged_property(self, property_nick: str) -> str:
        """Get a privileged property from config"""
        if not self._config_cache:
            if not self.load_config():
                return ""
        
        try:
            return self._config_cache.get("properties", property_nick, fallback="")
        except Exception as e:
            logger.error(f"Failed to get privileged property {property_nick}: {e}")
            return ""
    
    def get_all_privileged_properties(self, param_specs: list[ParamSpec]) -> dict[str, str]:
        """Get all privileged properties from config"""
        if not self._config_cache:
            if not self.load_config():
                return {}
        
        property_values = {}
        for p in param_specs:
            try:
                value = self._config_cache.get("properties", p.get_nick(), fallback="")
                property_values[p.get_name()] = value
            except Exception as e:
                logger.error(f"Failed to get privileged property {p.get_name()}: {e}")
                property_values[p.get_name()] = ""
        
        return property_values

    def get_all_waydroid_properties(self, param_specs: list[ParamSpec]) -> dict[str, str]:
        """Get all waydroid config properties from [waydroid] section"""
        if not self._config_cache:
            if not self.load_config():
                return {}

        property_values = {}
        for p in param_specs:
            try:
                value = self._config_cache.get("waydroid", p.get_nick(), fallback="")
                property_values[p.get_name()] = value
            except Exception as e:
                logger.error(f"Failed to get waydroid property {p.get_name()}: {e}")
                property_values[p.get_name()] = ""

        return property_values


    def set_waydroid_property(self, property_nick: str, raw_value: str):
        """Set a waydroid property in config (in memory only)"""
        if not self._config_cache:
            if not self.load_config():
                return
        
        if raw_value == "":
            # Remove empty properties
            self._config_cache.remove_option("waydroid", property_nick)
        else:
            self._config_cache.set("waydroid", property_nick, raw_value)

    def set_privileged_property(self, property_nick: str, raw_value: str):
        """Set a privileged property in config (in memory only)"""
        if not self._config_cache:
            if not self.load_config():
                return
        
        if raw_value == "":
            # Remove empty properties
            self._config_cache.remove_option("properties", property_nick)
        else:
            self._config_cache.set("properties", property_nick, raw_value)
    
    def set_multiple_privileged_properties(self, properties: dict[str, str]):
        """Set multiple privileged properties in config (in memory only)"""
        if not self._config_cache:
            if not self.load_config():
                logger.error("Failed to load config for setting privileged properties")
                return

        for property_nick, raw_value in properties.items():
            if raw_value == "":
                if self._config_cache.has_option("properties", property_nick):
                    self._config_cache.remove_option("properties", property_nick)
            else:
                self._config_cache.set("properties", property_nick, raw_value)

    def set_multiple_waydroid_properties(self, properties: dict[str, str]):
        """Set multiple waydroid config properties in [waydroid] section (in memory only)"""
        if not self._config_cache:
            if not self.load_config():
                logger.error("Failed to load config for setting waydroid properties")
                return

        # Ensure [waydroid] section exists
        if not self._config_cache.has_section("waydroid"):
            self._config_cache.add_section("waydroid")

        for property_nick, raw_value in properties.items():
            if raw_value == "":
                if self._config_cache.has_option("waydroid", property_nick):
                    self._config_cache.remove_option("waydroid", property_nick)
            else:
                self._config_cache.set("waydroid", property_nick, raw_value)

    # def reset_waydroid_properties(self, param_specs: list[ParamSpec]):
    #     """Reset waydroid properties to defaults"""
    #     if not self._config_cache:
    #         if not self.load_config():
    #             logger.error("Failed to load config for resetting waydroid properties")
    #             return

    #     # Ensure [waydroid] section exists
    #     if not self._config_cache.has_section("waydroid"):
    #         self._config_cache.add_section("waydroid")

    #     for p in param_specs:
    #         self._config_cache.set("waydroid", p.get_nick(), p.get_default_value())

    async def save_config(self) -> bool:
        """Save config to file using privileged access"""
        if not self._config_cache:
            logger.error("No config loaded to save")
            return False
        
        try:
            # Save to cache directory first
            cache_dir = os.path.join(GLib.get_user_cache_dir(), "waydroid-helper")
            cache_config_path = os.path.join(cache_dir, "waydroid.cfg")
            
            os.makedirs(cache_dir, exist_ok=True)
            with open(cache_config_path, "w") as f:
                self._config_cache.write(f)
            
            # Copy to system location with pkexec
            cmd = f"pkexec {os.environ['WAYDROID_CLI_PATH']} copy_to_var {cache_config_path} waydroid.cfg"
            await self._subprocess.run(cmd, flag=True, shell=False)
            return True
        except SubprocessError as e:
            logger.error(f"Failed to save config: {e}")
            return False
    
    async def get_android_version(self) -> str:
        """Get Android version from system image"""
        if not self._config_cache:
            if not self.load_config():
                return ""
        
        try:
            system_image_path = os.path.join(
                self._config_cache.get("waydroid", "images_path"), "system.img"
            )
            result = await self._subprocess.run(
                f"debugfs -R 'cat /system/build.prop' {system_image_path} | grep '^ro.build.version.release=' | cut -d'=' -f2",
                shell=True
            )
            return result["stdout"].strip()
        except Exception as e:
            logger.error(f"Failed to get Android version: {e}")
            return ""
    
    # def reset_privileged_properties(self):
    #     """Reset all privileged properties to defaults (in memory only)"""
    #     if not self._config_cache:
    #         if not self.load_config():
    #             return
        
    #     # 清空 [properties] 下面的所有内容, 但保留 section
    #     for option in self._config_cache.options("properties"):
    #         self._config_cache.remove_option("properties", option)
