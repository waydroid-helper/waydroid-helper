"""Play timed multi-finger paths in the geometry of a placed mapping control."""

from bisect import bisect_right
import math
import time
from gettext import gettext as _

from gi.repository import GLib

from waydroid_helper.controller.android.input import AMotionEventAction as Motion
from waydroid_helper.controller.widgets.base import control_art as art
from waydroid_helper.controller.widgets.base.touch_control import TouchControl
from waydroid_helper.controller.widgets.config import create_slider_config


class TimedGesture(TouchControl):
    DEFAULT_DURATION = 300

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.timer = 0
        self.next_notch = None
        self.add_config_item(
            create_slider_config(
                "duration",
                _("Gesture duration (ms)"),
                self.DEFAULT_DURATION,
                16,
                3000,
                1,
            )
        )

    def get_editable_regions(self):
        return [
            dict(
                id="default",
                name=self.WIDGET_NAME,
                bounds=(0, 0, self.width, self.height),
                get_keys=lambda: self.final_keys.copy(),
                set_keys=self.set_default_keys,
            )
        ]

    def draw_widget_content(self, cr, width, height):
        super().draw_widget_content(cr, width, height)
        cr.set_source_rgba(0.56, 0.87, 1, 0.98)
        for path in self.paths(False):
            art.guide(
                cr, [(7 + x * (width - 14), 7 + y * (height - 14)) for x, y in path]
            )

    def paths(self, reverse):
        raise NotImplementedError

    def on_key_triggered(self, key_combination=None, event=None):
        wheel = (
            event is not None
            and event.key is not None
            and event.key.name.startswith("Wheel_")
        )
        if wheel and self.timer and self.wheel_direction == event.key.name:
            # Real wheels can report several notches in one frame. Restarting
            # at the origin for every notch would cancel the stroke before a
            # MOVE reaches Android. Queue at most one more complete stroke.
            self.next_notch = (key_combination, event)
            return True
        self.stop_gesture()
        self.wheel_direction = event.key.name if wheel else None
        reverse = self.reverse_binding(key_combination, event)
        self.tracks = []
        for finger, track in enumerate(self.paths(reverse)):
            points = [
                (self.x + x * self.width, self.y + y * self.height) for x, y in track
            ]
            if not self.touch(finger, Motion.DOWN, *points[0]):
                self.stop_gesture()
                return False
            # Parameterize by distance so densely sampled corners in a drawn
            # stroke do not slow down compared to a long straight segment.
            lengths = [0.0]
            for start, end in zip(points, points[1:]):
                lengths.append(lengths[-1] + math.dist(start, end))
            self.tracks.append((points, lengths))
        self.next_vertices = [1] * len(self.tracks)
        self.started = time.monotonic() + (self.get_config_value("pause") or 0) / 1000
        self.timer = GLib.timeout_add(16, self._advance)
        return True

    def _advance(self):
        fraction = min(
            1,
            max(
                0,
                (time.monotonic() - self.started)
                * 1000
                / self.get_config_value("duration"),
            ),
        )
        for finger, (points, lengths) in enumerate(self.tracks):
            distance = fraction * lengths[-1]
            i = min(len(points) - 2, bisect_right(lengths, distance) - 1)
            # GTK frame deadlines can skip several recorded vertices. Deliver
            # crossed vertices in order before interpolating the current MOVE,
            # otherwise a short turn or a reversal disappears during playback.
            while self.next_vertices[finger] <= i:
                self.touch(finger, Motion.MOVE, *points[self.next_vertices[finger]])
                self.next_vertices[finger] += 1
            portion = (
                (distance - lengths[i]) / (lengths[i + 1] - lengths[i])
                if lengths[i + 1] > lengths[i]
                else 1
            )
            x, y = points[i]
            nx, ny = points[i + 1]
            self.touch(
                finger, Motion.MOVE, x + (nx - x) * portion, y + (ny - y) * portion
            )
        if fraction == 1:
            self.timer = 0
            pending = self.next_gesture()
            self.stop_gesture()
            if pending is not None:
                self.on_key_triggered(*pending)
            return GLib.SOURCE_REMOVE
        return GLib.SOURCE_CONTINUE

    def reverse_binding(self, combo, event):
        return False

    def next_gesture(self):
        return self.next_notch

    def on_key_released(self, key_combination=None, event=None):
        # A key press or one wheel notch launches the complete gesture.
        return True

    def stop_gesture(self):
        self.next_notch = None
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = 0
        super().stop_gesture()
