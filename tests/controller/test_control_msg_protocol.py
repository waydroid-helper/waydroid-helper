from __future__ import annotations

from waydroid_helper.controller.core.control_msg import ControlMsgType


def test_control_msg_type_values_match_scrcpy_server_protocol():
    expected_values = {
        "INJECT_KEYCODE": 0,
        "INJECT_TEXT": 1,
        "INJECT_TOUCH_EVENT": 2,
        "INJECT_SCROLL_EVENT": 3,
        "BACK_OR_SCREEN_ON": 4,
        "EXPAND_NOTIFICATION_PANEL": 5,
        "EXPAND_SETTINGS_PANEL": 6,
        "COLLAPSE_PANELS": 7,
        "GET_CLIPBOARD": 8,
        "SET_CLIPBOARD": 9,
        "SET_DISPLAY_POWER": 10,
        "SET_SCREEN_POWER_MODE": 10,
        "ROTATE_DEVICE": 11,
        "UHID_CREATE": 12,
        "UHID_INPUT": 13,
        "UHID_DESTROY": 14,
        "OPEN_HARD_KEYBOARD_SETTINGS": 15,
        "START_APP": 16,
        "RESET_VIDEO": 17,
    }

    assert {
        name: int(ControlMsgType.__members__[name])
        for name in expected_values
    } == expected_values
