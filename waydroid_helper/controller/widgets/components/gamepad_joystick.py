from __future__ import annotations
import asyncio
import math
import evdev
import logging
from typing import TYPE_CHECKING

# Import BaseWidget and decorators
from waydroid_helper.controller.widgets.base import BaseWidget
from waydroid_helper.controller.widgets.decorators import Resizable, ResizableDecorator
from waydroid_helper.controller.android.input import AMotionEventAction
from waydroid_helper.controller.core.control_msg import InjectTouchEventMsg, ScreenInfo
from waydroid_helper.controller.core.event_bus import Event, EventType

if TYPE_CHECKING:
    from cairo import Context

logger = logging.getLogger(__name__)

@Resizable(resize_strategy=ResizableDecorator.RESIZE_CENTER)
class GamepadJoystick(BaseWidget):
    # This name appears in the right-click menu
    WIDGET_NAME = "Gamepad Analog Stick"
    WIDGET_DESCRIPTION = "Dedicated 360-degree analog stick for gamepads."
    
    # Allow creating this widget from the menu
    ALLOW_CONTEXT_MENU_CREATION = True

    def __init__(self, x=0, y=0, width=150, height=150, 
                 event_bus=None, pointer_id_manager=None, key_registry=None, 
                 **kwargs):
        
        # ----------------------------------------------------------------------
        # FIX: The 'menus.py' loader passes 'text' in kwargs, but BaseWidget 
        # usually takes 'text' as a positional argument (often empty string by default).
        # Passing it in both places causes a TypeError. We remove it from kwargs.
        # ----------------------------------------------------------------------
        if "text" in kwargs:
            kwargs.pop("text")

        # Initialize BaseWidget
        # We pass "" as the default text (positional arg #6 usually) to avoid conflict
        super().__init__(
            x, y, min(width, height), min(width, height), 
            self.WIDGET_NAME, "", 
            min_width=60, min_height=60, 
            event_bus=event_bus, 
            pointer_id_manager=pointer_id_manager, 
            key_registry=key_registry, 
            **kwargs
        )
        
        self.screen_info = ScreenInfo()
        self._current_position = (x + width/2, y + height/2)
        self._joystick_active = False
        self.swipehold_radius_factor = 1.0

        # Subscribe to radius changes if needed
        if self.event_bus:
            self.event_bus.subscribe(EventType.SWIPEHOLD_RADIUS, self.on_radius_change, subscriber=self)

        # Start Gamepad Monitor Task
        self._monitor_task = asyncio.create_task(self._monitor_gamepads())
        self._gamepad_task = None

    # --- SAVE & LOAD SUPPORT ---
    def get_config(self):
        """Save specific settings to JSON"""
        # This is called by the ConfigManager when saving layout
        config = super().get_config()
        config['swipehold_radius_factor'] = self.swipehold_radius_factor
        return config

    def apply_config(self, config):
        """Load settings from JSON"""
        super().apply_config(config)
        self.swipehold_radius_factor = config.get('swipehold_radius_factor', 1.0)
    # ---------------------------

    async def _monitor_gamepads(self):
        """Watch for gamepads connecting/disconnecting"""
        logger.info("GamepadJoystick: Monitoring started...")
        while True:
            if self._gamepad_task and not self._gamepad_task.done():
                await asyncio.sleep(2)
                continue

            target = None
            try:
                for path in evdev.list_devices():
                    dev = evdev.InputDevice(path)
                    # Broad check for controllers
                    if any(x in dev.name for x in ["Xbox", "Gamepad", "Controller", "Sony", "Microsoft"]):
                        target = dev
                        break
            except Exception:
                pass

            if target:
                logger.info(f"GamepadJoystick: Hooked {target.name}")
                self._gamepad_task = asyncio.create_task(self._gamepad_loop(target))
            
            await asyncio.sleep(3)

    async def _gamepad_loop(self, device):
        """Read 360 analog data"""
        x, y = 0.0, 0.0
        try:
            abs_x = device.absinfo(evdev.ecodes.ABS_X)
            abs_y = device.absinfo(evdev.ecodes.ABS_Y)
            
            def norm(v, i): return ((v - i.min) / (i.max - i.min)) * 2 - 1 if i else 0

            async for event in device.async_read_loop():
                if event.type == evdev.ecodes.EV_ABS:
                    if event.code == evdev.ecodes.ABS_X: x = norm(event.value, abs_x)
                    elif event.code == evdev.ecodes.ABS_Y: y = norm(event.value, abs_y)
                    self.update_stick(x, y)
        except Exception:
            logger.warning("GamepadJoystick: Device disconnected")

    def update_stick(self, x, y):
        """Process stick movement and emit touch events"""
        dist = math.sqrt(x*x + y*y)
        deadzone = 0.15

        if dist < deadzone:
            if self._joystick_active:
                self._joystick_active = False
                self._emit_touch(AMotionEventAction.UP)
                if self.pointer_id_manager:
                    self.pointer_id_manager.release(self)
                self._current_position = self.center
                self.queue_draw()
            return

        if dist > 1.0: x, y = x/dist, y/dist
        
        radius_x = (self.width / 2) * self.swipehold_radius_factor
        radius_y = (self.height / 2) * self.swipehold_radius_factor
        
        target_x = self.center[0] + x * radius_x
        target_y = self.center[1] + y * radius_y

        if not self._joystick_active:
            if self.pointer_id_manager and self.pointer_id_manager.allocate(self) is not None:
                self._joystick_active = True
                self._emit_touch(AMotionEventAction.DOWN, position=self.center)
        
        self._current_position = (target_x, target_y)
        if self._joystick_active:
            self._emit_touch(AMotionEventAction.MOVE)
        self.queue_draw()

    def _emit_touch(self, action, position=None):
        if not self.pointer_id_manager or not self.event_bus:
            return

        pos = position if position else self._current_position
        w, h = self.screen_info.get_host_resolution()
        pid = self.pointer_id_manager.get_allocated_id(self)
        if pid is None: return
        
        msg = InjectTouchEventMsg(
            action=action, pointer_id=pid, position=(int(pos[0]), int(pos[1]), w, h),
            pressure=1.0, action_button=1, buttons=1
        )
        self.event_bus.emit(Event(EventType.CONTROL_MSG, self, msg))

    def draw_widget_content(self, cr: Context, width: int, height: int):
        """Draw the widget visuals"""
        cx, cy = width / 2, height / 2
        radius = min(width, height) / 2 - 5
        
        # Draw Background Ring
        cr.set_source_rgba(0.2, 0.2, 0.2, 0.6)
        cr.arc(cx, cy, radius, 0, 2 * math.pi)
        cr.fill()
        cr.set_source_rgba(1, 0.6, 0.0, 0.8) # Orange Border
        cr.set_line_width(2)
        cr.stroke()

        # Draw Stick Position (Red Dot)
        stick_x = self._current_position[0] - self.x
        stick_y = self._current_position[1] - self.y
        
        cr.set_source_rgba(1.0, 0.2, 0.2, 0.9)
        cr.arc(stick_x, stick_y, 10, 0, 2 * math.pi)
        cr.fill()

    def on_radius_change(self, event): 
        self.swipehold_radius_factor = event.data
        
    def on_delete(self): 
        if self._monitor_task: self._monitor_task.cancel()
        if self._gamepad_task: self._gamepad_task.cancel()
        super().on_delete()
        
    @property
    def center(self): 
        return (self.x + self.width/2, self.y + self.height/2)
        
    def get_editable_regions(self): 
        return []
