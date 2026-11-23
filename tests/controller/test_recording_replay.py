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
