"""Placement, endpoint keycap and editor geometry shared by drawn paths."""

import math
from gettext import gettext as _

from waydroid_helper.controller.widgets.base import control_art as art
from waydroid_helper.controller.widgets.base.decorator_contracts import EditableWidgetBehavior
from waydroid_helper.controller.widgets.base.stroke_config import StrokeConfig


class PlacedPath:
    PLACEMENT_HINT = _("Drag on the Android screen to record a swipe")
    PLACED_HINT = _(
        "Press the key or button that should replay this swipe"
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_config_item(StrokeConfig(
            "path", _("Draw the swipe path"), value=[[0.1, 0.5], [0.9, 0.5]], visible=False,
        ))
        self.add_config_change_callback("path", self.refresh_mapping_hint)

    def placed_points(self):
        return self.get_config_value("path")

    @property
    def mapping_anchor(self):
        x, y = self.endpoint
        return self.x + x, self.y + y

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
        return x, y

    @property
    def endpoint(self):
        x, y = self.get_config_value("path")[-1]
        return (x * self.width, y * self.height)

    @property
    def keycap_center(self):
        # Existing layouts and strokes ending at the screen edge may have no
        # padding beyond the last point. Fit the editor chrome inside the
        # allocation without moving any recorded Android coordinates.
        x, y = self.endpoint
        return (max(18, min(self.width - 18, x)), max(14, min(self.height - 14, y)))

    def get_editable_regions(self):
        x, y = self.keycap_center
        return [dict(id="default", name=self.WIDGET_NAME, bounds=(x - 24, y - 11, 48, 22),
                     get_keys=lambda: self.final_keys.copy(), set_keys=self.set_default_keys)]

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

    def path_contains(self, x, y):
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
            points = [(x * width, y * height) for x, y in self.placed_points()]
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
