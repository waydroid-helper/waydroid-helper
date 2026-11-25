"""Bindings and contact lifetime for paths driven by physical trigger travel."""

from gettext import gettext as _

from waydroid_helper.controller.core.key_system import KeyCombination, bound_trigger
from waydroid_helper.controller.core.event_bus import EventType
from waydroid_helper.controller.widgets.base.placed_path import PlacedPath
from waydroid_helper.controller.widgets.base.touch_control import TouchControl
from waydroid_helper.controller.widgets.decorators import Editable


@Editable(max_keys=1)
class TriggerPath(PlacedPath, TouchControl):
    EMBEDDED_ONLY = True
    REQUIRES_ANALOG_TRIGGER = True
    PLACED_HINT = _(
        "Squeeze the trigger you want to bind to this path"
    )

    DEFAULT_TRIGGER = "Pad_RT"

    def do_contains(self, x, y):
        # PyGObject installs virtual methods from the GObject class dictionary.
        # A plain Python mixin alone would leave the entire path rectangle clickable.
        return self.path_contains(x, y)

    def __init__(self, *args, default_keys=None, **kwargs):
        if default_keys is None:
            combo = KeyCombination.from_names([self.DEFAULT_TRIGGER], kwargs["runtime_context"].key_registry)
            default_keys = [combo] if combo else []
        super().__init__(*args, default_keys=default_keys, **kwargs)
        if self.final_keys and not self.text:
            self.text = next(iter(self.final_keys)).display_text
        self.device = None
        self.event_bus.subscribe(EventType.GAMEPAD_TRIGGER, self._axis, subscriber=self)

    def _axis(self, event):
        sample = event.data
        if not self.mapping_mode or not sample.analog or sample.name != bound_trigger(self.final_keys):
            return
        if self.device is not None and self.device != sample.device:
            return
        if sample.travel is None:
            # Losing focus or unplugging the owner cancels at the current point.
            # Replaying a slider's return path here could activate other targets.
            self.stop_gesture()
            return
        self.apply_travel(sample.travel)
        self.device = sample.device if self.contacts else None

    def stop_gesture(self):
        super().stop_gesture()
        self.device = None

    def apply_travel(self, travel):
        raise NotImplementedError
