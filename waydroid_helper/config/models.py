from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from gi.repository import Gio, GLib, GObject

from .file_manager import ConfigManager
from waydroid_helper.util.log import logger


class CageConfig(GObject.Object):

    enabled = GObject.Property(type=bool, default=False)
    executable_path = GObject.Property(type=str, default="")
    refresh_rate = GObject.Property(type=int, default=60)
    window_width = GObject.Property(type=int, default=1920)
    window_height = GObject.Property(type=int, default=1080)
    logical_width = GObject.Property(type=int, default=1920)
    logical_height = GObject.Property(type=int, default=1080)
    scale = GObject.Property(type=int, default=100)
    socket_name = GObject.Property(type=str, default="waydroid-0")
    hide_titlebar = GObject.Property(type=bool, default=False)
    confine_pointer = GObject.Property(type=bool, default=False)


class DefaultHandlerConfig(GObject.Object):

    keyboard_inject_mode = GObject.Property(type=str, default="mixed")
    mouse_natural_scroll = GObject.Property(type=bool, default=True)
    mouse_hover = GObject.Property(type=bool, default=False)


@dataclass(frozen=True)
class SettingsBinding:
    """Declarative mapping between a GObject property and one GSettings key."""

    property_name: str
    settings_key: str
    variant_type: str
    allowed_values: tuple[Any, ...] | None = None


class RootConfig(GObject.Object):
    SETTINGS_SCHEMA_ID = "com.jaoushingan.WaydroidHelper"
    MIGRATION_KEY = "key-mapping-config-migrated"
    CAGE_SETTINGS = (
        SettingsBinding("enabled", "cage-enabled", "b"),
        SettingsBinding("executable_path", "cage-executable-path", "s"),
        SettingsBinding("refresh_rate", "cage-refresh-rate", "i"),
        SettingsBinding("window_width", "cage-window-width", "i"),
        SettingsBinding("window_height", "cage-window-height", "i"),
        SettingsBinding("logical_width", "cage-logical-width", "i"),
        SettingsBinding("logical_height", "cage-logical-height", "i"),
        SettingsBinding("scale", "cage-scale", "i"),
        SettingsBinding("socket_name", "cage-socket-name", "s"),
        SettingsBinding("hide_titlebar", "cage-hide-titlebar", "b"),
        SettingsBinding("confine_pointer", "cage-confine-pointer", "b"),
    )
    DEFAULT_HANDLER_SETTINGS = (
        SettingsBinding(
            "keyboard_inject_mode",
            "default-handler-keyboard-inject-mode",
            "s",
            ("mixed", "text", "raw"),
        ),
        SettingsBinding(
            "mouse_natural_scroll",
            "default-handler-mouse-natural-scroll",
            "b",
        ),
        SettingsBinding("mouse_hover", "default-handler-mouse-hover", "b"),
    )
    SETTINGS_GROUPS = (
        ("cage", CAGE_SETTINGS),
        ("default_handler", DEFAULT_HANDLER_SETTINGS),
    )
    
    cage = GObject.Property(type=object)
    default_handler = GObject.Property(type=object)
    
    def __init__(
        self,
        settings: Any | None = None,
        legacy_file_manager: ConfigManager | None = None,
        migrate_legacy: bool = True,
    ):
        super().__init__()
        self._settings = settings or Gio.Settings(schema_id=self.SETTINGS_SCHEMA_ID)
        self._legacy_file_manager = legacy_file_manager
        self.cage = CageConfig()
        self.default_handler = DefaultHandlerConfig()
        self.load_from_settings()

        if migrate_legacy:
            self.migrate_legacy_file_config()
    
    def load_from_settings(self) -> None:
        for config_object, binding in self._iter_settings_bindings():
            value = self._get_setting_value(config_object, binding)
            config_object.set_property(binding.property_name, value)
    
    def save_to_settings(self) -> bool:
        try:
            for config_object, binding in self._iter_settings_bindings():
                value = config_object.get_property(binding.property_name)
                self._set_setting_value(binding, value)
            return True
        except Exception as e:
            logger.error(f"Failed to save configuration: {e}")
            return False

    def migrate_legacy_file_config(self) -> bool:
        """Migrate the old JSON config into GSettings once.

        Runtime reads and writes are GSettings-only. The legacy file manager is
        touched only here so existing user preferences survive the backend
        switch.
        """
        if self._get_migration_complete():
            return False

        legacy_file_manager = self._legacy_file_manager or ConfigManager()
        legacy_config = legacy_file_manager.load_config()

        if not legacy_config:
            self._set_migration_complete(True)
            return False

        migrated = self._apply_legacy_config(legacy_config)
        if migrated and not self.save_to_settings():
            logger.error("Failed to migrate key mapping configuration to GSettings")
            self.load_from_settings()
            return False

        self._set_migration_complete(True)
        if migrated:
            logger.info("Migrated key mapping configuration from JSON file to GSettings")
        return migrated

    def _iter_settings_bindings(self):
        for group_name, bindings in self.SETTINGS_GROUPS:
            config_object = getattr(self, group_name)
            for binding in bindings:
                yield config_object, binding

    def _get_setting_value(
        self,
        config_object: GObject.Object,
        binding: SettingsBinding,
    ) -> Any:
        try:
            return self._settings.get_value(binding.settings_key).unpack()
        except Exception as e:
            fallback = config_object.get_property(binding.property_name)
            logger.error(
                f"Failed to read GSettings key {binding.settings_key}: {e}"
            )
            return fallback

    def _set_setting_value(self, binding: SettingsBinding, value: Any) -> None:
        self._settings.set_value(
            binding.settings_key,
            GLib.Variant(binding.variant_type, value),
        )

    def _get_migration_complete(self) -> bool:
        try:
            return bool(self._settings.get_value(self.MIGRATION_KEY).unpack())
        except Exception as e:
            logger.error(f"Failed to read migration state from GSettings: {e}")
            return False

    def _set_migration_complete(self, migrated: bool) -> None:
        try:
            self._settings.set_value(self.MIGRATION_KEY, GLib.Variant("b", migrated))
        except Exception as e:
            logger.error(f"Failed to write migration state to GSettings: {e}")

    def _apply_legacy_config(self, legacy_config: dict[str, Any]) -> bool:
        """Apply known legacy keys to the in-memory model before saving.

        The old JSON backend stored the key mapping window preferences below the
        ``cage`` object. Keeping the migration table-driven makes the legacy
        format explicit and prevents unrelated JSON keys from leaking into the
        current GSettings-backed model.
        """
        migrated = False
        for group_name, bindings in self.SETTINGS_GROUPS:
            group_config = legacy_config.get(group_name)
            if not isinstance(group_config, dict):
                continue

            config_object = getattr(self, group_name)
            for binding in bindings:
                if binding.property_name not in group_config:
                    continue

                value = group_config[binding.property_name]
                if not self._is_valid_setting_value(binding, value):
                    logger.error(
                        "Skipping invalid legacy key mapping configuration value "
                        f"{group_name}.{binding.property_name}={value!r}"
                    )
                    continue

                config_object.set_property(binding.property_name, value)
                migrated = True

        return migrated

    def _is_valid_setting_value(self, binding: SettingsBinding, value: Any) -> bool:
        valid_type = False
        if binding.variant_type == "b":
            valid_type = isinstance(value, bool)
        elif binding.variant_type == "i":
            valid_type = isinstance(value, int) and not isinstance(value, bool)
        elif binding.variant_type == "s":
            valid_type = isinstance(value, str)
        else:
            try:
                GLib.Variant(binding.variant_type, value)
                valid_type = True
            except Exception:
                valid_type = False

        if not valid_type:
            return False

        if binding.allowed_values is not None:
            return value in binding.allowed_values

        return True
