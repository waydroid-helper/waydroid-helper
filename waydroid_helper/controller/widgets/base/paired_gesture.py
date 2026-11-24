"""Two independently bindable directions at one Android target."""

from gettext import gettext as _

from waydroid_helper.controller.core.key_system import KeyCombination
from waydroid_helper.controller.widgets.base import binding_art, control_art as art
from waydroid_helper.controller.widgets.base.timed_gesture import TimedGesture
from waydroid_helper.controller.widgets.config import create_slider_config
from waydroid_helper.controller.widgets.decorators import Editable


@Editable(max_keys=1)
class PairedGesture(TimedGesture):
    CENTER_MAPPING_HINT = True
    MAPPING_MODE_WIDTH = 62
    MAPPING_MODE_HEIGHT = 42
    DIRECTIONS = ("forward", "reverse")
    ROW_ICONS = ("+", "−")
    DEFAULT_DISTANCE = 100
    DEFAULT_BINDINGS = ("Wheel_Up", "Wheel_Down")

    def __init__(self, *args, binding_rows=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.rows = {direction: set() for direction in self.DIRECTIONS}
        if binding_rows is not None:
            self.rows.update(binding_rows)
        elif kwargs.get("default_keys") is not None:
            # Layouts predating the two keycaps stored a flat set. Retain all
            # chords, including Ctrl+wheel and custom keyboard assignments.
            for combo in self.final_keys:
                reverse = any(
                    k.name in ("Wheel_Down", "Wheel_Left", "Down") for k in combo
                )
                self.rows[self.DIRECTIONS[reverse]].add(combo)
        else:
            for direction, name in zip(self.DIRECTIONS, self.DEFAULT_BINDINGS):
                self.rows[direction].add(
                    KeyCombination.from_names([name], self.key_registry)
                )
        self.final_keys = set.union(*self.rows.values())
        self.held_binding = None
        self.add_config_item(
            create_slider_config(
                "distance", _("Gesture distance"), self.DEFAULT_DISTANCE, 1, 100, 1
            )
        )
        self.add_config_change_callback("distance", lambda *_: self.queue_draw())

    def get_layout_binding_rows(self):
        return self.rows

    def _bind(self, direction, keys):
        # Moving the same chord from one row to the other must leave exactly
        # one direction for that chord after saving and reopening the layout.
        for ident in self.DIRECTIONS:
            if ident != direction:
                self.rows[ident].difference_update(keys)
        self.rows[direction] = set(keys)
        self.final_keys = set.union(*self.rows.values())

    def regions(self, width, height, compact=False):
        cx, cy = width / 2, height / 2
        row_width = min(width - 4, 48 if compact else width * 0.46)
        spacing = min(9 if compact else 14, height * 0.18)
        for index, direction in enumerate(self.DIRECTIONS):
            x = cx if compact else cx + 4
            y = cy + (2 * index - 1) * spacing
            yield dict(
                id=direction,
                name=self.WIDGET_NAME,
                bounds=(x - row_width / 2, y - spacing, row_width, 2 * spacing),
                get_keys=lambda d=direction: self.rows[d].copy(),
                set_keys=lambda keys, d=direction: self._bind(d, keys),
            )

    def get_editable_regions(self):
        return list(self.regions(self.width, self.height))

    def draw_widget_content(self, cr, width, height):
        radius = self._radius(width, height)
        art.disc(cr, width / 2, height / 2, radius, art.BODY, art.OUTLINE)
        for icon, region in zip(self.ROW_ICONS, self.get_editable_regions()):
            _, y, _, h = region["bounds"]
            art.caption(cr, width / 2 - radius * 0.54, y + h / 2, icon, 9)
        ax = max(8, width / 2 - radius - 9)
        ay = height / 2
        for delta, icon in ((-13, "▴"), (13, "▾")):
            art.caption(cr, ax, ay + delta, icon, 10)
        art.caption(cr, ax, ay, str(int(self.get_config_value("distance"))), 9)

    def adjust_at(self, x, y):
        ax = max(8, self.width / 2 - self._radius(self.width, self.height) - 9)
        dy = y - self.height / 2
        if abs(x - ax) > 8 or not 6 <= abs(dy) <= 22:
            return False
        value = self.get_config_value("distance") + (1 if dy < 0 else -1)
        self.set_config_value("distance", max(1, min(100, value)))
        return True

    @staticmethod
    def _radius(width, height):
        return min(width * 0.33, height / 2 - 6)

    def get_edit_chrome_radius(self):
        return self._radius(self.width, self.height)

    def draw_selection_border(self, cr, width, height):
        art.ring(
            cr, width / 2, height / 2, self._radius(width, height), self.is_selected
        )

    def draw_mapping_mode_background(self, cr, width, height):
        pass  # The two rows share one pill fitted to the longest key.

    def draw_mapping_mode_content(self, cr, width, height):
        regions = list(self.regions(width, height, compact=True))
        cap_width = (
            max(binding_art.keycap(self, r, compact=True).width for r in regions) + 3
        )
        art.rounded(cr, (width - cap_width) / 2, 2, cap_width, height - 4, 10)
        cr.set_source_rgba(*art.HINT)
        cr.fill()
        for region in regions:
            binding_art.paint(self, cr, region, compact=True)

    def reverse_binding(self, combo, event):
        return combo in self.rows["reverse"]

    def on_key_triggered(self, key_combination=None, event=None):
        handled = super().on_key_triggered(key_combination, event)
        if handled and event and event.key and not event.key.name.startswith("Wheel_"):
            self.held_binding = (key_combination, event)
        return handled

    def on_key_released(self, key_combination=None, event=None):
        if self.held_binding and self.held_binding[0] == key_combination:
            self.held_binding = None
        return True

    def next_gesture(self):
        return super().next_gesture() or self.held_binding

    def stop_gesture(self):
        self.held_binding = None
        super().stop_gesture()
