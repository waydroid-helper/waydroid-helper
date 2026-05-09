from __future__ import annotations

import struct

from waydroid_helper.controller.android import AMotionEventAction, AMotionEventButtons
from waydroid_helper.controller.core.control_msg import InjectTouchEventMsg
from waydroid_helper.controller.core.runtime import ScreenGeometry


def test_screen_geometry_instances_are_isolated():
    first = ScreenGeometry()
    second = ScreenGeometry()

    first.set_resolution(1000, 500)
    second.set_resolution(2000, 1000)

    assert first.get_resolution() == (1000, 500)
    assert second.get_resolution() == (2000, 1000)


def test_touch_message_uses_explicit_device_resolution():
    msg = InjectTouchEventMsg(
        action=AMotionEventAction.DOWN,
        pointer_id=7,
        position=(50, 25, 100, 50),
        device_resolution=(1000, 500),
        pressure=1.0,
        action_button=AMotionEventButtons.PRIMARY,
        buttons=AMotionEventButtons.PRIMARY,
    )

    unpacked = struct.unpack(">BBQIIHHHII", msg.pack())

    assert unpacked[3:7] == (500, 250, 1000, 500)
