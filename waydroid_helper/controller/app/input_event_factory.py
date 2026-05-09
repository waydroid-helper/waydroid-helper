#!/usr/bin/env python3
"""GTK input adapter for the controller backend."""

from __future__ import annotations

import gi

gi.require_version("Gdk", "4.0")
gi.require_version("Gtk", "4.0")
from gi.repository import Gdk, Gtk

from waydroid_helper.controller.android.input import AMotionEventButtons
from waydroid_helper.controller.core.handler.event_handlers import (
    InputEvent,
    InputEventSource,
    InputEventType,
    InputModifierState,
)
from waydroid_helper.controller.core.key_system import Key, KeyRegistry
from waydroid_helper.util.log import logger


class GdkKeySymbolResolver:
    """Resolve GDK key symbols behind the core KeyRegistry abstraction."""

    def name_from_code(self, code: int) -> str | None:
        return Gdk.keyval_name(code)

    def code_from_name(self, name: str) -> int | None:
        keyval = Gdk.keyval_from_name(name)
        if keyval == Gdk.KEY_VoidSymbol:
            return None
        return int(keyval)


class GtkInputEventFactory:
    """Converts GTK/GDK input into source-neutral InputEvent objects.

    This is the only layer in the mapping pipeline that is allowed to inspect
    GTK controllers or Gdk.Event instances. Everything after this adapter works
    from normalized values, so alternative input sources can plug in without
    changing widget behavior or backend handlers.
    """

    def __init__(self, widget: Gtk.Widget, key_registry: KeyRegistry):
        self._widget = widget
        self._key_registry = key_registry

    def create_key_event(
        self,
        event_type: InputEventType | str,
        controller: Gtk.EventControllerKey | None,
        keyval: int,
        keycode: int,
        state: int,
    ) -> InputEvent | None:
        physical_keyval = self.get_physical_keyval(keycode) or keyval
        main_key = self._create_main_key(keyval, physical_keyval)
        if main_key is None:
            return None

        modifier_state = self._modifier_state_from_gdk(state)
        return InputEvent(
            event_type=InputEventType(event_type),
            key=main_key,
            modifiers=self._collect_modifier_keys(modifier_state),
            source=InputEventSource.GTK,
            keyval=keyval,
            physical_keyval=physical_keyval,
            key_symbol_name=Gdk.keyval_name(keyval),
            physical_key_symbol_name=Gdk.keyval_name(physical_keyval),
            keycode=keycode,
            modifier_state=modifier_state,
            text=self._text_from_keyval(keyval),
            is_modifier=self.is_modifier_key(keyval),
        )

    def create_mouse_capture_event(
        self,
        event_type: InputEventType | str,
        controller: Gtk.GestureClick,
        n_press: int,
        x: float,
        y: float,
    ) -> InputEvent | None:
        """Create a normalized mouse event from Gtk.GestureClick capture.

        Edit-mode key capture uses GestureClick instead of the runtime legacy
        event controller. Keeping this path in the GTK adapter prevents the
        decorator from duplicating button/key normalization rules.
        """
        button = controller.get_current_button()
        if button == 0:
            return None

        event = controller.get_current_event()
        state = event.get_modifier_state() if event is not None else 0
        action_button = self._android_button_from_source_button(button)
        buttons = self._android_buttons_from_gdk_state(state)

        return InputEvent(
            event_type=InputEventType(event_type),
            key=self._key_registry.create_mouse_key(button),
            button=button,
            position=(int(x), int(y)),
            source=InputEventSource.GTK,
            modifier_state=self._modifier_state_from_gdk(state),
            n_press=n_press,
            action_button=action_button,
            buttons=buttons,
        )

    def create_mouse_button_event(
        self,
        controller: Gtk.EventControllerLegacy,
        event: Gdk.Event | None,
    ) -> InputEvent | None:
        if event is None:
            return None

        event_type = event.get_event_type()
        if event_type not in (Gdk.EventType.BUTTON_PRESS, Gdk.EventType.BUTTON_RELEASE):
            return None

        button = event.get_button()
        ok, x, y = event.get_position()
        if not ok:
            return None

        action_button = self._android_button_from_source_button(button)
        buttons = self._android_buttons_from_gdk_state(event.get_modifier_state())
        if action_button:
            buttons ^= action_button

        return InputEvent(
            event_type=(
                InputEventType.MOUSE_PRESS
                if event_type == Gdk.EventType.BUTTON_PRESS
                else InputEventType.MOUSE_RELEASE
            ),
            key=self._key_registry.create_mouse_key(button),
            button=button,
            position=(int(x), int(y)),
            source=InputEventSource.GTK,
            modifier_state=self._modifier_state_from_gdk(event.get_modifier_state()),
            n_press=1,
            action_button=action_button,
            buttons=buttons,
        )

    def create_mouse_motion_event(
        self,
        controller: Gtk.EventControllerMotion,
        x: float,
        y: float,
    ) -> InputEvent | None:
        event = controller.get_current_event()
        if event is None:
            return None

        state = event.get_modifier_state()
        modifier_state = self._modifier_state_from_gdk(state)
        button, mouse_key = self._pressed_mouse_button_from_state(modifier_state)

        return InputEvent(
            event_type=InputEventType.MOUSE_MOTION,
            key=mouse_key,
            button=button,
            position=(int(x), int(y)),
            source=InputEventSource.GTK,
            modifier_state=modifier_state,
            buttons=self._android_buttons_from_gdk_state(state),
        )

    def create_scroll_event(
        self,
        controller: Gtk.EventControllerScroll,
        dx: float | None = None,
        dy: float | None = None,
    ) -> InputEvent:
        event = controller.get_current_event()
        state = event.get_modifier_state() if event is not None else 0

        return InputEvent(
            event_type=InputEventType.MOUSE_SCROLL,
            source=InputEventSource.GTK,
            modifier_state=self._modifier_state_from_gdk(state),
            buttons=self._android_buttons_from_gdk_state(state),
            scroll_delta=(float(dx or 0), float(dy or 0)),
            scroll_is_surface=controller.get_unit() == Gdk.ScrollUnit.SURFACE,
        )

    def create_zoom_event(
        self,
        controller: Gtk.GestureZoom,
        zoom: float,
        status: str,
    ) -> InputEvent:
        event = controller.get_current_event()
        state = event.get_modifier_state() if event is not None else 0
        is_touchpad = (
            event is not None
            and event.get_event_type() == Gdk.EventType.TOUCHPAD_PINCH
        )

        return InputEvent(
            event_type=InputEventType.MOUSE_ZOOM,
            source=InputEventSource.GTK,
            modifier_state=self._modifier_state_from_gdk(state),
            buttons=0 if is_touchpad else self._android_buttons_from_gdk_state(state),
            zoom=zoom,
            zoom_status=status,
            zoom_is_touchpad=is_touchpad,
        )

    def get_physical_keyval(self, keycode: int) -> int:
        """Returns a layout-independent key symbol for the physical key."""
        try:
            display = self._widget.get_display()
            if display:
                success, keyval, _, _, _ = display.translate_key(
                    keycode=keycode, state=Gdk.ModifierType(0), group=0
                )
                if success:
                    return Gdk.keyval_to_upper(keyval)
        except Exception as e:
            logger.error(f"Failed to get physical keyval: {e}")
        return 0

    def is_modifier_key(self, keyval: int) -> bool:
        modifier_keys = {
            Gdk.KEY_Control_L,
            Gdk.KEY_Control_R,
            Gdk.KEY_Alt_L,
            Gdk.KEY_Alt_R,
            Gdk.KEY_Shift_L,
            Gdk.KEY_Shift_R,
            Gdk.KEY_Super_L,
            Gdk.KEY_Super_R,
            Gdk.KEY_Meta_L,
            Gdk.KEY_Meta_R,
            Gdk.KEY_Hyper_L,
            Gdk.KEY_Hyper_R,
        }
        return keyval in modifier_keys

    def _create_main_key(self, keyval: int, physical_keyval: int) -> Key | None:
        if self.is_modifier_key(keyval):
            return self._create_key_from_keyval(keyval)
        return self._create_key_from_keyval(physical_keyval)

    def _create_key_from_keyval(self, keyval: int) -> Key | None:
        return self._key_registry.create_from_symbol(Gdk.keyval_name(keyval), keyval)

    def _collect_modifier_keys(
        self, modifier_state: InputModifierState
    ) -> list[Key]:
        modifiers: list[Key] = []
        modifier_names = (
            (InputModifierState.CTRL, "Ctrl_L"),
            (InputModifierState.ALT, "Alt_L"),
            (InputModifierState.SHIFT, "Shift_L"),
            (InputModifierState.META, "Super_L"),
        )
        for flag, key_name in modifier_names:
            if modifier_state & flag:
                key = self._key_registry.get_by_name(key_name)
                if key:
                    modifiers.append(key)
        return modifiers

    def _modifier_state_from_gdk(self, state: int) -> InputModifierState:
        modifier_state = InputModifierState.NONE
        if state & Gdk.ModifierType.SHIFT_MASK:
            modifier_state |= InputModifierState.SHIFT
        if state & Gdk.ModifierType.ALT_MASK:
            modifier_state |= InputModifierState.ALT
        if state & Gdk.ModifierType.META_MASK:
            modifier_state |= InputModifierState.META
        if state & Gdk.ModifierType.SUPER_MASK:
            modifier_state |= InputModifierState.META
        if state & Gdk.ModifierType.CONTROL_MASK:
            modifier_state |= InputModifierState.CTRL
        if state & Gdk.ModifierType.BUTTON1_MASK:
            modifier_state |= InputModifierState.BUTTON_PRIMARY
        if state & Gdk.ModifierType.BUTTON2_MASK:
            modifier_state |= InputModifierState.BUTTON_MIDDLE
        if state & Gdk.ModifierType.BUTTON3_MASK:
            modifier_state |= InputModifierState.BUTTON_SECONDARY
        if state & Gdk.ModifierType.BUTTON4_MASK:
            modifier_state |= InputModifierState.BUTTON_BACK
        if state & Gdk.ModifierType.BUTTON5_MASK:
            modifier_state |= InputModifierState.BUTTON_FORWARD
        return modifier_state

    def _android_buttons_from_gdk_state(self, state: int) -> int:
        buttons = 0
        if state & Gdk.ModifierType.BUTTON1_MASK:
            buttons |= AMotionEventButtons.PRIMARY
        if state & Gdk.ModifierType.BUTTON2_MASK:
            buttons |= AMotionEventButtons.TERTIARY
        if state & Gdk.ModifierType.BUTTON3_MASK:
            buttons |= AMotionEventButtons.SECONDARY
        if state & Gdk.ModifierType.BUTTON4_MASK:
            buttons |= AMotionEventButtons.BACK
        if state & Gdk.ModifierType.BUTTON5_MASK:
            buttons |= AMotionEventButtons.FORWARD
        return int(buttons)

    def _android_button_from_source_button(self, button: int) -> int:
        if button == Gdk.BUTTON_PRIMARY:
            return int(AMotionEventButtons.PRIMARY)
        if button == Gdk.BUTTON_MIDDLE:
            return int(AMotionEventButtons.TERTIARY)
        if button == Gdk.BUTTON_SECONDARY:
            return int(AMotionEventButtons.SECONDARY)
        if button == 8:
            return int(AMotionEventButtons.BACK)
        if button == 9:
            return int(AMotionEventButtons.FORWARD)
        return 0

    def _pressed_mouse_button_from_state(
        self, modifier_state: InputModifierState
    ) -> tuple[int | None, Key | None]:
        if modifier_state & InputModifierState.BUTTON_PRIMARY:
            return Gdk.BUTTON_PRIMARY, self._key_registry.create_mouse_key(Gdk.BUTTON_PRIMARY)
        if modifier_state & InputModifierState.BUTTON_MIDDLE:
            return Gdk.BUTTON_MIDDLE, self._key_registry.create_mouse_key(Gdk.BUTTON_MIDDLE)
        if modifier_state & InputModifierState.BUTTON_SECONDARY:
            return Gdk.BUTTON_SECONDARY, self._key_registry.create_mouse_key(Gdk.BUTTON_SECONDARY)
        return None, None

    def _text_from_keyval(self, keyval: int) -> str | None:
        unicode_value = Gdk.keyval_to_unicode(keyval)
        if unicode_value == 0:
            return None
        try:
            return chr(unicode_value)
        except ValueError:
            return None
