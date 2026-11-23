"""Collect a single mouse stroke over the actual Android viewport."""

import math
import time

from gi.repository import Gdk, Gtk


class SwipePlacement(Gtk.DrawingArea):
    def __init__(self, completed):
        super().__init__(hexpand=True, vexpand=True, focusable=True)
        self.completed = completed
        self.points = []
        self.set_cursor_from_name("crosshair")
        self.set_draw_func(self._draw)
        drag = Gtk.GestureDrag(button=Gdk.BUTTON_PRIMARY)
        drag.connect("drag-begin", self._begin)
        drag.connect("drag-update", self._update)
        drag.connect("drag-end", self._end)
        drag.connect("cancel", lambda *_: self._reset())
        self.add_controller(drag)

    def _reset(self):
        self.points.clear()
        self.queue_draw()

    def _point(self, x, y):
        return (
            max(0, min(x, self.get_width() - 1)),
            max(0, min(y, self.get_height() - 1)),
        )

    def _begin(self, gesture, x, y):
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        self.origin = (x, y)
        self.started = time.monotonic()
        self.points = [self._point(x, y)]

    def _update(self, gesture, dx, dy):
        if not self.points:
            return
        point = self._point(self.origin[0] + dx, self.origin[1] + dy)
        if point != self.points[-1]:
            self.points.append(point)
            self.queue_draw()

    def _end(self, gesture, dx, dy):
        self._update(gesture, dx, dy)
        # A closed loop can have identical endpoints. Measure travel from the
        # origin over all samples, so a click is rejected but a loop survives.
        if any(math.dist(self.points[0], p) >= 3 for p in self.points):
            self.completed(self.points, round((time.monotonic() - self.started) * 1000))
        self._reset()

    def _draw(self, _area, cr, width, height):
        if not self.points:
            return
        cr.move_to(*self.points[0])
        for point in self.points[1:]:
            cr.line_to(*point)
        cr.set_source_rgb(0.45, 0.86, 1)
        cr.set_line_width(2)
        cr.stroke()
