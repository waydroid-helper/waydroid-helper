from __future__ import annotations

import gi

gi.require_version("Gdk", "4.0")

from gi.repository import Gdk

from waydroid_helper.controller.app.window_input_router import (
    WindowInputRouter,
    WindowInputRouterDependencies,
)


class FakeModeController:
    def is_mode_switch_key(self, keyval: int) -> bool:
        return False


class RaisingInputEventFactory:
    def create_key_event(self, *args, **kwargs):
        raise AssertionError("F12 shortcut should not be forwarded as a key mapping")


class FakeWindow:
    EDIT_MODE = "edit"
    MAPPING_MODE = "mapping"

    def __init__(self):
        self.current_mode = self.MAPPING_MODE
        self.mode_controller = FakeModeController()
        self.input_event_factory = RaisingInputEventFactory()
        self.toggle_count = 0

    def toggle_all_widgets_transparency(self):
        self.toggle_count += 1
        return True


def make_router(window: FakeWindow) -> WindowInputRouter:
    return WindowInputRouter(
        WindowInputRouterDependencies(
            host=object(),
            get_current_mode=lambda: window.current_mode,
            switch_mode=lambda mode: True,
            toggle_widget_transparency=window.toggle_all_widgets_transparency,
            clear_selections=lambda: None,
            show_widget_creation_menu=lambda x, y: None,
            mode_controller=window.mode_controller,
            input_event_factory=window.input_event_factory,
            event_handler_chain=object(),
            event_bus=object(),
            workspace_manager=object(),
            finish_wheel_zoom=lambda: None,
            cancel_zoom=lambda: None,
        )
    )


def test_mapping_mode_f12_toggles_widgets_before_key_mapping_dispatch():
    window = FakeWindow()
    router = make_router(window)

    handled = router.on_global_key_press(None, Gdk.KEY_F12, 0, 0)

    assert handled is True
    assert window.toggle_count == 1


def test_mapping_mode_f12_release_is_consumed_without_toggling_again():
    window = FakeWindow()
    router = make_router(window)

    handled = router.on_global_key_release(None, Gdk.KEY_F12, 0, 0)

    assert handled is True
    assert window.toggle_count == 0
