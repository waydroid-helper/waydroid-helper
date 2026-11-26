import asyncio
from unittest.mock import AsyncMock, Mock, call

from gi.repository import GLib

import pytest

from waydroid_helper.controller.app import emulator_display as display


def test_offline_display_mode_is_stored_in_pixel_units():
    mode = display.DisplayMode(1080, 1920, 480)
    settings = Mock()
    display.store_display_mode(settings, "emulator-display-mode", mode)
    settings.set_value.assert_called_once_with(
        "emulator-display-mode", GLib.Variant("(iii)", (1080, 1920, 480))
    )
    settings.get_value.return_value = settings.set_value.call_args.args[1]
    assert display.load_display_mode(settings, "emulator-display-mode") == mode
    assert mode.logical_size(2) == (540, 960)


def test_native_dimensions_are_only_cleared_if_they_conflict(monkeypatch):
    props = AsyncMock(return_value="")
    monkeypatch.setattr(display, "waydroid_output", props)
    assert not asyncio.run(display.clear_conflicting_native_size(("", "960"), (540, 960)))
    props.assert_not_awaited()
    assert asyncio.run(display.clear_conflicting_native_size(("800", "600"), (540, 960), "blue"))
    assert props.await_args_list[:2] == [
        call("prop", "set", "persist.waydroid.width", "", instance="blue"),
        call("prop", "set", "persist.waydroid.height", "", instance="blue"),
    ]


def test_partial_native_clear_restores_previous_mode(monkeypatch):
    props = AsyncMock(side_effect=["", OSError("write failed"), "", ""])
    monkeypatch.setattr(display, "waydroid_output", props)
    with pytest.raises(OSError):
        asyncio.run(display.clear_conflicting_native_size(("800", "600"), (540, 960)))
    assert props.await_args == call("prop", "set", "persist.waydroid.width", "800", instance="default")


def test_existing_override_is_removed_when_native_mode_now_matches(monkeypatch):
    command = AsyncMock(
        side_effect=[
            b"Physical size: 1080x1920\nOverride size: 1920x1080",
            b"",
            b"Physical density: 360",
            b"",
            b"Physical size: 1080x1920",
            b"Physical density: 360\nOverride density: 480",
        ]
    )
    monkeypatch.setattr(display, "device_command", command)
    asyncio.run(
        display.apply_android_mode("instance", display.DisplayMode(1080, 1920, 480))
    )
    for setting, value in (("size", "reset"), ("density", "480")):
        command.assert_any_await("instance", "shell", "wm", setting, value)


@pytest.mark.parametrize(("saved", "measured", "expected"), [
    (None, (0, 0, 0), (1920, 1080, 280)),
    ((0, 0, 0), (1080, 1920, 480), (1080, 1920, 480)),
    ((2560, 1440, 360), (1920, 1080, 280), (2560, 1440, 360)),
])
def test_startup_mode_preserves_existing_devices_and_gives_new_devices_a_preset(saved, measured, expected):
    settings = Mock()
    key = "emulator-display-mode"
    variant = lambda value: GLib.Variant("(iii)", value)
    settings.get_user_value.return_value = variant(saved) if saved else None
    settings.get_default_value.return_value = variant((1920, 1080, 280))
    settings.get_value.side_effect = lambda name: variant(saved if name == key else measured)
    assert display.startup_display_mode(settings) == display.DisplayMode(*expected)
