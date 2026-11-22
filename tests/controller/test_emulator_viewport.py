from types import SimpleNamespace
from unittest.mock import Mock

from waydroid_helper.controller.app.emulator_viewport import EmulatorViewport


def test_desktop_resize_never_advertises_a_new_android_mode():
    for initial, configured in (((960, 540), None), ((800, 600), (800, 600))):
        view = SimpleNamespace(mapping_size=initial, configured_output=configured, output_size=None,
                               compositor=Mock(), canvas=Mock(), emit=Mock())
        for width, height in (initial, (720, 405), (1600, 1000)):
            EmulatorViewport.do_size_allocate(view, width, height, -1)
            assert view.compositor.allocate.call_args.args[:2] == initial
            assert view.canvas.allocate.call_args.args[:2] == initial
        view.emit.assert_called_once_with("output-resized")


def test_all_resize_handles_use_one_scale_for_landscape_and_portrait():
    for ratio in (9 / 16, 16 / 9):
        for edge in ("n", "s", "w", "e", "nw", "ne", "sw", "se"):
            for growth in (-80, 80):
                dx = -growth if "w" in edge else growth if "e" in edge else 0
                dy = -growth * ratio if "n" in edge else growth * ratio if "s" in edge else 0
                assert EmulatorViewport.drag_width(640, ratio, edge, dx, dy) == 640 + growth
