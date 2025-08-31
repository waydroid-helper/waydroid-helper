import gi

from waydroid_helper.controller.core.handler.event_handlers import InputEvent

gi.require_version("Gdk", "4.0")
from abc import ABC, abstractmethod
from enum import IntEnum
from typing import TYPE_CHECKING, cast

from gi.repository import Gdk

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
        self, controller: "Gtk.EventControllerScroll", range: float
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
        ctrl_zoom_range = 1.0

        # ctrl+scroll
        if (state & Gdk.ModifierType.CONTROL_MASK) and dy is not None:
            ctrl_zoom_range = ctrl_zoom_range + dy * 0.01
            if ctrl_zoom_range <= 0.01:
                ctrl_zoom_range = 0.01
            return self.zoom_processor(controller, ctrl_zoom_range)
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

    def zoom_processor(
        self, controller: "Gtk.EventControllerScroll", range: float
    ) -> bool:
        # msg = ControlMsg(
        #     ControlMsgType.INJECT_TOUCH_EVENT,
        #     {
        #         "action": action,
        #         "position": [int(x), int(y), w, h],
        #         "pressure": pressure,
        #         "action_button": action_button,
        #         "buttons": buttons,
        #     },
        # )
        # logging.info(msg.data)
        # self.server.send(msg.pack())
        return True
