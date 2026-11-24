"""Geometry shared by keycap painting, pointer hit tests and the capture caret."""

from dataclasses import dataclass

from gi.repository import Pango, PangoCairo

from waydroid_helper.controller.widgets.base.control_art import rounded


@dataclass(frozen=True)
class Keycap:
    cx: float
    cy: float
    width: float
    height: float
    layout: Pango.Layout

    def contains(self, x, y):
        return (
            abs(x - self.cx) <= self.width / 2 and abs(y - self.cy) <= self.height / 2
        )


def keycap(widget, region, *, compact=False):
    x, y, w, h = region["bounds"]
    keys = region["get_keys"]()
    if widget.capture_region == region["id"] and widget.capture_preview is not None:
        keys = {widget.capture_preview}
    label = " / ".join(sorted(combo.format_keycap(widget.key_registry.keycap_labels) for combo in keys))
    layout = widget.create_pango_layout(label)
    size = 10 if compact else 13
    font = Pango.FontDescription.from_string("Sans Bold")
    font.set_absolute_size(size * Pango.SCALE)
    layout.set_font_description(font)
    available = max(1, int(w - 4))
    natural, _ = layout.get_pixel_size()
    if natural > available:
        # Keep both directions legible even when a translated wheel name or
        # a modifier chord is wider than the ordinary single-letter keycap.
        font.set_absolute_size(max(8, size * available / natural) * Pango.SCALE)
        layout.set_font_description(font)
    layout.set_ellipsize(Pango.EllipsizeMode.MIDDLE)
    layout.set_width(available * Pango.SCALE)
    layout.set_alignment(Pango.Alignment.CENTER)
    ink, logical = layout.get_pixel_extents()
    width = min(w, max(16, ink.width + 8))
    return Keycap(x + w / 2, y + h / 2, width, min(h, logical.height + 4), layout)


def paint(widget, cr, region, *, compact=False):
    box = keycap(widget, region, compact=compact)
    ident = region["id"]
    editing = widget.capture_region == ident
    if editing or (not compact and widget.hover_region == ident):
        rounded(
            cr,
            box.cx - box.width / 2,
            box.cy - box.height / 2,
            box.width,
            box.height,
            4,
        )
        cr.set_source_rgba(0, 0, 0, 0.52 if editing else 0.32)
        cr.fill()
    _, logical = box.layout.get_pixel_extents()
    cr.move_to(
        box.cx - box.layout.get_width() / Pango.SCALE / 2, box.cy - logical.height / 2
    )
    cr.set_source_rgba(1, 1, 1, 0.96)
    PangoCairo.show_layout(cr, box.layout)
    if editing and widget.caret_visible:
        width = max(10, box.width - 6)
        cr.rectangle(box.cx - width / 2, box.cy + box.height / 2 - 2, width, 2)
        cr.fill()
