"""Physical input tester for one connected controller."""

from gettext import gettext as _

from gi.repository import Adw, Gtk

from waydroid_helper.gamepad_diagram import GamepadDiagram
from waydroid_helper.gamepad_layout import PreviewInputs, TriggerAxes, artwork_for_device, button_labels_for


class GamepadPreview(Adw.PreferencesPage):
    def __init__(self, device):
        super().__init__()
        self.device = device
        self.handlers = []
        self.redraw_tick = 0
        self.mapping = (device.get_mapping() or "") if hasattr(device, "get_mapping") else ""
        layout = artwork_for_device(device, self.mapping)
        group = Adw.PreferencesGroup()
        self.add(group)
        self.diagram = GamepadDiagram()
        self.diagram.configure(layout)
        self.diagram.update_property([Gtk.AccessibleProperty.LABEL], [device.get_name()])
        card = Gtk.Box(overflow=Gtk.Overflow.HIDDEN, css_classes=["card", "view"])
        card.append(self.diagram)
        group.add(card)

        columns = Gtk.Box(homogeneous=True, spacing=12, margin_top=10)
        group.add(columns)
        labels = button_labels_for(layout, bool(self.mapping))
        trigger_names = (labels.get("LT", "LT"), labels.get("RT", "RT"))
        self.trigger_labels = []
        self.stick_labels = []
        self.meters = []
        self.analog_triggers = []
        available = TriggerAxes(self.mapping).available(device, bool(self.mapping))
        for i, (trigger, stick) in enumerate(zip(trigger_names, (_("Left stick"), _("Right stick")))):
            column = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            columns.append(column)
            trigger_group = Adw.PreferencesGroup()
            self.trigger_labels.append(self._reading(trigger_group, _("%s button") % trigger))
            meter = Gtk.ProgressBar(valign=Gtk.Align.END, can_target=False)
            meter.update_property([Gtk.AccessibleProperty.LABEL], [trigger])
            overlay = Gtk.Overlay(child=trigger_group)
            overlay.add_overlay(meter)
            column.append(overlay)
            self.meters.append(meter)
            stick_group = Adw.PreferencesGroup()
            self.stick_labels.append(self._reading(stick_group, stick))
            column.append(stick_group)
            if ("LT", "RT")[i] in available:
                self.analog_triggers.append(4 + i)
            overlay.set_visible(4 + i in self.analog_triggers or device.has_input(1, 0x138 + i) or (("lefttrigger:" if i == 0 else "righttrigger:") in self.mapping))
            stick_group.set_visible(any(device.has_input(3, axis) for axis in ((0, 1), (3, 4))[i]))

        self.connect("map", self._listen)
        self.connect("unmap", self._stop)

    @staticmethod
    def _reading(group, title):
        row = Adw.ActionRow(title=title)
        label = Gtk.Label(css_classes=["numeric", "dim-label"])
        row.add_suffix(label)
        group.add(row)
        return label

    def _listen(self, *_):
        self.inputs = PreviewInputs(bool(self.mapping), self.mapping, self.analog_triggers)
        self._redraw()
        self.handlers = [
            self.device.connect("button-press-event", self._button, True),
            self.device.connect("button-release-event", self._button, False),
            self.device.connect("absolute-axis-event", self._axis),
            self.device.connect("hat-axis-event", self._hat),
        ]
        if self.inputs.triggers.sources:
            self.handlers.append(self.device.connect("event", self._raw_axis))

    def _stop(self, *_):
        for handler in self.handlers:
            self.device.disconnect(handler)
        self.handlers.clear()
        if self.redraw_tick:
            self.remove_tick_callback(self.redraw_tick)
            self.redraw_tick = 0

    def _raw_axis(self, device, event):
        ok, _, value = event.get_absolute()
        if ok and self.inputs.raw_axis(event.get_hardware_index(), value):
            self._queue_redraw()

    def _button(self, device, event, pressed):
        ok, code = event.get_button()
        if ok:
            self.inputs.button(code, pressed)
            self._queue_redraw()

    def _axis(self, device, event):
        ok, code, value = event.get_absolute()
        if ok:
            self.inputs.axis(code, value)
            self._queue_redraw()

    def _hat(self, device, event):
        ok, code, value = event.get_hat()
        if ok:
            self.inputs.axis(code, value)
            self._queue_redraw()

    def _queue_redraw(self):
        # Publish the latest device state at most once per display frame.
        if not self.redraw_tick:
            self.redraw_tick = self.add_tick_callback(self._on_frame)

    def _on_frame(self, widget, clock):
        self.redraw_tick = 0
        self._redraw()
        return False

    def _redraw(self):
        axes = self.inputs.axes
        self.diagram.set_state(self.inputs.buttons, (*axes[:4], 0, 0))
        for i, value in enumerate(axes[4:]):
            if self.trigger_labels[i].get_text() != str(value):
                self.trigger_labels[i].set_text(str(value))
                self.meters[i].set_fraction(value / 32767)
            coords = f"{axes[2*i]}, {axes[2*i+1]}"
            if self.stick_labels[i].get_text() != coords:
                self.stick_labels[i].set_text(coords)
