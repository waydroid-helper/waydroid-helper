"""Animate input layers annotated from Steam's original SVG components."""

from copy import deepcopy
from dataclasses import dataclass
from functools import lru_cache
from itertools import groupby
from math import ceil, floor
import sys
import xml.etree.ElementTree as ET

import cairo
import gi

gi.require_version("Rsvg", "2.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Gsk", "4.0")
gi.require_version("Graphene", "1.0")
from gi.repository import Gdk, GLib, Graphene, Gsk, Rsvg

from .gamepad_layout import normalize_stick

SVG = "http://www.w3.org/2000/svg"
ET.register_namespace("", SVG)


@dataclass(frozen=True)
class ArtworkPalette:
    """Resolved GTK colors; the SVG renderer does not select an application theme."""

    foreground: str
    accent: str
    background_rgb: tuple[float, float, float]
    foreground_rgb: tuple[float, float, float]
    high_contrast: bool = False

    @staticmethod
    def _luminance(rgb):
        linear = (
            c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in rgb
        )
        return sum(c * weight for c, weight in zip(linear, (0.2126, 0.7152, 0.0722)))

    @lru_cache(maxsize=256)
    def source_color(self, value):
        if value in ("none", "currentColor"):
            return value
        if self.high_contrast:
            return "currentColor"
        if value == "black":
            return value
        if not value.startswith("#") or len(value) != 7:
            return value
        rgb = tuple(int(value[i : i + 2], 16) / 255 for i in (1, 3, 5))
        if max(rgb) == min(rgb):
            return value  # Preserve the original neutral thumbstick shading.
        background = self._luminance(self.background_rgb)

        def contrast(candidate):
            light = self._luminance(candidate)
            return (max(light, background) + 0.05) / (min(light, background) + 0.05)

        if contrast(rgb) >= 3:
            return value
        # Steam's pastel glyphs suit its dark surface. Blend only insufficiently
        # contrasting colors toward GTK's foreground, preserving each glyph's
        # hue as far as possible instead of maintaining a second hardcoded theme.
        if contrast(self.foreground_rgb) < 3:
            return "currentColor"
        low, high = 0.0, 1.0
        for _ in range(14):
            amount = (low + high) / 2
            candidate = tuple(
                c + (ink - c) * amount for c, ink in zip(rgb, self.foreground_rgb)
            )
            if contrast(candidate) >= 3:
                high = amount
            else:
                low = amount
        adjusted = tuple(
            c + (ink - c) * high for c, ink in zip(rgb, self.foreground_rgb)
        )
        return "rgb(%s)" % ",".join(f"{c * 255:.4f}" for c in adjusted)


@dataclass(frozen=True)
class LayerInput:
    buttons: tuple[int, ...]
    axes: tuple[int, ...]
    stick: int | None
    travel_x: float
    travel_y: float

    @classmethod
    def from_element(cls, element):
        # The extraction tool annotates each drawable at the SVG root. Some
        # shapes belong to multiple inputs; any of those inputs can light it.
        return cls(
            tuple(
                int(k.removeprefix("data-button-"))
                for k in element.attrib
                if k.startswith("data-button-")
            ),
            tuple(
                int(k.removeprefix("data-axis-"))
                for k in element.attrib
                if k.startswith("data-axis-")
            ),
            next((i for i in (0, 1) if element.get(f"data-stick-{i}")), None),
            float(element.get("data-stick-x-travel", 0)),
            float(element.get("data-stick-y-travel", 0)),
        )


class ControllerArtwork:
    def __init__(self, data):
        self.source = ET.fromstring(data)
        self.bounds = tuple(float(v) for v in self.source.get("viewBox").split())
        self.ratio = self.bounds[2] / self.bounds[3]
        # Preserve the component's original viewBox, path coordinates, outline
        # weights and glyph colors. Annotations were obtained by comparing the
        # component's own highlight properties during extraction, not by
        # manually assigning guessed regions to an approximate drawing.
        self.source.set("width", str(self.bounds[2]))
        self.source.set("height", str(self.bounds[3]))
        self.layers = []
        # Batch adjacent shapes that always change together. Do not reorder
        # them: on some models a stationary outline is painted over a stick.
        children = list(self.source)
        self.source[:] = [e for e in children if e.tag == f"{{{SVG}}}defs"]
        drawables = (e for e in children if e.tag != f"{{{SVG}}}defs")
        for index, (inputs, shapes) in enumerate(
            groupby(drawables, LayerInput.from_element)
        ):
            group_id = f"input-layer-{index}"
            group = ET.SubElement(self.source, f"{{{SVG}}}g", id=group_id)
            group.extend(shapes)
            self.layers.append(("#" + group_id, inputs))
        self.touchpad = None
        handle = Rsvg.Handle.new_from_data(ET.tostring(self.source))
        viewport = self._viewport(0, 0, self.bounds[2], self.bounds[3])
        for element in self.source.iter():
            if element.get("data-touchpad"):
                _, ink, _ = handle.get_geometry_for_layer(
                    "#" + element.get("id"), viewport
                )
                self.touchpad = (ink.x, ink.y, ink.width, ink.height)
                break

    @staticmethod
    def _viewport(x, y, width, height):
        rectangle = Rsvg.Rectangle()
        rectangle.x, rectangle.y = x, y
        rectangle.width, rectangle.height = width, height
        return rectangle

    def frame(self, buttons, axes, touches, palette=None):
        root = deepcopy(self.source)
        if palette:
            root.set("color", palette.foreground)
        accent = palette.accent if palette else "#4897d2"
        for element in root.iter():
            if palette:
                for attribute in ("fill", "stroke"):
                    if value := element.get(attribute):
                        element.set(attribute, palette.source_color(value))
                if palette.high_contrast and element.get("opacity"):
                    element.set("opacity", "1")
            active = False
            for attribute in element.attrib:
                if attribute.startswith("data-button-"):
                    active |= bool(buttons[int(attribute.removeprefix("data-button-"))])
                elif attribute.startswith("data-axis-"):
                    active |= axes[int(attribute.removeprefix("data-axis-"))] > 0
            if element.get("data-conditional"):
                element.set("display", "inline" if active else "none")
            if active:
                element.set("fill", accent)
            for stick in range(2):
                if element.get(f"data-stick-{stick}"):
                    x, y = normalize_stick(*axes[stick * 2 : stick * 2 + 2])
                    # Travel distances come from Steam's translateX/translateY
                    # expressions, converted from viewport percentages by the
                    # extraction tool. Keep the native stationary stick rings.
                    dx = x * float(element.get("data-stick-x-travel", 0))
                    dy = y * float(element.get("data-stick-y-travel", 0))
                    original = element.get("transform", "")
                    element.set("transform", f"translate({dx} {dy}) {original}")
        if self.touchpad:
            x, y, width, height = self.touchpad
            for pad, _finger, tx, ty, _pressure in touches:
                if pad == 0:
                    ET.SubElement(
                        root,
                        "{" + SVG + "}circle",
                        {
                            "cx": str(x + tx * width),
                            "cy": str(y + ty * height),
                            "r": str(width * 0.025),
                            "fill": accent,
                        },
                    )
        return Rsvg.Handle.new_from_data(ET.tostring(root))

    def render(self, frame, cr, width, height):
        frame.render_document(cr, self._viewport(0, 0, width, height))

    def prepare_nodes(self, width, height, density, palette):
        """Rasterize the SVG once per allocation, device scale and theme."""
        buttons = [False] * 26
        neutral = self.frame(buttons, [0] * 6, (), palette)
        pressed = self.frame([True] * len(buttons), [0, 0, 0, 0, 1, 1], (), palette)
        _, _, svg_width, svg_height = self.bounds
        fit = min(width / svg_width, height / svg_height)
        left, top = (width - svg_width * fit) / 2, (height - svg_height * fit) / 2
        viewport = self._viewport(0, 0, svg_width, svg_height)

        def rasterize(handle, selector):
            _, ink, _ = handle.get_geometry_for_layer(selector, viewport)
            if ink.width <= 0 or ink.height <= 0:
                return None
            # Snap the crop to physical pixels with a one-pixel AA margin.
            # A stick then occupies a small texture even on a HiDPI monitor.
            x = floor((left + ink.x * fit) * density) - 1
            y = floor((top + ink.y * fit) * density) - 1
            w = ceil((left + (ink.x + ink.width) * fit) * density) + 1 - x
            h = ceil((top + (ink.y + ink.height) * fit) * density) + 1 - y
            surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, w, h)
            cr = cairo.Context(surface)
            cr.translate(left * density - x, top * density - y)
            cr.scale(fit * density, fit * density)
            handle.render_layer(cr, selector, viewport)
            surface.flush()
            fmt = (
                Gdk.MemoryFormat.B8G8R8A8_PREMULTIPLIED
                if sys.byteorder == "little"
                else Gdk.MemoryFormat.A8R8G8B8_PREMULTIPLIED
            )
            # PyGObject can copy bytes directly. Passing Cairo's memoryview
            # would marshal its pixels individually during the first frame.
            texture = Gdk.MemoryTexture.new(
                w,
                h,
                fmt,
                GLib.Bytes.new(bytes(surface.get_data())),
                surface.get_stride(),
            )
            return Gsk.TextureNode.new(
                texture,
                Graphene.Rect().init(
                    x / density, y / density, w / density, h / density
                ),
            )

        nodes = []
        for selector, inputs in self.layers:
            off = rasterize(neutral, selector)
            on = rasterize(pressed, selector) if inputs.buttons or inputs.axes else off
            nodes.append((inputs, off, on))
        return nodes
