from __future__ import annotations

from gi.repository import GLib

from waydroid_helper.config.models import RootConfig


DEFAULT_SETTINGS = {
    "key-mapping-config-migrated": False,
    "cage-enabled": False,
    "cage-executable-path": "",
    "cage-refresh-rate": 60,
    "cage-window-width": 1920,
    "cage-window-height": 1080,
    "cage-logical-width": 1920,
    "cage-logical-height": 1080,
    "cage-scale": 100,
    "cage-socket-name": "waydroid-0",
    "cage-hide-titlebar": False,
    "cage-confine-pointer": False,
    "default-handler-keyboard-inject-mode": "mixed",
    "default-handler-mouse-natural-scroll": True,
    "default-handler-mouse-hover": False,
}

SETTING_TYPES = {
    "key-mapping-config-migrated": "b",
    **{
        binding.settings_key: binding.variant_type
        for binding in RootConfig.CAGE_SETTINGS
    },
    **{
        binding.settings_key: binding.variant_type
        for binding in RootConfig.DEFAULT_HANDLER_SETTINGS
    },
}


class FakeSettings:
    def __init__(self, values: dict[str, object] | None = None):
        self.values = dict(DEFAULT_SETTINGS)
        if values:
            self.values.update(values)

    def get_value(self, key: str):
        return GLib.Variant(SETTING_TYPES[key], self.values[key])

    def set_value(self, key: str, value):
        self.values[key] = value.unpack()
        return True


class FakeLegacyFileManager:
    def __init__(self, config: dict | None = None):
        self.config = config or {}
        self.load_calls = 0
        self.save_calls = 0

    def load_config(self):
        self.load_calls += 1
        return self.config

    def save_config(self, config):
        self.save_calls += 1
        raise AssertionError("RootConfig must not save legacy JSON config files")


def test_root_config_uses_gsettings_defaults_and_marks_empty_migration_complete():
    settings = FakeSettings()
    legacy = FakeLegacyFileManager()

    config = RootConfig(settings=settings, legacy_file_manager=legacy)

    assert config.cage.enabled is False
    assert config.cage.window_width == 1920
    assert config.default_handler.keyboard_inject_mode == "mixed"
    assert config.default_handler.mouse_natural_scroll is True
    assert config.default_handler.mouse_hover is False
    assert settings.values["key-mapping-config-migrated"] is True
    assert legacy.load_calls == 1
    assert legacy.save_calls == 0


def test_root_config_does_not_read_legacy_file_after_migration_marker_is_set():
    settings = FakeSettings({"key-mapping-config-migrated": True})
    legacy = FakeLegacyFileManager({"cage": {"enabled": True}})

    config = RootConfig(settings=settings, legacy_file_manager=legacy)

    assert config.cage.enabled is False
    assert legacy.load_calls == 0


def test_root_config_migrates_legacy_json_to_gsettings_once():
    settings = FakeSettings()
    legacy = FakeLegacyFileManager(
        {
            "cage": {
                "enabled": True,
                "executable_path": "/usr/bin/cage",
                "refresh_rate": 144,
                "window_width": 1280,
                "window_height": 720,
                "logical_width": 1920,
                "logical_height": 1080,
                "scale": 125,
                "socket_name": "waydroid-test",
                "hide_titlebar": True,
                "confine_pointer": True,
            },
            "default_handler": {
                "keyboard_inject_mode": "raw",
                "mouse_natural_scroll": False,
                "mouse_hover": True,
            },
        }
    )

    config = RootConfig(settings=settings, legacy_file_manager=legacy)

    assert config.cage.enabled is True
    assert config.cage.executable_path == "/usr/bin/cage"
    assert config.cage.refresh_rate == 144
    assert settings.values["cage-enabled"] is True
    assert settings.values["cage-executable-path"] == "/usr/bin/cage"
    assert settings.values["cage-refresh-rate"] == 144
    assert settings.values["cage-window-width"] == 1280
    assert settings.values["cage-window-height"] == 720
    assert settings.values["cage-logical-width"] == 1920
    assert settings.values["cage-logical-height"] == 1080
    assert settings.values["cage-scale"] == 125
    assert settings.values["cage-socket-name"] == "waydroid-test"
    assert settings.values["cage-hide-titlebar"] is True
    assert settings.values["cage-confine-pointer"] is True
    assert config.default_handler.keyboard_inject_mode == "raw"
    assert config.default_handler.mouse_natural_scroll is False
    assert config.default_handler.mouse_hover is True
    assert settings.values["default-handler-keyboard-inject-mode"] == "raw"
    assert settings.values["default-handler-mouse-natural-scroll"] is False
    assert settings.values["default-handler-mouse-hover"] is True
    assert settings.values["key-mapping-config-migrated"] is True
    assert legacy.save_calls == 0


def test_root_config_logs_and_skips_invalid_legacy_values():
    settings = FakeSettings()
    legacy = FakeLegacyFileManager(
        {
            "cage": {
                "enabled": True,
                "window_width": "wide",
            },
            "default_handler": {
                "keyboard_inject_mode": "invalid",
                "mouse_hover": "yes",
            },
        }
    )

    config = RootConfig(settings=settings, legacy_file_manager=legacy)

    assert config.cage.enabled is True
    assert settings.values["cage-enabled"] is True
    assert config.cage.window_width == 1920
    assert settings.values["cage-window-width"] == 1920
    assert config.default_handler.keyboard_inject_mode == "mixed"
    assert settings.values["default-handler-keyboard-inject-mode"] == "mixed"
    assert config.default_handler.mouse_hover is False
    assert settings.values["default-handler-mouse-hover"] is False
    assert settings.values["key-mapping-config-migrated"] is True


def test_root_config_save_and_load_round_trip_through_gsettings():
    settings = FakeSettings({"key-mapping-config-migrated": True})
    config = RootConfig(settings=settings, migrate_legacy=False)

    config.cage.enabled = True
    config.cage.executable_path = "/opt/cage"
    config.cage.window_width = 2560
    config.cage.window_height = 1440
    config.cage.socket_name = "custom-socket"
    config.default_handler.keyboard_inject_mode = "text"
    config.default_handler.mouse_natural_scroll = False
    config.default_handler.mouse_hover = True

    assert config.save_to_settings() is True

    reloaded = RootConfig(settings=settings, migrate_legacy=False)

    assert reloaded.cage.enabled is True
    assert reloaded.cage.executable_path == "/opt/cage"
    assert reloaded.cage.window_width == 2560
    assert reloaded.cage.window_height == 1440
    assert reloaded.cage.socket_name == "custom-socket"
    assert reloaded.default_handler.keyboard_inject_mode == "text"
    assert reloaded.default_handler.mouse_natural_scroll is False
    assert reloaded.default_handler.mouse_hover is True
