"""Allocate the nested output and map saved controls onto its visible area."""

from gi.repository import GObject, Graphene, Gsk, Gtk


class EmulatorViewport(Gtk.Widget):
    __gsignals__ = {"output-resized": (GObject.SignalFlags.RUN_LAST, None, ())}
    DEFAULT_WINDOW_SIZE = (960, 540)

    def __init__(self, compositor, canvas):
        super().__init__(hexpand=True, vexpand=True, overflow=Gtk.Overflow.HIDDEN)
        self.compositor = compositor
        self.canvas = canvas
        self.mapping_size = self.DEFAULT_WINDOW_SIZE
        self.configured_output = None
        self.output_size = None
        compositor.set_parent(self)
        canvas.set_parent(self)

    def set_configured_output(self, size: tuple[int, int] | None):
        """Adopt the logical extent negotiated with the Waydroid HWC."""
        self.configured_output = size
        self.mapping_size = size or self.DEFAULT_WINDOW_SIZE
        self.queue_allocate()

    @staticmethod
    def drag_width(initial_width, height_per_width, edge, dx, dy):
        horizontal = -dx if "w" in edge else dx
        vertical = -dy if "n" in edge else dy
        if len(edge) == 2:
            return initial_width + (horizontal + vertical * height_per_width) / (
                1 + height_per_width**2
            )
        if edge in ("n", "s"):
            return initial_width + vertical / height_per_width
        return initial_width + horizontal

    def do_size_allocate(self, width, height, baseline):
        if width <= 0 or height <= 0:
            return
        map_w, map_h = self.mapping_size
        scale = min(width / map_w, height / map_h)
        view_w, view_h = max(1, round(map_w * scale)), max(1, round(map_h * scale))
        origin = Graphene.Point().init((width - view_w) / 2, (height - view_h) / 2)
        position = Gsk.Transform().translate(origin)

        # A desktop resize changes only the presentation transform. Waydroid's
        # hardware composer treats a new wl_output mode as a display hotplug.
        # Latch the initial allocation for instances without a configured mode
        # so dragging a corner never reconfigures SurfaceFlinger.
        guest_w, guest_h = (
            self.configured_output or self.output_size or (view_w, view_h)
        )
        self.compositor.allocate(
            guest_w, guest_h, -1, position.scale(view_w / guest_w, view_h / guest_h)
        )

        # Stored controls have their own stable coordinate system. Their GTK
        # transform maps both drawing and pointer events to the visible output.
        self.canvas.allocate(
            map_w, map_h, -1, position.scale(view_w / map_w, view_h / map_h)
        )
        if self.output_size != (guest_w, guest_h):
            self.output_size = (guest_w, guest_h)
            self.emit("output-resized")

    def do_snapshot(self, snapshot):
        self.snapshot_child(self.compositor, snapshot)
        self.snapshot_child(self.canvas, snapshot)

    def detach(self):
        self.canvas.unparent()
        self.compositor.unparent()
