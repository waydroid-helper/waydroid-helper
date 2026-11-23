"""Cairo artwork for placed controls, in GTK logical pixels."""

import math

from cairo import LINE_CAP_ROUND, LINE_JOIN_ROUND


def rounded(cr, x, y, width, height, radius):
    radius = min(radius, width / 2, height / 2)
    cr.new_sub_path()
    for cx, cy, start in (
        (x + width - radius, y + radius, -90),
        (x + width - radius, y + height - radius, 0),
        (x + radius, y + height - radius, 90),
        (x + radius, y + radius, 180),
    ):
        cr.arc(cx, cy, radius, math.radians(start), math.radians(start + 90))
    cr.close_path()


def disc(cr, x, y, radius, fill, outline=None, weight=1.5):
    cr.new_sub_path()
    cr.arc(x, y, max(1, radius), 0, math.tau)
    cr.set_source_rgba(*fill)
    cr.fill_preserve()
    if outline:
        cr.set_line_width(weight)
        cr.set_source_rgba(*outline)
        cr.stroke()
    else:
        cr.new_path()


def guide(cr, points):
    """Mark the initial contact with a dot and the final tangent with an arrow."""
    x, y = points[0]
    cr.set_line_width(2.2)
    cr.set_line_cap(LINE_CAP_ROUND)
    cr.set_line_join(LINE_JOIN_ROUND)
    cr.move_to(x, y)
    for px, py in points[1:]:
        cr.line_to(px, py)
    cr.stroke()
    cr.arc(x, y, 3.4, 0, math.tau)
    cr.fill()
    tip = points[-1]
    start = next((p for p in reversed(points[:-1]) if math.dist(p, tip) > 1), None)
    if start:
        angle = math.atan2(tip[1] - start[1], tip[0] - start[0])
        for delta in (-0.60, 0.60):
            cr.move_to(*tip)
            cr.rel_line_to(-7 * math.cos(angle + delta), -7 * math.sin(angle + delta))
        cr.stroke()


# The editor draws on a dimmed guest surface. Hints are composited on the
# undimmed surface and the user's F12/opacity settings apply to the result.
BODY = (0.12, 0.14, 0.19, 0.78)
OUTLINE = (0.82, 0.85, 0.9, 0.32)
HINT = (0.12, 0.13, 0.16, 0.58)


def ring(cr, x, y, radius, selected):
    cr.set_source_rgba(*((0.02, 0.77, 1, 1) if selected else (1, 1, 1, 0.95)))
    cr.set_line_width(2.5 if selected else 1.5)
    cr.new_sub_path()
    cr.arc(x, y, max(1, radius), 0, math.tau)
    cr.stroke()


def caption(cr, x, y, text, size, color=(1, 1, 1, 0.94)):
    from gi.repository import Pango, PangoCairo

    layout = PangoCairo.create_layout(cr)
    font = Pango.FontDescription.from_string("Sans Bold")
    font.set_absolute_size(size * Pango.SCALE)
    layout.set_font_description(font)
    layout.set_text(text, -1)
    w, h = layout.get_pixel_size()
    cr.move_to(x - w / 2, y - h / 2)
    cr.set_source_rgba(*color)
    PangoCairo.show_layout(cr, layout)


def compass(cr, x, y, radius):
    for i in range(4):
        cr.save()
        cr.translate(x, y)
        cr.rotate(i * math.pi / 2)
        cr.move_to(-3, -radius + 2)
        cr.line_to(0, -radius - 2)
        cr.line_to(3, -radius + 2)
        cr.close_path()
        cr.set_source_rgba(0.65, 0.7, 0.78, 0.55)
        cr.set_line_width(1)
        cr.stroke()
        cr.restore()


def sights(cr, x, y, radius):
    for i in range(4):
        cr.save()
        cr.translate(x, y)
        cr.rotate(i * math.pi / 2)
        cr.move_to(0, -radius)
        cr.line_to(0, -radius * 0.66)
        cr.set_source_rgba(1, 1, 1, 0.65)
        cr.set_line_width(1.5)
        cr.stroke()
        cr.restore()


def range_guides(cr, width, height):
    cr.set_source_rgba(0.85, 0.91, 0.98, 0.14)
    cr.rectangle(2, 2, width - 4, height - 4)
    cr.fill()
    cr.set_source_rgba(0.85, 0.91, 0.98, 0.6)
    cr.set_line_width(1)
    cr.move_to(width / 2, 2)
    cr.line_to(width / 2, height - 2)
    cr.move_to(2, height / 2)
    cr.line_to(width - 2, height / 2)
    cr.stroke()


def cross_pad(cr, x, y, radius):
    cr.save()
    cr.translate(x, y)
    cr.scale(radius, radius)
    cr.move_to(-0.18, -1)
    for i in range(4):
        cr.line_to(0.18, -1)
        cr.curve_to(0.31, -1, 0.31, -0.89, 0.31, -0.74)
        cr.curve_to(0.31, -0.45, 0.45, -0.31, 0.74, -0.31)
        cr.curve_to(0.89, -0.31, 1, -0.31, 1, -0.18)
        cr.rotate(math.pi / 2)
    cr.close_path()
    cr.set_source_rgba(0.38, 0.40, 0.44, 0.8)
    cr.fill()
    cr.restore()
    disc(cr, x, y, radius * 0.20, BODY)


def mouse(cr, x, y, radius, right):
    w, h = radius * 1.26, radius * 1.8
    rounded(cr, x - w / 2, y - h / 2, w, h, w * 0.46)
    cr.set_source_rgba(1, 1, 1, 0.95)
    cr.set_line_width(1.5)
    cr.stroke()
    cr.move_to(x, y - h * 0.44)
    cr.line_to(x, y)
    cr.line_to(x - w * 0.48, y)
    cr.move_to(x, y)
    cr.line_to(x + w * 0.48, y)
    cr.stroke()
    cr.save()
    rounded(cr, x - w / 2 + 1, y - h / 2 + 1, w - 2, h - 2, w * 0.44)
    cr.clip()
    cr.set_source_rgb(0.05, 0.78, 1)
    cr.rectangle(x + 1 if right else x - w / 2 + 1, y - h / 2 + 1, w / 2 - 2, h / 2 - 2)
    cr.fill()
    cr.restore()
