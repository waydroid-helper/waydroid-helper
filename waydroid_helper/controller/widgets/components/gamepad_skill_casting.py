"""Hold a gamepad button and aim a virtual skill stick with the right stick."""

from gettext import gettext as _, pgettext
from math import hypot

from waydroid_helper.controller.android.input import AMotionEventAction as Motion
from waydroid_helper.controller.core.handler.event_handlers import InputEventType
from waydroid_helper.controller.widgets.base import control_art as art
from waydroid_helper.controller.widgets.base.touch_control import TouchControl
from waydroid_helper.controller.widgets.decorators import Editable, Resizable
from waydroid_helper.controller.widgets.decorators.resize_geometry import ResizeStrategy


@Editable
@Resizable(resize_strategy=ResizeStrategy.CENTER)
class GamepadSkillCasting(TouchControl):
    EMBEDDED_ONLY = True
    MIN_WIDTH = MIN_HEIGHT = 25
    WIDGET_NAME = pgettext("Controller Widgets", "Skill Casting")
    WIDGET_DESCRIPTION = _("Hold the bound button, aim with the right stick, and release the button to cast")

    def __init__(self, x=0, y=0, width=150, height=150, **kwargs):
        diameter = min(width, height)
        super().__init__(x, y, diameter, diameter, **kwargs)
        self.stick = None

    @property
    def radius(self):
        """Maximum touch travel from the center of the placed gamepad control."""
        return self.width / 2

    def get_edit_chrome_radius(self):
        return max(5, min(24, self.radius - 4))

    def draw_widget_content(self, cr, width, height):
        cx, cy = width / 2, height / 2
        cap = self.get_edit_chrome_radius()
        art.disc(cr, cx, cy, cap, art.BODY, art.OUTLINE)
        art.disc(cr, cx, cy, cap * .74, (.16, .26, .32, .78))
        art.disc(cr, cx, cy, cap * .48, (.2, .34, .40, .66))
        if self.is_selected or self.is_hovered:
            art.ring(cr, cx, cy, max(1, self.radius - 1.5), self.is_selected)

    def draw_selection_border(self, cr, width, height):
        art.ring(cr, width / 2, height / 2, self.get_edit_chrome_radius(), self.is_selected)

    def on_key_triggered(self, key_combination=None, event=None):
        if (not self.mapping_mode or not event or event.event_type != InputEventType.KEY_PRESS
                or not event.right_stick or not key_combination or event.key not in key_combination):
            return False
        if self.stick or not event.right_stick.claim(self, key_combination):
            return True  # A held skill has exclusive aim until its button goes up.
        self.stick = event.right_stick
        if not self.touch(0, Motion.DOWN, *self.center):
            self.stop_gesture()
            return False
        self.aim_at(*self.stick.position)
        return True

    def aim_at(self, x, y):
        # Manette reports square axis bounds. Preserve partial deflection and
        # project only the corners onto the skill circle. Center is a valid
        # aiming position and must keep the Android finger down.
        scale = self.radius / max(1, hypot(x, y))
        cx, cy = self.center
        w, h = self.screen_geometry.get_host_resolution()
        point = (max(0, min(w - 1, round(cx + x * scale))),
                 max(0, min(h - 1, round(cy + y * scale))))
        if self.contacts.get(0) != point:
            self.touch(0, Motion.MOVE, *point)

    def cancel_at(self, x, y):
        # Games decide whether to cast or cancel from the final position of
        # the original skill finger. A second tap on the cancel area would
        # leave that finger aiming and release the skill on the next button up.
        self.touch(0, Motion.MOVE, x, y)
        self.stop_gesture()

    def on_key_released(self, key_combination=None, event=None):
        if self.stick and self.stick.binding == key_combination:
            self.stop_gesture()
            return True
        return False

    def stop_gesture(self):
        super().stop_gesture()
        if self.stick is not None:
            self.stick.release(self)
            self.stick = None
