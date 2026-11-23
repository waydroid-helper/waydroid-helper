"""Record and replay the Android input delivered by this mapping workspace."""

import asyncio
import json
import math
import time
from dataclasses import asdict, replace
from gettext import gettext as _

from gi.repository import Gio

from waydroid_helper.controller.core.control_msg import (
    InjectKeycodeMsg,
    InjectScrollEventMsg,
    InjectTextMsg,
    InjectTouchEventMsg,
)
from waydroid_helper.controller.core.handler.default.default_mouse_handler import (
    PointerId,
)
from waydroid_helper.controller.core.event_bus import Event, EventType


class InputRecording:
    TYPES = {
        "key": InjectKeycodeMsg,
        "touch": InjectTouchEventMsg,
        "scroll": InjectScrollEventMsg,
        "text": InjectTextMsg,
    }

    def __init__(self, window):
        self.window = window
        self.events = []
        self.started = None
        self.player = None
        window.event_bus.subscribe(
            EventType.COPY_RECORDING, self._copy, subscriber=self
        )
        window.event_bus.subscribe(
            EventType.PLAY_RECORDING, self._play_binding, subscriber=self
        )

    def snapshot(self):
        names = {cls: name for name, cls in self.TYPES.items()}
        return {
            "version": 1,
            "events": [(t, names[type(msg)], asdict(msg)) for t, msg in self.events],
        }

    def _copy(self, event):
        if self.events:
            event.data(self.snapshot())
        else:
            self.window.show_notification(_("Record or import input first"))

    def _play_binding(self, event):
        self.window.run_device_action(
            lambda: self.play(self.decode_document(event.data))
        )

    def toggle(self):
        if self.started is not None:
            self.stop()
            self.window.show_notification(_("Input recording stopped"))
        elif self.player is None and self.window.server.connected_event.is_set():
            self.events = []
            self.started = time.monotonic()
            self.window.event_bus.subscribe(
                EventType.CONTROL_MSG, self._capture, subscriber=self
            )
            self.window.show_notification(_("Recording Android input"))

    def _capture(self, event):
        if type(event.data) in self.TYPES.values():
            self.events.append((time.monotonic() - self.started, event.data))

    def stop(self):
        self.window.event_bus.unsubscribe(EventType.CONTROL_MSG, self._capture)
        self.started = None
        if self.player:
            self.player.cancel()

    def export(self):
        self.stop()
        if not self.events:
            self.window.show_notification(_("No recorded input"))
            return
        # Capture the selected recording before the asynchronous file chooser
        # opens. Starting another recording cannot change what gets exported.
        snapshot = self.snapshot()

        async def save(path):
            data = json.dumps(snapshot, ensure_ascii=False).encode()
            await asyncio.to_thread(
                Gio.File.new_for_path(str(path)).replace_contents,
                data,
                None,
                False,
                Gio.FileCreateFlags.NONE,
                None,
            )

        self.window.tools.pick_file(
            _("Export recording"), "*.json", save, "recording.json"
        )

    @classmethod
    def decode(cls, content):
        return cls.decode_document(json.loads(content))

    @classmethod
    def decode_document(cls, document):
        if document["version"] != 1 or not isinstance(document["events"], list):
            raise ValueError(_("Unknown recording format"))
        events = []
        for timestamp, name, fields in document["events"]:
            if not math.isfinite(timestamp) or timestamp < (
                events[-1][0] if events else 0
            ):
                raise ValueError(_("Invalid recording timestamp"))
            message = cls.TYPES[name](**fields)
            message.pack()
            events.append((timestamp, message))
        return events

    def load(self):
        async def read(path):
            events = await asyncio.to_thread(
                lambda: self.decode(path.read_text(encoding="utf-8"))
            )
            self.stop()
            self.events = events
            self.window.show_notification(_("Recording loaded"))

        self.window.tools.pick_file(_("Import recording"), "*.json", read)

    async def play(self, events=None):
        if self.player:
            self.player.cancel()
            return
        self.stop()
        events = self.events if events is None else events
        if not events:
            self.window.show_notification(_("No recorded input"))
            return
        self.player = asyncio.current_task()
        held = {}
        owners = set()
        started = time.monotonic()
        try:
            for timestamp, original in events:
                await asyncio.sleep(max(0, started + timestamp - time.monotonic()))
                if not self.window.server.connected_event.is_set():
                    break
                msg = original
                if isinstance(msg, (InjectScrollEventMsg, InjectTouchEventMsg)):
                    msg = replace(
                        msg,
                        device_resolution=self.window.screen_geometry.get_resolution(),
                    )
                # Recorded IDs belong to the source workspace. Reserve fresh
                # IDs so replay can overlap a live stick or a two-finger zoom.
                if (
                    isinstance(msg, InjectTouchEventMsg)
                    and msg.pointer_id != PointerId.MOUSE
                    and msg.action in (0, 1, 2, 3)
                ):
                    owner = (self, original.pointer_id)
                    pool = self.window.pointer_id_manager
                    pointer = (
                        pool.allocate(owner)
                        if msg.action == 0
                        else pool.get_allocated_id(owner)
                    )
                    if pointer is None:
                        continue
                    owners.add(owner)
                    msg = replace(msg, pointer_id=pointer)
                    if msg.action in (1, 3):
                        pool.release(owner)
                        owners.discard(owner)
                # Balance held buttons and multitouch contacts on cancellation,
                # disconnect or a recording that ended mid-gesture.
                if isinstance(msg, (InjectKeycodeMsg, InjectTouchEventMsg)):
                    touch = isinstance(msg, InjectTouchEventMsg)
                    key = ("touch", msg.pointer_id) if touch else ("key", msg.keycode)
                    if msg.action == 0:
                        held[key] = (
                            replace(msg, action=1, pressure=0, buttons=0)
                            if touch
                            else replace(msg, action=1)
                        )
                    elif touch and msg.action == 2 and key in held:
                        held[key] = replace(msg, action=1, pressure=0, buttons=0)
                    elif msg.action in (1, 3):
                        held.pop(key, None)
                self._send(msg)
        finally:
            for release in held.values():
                self._send(release)
            for owner in owners:
                self.window.pointer_id_manager.release(owner)
            self.player = None

    def _send(self, msg):
        self.window.event_bus.emit(Event(EventType.CONTROL_MSG, self, msg))
