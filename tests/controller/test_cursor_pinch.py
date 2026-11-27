import asyncio
import struct
from unittest.mock import AsyncMock

from waydroid_helper.controller.android.input import AMotionEventAction as Action
from waydroid_helper.controller.core.control_msg import ControlMsgType
from waydroid_helper.controller.core.event_bus import EventBus, EventType
from waydroid_helper.controller.core.handler.default.default_mouse_handler import MouseDefault
from waydroid_helper.controller.core.handler.event_handlers import (
    InputEvent, InputEventType, InputModifierState,
)
from waydroid_helper.controller.core.pinch import PINCH_POINTERS, touch_interval
from waydroid_helper.controller.core.runtime import ScreenGeometry


def window(rect, flags=""):
    return (f"0: name='window', displayId=0, inputConfig={flags}, frame={rect}, "
            f"touchableRegion={rect}, ownerPid=42, hasToken=true")


def make_handler(read=None):
    bus = EventBus()
    messages = []
    bus.subscribe(EventType.CONTROL_MSG, lambda event: messages.append(event.data))
    read = read or AsyncMock(return_value=window("[0,0][1000,600]"))
    return MouseDefault(bus, ScreenGeometry(1000, 600, 500, 300),
                        read_input_windows=read), messages


def pinch(mouse, status, scale=None, position=(250, 150)):
    mouse.zoom_processor(InputEvent(event_type=InputEventType.MOUSE_ZOOM,
        position=position, zoom=scale, zoom_status=status))


def wheel(mouse, dy):
    mouse.scroll_processor(InputEvent(event_type=InputEventType.MOUSE_SCROLL,
        position=(250, 150), scroll_delta=(0., float(dy)),
        modifier_state=InputModifierState.CTRL))


def test_pinch_keeps_two_contacts_at_initial_cursor_across_reversals():
    async def run():
        mouse, sent = make_handler()
        pinch(mouse, "begin")
        scales = (.9, .2, .1, .8, 4)
        for scale in scales:
            pinch(mouse, "scale-changed", scale, position=(3, 4))
            await asyncio.sleep(0)
        pinch(mouse, "end")
        assert [m.action for m in sent] == [Action.DOWN] * 2 + [Action.MOVE] * 10 + [Action.UP] * 2
        assert tuple(m.pointer_id for m in sent[:2]) == PINCH_POINTERS
        assert tuple(m.pointer_id for m in sent[-2:]) == PINCH_POINTERS[::-1]
        for i, scale in enumerate(scales):
            left, right = sent[2 + 2*i:4 + 2*i]
            assert left.position[:2] == (500 - round(150*scale), 300)
            assert right.position[:2] == (500 + round(150*scale), 300)
            assert left.msg_type == right.msg_type == ControlMsgType.INJECT_TOUCH_EVENT
        assert struct.unpack_from(">ii", sent[-4].pack(), 10) == (-100, 300)
    asyncio.run(run())


def test_ctrl_wheel_honors_quick_release_while_fetching_bounds():
    async def run():
        read = AsyncMock(return_value=window("[0,0][1000,600]"))
        mouse, sent = make_handler(read)
        for dy in (1, 0, 1, 0, -1):
            wheel(mouse, dy)
        mouse.finish_wheel_zoom()
        assert sent == []
        await asyncio.sleep(0)
        mouse.finish_wheel_zoom()
        assert [m.action for m in sent] == [Action.DOWN] * 2 + [Action.MOVE] * 6 + [Action.UP] * 2
        assert sent[4].position[0] > sent[2].position[0] == sent[6].position[0]
        read.assert_awaited_once()
    asyncio.run(run())


def test_cancelled_lookup_and_unknown_window_send_no_touches():
    async def run():
        mouse, sent = make_handler()
        wheel(mouse, 1)
        mouse.finish_zoom(cancel=True)
        await asyncio.sleep(0)
        assert sent == []
        mouse, sent = make_handler(AsyncMock(return_value=""))
        wheel(mouse, 1)
        await asyncio.sleep(0)
        mouse.finish_wheel_zoom()
        assert sent == []
    asyncio.run(run())


def test_small_window_corner_and_overlapping_window():
    async def run():
        dump = "\n".join((window("[100,100][250,500]", "NOT_TOUCHABLE"),
                          window("[95,100][150,500]"), window("[75,100][475,500]")))
        assert touch_interval(dump, 160, 130, 1000, 600) == (150, 475)
        mouse, sent = make_handler(AsyncMock(return_value=dump))
        pinch(mouse, "scale-changed", .5, position=(80, 65))
        await asyncio.sleep(0)
        mouse.finish_zoom(cancel=True)
        assert [m.position[:2] for m in sent] == [
            (160, 130), (322, 130), (241, 130), (241, 130), (160, 130)]
    asyncio.run(run())


def test_rotated_display_intersects_window_in_injection_coordinates():
    dump = ("  Display: 0\n    logicalSize=600x1000\n        transform (ROT_90)\n"
            "            0.0000  -1.0000  600.0000\n"
            "            1.0000  0.0000  0.0000\n"
            "            0.0000  0.0000  1.0000\n    Windows:\n"
            + window("[120,200][480,320]"))
    assert touch_interval(dump, 282, 124, 600, 1000) == (280, 400)
    assert touch_interval(dump, 282, 124, 1000, 600) is None


def test_android_11_windows_use_logical_coordinates_and_layout_flags():
    decoration = window("[0,0][500,300]").replace("inputConfig=", "flags=0x00000010")
    target = window("[25,45][275,145]").replace("inputConfig=", "flags=0x00000028")
    dump = "  Display: 0\n    Windows:\n" + decoration + "\n" + target
    assert touch_interval(dump, 40, 80, 500, 300) == (25, 275)
