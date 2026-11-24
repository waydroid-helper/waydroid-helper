"""Two ordered stage thresholds on one physical trigger travel scale."""

from gettext import gettext as _
from math import tau

from gi.repository import Gtk

from waydroid_helper.controller.widgets.config import ConfigItem


class TriggerThresholds(ConfigItem):
    def validate(self, value):
        return (isinstance(value, (list, tuple)) and len(value) == 2
                and all(type(v) is int for v in value) and 1 <= value[0] < value[1] <= 100)

    def create_ui_widget(self, changed):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        spins = []
        row = Gtk.Box(spacing=6)
        for index, label in enumerate((_("Soft pull (%)"), _("Full pull (%)"))):
            spin = Gtk.SpinButton.new_with_range(1, 100, 1)
            spin.set_value(self.value[index])
            text = Gtk.Label(label=label)
            text.set_mnemonic_widget(spin)
            row.append(text)
            row.append(spin)
            spins.append(spin)
        box.append(row)
        track = Gtk.DrawingArea(content_height=28, hexpand=True)
        box.append(track)
        box.spins = spins

        def update(spin, index):
            other = spins[1 - index].get_value_as_int()
            value = spin.get_value_as_int()
            limit = min(value, other - 1) if index == 0 else max(value, other + 1)
            if value != limit:
                spin.set_value(limit)
                return
            changed(self.key, self.get_value_from_ui(box))
            track.queue_draw()

        for index, spin in enumerate(spins):
            spin.connect("value-changed", update, index)

        def draw(area, cr, width, height):
            y = height / 2
            color = area.get_style_context().get_color()
            cr.set_source_rgba(color.red, color.green, color.blue, .35)
            cr.set_line_width(3)
            cr.move_to(8, y)
            cr.line_to(width - 8, y)
            cr.stroke()
            for value in self.get_value_from_ui(box):
                cr.new_sub_path()
                cr.arc(8 + value / 100 * (width - 16), y, 5, 0, tau)
                cr.set_source_rgba(color.red, color.green, color.blue, .95)
                cr.fill()

        def percent(x):
            return round(100 * (x - 8) / max(1, track.get_width() - 16))

        def begin(drag, x, y):
            values = self.get_value_from_ui(box)
            drag.thumb = min(range(2), key=lambda i: abs(percent(x) - values[i]))
            drag.origin = x
            spins[drag.thumb].set_value(percent(x))

        track.set_draw_func(draw)
        drag = Gtk.GestureDrag(button=1)
        drag.connect("drag-begin", begin)
        drag.connect("drag-update", lambda g, dx, dy: spins[g.thumb].set_value(percent(g.origin + dx)))
        track.add_controller(drag)
        return box

    def get_value_from_ui(self, widget):
        return [spin.get_value_as_int() for spin in widget.spins]

    def set_value_to_ui(self, widget, value):
        # Move the upper bound first when the new pair is above the old range.
        order = (1, 0) if value[0] >= widget.spins[1].get_value() else (0, 1)
        for index in order:
            widget.spins[index].set_value(value[index])
