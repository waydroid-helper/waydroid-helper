"""Shared drawing and contact lifetime for controls that synthesize gestures."""

from waydroid_helper.controller.android.input import AMotionEventAction
from waydroid_helper.controller.core.control_msg import InjectTouchEventMsg
from waydroid_helper.controller.core.event_bus import Event, EventType
from waydroid_helper.controller.widgets.base.base_widget import BaseWidget
from waydroid_helper.controller.widgets.base import control_art as art


class TouchControl(BaseWidget):
    MAPPING_MODE_WIDTH = 68
    MAPPING_MODE_HEIGHT = 36

    def __init__(
        self,
        x=0,
        y=0,
        width=100,
        height=100,
        text="",
        default_keys=None,
        *,
        runtime_context
    ):
        super().__init__(
            x,
            y,
            width,
            height,
            self.WIDGET_NAME,
            text,
            default_keys,
            min_width=32,
            min_height=32,
            runtime_context=runtime_context,
        )
        self.contacts = {}

    @property
    def center(self):
        return self.x + self.width / 2, self.y + self.height / 2

    @property
    def mapping_start_x(self):
        return self.center[0] - self.MAPPING_MODE_WIDTH / 2

    @property
    def mapping_start_y(self):
        return self.center[1] - self.MAPPING_MODE_HEIGHT / 2

    def touch(self, finger, action, x, y):
        # Each finger owns a distinct pool slot until its final UP. A MOVE or
        # cleanup after pool exhaustion must never create a new Android contact.
        owner = (self, finger)
        pointer = self.pointer_id_manager.get_allocated_id(owner)
        if action == AMotionEventAction.DOWN:
            if pointer is not None:
                return False
            pointer = self.pointer_id_manager.allocate(owner)
        if pointer is None:
            return False
        w, h = self.screen_geometry.get_host_resolution()
        x, y = max(0, min(w - 1, round(x))), max(0, min(h - 1, round(y)))
        up = action == AMotionEventAction.UP
        message = InjectTouchEventMsg(
            action,
            pointer,
            (x, y, w, h),
            self.screen_geometry.get_device_resolution_for_client(w, h),
            0.0 if up else 1.0,
            0,
            0 if up else 1,
        )
        if up:
            self.contacts.pop(finger, None)
            self.pointer_id_manager.release(owner)
        else:
            self.contacts[finger] = (x, y)
        self.event_bus.emit(Event(EventType.CONTROL_MSG, self, message))
        return True

    def stop_gesture(self):
        for finger, position in list(self.contacts.items()):
            self.touch(finger, AMotionEventAction.UP, *position)

    def set_mapping_mode(self, mapping_mode):
        if not mapping_mode:
            self.stop_gesture()
        super().set_mapping_mode(mapping_mode)

    def on_delete(self):
        self.stop_gesture()
        super().on_delete()
