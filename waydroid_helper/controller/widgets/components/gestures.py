"""Key, wheel or gamepad-triggered touchscreen gestures."""

from gettext import gettext as _
import math

from waydroid_helper.controller.widgets.base import control_art as art
from waydroid_helper.controller.widgets.base.decorator_contracts import (
    EditableWidgetBehavior,
)

from waydroid_helper.controller.widgets.base.stroke_config import StrokeConfig
from waydroid_helper.controller.widgets.base.timed_gesture import TimedGesture
from waydroid_helper.controller.widgets.base.paired_gesture import PairedGesture
from waydroid_helper.controller.widgets.decorators import Editable
from waydroid_helper.controller.widgets.config import (
    create_dropdown_config,
    create_slider_config,
    create_switch_config,
)


@Editable
class Swipe(TimedGesture):
    WIDGET_NAME = _("Swipe path")
    WIDGET_DESCRIPTION = _(
        "Drag on the Android screen to record a path. Press the bound key to replay it."
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_config_item(
            StrokeConfig(
                "path",
                _("Draw the swipe path"),
                value=[[0.1, 0.5], [0.9, 0.5]],
                visible=False,
            )
        )
        self.add_config_item(
            create_slider_config("pause", _("Hold at start (ms)"), 0, 0, 2000)
        )
        self.add_config_item(
            create_switch_config("straight", _("Use a straight line"), False)
        )

        self.add_config_change_callback("path", self._path_changed)

    def _path_changed(self, *_):
        if self.mapping_mode and self.get_parent():
            self.get_parent().move(self, self.mapping_start_x, self.mapping_start_y)
        self.queue_draw()

    def set_recorded_path(self, points, duration, canvas_width, canvas_height):
        # Include room for the endpoint keycap. The same normalized geometry
        # drives drawing, layout scaling, dragging and Android injection.
        xs, ys = zip(*points)
        x = max(0, math.floor(min(xs)) - 34)
        y = max(0, math.floor(min(ys)) - 24)
        self.width = max(1, min(canvas_width, math.ceil(max(xs)) + 35) - x)
        self.height = max(1, min(canvas_height, math.ceil(max(ys)) + 25) - y)
        self.set_size_request(self.width, self.height)
        self.set_config_value(
            "path",
            [[(px - x) / self.width, (py - y) / self.height] for px, py in points],
        )
        self.set_config_value("duration", max(16, min(3000, duration)))
        return x, y

    @property
    def endpoint(self):
        x, y = self.get_config_value("path")[-1]
        return (x * self.width, y * self.height)

    @property
    def mapping_start_x(self):
        return self.x + self.endpoint[0] - self.MAPPING_MODE_WIDTH / 2

    @property
    def mapping_start_y(self):
        return self.y + self.endpoint[1] - self.MAPPING_MODE_HEIGHT / 2

    @property
    def keycap_center(self):
        # Existing layouts and strokes ending at the screen edge may have no
        # padding beyond the last point. Fit the editor chrome inside the
        # allocation without moving any recorded Android coordinates.
        x, y = self.endpoint
        return (max(18, min(self.width - 18, x)), max(14, min(self.height - 14, y)))

    def get_editable_regions(self):
        x, y = self.keycap_center
        (region,) = super().get_editable_regions()
        region["bounds"] = (x - 24, y - 11, 48, 22)
        return [region]

    def capture_key_at_endpoint(self):
        self.get_widget_behavior(EditableWidgetBehavior).capture_at(*self.keycap_center)

    def get_delete_button_bounds(self):
        x, y = self.keycap_center
        return int(min(self.width - 14, x + 7)), int(max(0, y - 19)), 14, 14

    def get_settings_button_bounds(self):
        x, y = self.keycap_center
        return (
            int(min(self.width - 16, x + 17)),
            int(min(self.height - 16, y + 3)),
            16,
            16,
        )

    def do_contains(self, x, y):
        if self.mapping_mode:
            return False
        cx, cy = self.keycap_center
        return (
            abs(x - cx) <= 19
            and abs(y - cy) <= 16
            or self.is_point_in_settings_button(x, y)
            or self.is_point_in_delete_button(x, y)
        )

    def draw_widget_content(self, cr, width, height):
        if self.is_selected or self.is_hovered:
            points = [(x * width, y * height) for x, y in self.paths(False)[0]]
            cr.set_source_rgb(0.45, 0.86, 1)
            cr.set_line_width(1.5)
            cr.move_to(*points[0])
            for point in points[1:]:
                cr.line_to(*point)
            cr.stroke()
        x, y = self.keycap_center
        art.rounded(cr, x - 18, y - 14, 36, 28, 14)
        cr.set_source_rgba(0.16, 0.19, 0.25, 0.86)
        cr.fill()
        cr.set_line_width(2)
        cr.set_source_rgba(0.10, 0.68, 0.94, 0.88)
        cr.move_to(x - 8, y + 9)
        cr.curve_to(x - 2, y + 9, x + 1, y + 5, x + 7, y + 5)
        cr.stroke()

    def draw_selection_border(self, cr, width, height):
        x, y = self.keycap_center
        art.rounded(cr, x - 18, y - 14, 36, 28, 14)
        cr.set_source_rgb(*((0.02, 0.76, 0.99) if self.is_selected else (1, 1, 1)))
        cr.set_line_width(2)
        cr.stroke()

    def paths(self, reverse):
        points = self.get_config_value("path")
        if self.get_config_value("straight"):
            points = [points[0], points[-1]]
        return [points[::-1] if reverse else points]


class Scroll(PairedGesture):
    DEFAULT_DURATION = 200
    DEFAULT_DISTANCE = 50
    DEFAULT_BINDINGS = ("Up", "Down")
    ROW_ICONS = ("⌃", "⌄")
    WIDGET_NAME = _("Scroll gesture")
    WIDGET_DESCRIPTION = _(
        "Bind a key or wheel notch to scroll within the selected area."
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
        "Move two fingers around this point to zoom. Opposite wheel directions reverse the gesture."
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
