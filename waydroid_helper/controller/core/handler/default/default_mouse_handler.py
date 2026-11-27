import asyncio
import math
from abc import ABC, abstractmethod

from waydroid_helper.controller.android.input import (
    AMotionEventAction,
    AMotionEventButtons,
)
from waydroid_helper.controller.core.control_msg import (
    InjectScrollEventMsg,
    InjectTouchEventMsg,
    PointerId,
)
from waydroid_helper.controller.core.event_bus import Event, EventType, EventBus
from waydroid_helper.controller.core.handler.event_handlers import (
    InputEvent,
    InputEventType,
    InputModifierState,
)
from waydroid_helper.controller.core.runtime import ScreenGeometry
from waydroid_helper.controller.core.pinch import PinchContacts
from waydroid_helper.util.log import logger


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
    def __init__(
        self,
        event_bus: EventBus,
        screen_geometry: ScreenGeometry,
        natural_scroll: bool = True,
        mouse_hover: bool = False,
        *, read_input_windows=None,
    ) -> None:
        self.event_bus = event_bus
        self.natural_scroll = natural_scroll
        self.mouse_hover = mouse_hover
        self._current_x: float = 0
        self._current_y: float = 0
        self._have_pointer_position = False
        self._pinch_begin_position: tuple[int, int] | None = None
        self.screen_geometry = screen_geometry
        self._zoom_source: str | None = None
        self._read_windows = read_input_windows
        self._contacts: PinchContacts | None = None
        self._lookup: asyncio.Task | None = None
        self._pending_scales: list[float] = []
        self._zoom_scale = 1.0

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
        self._have_pointer_position = True
        if self._zoom_source is not None and buttons_state == 0:
            return True

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
        self.finish_zoom(cancel=True)

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
        # GTK also reports the boundaries of a scroll sequence. These carry
        # no movement and must not start a second pair of zoom contacts.
        if dx == 0 and dy == 0:
            return False

        scroll_begin_x = round(self._current_x)
        scroll_begin_y = round(self._current_y)
        if event.modifier_state & InputModifierState.CTRL:
            if dy:
                # Wheel notches and surface scroll pixels use different units.
                # Compose in log space so equal opposite deltas undo each other.
                sensitivity = 0.01 if event.scroll_is_surface else 0.1
                previous = self._zoom_scale if self._zoom_source == "wheel" else 1.0
                log_scale = math.log(previous) - dy * sensitivity
                self._update_zoom("wheel", math.exp(max(-8, min(8, log_scale))), event.position)
            return True
        else:

            position = (scroll_begin_x, scroll_begin_y, w, h)
            hscroll = dx
            vscroll = dy
            if event.scroll_is_surface:
                hscroll = float(hscroll)
                vscroll = float(vscroll)
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

    def _send_contacts(self, messages):
        for message in messages:
            self.event_bus.emit(Event(EventType.CONTROL_MSG, self, message))

    async def _start_zoom(self, position, resolution):
        try:
            contacts = await PinchContacts.at(position, resolution, self._read_windows)
        except (OSError, RuntimeError, TimeoutError) as error:
            logger.warning("Cannot locate pinch target: %s", error)
            contacts = None
        if self._lookup is not asyncio.current_task():
            return
        self._lookup = None
        if contacts is None:
            logger.debug("No touchable pinch interval at %s", position)
            self._pending_scales.clear()
            return
        self._contacts = contacts
        self._send_contacts(contacts.down())
        for scale in self._pending_scales:
            self._send_contacts(contacts.move(scale))
        self._pending_scales.clear()
        if self._zoom_source is None:
            self.finish_zoom()

    def _update_zoom(self, source: str, scale: float, position: tuple[int, int] | None) -> None:
        if not math.isfinite(scale) or scale <= 0:
            return
        if self._zoom_source != source:
            self.finish_zoom(cancel=True)
            if scale == 1.0 or self._read_windows is None:
                return
            w, h = self.screen_geometry.get_host_resolution()
            if position is None and not self._have_pointer_position:
                return
            x, y = position if position is not None else (self._current_x, self._current_y)
            if not (0 <= x < w and 0 <= y < h):
                return
            self._zoom_source = source
            resolution = self.screen_geometry.get_device_resolution_for_client(w, h)
            self._lookup = asyncio.create_task(self._start_zoom((int(x), int(y), w, h), resolution))
        if scale != self._zoom_scale:
            self._zoom_scale = scale
            if self._contacts is not None:
                self._send_contacts(self._contacts.move(scale))
            elif self._lookup is not None:
                self._pending_scales.append(scale)

    def finish_zoom(self, *, cancel: bool = False) -> None:
        self._pinch_begin_position = None
        self._zoom_source = None
        self._zoom_scale = 1.0
        # A quick Ctrl release can precede the ADB reply. Honor the completed
        # gesture once its target is known. On focus loss, click, or a new
        # gesture, discard pending input so it cannot land on a different UI.
        if cancel and self._lookup is not None:
            self._lookup.cancel()
            self._lookup = None
            self._pending_scales.clear()
        if self._contacts is not None:
            self._send_contacts(self._contacts.up())
            self._contacts = None

    def finish_wheel_zoom(self) -> None:
        if self._zoom_source == "wheel":
            self.finish_zoom()

    def zoom_processor(self, event: InputEvent) -> bool:
        # GtkGestureZoom reports scale relative to the gesture start. Preserve
        # it as an absolute value, including reversals, instead of integrating
        # rounded pointer distances or restarting contacts at a window edge.
        if event.zoom_status == "begin":
            self._pinch_begin_position = event.position
        elif event.zoom_status == "scale-changed" and event.zoom is not None:
            self._update_zoom("pinch", event.zoom, self._pinch_begin_position or event.position)
        elif event.zoom_status in ("end", "cancel"):
            self._pinch_begin_position = None
            if self._zoom_source == "pinch":
                self.finish_zoom(cancel=event.zoom_status == "cancel")
        return True
