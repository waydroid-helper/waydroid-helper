"""Route local gamepad buttons and stick directions to saved Android mappings."""

from gettext import gettext as _

import gi

from waydroid_helper.controller.core.handler.event_handlers import (
    InputEvent,
    InputEventType,
)
from waydroid_helper.controller.core.key_system import KeyType
from waydroid_helper.controller.widgets.base.decorator_contracts import (
    EditableWidgetBehavior,
)


class GamepadInput:
    # libmanette normalizes SDL controller mappings to Linux input codes.
    # Register names even without a controller so a saved JSON scheme loads
    # identically before and after hotplug.
    BUTTONS = {
        0x130: "A",
        0x131: "B",
        0x133: "X",
        0x134: "Y",
        0x136: "LB",
        0x137: "RB",
        0x138: "LT",
        0x139: "RT",
        0x13A: "Select",
        0x13B: "Start",
        0x13C: "Guide",
        0x13D: "LS",
        0x13E: "RS",
        0x220: "Up",
        0x221: "Down",
        0x222: "Left",
        0x223: "Right",
    }
    AXES = {
        0: ("LS_Left", "LS_Right"),
        1: ("LS_Up", "LS_Down"),
        2: (None, "LT"),
        3: ("RS_Left", "RS_Right"),
        4: ("RS_Up", "RS_Down"),
        5: (None, "RT"),
        16: ("Left", "Right"),
        17: ("Up", "Down"),
    }

    def __init__(self, window):
        self.window = window
        self.devices = {}
        self.held = set()
        self.monitor = None
        names = set(self.BUTTONS.values())
        names.update(name for pair in self.AXES.values() for name in pair if name)
        self.keys = {
            name: window.key_registry.register_key(
                "Pad_" + name, -65536 - i, KeyType.SPECIAL
            )
            for i, name in enumerate(sorted(names))
        }
        try:
            gi.require_version("Manette", "0.2")
            from gi.repository import Manette
        except (ValueError, ImportError):
            return
        self.monitor = Manette.Monitor.new()
        self.monitor.connect("device-connected", self._connect)
        self.monitor.connect("device-disconnected", self._disconnect)
        iterator = self.monitor.iterate()
        while True:
            ok, device = iterator.next()
            if not ok:
                break
            self._connect(self.monitor, device)
        window.connect("notify::is-active", self._focus_changed)

    def _connect(self, monitor, device):
        if device not in self.devices:
            self.devices[device] = [
                device.connect("button-press-event", self._button, True),
                device.connect("button-release-event", self._button, False),
                device.connect("absolute-axis-event", self._axis),
            ]

    def _disconnect(self, monitor, device):
        for instance, name in tuple(self.held):
            if instance == device:
                self._transition(device, name, False)
        for handler in self.devices.pop(device, ()):
            device.disconnect(handler)

    def _focus_changed(self, window, _prop):
        if not window.is_active():
            for device, name in tuple(self.held):
                self._transition(device, name, False)

    def _button(self, device, event, pressed):
        ok, code = event.get_button()
        if ok and code in self.BUTTONS:
            self._transition(device, self.BUTTONS[code], pressed)

    def _axis(self, device, event):
        ok, code, value = event.get_absolute()
        if ok and code in self.AXES:
            for name, strength in zip(self.AXES[code], (-value, value)):
                if name:
                    threshold = 0.35 if (device, name) in self.held else 0.55
                    self._transition(device, name, strength >= threshold)

    def _transition(self, device, name, pressed):
        token = (device, name)
        if pressed == (token in self.held) or (pressed and not self.window.is_active()):
            return
        # Multiple pads can hold the same logical binding at once. Emit its
        # release only after the last device lets go or disappears.
        if pressed:
            first = not any(n == name for _, n in self.held)
            self.held.add(token)
            if not first:
                return
        else:
            self.held.remove(token)
            if any(n == name for _, n in self.held):
                return
        key = self.keys[name]
        if self.window.current_mode == self.window.EDIT_MODE:
            focus = self.window.get_focus()
            if focus and hasattr(focus, "get_widget_behavior"):
                editor = focus.get_widget_behavior(EditableWidgetBehavior)
                if editor:
                    editor.capture_external_key(key, pressed)
            return
        if self.window.server.connected_event.is_set():
            manager = self.window.key_mapping_manager
            if pressed:
                manager.handle_key_press(
                    InputEvent(InputEventType.KEY_PRESS, key=key, source="gamepad")
                )
            else:
                manager.handle_key_release(
                    InputEvent(InputEventType.KEY_RELEASE, key=key, source="gamepad")
                )

    def edit(self):
        self.window.switch_mode(self.window.EDIT_MODE)
        if self.devices:
            self.window.show_notification(
                _("Double-click a control and press a gamepad button")
            )
        elif self.monitor is not None:
            self.window.show_notification(_("Connect a gamepad to bind its buttons"))
        else:
            self.window.show_notification(_("Gamepad bindings require libmanette 0.2"))

    def close(self):
        for device in list(self.devices):
            self._disconnect(self.monitor, device)
        if self.monitor:
            self.monitor.disconnect_by_func(self._connect)
            self.monitor.disconnect_by_func(self._disconnect)
        self.monitor = None
