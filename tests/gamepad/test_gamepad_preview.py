from types import SimpleNamespace

import pytest

from waydroid_helper.gamepad_layout import PreviewInputs, artwork_for_device, button_labels_for


@pytest.mark.parametrize(
    "mapped,west,north", [(False, 0x133, 0x134), (True, 0x134, 0x133)]
)
def test_face_buttons_hold_and_release_independently(mapped, west, north):
    inputs = PreviewInputs(mapped)
    inputs.button(west, True)
    inputs.button(north, True)
    assert inputs.buttons[2:4] == [True, True]
    inputs.button(west, False)
    assert inputs.buttons[2:4] == [False, True]
    inputs.button(north, False)
    assert not any(inputs.buttons)


def test_hat_and_analog_trigger_return_to_rest():
    inputs = PreviewInputs(False)
    inputs.axis(16, -1)
    inputs.axis(17, 1)
    inputs.axis(2, 0)
    assert inputs.buttons[11:15] == [False, True, True, False]
    assert inputs.axes[4] == 16384
    inputs.axis(16, 1)
    assert inputs.buttons[13:15] == [False, True]
    inputs.axis(16, 0)
    inputs.axis(17, 0)
    inputs.axis(2, -1)
    assert not any(inputs.buttons) and not any(inputs.axes)


def test_hardware_and_mapping_names_select_the_corresponding_artwork():
    device = SimpleNamespace(
        get_name=lambda: "Wireless Controller",
        get_guid=lambda: "030000004c050000cc09000000010000",
    )
    assert artwork_for_device(device) == "ps4"
    clone = SimpleNamespace(get_name=lambda: "Zikway Pro Controller")
    assert (
        artwork_for_device(clone, "guid,Nintendo Switch Pro Controller,a:b0,")
        == "switch-pro"
    )
    assert artwork_for_device(clone) == "generic"


def test_combined_joycons_can_report_the_left_units_product_id():
    device = SimpleNamespace(get_guid=lambda: "060000007e0500000620000000000000",
                             get_name=lambda: "Joy-Con (L)")
    assert artwork_for_device(device) == "joycon-left"
    assert artwork_for_device(device, "guid,Nintendo Switch Combined Joy-Cons,a:b0,") == "joycon-pair"


@pytest.mark.parametrize("side,faces,stick", [
    ("joycon-left", "↓→←↑", "Ⓛ"), ("joycon-right", "AXBY", "Ⓡ"),
])
def test_single_joycon_keycaps_in_the_horizontal_layout(side, faces, stick):
    labels = button_labels_for(side, mapped=True)
    assert [labels[key] for key in "ABXY"] == list(faces)
    assert (labels["LB"], labels["RB"], labels["LS"]) == ("SL", "SR", stick)


def test_nintendo_raw_evdev_labels_follow_the_kernel_button_codes():
    labels = button_labels_for("switch-pro", mapped=False)
    assert [labels[key] for key in "ABXY"] == list("BAXY")
    left = button_labels_for("joycon-left", mapped=False)
    right = button_labels_for("joycon-right", mapped=False)
    assert [left[key] for key in ("LB", "RB", "LT", "RT")] == ["L", "SL", "ZL", "SR"]
    assert [right[key] for key in ("LB", "RB", "LT", "RT")] == ["SL", "R", "SR", "ZR"]


@pytest.mark.parametrize(
    "guid,name,expected",
    [
        ("03000000373500009810000000010000", "Generic X-Box pad", "generic"),
        ("030000007e0500000920000011810000", "Zikway Pro Controller", "switch-pro"),
        ("050000004c050000cc09000000010000", "Wireless Controller", "ps4"),
        ("030000005e0400008e02000014010000", "Generic X-Box pad", "xbox-360"),
    ],
)
def test_hardware_identity_takes_precedence_over_driver_names(guid, name, expected):
    device = SimpleNamespace(get_guid=lambda: guid, get_name=lambda: name)
    assert artwork_for_device(device) == expected


@pytest.mark.parametrize(
    "mapped,west,north", [(False, 0x133, 0x134), (True, 0x134, 0x133)]
)
def test_binding_signals_match_highlight_positions(mapped, west, north):
    from unittest.mock import Mock, patch
    from waydroid_helper.controller.app.emulator_gamepad import GamepadInput
    from waydroid_helper.controller.core.key_system import KeyRegistry

    with patch("gi.require_version", side_effect=ValueError):
        gamepad = GamepadInput(SimpleNamespace(key_registry=KeyRegistry()))
    gamepad._transition = Mock()
    gamepad._settings_for = Mock()
    gamepad._settings_for.return_value.get_boolean.return_value = False
    device = Mock()
    device.get_guid.return_value = "03000000373500009810000000010000"
    device.get_mapping.return_value = "guid,Test,x:b3,y:b2," if mapped else None
    gamepad._connect(None, device)
    signals = {call.args[0]: call.args[1:] for call in device.connect.call_args_list}

    for code, name in [(west, "X"), (north, "Y")]:
        event = SimpleNamespace(get_button=lambda: (True, code))
        for signal, pressed in [("button-press-event", True), ("button-release-event", False)]:
            handler, *data = signals[signal]
            handler(device, event, *data)
            gamepad._transition.assert_called_with(device, name, pressed)

    handler, = signals["hat-axis-event"]
    for value in (-1, 0, 1):
        gamepad._transition.reset_mock()
        handler(device, SimpleNamespace(get_hat=lambda: (True, 16, value)))
        assert [call.args[1:] for call in gamepad._transition.call_args_list] == [
            ("Left", value < 0), ("Right", value > 0),
        ]


def test_mapped_trigger_keeps_analog_pressure_after_button_threshold():
    inputs = PreviewInputs(True, "guid,Test,lefttrigger:a2,righttrigger:b7,")
    for sample, expected in [(-1, 0), (-0.5, 8192), (0, 16384), (1, 32767), (-1, 0)]:
        assert inputs.raw_axis(2, sample)
        inputs.button(0x138, sample > 0)
        assert inputs.axes[4] == expected
    inputs.button(0x139, True)
    assert inputs.axes[5] == 32767
    inputs.button(0x139, False)
    assert inputs.axes[5] == 0


def test_two_triggers_sharing_one_axis_and_full_axis_inversion():
    shared = PreviewInputs(True, "guid,Test,lefttrigger:-a1,righttrigger:+a1,")
    shared.raw_axis(1, -.5)
    assert shared.axes[4:] == [16384, 0]
    shared.raw_axis(1, 1)
    assert shared.axes[4:] == [0, 32767]
    inverted = PreviewInputs(True, "guid,Test,lefttrigger:a3~,")
    inverted.raw_axis(3, 1)
    assert inverted.axes[4] == 0
    inverted.raw_axis(3, -1)
    assert inverted.axes[4] == 32767


def test_nintendo_layout_keeps_press_and_release_paired_across_a_change():
    from unittest.mock import Mock
    from waydroid_helper.controller.app.emulator_gamepad import ConnectedGamepad

    pad = ConnectedGamepad(Mock(), Mock())
    pad.settings.get_boolean.return_value = False
    assert pad.face_binding("A", True) == "A"
    pad.settings.get_boolean.return_value = True
    assert pad.face_binding("B", True) == "A"
    assert pad.face_binding("A", False) is None
    assert pad.face_binding("B", False) == "A"
    for key, binding in zip("ABXY", "BAYX"):
        assert pad.face_binding(key, True) == binding
        assert pad.face_binding(key, False) == binding
