"""Route local gamepad buttons and stick directions to saved Android mappings."""

from dataclasses import dataclass, field
from hashlib import sha256

import gi
from gi.repository import Gio

from waydroid_helper.gamepad_layout import TriggerAxes, artwork_for_device, button_labels_for, physical_button_code
from waydroid_helper.controller.core.event_bus import Event, EventType, GamepadTrigger
from waydroid_helper.controller.core.handler.event_handlers import (
    InputEvent,
    InputEventType,
)
from waydroid_helper.controller.core.gamepad_right_stick import GamepadRightStick
from waydroid_helper.controller.core.key_system import KeyType
from waydroid_helper.controller.widgets.base.decorator_contracts import (
    EditableWidgetBehavior,
)


NINTENDO_SWAP = {"A": "B", "B": "A", "X": "Y", "Y": "X"}


@dataclass
class ConnectedGamepad:
    device: object
    settings: Gio.Settings
    family: str = "generic"
    mapped: bool = False
    handlers: list = field(default_factory=list)
    face_bindings: dict = field(default_factory=dict)
    right_stick: GamepadRightStick | None = None

    trigger_axes: TriggerAxes = field(default_factory=lambda: TriggerAxes(""))
    analog_triggers: set = field(default_factory=set)
    travel: dict = field(default_factory=dict)
    wait_for_release: set = field(default_factory=set)

    @property
    def name(self):
        return self.settings.get_string("name") or self.device.get_name()

    @property
    def keycap_labels(self):
        labels = button_labels_for(self.family, self.mapped)
        if not labels:
            return {}
        swapped = self.settings.get_boolean("nintendo-layout")
        # Captions are indexed by the saved logical binding. When A/B and X/Y
        # are swapped, the glyph must still identify the physical button to press.
        return {
            "Pad_" + (NINTENDO_SWAP.get(name, name) if swapped else name): label
            for name, label in labels.items()
        }

    def face_binding(self, name, pressed):
        # A layout change takes effect on the next press. Keep the original
        # logical key until release, even if two physical buttons now share it.
        if pressed:
            if name in self.face_bindings:
                return None
            binding = name
            if self.settings.get_boolean("nintendo-layout"):
                binding = NINTENDO_SWAP[name]
            self.face_bindings[name] = binding
        else:
            binding = self.face_bindings.pop(name, None)
            if binding in self.face_bindings.values():
                return None
        return binding


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

    def __init__(self, window, on_keycaps_changed=None):
        self.window = window
        self.devices = {}
        self.held = set()
        self.sticks = {}
        self.monitor = None
        self.on_keycaps_changed = on_keycaps_changed
        self._keycap_pad = None
        self._layout_handler = None
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

    def _settings_for(self, device):
        instance = device.get_instance_identifier() if hasattr(device, "get_instance_identifier") else ""
        model = device.get_guid() if hasattr(device, "get_guid") else device.get_name()
        identity = (model + "\0" + (instance or "")).encode()
        base = "/com/jaoushingan/WaydroidHelper/gamepads/" + sha256(identity).hexdigest()
        paths = {pad.settings.get_property("path") for pad in self.devices.values()}
        # Some receivers report neither serial nor port. Allocate a separate
        # settings slot for each indistinguishable pad connected at once.
        slot = 1
        while f"{base}/{slot}/" in paths:
            slot += 1
        return Gio.Settings.new_with_path("com.jaoushingan.WaydroidHelper.Gamepad", f"{base}/{slot}/")

    def _connect(self, monitor, device):
        if device not in self.devices:
            mapping = (device.get_mapping() or "") if hasattr(device, "get_mapping") else ""
            pad = ConnectedGamepad(
                device, self._settings_for(device), artwork_for_device(device, mapping),
                mapped=bool(mapping), trigger_axes=TriggerAxes(mapping),
                right_stick=GamepadRightStick(lambda: self.window.event_bus.emit(
                    Event(EventType.GAMEPAD_STICK, self, (device, "right", 0.0, 0.0))
                )),
            )
            pad.analog_triggers = pad.trigger_axes.available(device, pad.mapped)
            self.devices[device] = pad
            pad.handlers = [
                device.connect("button-press-event", self._button, True, bool(mapping)),
                device.connect("button-release-event", self._button, False, bool(mapping)),
                device.connect("absolute-axis-event", self._axis),
                device.connect("hat-axis-event", self._hat),
            ]
            if pad.trigger_axes.sources:
                pad.handlers.append(device.connect("event", self._raw_trigger))
            if self._keycap_pad is None:
                self._use_keycaps(pad)

    def _disconnect(self, monitor, device):
        pad = self.devices.get(device)
        if pad and pad.right_stick:
            pad.right_stick.reset()
        self._release_triggers(device)
        self._release_sticks(device)
        for instance, name in tuple(self.held):
            if instance == device:
                self._transition(device, name, False)
        pad = self.devices.pop(device, None)
        if pad is not None:
            for handler in pad.handlers:
                device.disconnect(handler)
            if pad is self._keycap_pad:
                self._use_keycaps(next(iter(self.devices.values()), None))

    def _use_keycaps(self, pad):
        # Prefer the first connected pad until another pad sends an accepted
        # press. Analog noise and releases cannot switch the overlay's labels.
        if pad is self._keycap_pad:
            return
        if self._keycap_pad is not None:
            self._keycap_pad.settings.disconnect(self._layout_handler)
        self._keycap_pad = pad
        if pad is not None:
            self._layout_handler = pad.settings.connect("changed::nintendo-layout", self._update_keycaps)
        self._update_keycaps()

    def _update_keycaps(self, *_):
        labels = self._keycap_pad.keycap_labels if self._keycap_pad else {}
        if self.window.key_registry.keycap_labels != labels:
            self.window.key_registry.keycap_labels = labels
            if self.on_keycaps_changed:
                self.on_keycaps_changed()

    def _focus_changed(self, window, _prop):
        if not window.is_active():
            self.reset()

    @property
    def available_triggers(self):
        # Offline editing is useful before a controller is plugged in.
        if not self.devices:
            return {"LT", "RT"}
        return set().union(*(pad.analog_triggers for pad in self.devices.values()))

    def reset(self):
        for device, pad in self.devices.items():
            if pad.right_stick:
                pad.right_stick.reset()
            self._release_triggers(device)
        for device, _stick in list(self.sticks):
            self._release_sticks(device)
        for device, name in tuple(self.held):
            self._transition(device, name, False)

    def _accept_input(self):
        window = self.window
        if window.current_mode == window.MAPPING_MODE and window.key_mapping_handler.ime_visible:
            return False
        return window.profiles.kind == "gamepad" and window.is_active() and not (
            hasattr(window, "get_visible_dialog") and window.get_visible_dialog()
        )

    def _button(self, device, event, pressed, mapped):
        ok, code = event.get_button()
        if ok:
            name = self.BUTTONS.get(physical_button_code(code, mapped))
            if name in ("LT", "RT") and name not in self.devices[device].analog_triggers:
                # An existing variable-rate binding can use its peak rate on a
                # digital pad. Never feed a thresholded duplicate from an analog pad.
                self._trigger(device, name, float(pressed))
            if name in ("A", "B", "X", "Y"):
                name = self.devices[device].face_binding(name, pressed)
            if name:
                self._transition(device, name, pressed)

    def _axis(self, device, event):
        ok, code, value = event.get_absolute()
        if ok and code in self.AXES:
            if code in (0, 1, 3, 4):
                if self._update_stick(device, code, value):
                    # Already-held directions (including a skill bound to a
                    # direction) still need their release edges during aiming.
                    self._axis_buttons(device, code, value, releases_only=True)
                    return
            elif code in TriggerAxes.AXIS_NAMES and not self.devices[device].mapped:
                self._trigger(device, TriggerAxes.AXIS_NAMES[code], (value + 1) / 2)
            self._axis_buttons(device, code, value)

    def _raw_trigger(self, device, event):
        ok, _, value = event.get_absolute()
        if ok:
            axes = self.devices[device].trigger_axes
            for name, travel in axes.raw_values(event.get_hardware_index(), value):
                self._trigger(device, name, travel)

    def _trigger(self, device, name, travel):
        pad = self.devices[device]
        if name in pad.wait_for_release:
            if travel <= .005:
                pad.wait_for_release.remove(name)
            return
        if (self.window.current_mode != self.window.MAPPING_MODE or not self._accept_input()
                or not self.window.server.connected_event.is_set()):
            if travel > .005:
                pad.wait_for_release.add(name)
            return
        if pad.travel.get(name, 0) == travel:
            return
        if travel:
            pad.travel[name] = travel
        else:
            pad.travel.pop(name, None)
        self._emit_trigger(pad, name, travel)

    def _emit_trigger(self, pad, name, travel):
        value = GamepadTrigger(pad.device, name, travel, name in pad.analog_triggers)
        self.window.event_bus.emit(Event(EventType.GAMEPAD_TRIGGER, self, value))

    def _release_triggers(self, device):
        pad = self.devices.get(device)
        if pad:
            for name in tuple(pad.travel):
                if pad.travel.pop(name) > .005:
                    pad.wait_for_release.add(name)
                self._emit_trigger(pad, name, None)

    def _hat(self, device, event):
        ok, code, value = event.get_hat()
        if ok and code in (16, 17):
            self._axis_buttons(device, code, value)

    def _axis_buttons(self, device, code, value, releases_only=False):
        for name, strength in zip(self.AXES[code], (-value, value)):
            if name and (not releases_only or (device, name) in self.held):
                threshold = 0.35 if (device, name) in self.held else 0.55
                self._transition(device, name, strength >= threshold)

    def _update_stick(self, device, code, value):
        window = self.window
        if (
            not self._accept_input()
            or window.current_mode != window.MAPPING_MODE
            or not window.server.connected_event.is_set()
        ):
            return
        stick = "left" if code < 3 else "right"
        vector = self.sticks.setdefault((device, stick), [0.0, 0.0])
        vector[0 if code in (0, 3) else 1] = value
        if stick == "right" and self.devices[device].right_stick.update(*vector):
            return True
        window.event_bus.emit(
            Event(EventType.GAMEPAD_STICK, self, (device, stick, *vector))
        )

    def _release_sticks(self, device):
        for stick in ("left", "right"):
            if self.sticks.pop((device, stick), None) is not None:
                self.window.event_bus.emit(
                    Event(EventType.GAMEPAD_STICK, self, (device, stick, 0.0, 0.0))
                )

    def _transition(self, device, name, pressed):
        token = (device, name)
        if pressed == (token in self.held) or (pressed and not self._accept_input()):
            return
        # Multiple pads can hold the same logical binding at once. Emit its
        # release only after the last device lets go or disappears.
        key = self.keys[name]
        route = self.devices[device].right_stick
        if pressed:
            self._use_keycaps(self.devices[device])
            first = not any(n == name for _, n in self.held)
            self.held.add(token)
            if not first:
                return
        else:
            self.held.remove(token)
            if route and route.binding and key in route.binding:
                # Ordinary buttons are aggregated across pads. The skill's
                # finger belongs to the pad that started it, even if another
                # controller is still holding the same logical button.
                route.owner.stop_gesture()
            if any(n == name for _, n in self.held):
                return
        if self.window.current_mode == self.window.EDIT_MODE:
            focus = self.window.get_focus()
            if focus and hasattr(focus, "get_widget_behavior"):
                if getattr(focus, "REQUIRES_ANALOG_TRIGGER", False) and name not in self.devices[device].analog_triggers:
                    return
                editor = focus.get_widget_behavior(EditableWidgetBehavior)
                if editor:
                    if editor.capture_external_key(key, pressed):
                        self.window.queue_editor_refresh()
            return
        if self.window.server.connected_event.is_set():
            manager = self.window.key_mapping_manager
            if pressed:
                previous_owner = route.owner if route else None
                manager.handle_key_press(
                    InputEvent(InputEventType.KEY_PRESS, key=key, source="gamepad", right_stick=route)
                )
                if route and route.owner and route.owner is not previous_owner:
                    # A previously held virtual direction may own another touch.
                    # Release it after the key manager finishes dispatching this
                    # press, preserving directions that form the skill chord.
                    for direction in (*self.AXES[3], *self.AXES[4]):
                        if (device, direction) in self.held and self.keys[direction] not in route.binding:
                            self._transition(device, direction, False)
            else:
                manager.handle_key_release(
                    InputEvent(InputEventType.KEY_RELEASE, key=key, source="gamepad", right_stick=route)
                )

    def close(self):
        for device in list(self.devices):
            self._disconnect(self.monitor, device)
        if self.monitor:
            self.monitor.disconnect_by_func(self._connect)
            self.monitor.disconnect_by_func(self._disconnect)
        self.monitor = None
