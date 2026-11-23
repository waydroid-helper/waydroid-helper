"""Continuous gamepad stick input for movement wheels and camera drags."""

import math
import time
from gettext import gettext as _

from gi.repository import GLib

from waydroid_helper.controller.android.input import AMotionEventAction as Motion
from waydroid_helper.controller.core.event_bus import EventType
from waydroid_helper.controller.widgets.base import control_art as art
from waydroid_helper.controller.widgets.base.touch_control import TouchControl
from waydroid_helper.controller.widgets.config import (
    create_dropdown_config,
    create_slider_config,
    create_switch_config,
)
from waydroid_helper.controller.widgets.decorators import Resizable


@Resizable()
class AnalogStick(TouchControl):
    MAPPING_MODE_WIDTH = MAPPING_MODE_HEIGHT = 54
    EMBEDDED_ONLY = True
    DEFAULT_STICK = "left"
    DEFAULT_ACTION = "move"
    WIDGET_NAME = _("Left stick")
    WIDGET_DESCRIPTION = _(
        "Place on a movement wheel or camera area and choose the physical stick."
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.add_config_item(
            create_dropdown_config(
                "stick",
                _("Stick"),
                ["left", "right"],
                value=self.DEFAULT_STICK,
                option_labels={"left": _("Left stick"), "right": _("Right stick")},
            )
        )
        self.add_config_item(
            create_dropdown_config(
                "action",
                _("Action"),
                ["move", "look"],
                value=self.DEFAULT_ACTION,
                option_labels={"move": _("Movement wheel"), "look": _("Camera pan")},
            )
        )
        self.add_config_item(
            create_slider_config("deadzone", _("Dead zone (%)"), 12, 0, 75)
        )
        self.add_config_item(
            create_slider_config("speed", _("Camera speed (%)"), 100, 10, 400)
        )
        self.add_config_item(
            create_switch_config("recenter", _("Resume panning at the edge"), True)
        )
        self.device = None
        self.vector = (0.0, 0.0)
        self.timer = 0
        self.event_bus.subscribe(EventType.GAMEPAD_STICK, self._axis, subscriber=self)

    def _radius(self, width, height):
        if self.get_config_value("action") == "move":
            return max(2, min(width, height) / 2 - 5)
        return min(24, width / 2 - 2, height / 2 - 2)

    def get_edit_chrome_radius(self):
        return self._radius(self.width, self.height)

    def draw_widget_content(self, cr, width, height):
        x, y = width / 2, height / 2
        radius = self._radius(width, height)
        movement = self.get_config_value("action") == "move"
        # The movement wheel represents the entire analog range. A camera
        # stick keeps a fixed-size knob and reveals its pan bounds on selection.
        if self.is_selected and not movement:
            art.range_guides(cr, width, height)
        art.disc(cr, x, y, radius, art.BODY, art.OUTLINE)
        art.disc(cr, x, y, radius * 0.77, (0.08, 0.10, 0.14, 0.54))
        art.compass(cr, x, y, radius * 0.63)
        vx, vy = self.vector if self.device else ((0, 0) if movement else (0.28, -0.28))
        knob = (0.20, 0.22, 0.26, 0.94) if movement else (0.62, 0.64, 0.68, 0.96)
        art.disc(
            cr, x + vx * radius * 0.55, y + vy * radius * 0.55, radius * 0.36, knob
        )

    def draw_text_content(self, cr, width, height):
        pass

    def draw_mapping_mode_background(self, cr, width, height):
        pass  # The stick paints its own circular background and moving knob.

    def draw_mapping_mode_content(self, cr, width, height):
        x, y = width / 2, height / 2
        radius = min(10, x - 2, y - 2)
        art.disc(cr, x, y, radius, art.HINT)
        # Each compact hint depicts a physical stick from the side. Mirror
        # the resting tilt so the two axes remain distinguishable at a glance.
        tilt = -0.22 if self.get_config_value("stick") == "left" else 0.22
        dx, dy = self.vector if self.device is not None else (0.0, 0.0)
        tip_x = x + (tilt + dx * 0.3) * radius
        tip_y = y + (-0.23 + dy * 0.24) * radius
        cr.save()
        cr.translate(x, y + radius * 0.42)
        cr.scale(1, 0.46)
        art.disc(cr, 0, 0, radius * 0.30, art.BODY, art.OUTLINE)
        cr.restore()
        cr.set_line_width(1.6)
        cr.move_to(x, y + radius * 0.42)
        cr.line_to(tip_x, tip_y)
        cr.set_source_rgb(0.24, 0.78, 0.96)
        cr.stroke()
        art.disc(cr, tip_x, tip_y, radius * 0.33, art.BODY, (1, 1, 1, 0.95), 1.2)

    def draw_selection_border(self, cr, width, height):
        art.ring(
            cr, width / 2, height / 2, self._radius(width, height), self.is_selected
        )

    def _axis(self, event):
        device, stick, x, y = event.data
        if not self.mapping_mode or stick != self.get_config_value("stick"):
            return
        if self.device is not None and self.device != device:
            return
        length = math.hypot(x, y)
        deadzone = self.get_config_value("deadzone") / 100
        if length <= deadzone:
            self.stop_gesture()
            return

        # Apply a radial dead zone and rescale the remaining travel. This keeps
        # diagonal and axial movements equally fast, including partial deflection.
        gain = (min(1, length) - deadzone) / ((1 - deadzone) * length)
        self.vector = (x * gain, y * gain)
        if not self.contacts and not self.touch(0, Motion.DOWN, *self.center):
            return
        self.device = device
        self.queue_draw()
        if self.get_config_value("action") == "move":
            cx, cy = self.center
            self.touch(
                0,
                Motion.MOVE,
                cx + self.vector[0] * self.width / 2,
                cy + self.vector[1] * self.height / 2,
            )
        elif not self.timer:
            self.position = self.center
            self.last_tick = time.monotonic()
            self.timer = GLib.timeout_add(16, self._pan)

    def _pan(self):
        now = time.monotonic()
        travel = min(now - self.last_tick, 0.05) * self.get_config_value("speed") / 100
        self.last_tick = now
        x = self.position[0] + self.vector[0] * self.width * travel
        y = self.position[1] + self.vector[1] * self.height * travel
        px = min(max(x, self.x), self.x + self.width)
        py = min(max(y, self.y), self.y + self.height)
        self.touch(0, Motion.MOVE, px, py)
        self.position = (px, py)
        if (px != x or py != y) and self.get_config_value("recenter"):
            self.touch(0, Motion.UP, px, py)
            self.position = self.center
            self.touch(0, Motion.DOWN, *self.position)
        return GLib.SOURCE_CONTINUE

    def stop_gesture(self):
        if self.timer:
            GLib.source_remove(self.timer)
            self.timer = 0
        self.device = None
        self.queue_draw()
        super().stop_gesture()


class RightStick(AnalogStick):
    WIDGET_NAME = _("Right stick")
    DEFAULT_STICK = "right"
    DEFAULT_ACTION = "look"
