"""Display Steam's original controller SVGs with live input feedback."""

from math import tau

import gi

gi.require_version("Graphene", "1.0")
from gi.repository import Adw, Gdk, Gio, Graphene, Gtk

from .gamepad_artwork import ArtworkPalette, ControllerArtwork
from .gamepad_layout import normalize_stick


class GamepadDiagram(Gtk.Widget):
    def __init__(self):
        super().__init__(hexpand=True)
        self.artwork = None
        self._nodes = []
        self._state = ((False,) * 26, (0,) * 6, ())
        self._texture_key = None
        self._style_manager = None
        self._style_handlers = []
        self.add_css_class("view")
        self.connect("map", self._watch_style)
        self.connect("unmap", self._unwatch_style)
        self.set_accessible_role(Gtk.AccessibleRole.IMG)

    def do_get_request_mode(self):
        return Gtk.SizeRequestMode.HEIGHT_FOR_WIDTH

    def do_measure(self, orientation, for_size):
        if orientation == Gtk.Orientation.HORIZONTAL:
            return 0, 900, -1, -1
        ratio = self.artwork.ratio if self.artwork else 1.6
        if for_size < 0:
            return 0, 260, -1, -1
        height = min(260, round(for_size / ratio))
        return height, height, -1, -1

    def configure(self, layout):
        resource = f"/com/jaoushingan/WaydroidHelper/gamepads/{layout}.svg"
        data = Gio.resources_lookup_data(
            resource, Gio.ResourceLookupFlags.NONE
        ).get_data()
        self.artwork = ControllerArtwork(data)
        self._state = ((False,) * 26, (0,) * 6, ())
        self._texture_key = None
        self.queue_resize()
        self.queue_draw()

    def set_state(self, buttons, axes, touches=()):
        state = (tuple(buttons), tuple(axes), tuple(tuple(touch) for touch in touches))
        if self._state != state:
            self._state = state
            self.queue_draw()

    def _watch_style(self, *_args):
        self._style_manager = Adw.StyleManager.get_for_display(self.get_display())
        for prop in ("dark", "high-contrast", "accent-color-rgba"):
            if self._style_manager.find_property(prop):
                handler = self._style_manager.connect(
                    "notify::" + prop, self._style_changed
                )
                self._style_handlers.append(handler)
        self.queue_draw()

    def _unwatch_style(self, *_args):
        for handler in self._style_handlers:
            self._style_manager.disconnect(handler)
        self._style_handlers.clear()
        self._style_manager = None
        self._nodes.clear()
        self._texture_key = None

    def _style_changed(self, *_args):
        # Theme changes must redraw an idle controller too; waiting for an input
        # event would leave the cached SVG in the previous color scheme.
        self.queue_draw()

    def _palette(self):
        context = self.get_style_context()
        foreground = (
            self.get_color() if hasattr(self, "get_color") else context.get_color()
        )
        _, background = context.lookup_color("view_bg_color")
        manager = self._style_manager or Adw.StyleManager.get_for_display(
            self.get_display()
        )
        if hasattr(manager, "get_accent_color_rgba"):
            accent = manager.get_accent_color_rgba()
        else:
            # libadwaita before 1.6 exposes its accent through named CSS colors.
            found, accent = context.lookup_color("accent_bg_color")
            if not found:
                accent = foreground
        return ArtworkPalette(
            foreground.to_string(),
            accent.to_string(),
            (background.red, background.green, background.blue),
            (foreground.red, foreground.green, foreground.blue),
            manager.get_high_contrast(),
        )

    def do_snapshot(self, snapshot):
        width, height = self.get_width(), self.get_height()
        if not self.artwork or width <= 0 or height <= 0:
            return
        density = self.get_scale_factor()
        palette = self._palette()
        key = (width, height, density, palette)
        if self._texture_key != key:
            self._nodes = self.artwork.prepare_nodes(width, height, density, palette)
            self._texture_key = key

        # The frame contains only retained texture nodes and up to two
        # translations. Button transitions select the other pre-rendered
        # variant without invalidating the artwork or uploading new textures.
        buttons, axes, touches = self._state
        _, _, svg_width, svg_height = self.artwork.bounds
        fit = min(width / svg_width, height / svg_height)
        for inputs, off, on in self._nodes:
            pressed = any(buttons[i] for i in inputs.buttons) or any(
                axes[i] > 0 for i in inputs.axes
            )
            node = on if pressed else off
            if node is None:
                continue
            if inputs.stick is None:
                snapshot.append_node(node)
                continue
            i = inputs.stick * 2
            x, y = normalize_stick(axes[i], axes[i + 1])
            snapshot.save()
            snapshot.translate(
                Graphene.Point().init(
                    x * inputs.travel_x * fit, y * inputs.travel_y * fit
                )
            )
            snapshot.append_node(node)
            snapshot.restore()

        if touches and self.artwork.touchpad:
            x, y, w, h = self.artwork.touchpad
            cr = snapshot.append_cairo(Graphene.Rect().init(0, 0, width, height))
            color = Gdk.RGBA()
            color.parse(palette.accent)
            cr.set_source_rgba(color.red, color.green, color.blue, color.alpha)
            cr.translate((width - svg_width * fit) / 2, (height - svg_height * fit) / 2)
            cr.scale(fit, fit)
            for pad, _finger, tx, ty, _pressure in touches:
                if pad == 0:
                    cr.arc(x + tx * w, y + ty * h, w * 0.025, 0, tau)
                    cr.fill()
