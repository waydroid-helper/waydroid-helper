"""Key, wheel or gamepad-triggered touchscreen gestures."""

from gettext import gettext as _
from waydroid_helper.controller.widgets.base.placed_path import PlacedPath
from waydroid_helper.controller.widgets.base.timed_gesture import TimedGesture
from waydroid_helper.controller.widgets.base.paired_gesture import PairedGesture
from waydroid_helper.controller.widgets.decorators import Editable
from waydroid_helper.controller.widgets.config import (
    create_dropdown_config,
    create_slider_config,
    create_switch_config,
)


@Editable
class Swipe(PlacedPath, TimedGesture):
    WIDGET_NAME = _("Swipe path")
    WIDGET_DESCRIPTION = _(
        "Drag on the Android screen to record a path. Press the bound key to replay it."
    )

    def do_contains(self, x, y):
        # PyGObject installs virtual methods from the GObject class dictionary.
        # A plain Python mixin alone would leave the entire path rectangle clickable.
        return self.path_contains(x, y)

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_config_item(
            create_slider_config("pause", _("Hold at start (ms)"), 0, 0, 2000)
        )
        self.add_config_item(
            create_switch_config("straight", _("Use a straight line"), False)
        )

    def set_recorded_path(self, points, duration, canvas_width, canvas_height):
        self.set_config_value("duration", max(16, min(3000, duration)))
        return super().set_recorded_path(points, duration, canvas_width, canvas_height)

    def placed_points(self):
        points = super().placed_points()
        return [points[0], points[-1]] if self.get_config_value("straight") else points

    def paths(self, reverse):
        points = self.placed_points()
        return [points[::-1] if reverse else points]


class Scroll(PairedGesture):
    DEFAULT_DURATION = 200
    DEFAULT_DISTANCE = 50
    DEFAULT_BINDINGS = ("Up", "Down")
    ROW_ICONS = ("⌃", "⌄")
    WIDGET_NAME = _("Scroll gesture")
    WIDGET_DESCRIPTION = _(
        "Bind a key or wheel notch to scroll within the selected area"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        labels = {
            "up": _("Up"),
            "down": _("Down"),
            "left": _("Left"),
            "right": _("Right"),
        }
        self.add_config_item(
            create_dropdown_config(
                "direction", _("Swipe direction"), list(labels), option_labels=labels
            )
        )

    def paths(self, reverse):
        direction = self.get_config_value("direction")
        vertical = direction in ("up", "down")
        sign = -1 if reverse != (direction in ("down", "right")) else 1
        ww, hh = self.screen_geometry.get_host_resolution()
        span = self.get_config_value("distance") / 400
        dx = 0 if vertical else sign * span * ww / self.width
        dy = sign * span * hh / self.height if vertical else 0
        return [[(0.5, 0.5), (0.5 + dx, 0.5 + dy)]]


class Pinch(PairedGesture):
    WIDGET_NAME = _("Pinch zoom")
    WIDGET_DESCRIPTION = _(
        "Scroll the wheel in either direction to pinch in or out around this point"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_config_item(create_switch_config("inward", _("Pinch inward"), False))

    def paths(self, reverse):
        _, height = self.screen_geometry.get_host_resolution()
        radius = self.get_config_value("distance") / 400 * height / self.height
        # Leave a small initial separation so gesture recognizers never see
        # two coincident fingers. Both tracks share the placed control's X.
        tracks = [
            [(0.5, 0.5 + sign * radius * 0.04), (0.5, 0.5 + sign * radius)]
            for sign in (-1, 1)
        ]
        if reverse != self.get_config_value("inward"):
            return [p[::-1] for p in tracks]
        return tracks
