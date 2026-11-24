"""Touch gestures controlled by the absolute position of an analog trigger."""

from bisect import bisect_left, bisect_right
from gettext import gettext as _
from math import dist

from waydroid_helper.controller.android.input import AMotionEventAction as Motion
from waydroid_helper.controller.widgets.base import control_art as art
from waydroid_helper.controller.widgets.base.trigger_path import TriggerPath
from waydroid_helper.controller.widgets.base.trigger_thresholds import TriggerThresholds
from waydroid_helper.controller.widgets.config import create_slider_config


class TriggerSlider(TriggerPath):
    WIDGET_NAME = _("Trigger slider")
    WIDGET_DESCRIPTION = _("Squeeze or release a trigger to drag in either direction along the drawn path.")
    PLACEMENT_HINT = _("Draw the slider path, then squeeze the trigger to bind it")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_config_item(create_slider_config("deadzone", _("Dead zone (%)"), 4, 0, 40))

    def _move(self, point):
        if self.contacts[0] != tuple(map(round, point)):
            self.touch(0, Motion.MOVE, *point)

    def apply_travel(self, travel):
        deadzone = self.get_config_value("deadzone") / 100
        fraction = max(0.0, travel - deadzone) / (1 - deadzone)
        if not self.contacts:
            if fraction == 0:
                return
            self.points = [(self.x + px * self.width, self.y + py * self.height)
                           for px, py in self.placed_points()]
            if not self.touch(0, Motion.DOWN, *self.points[0]):
                return
            self.lengths = [0.0]
            for start, end in zip(self.points, self.points[1:]):
                self.lengths.append(self.lengths[-1] + dist(start, end))
            self.previous = 0.0

        # Traverse every crossed bend in either direction, even if a device
        # jumps across several vertices in one sample. Binary search keeps
        # slow, precise moves independent of the size of the recorded path.
        offset = fraction * self.lengths[-1]
        if offset >= self.previous:
            crossed = range(bisect_right(self.lengths, self.previous), bisect_left(self.lengths, offset))
        else:
            crossed = range(bisect_left(self.lengths, self.previous) - 1,
                            bisect_right(self.lengths, offset) - 1, -1)
        for index in crossed:
            self._move(self.points[index])
        index = min(len(self.points) - 2, bisect_right(self.lengths, offset) - 1)
        span = self.lengths[index + 1] - self.lengths[index]
        t = (offset - self.lengths[index]) / span if span else 0
        x, y = self.points[index]
        nx, ny = self.points[index + 1]
        self._move((x + (nx - x) * t, y + (ny - y) * t))
        self.previous = offset
        if fraction == 0:
            self.stop_gesture()


class DualStageTrigger(TriggerPath):
    ENDPOINTS_ONLY = True
    DEFAULT_TRIGGER = "Pad_LT"
    WIDGET_NAME = _("Dual-stage trigger")
    WIDGET_DESCRIPTION = _("Hold the first point on a soft pull and add the second point on a full pull.")
    PLACEMENT_HINT = _("Drag from the soft-pull target to the full-pull target, then squeeze the trigger")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_config_item(TriggerThresholds("thresholds", _("Trigger thresholds"), value=[25, 85]))

    def set_recorded_path(self, points, duration, canvas_width, canvas_height):
        return super().set_recorded_path([points[0], points[-1]], duration, canvas_width, canvas_height)

    def draw_widget_content(self, cr, width, height):
        super().draw_widget_content(cr, width, height)
        px, py = self.placed_points()[0]
        art.disc(cr, px * width, py * height, 9, art.BODY, art.OUTLINE)
        art.caption(cr, px * width, py * height, "1", 10)
        x, y = self.keycap_center
        art.caption(cr, x - 13, y - 9, "2", 8)

    def apply_travel(self, travel):
        percent = travel * 100
        thresholds = self.get_config_value("thresholds")
        # Release the deep stage before its prerequisite. A three-point
        # hysteresis band prevents chatter around either activation threshold.
        for finger in (1, 0):
            if finger in self.contacts and percent <= max(0, thresholds[finger] - 3):
                self.touch(finger, Motion.UP, *self.contacts[finger])
        for finger, threshold in enumerate(thresholds):
            if finger not in self.contacts and percent >= threshold:
                px, py = self.placed_points()[finger]
                if not self.touch(finger, Motion.DOWN, self.x + px * self.width, self.y + py * self.height):
                    break
