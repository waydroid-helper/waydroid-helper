"""Schedule taps from changing trigger travel without polling an idle controller."""

from gi.repository import GLib

from waydroid_helper.controller.android.input import AMotionEventAction as Motion


class TriggerRepeat:
    def __init__(self, control):
        self.control = control
        self.device = None
        self.next_tap = None
        self.lift = 0
        self.interval_us = 0
        self.last_tap = 0

    def update(self, device, travel, peak_rate):
        if self.device is not None and self.device != device:
            return
        if travel is None or travel <= .04:
            self.stop()
            return
        minimum = min(2, peak_rate)
        rate = minimum + (peak_rate - minimum) * (travel - .04) / .96
        self.interval_us = round(1_000_000 / rate)
        if self.device is None:
            self.device = device
            self._tap()
        elif self.next_tap:
            # Anchor the deadline to the last tap. Resetting it relative to
            # each sample would starve clicks on controllers reporting at 1 kHz.
            self.next_tap.set_ready_time(self.last_tap + self.interval_us)

    def _tap(self, *_):
        self.next_tap = None
        self._lift()
        if not self.control.touch(0, Motion.DOWN, *self.control.center):
            self.stop()
            return GLib.SOURCE_REMOVE
        self.last_tap = GLib.get_monotonic_time()
        self.lift = GLib.timeout_add(min(8, self.interval_us // 2000), self._lift_timeout)
        self.next_tap = GLib.timeout_source_new(1)
        self.next_tap.set_callback(self._tap)
        self.next_tap.set_ready_time(self.last_tap + self.interval_us)
        self.next_tap.attach(None)
        return GLib.SOURCE_REMOVE

    def _lift_timeout(self):
        self.lift = 0
        self._lift()
        return GLib.SOURCE_REMOVE

    def _lift(self):
        if self.lift:
            GLib.source_remove(self.lift)
            self.lift = 0
        if 0 in self.control.contacts:
            self.control.touch(0, Motion.UP, *self.control.contacts[0])

    def stop(self):
        if self.next_tap:
            self.next_tap.destroy()
            self.next_tap = None
        self._lift()
        self.device = None
