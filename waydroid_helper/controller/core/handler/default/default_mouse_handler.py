import gi

from waydroid_helper.controller.core.handler.event_handlers import InputEvent

gi.require_version("Gdk", "4.0")
gi.require_version("GLib", "2.0")
from abc import ABC, abstractmethod
from enum import IntEnum
from typing import TYPE_CHECKING, cast

from gi.repository import Gdk, GLib

from waydroid_helper.controller.android.input import (
    AMotionEventAction,
    AMotionEventButtons,
)
from waydroid_helper.controller.core.control_msg import (
    InjectScrollEventMsg,
    InjectTouchEventMsg,
    ScreenInfo,
)
from waydroid_helper.controller.core.event_bus import Event, EventType, EventBus

if TYPE_CHECKING:
    from gi.repository import Gtk


class PointerId(IntEnum):
    MOUSE = 2**64 - 1
    GENERIC_FINGER = 2**64 - 2
    VIRTUAL_FINGER = 2**64 - 3


class MouseBase(ABC):
    @abstractmethod
    def click_processor(
        self, controller: "Gtk.GestureClick", n_press: int, x: float, y: float
    ) -> bool:
        pass

    @abstractmethod
    def scroll_processor(
        self,
        controller: "Gtk.EventControllerScroll",
        dx: float | None = None,
        dy: float | None = None,
    ) -> bool:
        pass

    @abstractmethod
    def motion_processor(
        self, controller: "Gtk.EventControllerMotion", x: float, y: float
    ) -> bool:
        pass

    @abstractmethod
    def zoom_processor(
        self, controller: "Gtk.EventControllerScroll", range: float, status:str|None
    ) -> bool:
        pass

    # @abstractmethod
    # def touch_processor(self, controller: Gtk.EventControllerMotion, keyval: int, keycode: int, state: int):
    #     pass


class MouseDefault(MouseBase):
    def __init__(self, event_bus: EventBus) -> None:
        self.event_bus = event_bus
        self.natural_scroll: bool = True
        self.mouse_hover: bool = False
        self._current_x: float = 0
        self._current_y: float = 0
        self.screen_info = ScreenInfo()
        self.zoom_in_init_length = 20
        self.zoom_out_init_length = 100
        self._is_zooming = False
        self._current_zoom_length = -1
        self._last_range = 1.0
        self._zoom_timer_id: int | None = None
        self._zoom_timeout_seconds = 0.5

    def _start_zoom_timer(self) -> None:
        self._stop_zoom_timer()
        self._zoom_timer_id = GLib.timeout_add(
            int(self._zoom_timeout_seconds * 1000),
            self._on_zoom_timeout
        )

    def _stop_zoom_timer(self) -> None:
        if self._zoom_timer_id is not None:
            GLib.source_remove(self._zoom_timer_id)
            self._zoom_timer_id = None

    def _on_zoom_timeout(self) -> bool:
        
        current_zoom_length = self._current_zoom_length
        
        self._is_zooming = False
        self._current_zoom_length = -1
        self._last_range = 1.0
        self._zoom_timer_id = None
        
        self._send_dual_finger_events(AMotionEventAction.UP, int(current_zoom_length), 0.0, 0, 0)
        
        return False

    def convert_click_action(self, event: Gdk.Event) -> AMotionEventAction:
        if event.get_event_type() == Gdk.EventType.BUTTON_PRESS:
            action = AMotionEventAction.DOWN
        else:
            action = AMotionEventAction.UP
        return action

    def convert_button(self, event: Gdk.ButtonEvent) -> AMotionEventButtons | int:
        button = event.get_button()  # type: ignore
        if button == Gdk.BUTTON_PRIMARY:
            return AMotionEventButtons.PRIMARY
        elif button == Gdk.BUTTON_MIDDLE:
            return AMotionEventButtons.TERTIARY
        elif button == Gdk.BUTTON_SECONDARY:
            return AMotionEventButtons.SECONDARY
        else:
            return 0

    def convert_buttons(
        self, event: Gdk.Event, action_button: AMotionEventButtons | int | None = None
    ) -> AMotionEventButtons | int:
        state = event.get_modifier_state()
        buttons = 0
        if state & Gdk.ModifierType.BUTTON1_MASK:
            buttons |= AMotionEventButtons.PRIMARY
        if state & Gdk.ModifierType.BUTTON2_MASK:
            buttons |= AMotionEventButtons.TERTIARY
        if state & Gdk.ModifierType.BUTTON3_MASK:
            buttons |= AMotionEventButtons.SECONDARY
        if action_button:
            buttons ^= action_button
        return buttons

    def motion_processor(
        self, controller: "Gtk.EventControllerMotion", x: float, y: float
    ) -> bool:
        # print(controller.get_current_event().get_event_type(), x, y)
        widget = controller.get_widget()
        if widget is None:
            return False
        w, h = self.screen_info.get_host_resolution()
        event = controller.get_current_event()
        if event is None:
            return False
        buttons_state = self.convert_buttons(event)

        x = max(0, x)
        y = max(0, y)
        self._current_x = x
        self._current_y = y

        if not self.mouse_hover and buttons_state == 0:
            return False
        action = (
            AMotionEventAction.MOVE
            if buttons_state != 0
            else AMotionEventAction.HOVER_MOVE
        )
        position = (int(x), int(y), w, h)
        pressure = 1.0
        msg = InjectTouchEventMsg(
            action=action,
            pointer_id=PointerId.MOUSE,
            position=position,
            pressure=pressure,
            action_button=0,
            buttons=buttons_state,
        )
        self.event_bus.emit(Event(EventType.CONTROL_MSG, self, msg))
        return True

    def click_processor(
        self, controller: "Gtk.GestureClick", n_press: int, x: float, y: float
    ) -> bool:
        widget = controller.get_widget()
        if widget is None:
            return False
        
        w, h = self.screen_info.get_host_resolution()

        event = controller.get_current_event()
        event = cast(Gdk.ButtonEvent, event)
        action = self.convert_click_action(event)
        position = (int(x), int(y), w, h)
        pressure = 1.0 if action == AMotionEventAction.DOWN else 0.0
        action_button = self.convert_button(event)
        buttons = self.convert_buttons(event, action_button)
        msg = InjectTouchEventMsg(
            action=action,
            pointer_id=PointerId.MOUSE,
            position=position,
            pressure=pressure,
            action_button=action_button,
            buttons=buttons,
        )
        self.event_bus.emit(Event(EventType.CONTROL_MSG, self, msg))
        return True

    def scroll_processor(
        self,
        controller: "Gtk.EventControllerScroll",
        dx: float | None = None,
        dy: float | None = None,
    ) -> bool:
        widget = controller.get_widget()
        if widget is None:
            return False

        w, h = self.screen_info.get_host_resolution()

        event = controller.get_current_event()
        if event is None:
            return False
        state = event.get_modifier_state()

        scroll_begin_x = round(self._current_x)
        scroll_begin_y = round(self._current_y)
        # ctrl+scroll begin

        # ctrl+scroll
        if (state & Gdk.ModifierType.CONTROL_MASK) and dy is not None:
            ctrl_zoom_range = -dy * 0.01
            return self.zoom_processor(controller, ctrl_zoom_range, None)
        else:

            position = (scroll_begin_x, scroll_begin_y, w, h)
            hscroll = dx if dx else 0
            vscroll = dy if dy else 0
            if controller.get_unit() == Gdk.ScrollUnit.SURFACE:
                hscroll = float(hscroll)
                vscroll = float(vscroll)
            if hscroll == 0 and vscroll == 0:
                return False
            if self.natural_scroll:
                hscroll = -hscroll
                vscroll = -vscroll
            buttons = self.convert_buttons(event)

            if hscroll !=0 and hscroll.is_integer() or vscroll != 0 and vscroll.is_integer():
                factor = 0.0625
            else:
                factor = 0.005

            hscroll_clamped = max(-1.0, min(1.0, hscroll * factor))
            vscroll_clamped = max(-1.0, min(1.0, vscroll * factor))

            msg = InjectScrollEventMsg(position, hscroll_clamped, vscroll_clamped, buttons)
            self.event_bus.emit(Event(EventType.CONTROL_MSG, self, msg))
            return True

    def touch_processor(self):
        return True

    def _create_touch_event(
        self, 
        action: AMotionEventAction, 
        pointer_id: PointerId, 
        x_offset: int, 
        y_offset: int, 
        pressure: float = 1.0,
        action_button: int = 0,
        buttons: int = 0
    ) -> InjectTouchEventMsg:
        w, h = self.screen_info.get_host_resolution()
        return InjectTouchEventMsg(
            action=action,
            pointer_id=pointer_id,
            position=(int(self._current_x + x_offset), int(self._current_y + y_offset), w, h),
            pressure=pressure,
            action_button=action_button,
            buttons=buttons,
        )

    def _send_dual_finger_events(
        self, 
        action: AMotionEventAction, 
        zoom_length: int, 
        pressure: float = 1.0,
        action_button: int = 0,
        buttons: int = 0
    ) -> None:
        msg1 = self._create_touch_event(
            action, PointerId.GENERIC_FINGER, -zoom_length, zoom_length, pressure, action_button, buttons
        )
        msg2 = self._create_touch_event(
            action, PointerId.VIRTUAL_FINGER, zoom_length, -zoom_length, pressure, action_button, buttons
        )
        self.event_bus.emit(Event(EventType.CONTROL_MSG, self, msg1))
        self.event_bus.emit(Event(EventType.CONTROL_MSG, self, msg2))

    def _handle_zoom_length_reset(self, new_zoom_length: float) -> float:
        if new_zoom_length > self.zoom_out_init_length:
            return self.zoom_in_init_length
        elif new_zoom_length < self.zoom_in_init_length:
            return self.zoom_out_init_length
        return new_zoom_length

    def _reset_zoom_fingers(self, old_length: float, new_length: float, action_button: int = 0, buttons: int = 0) -> None:
        self._send_dual_finger_events(AMotionEventAction.UP, int(old_length), 0.0, action_button, buttons)
        self._send_dual_finger_events(AMotionEventAction.DOWN, int(new_length), 1.0, action_button, buttons)

    def zoom_processor(
        self, controller, range: float, status:str|None
    ) -> bool:
        event = controller.get_current_event()
        if event is None:
            return False
        
        action_button = 0
        buttons = 0
        
        if event.get_event_type() != Gdk.EventType.TOUCHPAD_PINCH:
            buttons = self.convert_buttons(event)
        
        if event.get_event_type() == Gdk.EventType.TOUCHPAD_PINCH:
            if status == "begin":
                self._is_zooming = True
            elif status == "scale-changed":
                if self._current_zoom_length == -1:
                    self._current_zoom_length = self.zoom_in_init_length if range > 1 else self.zoom_out_init_length
                    self._send_dual_finger_events(AMotionEventAction.DOWN, int(self._current_zoom_length), 1.0, action_button, buttons)
                
                old_zoom_length = self._current_zoom_length
                new_zoom_length = self._current_zoom_length + (self.zoom_in_init_length + self.zoom_out_init_length) * (range - self._last_range)
                final_zoom_length = self._handle_zoom_length_reset(new_zoom_length)
                
                if final_zoom_length != new_zoom_length:
                    self._reset_zoom_fingers(old_zoom_length, final_zoom_length, action_button, buttons)
                
                self._current_zoom_length = final_zoom_length
                self._send_dual_finger_events(AMotionEventAction.MOVE, int(self._current_zoom_length), 1.0, action_button, buttons)
                self._last_range = range
            elif status == "end":
                current_zoom_length = self._current_zoom_length
                self._is_zooming = False
                self._current_zoom_length = -1
                self._last_range = 1.0 
                self._send_dual_finger_events(AMotionEventAction.UP, int(current_zoom_length), 0.0, action_button, buttons)
        else:
            # ctrl+scroll 
            if not self._is_zooming:
                # 开始新的缩放，启动计时器
                self._is_zooming = True
                self._current_zoom_length = self.zoom_in_init_length if range > 0 else self.zoom_out_init_length
                self._start_zoom_timer()
                self._send_dual_finger_events(AMotionEventAction.DOWN, int(self._current_zoom_length), 1.0, action_button, buttons)
            else:
                # 正在缩放中，刷新计时器
                self._start_zoom_timer()


            if abs(range) == 0.01:
                range *= 10

            old_zoom_length = self._current_zoom_length
            new_zoom_length = self._current_zoom_length + (self.zoom_in_init_length + self.zoom_out_init_length) * range
            
            final_zoom_length = self._handle_zoom_length_reset(new_zoom_length)
            
            if final_zoom_length != new_zoom_length:
                self._reset_zoom_fingers(old_zoom_length, final_zoom_length, action_button, buttons)

            self._current_zoom_length = final_zoom_length
            self._send_dual_finger_events(AMotionEventAction.MOVE, int(self._current_zoom_length), 1.0, action_button, buttons)

        return True
