import asyncio
from unittest.mock import AsyncMock, Mock, call

import pytest

from waydroid_helper.controller.app import emulator_display as display


def test_staging_converts_android_pixels_to_wayland_units_without_running_wm(
    monkeypatch,
):
    props = AsyncMock(side_effect=["", "", "", ""])
    monkeypatch.setattr(display, "waydroid_output", props)
    remember = Mock(return_value=True)
    asyncio.run(display.stage_mode(display.DisplayMode(1080, 1920, 480), 2, remember))
    assert props.await_args_list[-2:] == [
        call("prop", "set", "persist.waydroid.width", "540"),
        call("prop", "set", "persist.waydroid.height", "960"),
    ]
    remember.assert_called_once()


def test_partial_native_write_restores_previous_mode(monkeypatch):
    props = AsyncMock(side_effect=["800", "600", "", OSError("write failed"), ""])
    monkeypatch.setattr(display, "waydroid_output", props)
    remember = Mock()
    with pytest.raises(OSError):
        asyncio.run(
            display.stage_mode(display.DisplayMode(1080, 1920, 480), 2, remember)
        )
    assert props.await_args == call("prop", "set", "persist.waydroid.width", "800")
    remember.assert_not_called()


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
