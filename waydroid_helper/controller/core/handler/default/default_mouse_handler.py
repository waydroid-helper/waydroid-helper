from dataclasses import replace

import gi

from waydroid_helper.controller.core.handler.event_handlers import (
    InputEvent,
    InputEventType,
    InputModifierState,
)

gi.require_version("GLib", "2.0")
from abc import ABC, abstractmethod
from enum import IntEnum
from typing import TYPE_CHECKING

from gi.repository import GLib

from waydroid_helper.controller.android.input import (
    AMotionEventAction,
    AMotionEventButtons,
)
from waydroid_helper.controller.core.control_msg import (
    InjectScrollEventMsg,
    InjectTouchEventMsg,
)
from waydroid_helper.controller.core.event_bus import Event, EventType, EventBus
from waydroid_helper.controller.core.runtime import ScreenGeometry

if TYPE_CHECKING:
    from gi.repository import Gtk


class PointerId(IntEnum):
    MOUSE = 2**64 - 1
    GENERIC_FINGER = 2**64 - 2
    VIRTUAL_FINGER = 2**64 - 3


class MouseBase(ABC):
    @abstractmethod
    def click_processor(self, event: InputEvent) -> bool:
        pass

    @abstractmethod
    def scroll_processor(self, event: InputEvent) -> bool:
        pass

    @abstractmethod
    def motion_processor(self, event: InputEvent) -> bool:
        pass

    @abstractmethod
    def zoom_processor(self, event: InputEvent) -> bool:
        pass

    # @abstractmethod
    # def touch_processor(self, controller: Gtk.EventControllerMotion, keyval: int, keycode: int, state: int):
    #     pass


class MouseDefault(MouseBase):
    def __init__(self, event_bus: EventBus, screen_geometry: ScreenGeometry) -> None:
        self.event_bus = event_bus
        self.natural_scroll: bool = True
        self.mouse_hover: bool = False
        self._current_x: float = 0
        self._current_y: float = 0
        self.screen_geometry = screen_geometry
        self.zoom_in_init_length = 20
        self.zoom_out_init_length = 100
        self._is_zooming = False
        self._current_zoom_length = -1
        self._last_range = 1.0
        self._zoom_timer_id: int | None = None
        self._zoom_timeout_seconds = 0.25

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

    def convert_click_action(self, event: InputEvent) -> AMotionEventAction:
        if event.event_type == InputEventType.MOUSE_PRESS:
            action = AMotionEventAction.DOWN
        else:
            action = AMotionEventAction.UP
        return action

    def motion_processor(self, event: InputEvent) -> bool:
        if event.position is None:
            return False

        x, y = event.position
        w, h = self.screen_geometry.get_host_resolution()
        device_resolution = self.screen_geometry.get_device_resolution_for_client(w, h)
        buttons_state = event.buttons

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
            device_resolution=device_resolution,
            pressure=pressure,
            action_button=0,
            buttons=buttons_state,
        )
        self.event_bus.emit(Event(EventType.CONTROL_MSG, self, msg))
        return True

    def click_processor(self, event: InputEvent) -> bool:
        if event.position is None:
            return False

        x, y = event.position
        
        w, h = self.screen_geometry.get_host_resolution()
        device_resolution = self.screen_geometry.get_device_resolution_for_client(w, h)

        action = self.convert_click_action(event)
        position = (int(x), int(y), w, h)
        pressure = 1.0 if action == AMotionEventAction.DOWN else 0.0
        msg = InjectTouchEventMsg(
            action=action,
            pointer_id=PointerId.MOUSE,
            position=position,
            device_resolution=device_resolution,
            pressure=pressure,
            action_button=event.action_button,
            buttons=event.buttons,
        )
        self.event_bus.emit(Event(EventType.CONTROL_MSG, self, msg))
        return True

    def scroll_processor(self, event: InputEvent) -> bool:
        if event.scroll_delta is None:
            return False

        w, h = self.screen_geometry.get_host_resolution()
        device_resolution = self.screen_geometry.get_device_resolution_for_client(w, h)
        dx, dy = event.scroll_delta

        scroll_begin_x = round(self._current_x)
        scroll_begin_y = round(self._current_y)
        # ctrl+scroll begin

        # ctrl+scroll
        if (event.modifier_state & InputModifierState.CTRL) and dy is not None:
            ctrl_zoom_range = -dy
            zoom_event = replace(
                event,
                event_type=InputEventType.MOUSE_ZOOM,
                zoom=ctrl_zoom_range,
                zoom_status=None,
                zoom_is_touchpad=False,
            )
            return self.zoom_processor(zoom_event)
        else:

            position = (scroll_begin_x, scroll_begin_y, w, h)
            hscroll = dx
            vscroll = dy
            if event.scroll_is_surface:
                hscroll = float(hscroll)
                vscroll = float(vscroll)
            if hscroll == 0 and vscroll == 0:
                return False
            if self.natural_scroll:
                hscroll = -hscroll
                vscroll = -vscroll
            buttons = event.buttons

            if hscroll !=0 and hscroll.is_integer() or vscroll != 0 and vscroll.is_integer():
                factor = 0.0625
            else:
                factor = 0.005

            hscroll_clamped = max(-1.0, min(1.0, hscroll * factor))
            vscroll_clamped = max(-1.0, min(1.0, vscroll * factor))

            msg = InjectScrollEventMsg(
                position=position,
                device_resolution=device_resolution,
                hscroll=hscroll_clamped,
                vscroll=vscroll_clamped,
                buttons=buttons,
            )
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
        w, h = self.screen_geometry.get_host_resolution()
        device_resolution = self.screen_geometry.get_device_resolution_for_client(w, h)
        return InjectTouchEventMsg(
            action=action,
            pointer_id=pointer_id,
            position=(int(self._current_x + x_offset), int(self._current_y + y_offset), w, h),
            device_resolution=device_resolution,
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

    def zoom_processor(self, event: InputEvent) -> bool:
        if event.zoom is None:
            return False
        
        range = event.zoom
        status = event.zoom_status
        action_button = 0
        buttons = event.buttons
        
        if event.zoom_is_touchpad:
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


            if abs(range) == 1:
                range *= 0.1
            else:
                range *= 0.01

            old_zoom_length = self._current_zoom_length
            new_zoom_length = self._current_zoom_length + (self.zoom_in_init_length + self.zoom_out_init_length) * range
            
            final_zoom_length = self._handle_zoom_length_reset(new_zoom_length)
            
            if final_zoom_length != new_zoom_length:
                self._reset_zoom_fingers(old_zoom_length, final_zoom_length, action_button, buttons)

            self._current_zoom_length = final_zoom_length
            self._send_dual_finger_events(AMotionEventAction.MOVE, int(self._current_zoom_length), 1.0, action_button, buttons)

        return True
