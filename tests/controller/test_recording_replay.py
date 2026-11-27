import asyncio
from types import SimpleNamespace
from waydroid_helper.controller.app.input_recording import InputRecording
from waydroid_helper.controller.core.event_bus import EventBus, EventType
from waydroid_helper.controller.core.control_msg import InjectTouchEventMsg
from waydroid_helper.controller.core.utils import PointerIdManager


def test_incomplete_recording_releases_own_contact_after_move():
    pool = PointerIdManager()
    occupied = pool.allocate("held-stick")
    window = SimpleNamespace(
        pointer_id_manager=pool,
        event_bus=EventBus(),
        screen_geometry=SimpleNamespace(get_resolution=lambda: (800, 600)),
        server=SimpleNamespace(connected_event=SimpleNamespace(is_set=lambda: True)),
    )
    recorder = InputRecording(window)
    delivered = []
    window.event_bus.subscribe(
        EventType.CONTROL_MSG, lambda e: delivered.append(e.data)
    )
    recorder.events = [
        (
            0,
            InjectTouchEventMsg(
                action, occupied, (x, 40, 400, 300), (400, 300), 1, 0, 1
            ),
        )
        for action, x in [(0, 20), (2, 70)]
    ]
    asyncio.run(recorder.play(recorder.decode_document(recorder.snapshot())))
    assert [m.action for m in delivered] == [0, 2, 1]
    assert all(
        m.pointer_id != occupied and m.device_resolution == (800, 600)
        for m in delivered
    )
    assert delivered[-1].position == delivered[-2].position
    assert pool.get_status()["allocated_count"] == 1


def test_logical_pinch_recording_replays_as_stock_touches():
    from unittest.mock import AsyncMock

    window = SimpleNamespace(
        pointer_id_manager=PointerIdManager(), event_bus=EventBus(),
        screen_geometry=SimpleNamespace(get_resolution=lambda: (800, 600)),
        server=SimpleNamespace(connected_event=SimpleNamespace(is_set=lambda: True)),
        scrcpy_lifecycle=SimpleNamespace(adb_helper=SimpleNamespace(
            read_input_windows=AsyncMock(return_value=(
                "0: name='w', displayId=0, inputConfig=0x0, frame=[0,0][800,600], "
                "touchableRegion=[0,0][800,600], ownerPid=42, hasToken=true"
            )),
        )),
    )
    recorder = InputRecording(window)
    delivered = []
    window.event_bus.subscribe(EventType.CONTROL_MSG, lambda e: delivered.append(e.data))
    events = [(0, "pinch", dict(action=action, position=(200, 150, 400, 300),
                                device_resolution=(400, 300), scale=scale))
              for action, scale in [(0, 1), (2, .5), (1, .5)]]
    asyncio.run(recorder.play(recorder.decode_document(dict(version=1, events=events))))
    assert all(isinstance(m, InjectTouchEventMsg) for m in delivered)
    assert [m.action for m in delivered] == [0, 0, 2, 2, 1, 1]
    assert [m.position[0] for m in delivered] == [250, 550, 325, 475, 475, 325]
    assert window.pointer_id_manager.get_status()["allocated_count"] == 0
