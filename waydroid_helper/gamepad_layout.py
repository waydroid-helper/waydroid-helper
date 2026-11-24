"""Select controller artwork and translate libmanette inputs into its layer order."""

from math import hypot
import re

from .gamepad_hardware import DEVICE_IDS

# Keys in the SVGs follow SDL's physical button positions. libmanette emits
# Linux input codes, even when it applied an SDL mapping internally.
BUTTON_CODES = (
    0x130,
    0x131,
    0x133,
    0x134,
    0x13A,
    0x13C,
    0x13B,
    0x13D,
    0x13E,
    0x136,
    0x137,
    0x220,
    0x221,
    0x222,
    0x223,
    0x2C4,
    0x2C1,
    0x2C0,
    0x2C3,
    0x2C2,
    0x2CA,
    0x2C5,
    0x2C6,
    0x2C7,
    0x2C8,
    0x2C9,
)
BUTTON_INDICES = {code: index for index, code in enumerate(BUTTON_CODES)}
STICK_AXES = {0: 0, 1: 1, 3: 2, 4: 3}

PLAYSTATION_BUTTON_LABELS = {
    "A": "×", "B": "○", "X": "□", "Y": "△",
    "LB": "L1", "RB": "R1", "LT": "L2", "RT": "R2", "LS": "L3", "RS": "R3",
}
SWITCH_BUTTON_LABELS = {
    "A": "B", "B": "A", "X": "Y", "Y": "X",
    "LB": "L", "RB": "R", "LT": "ZL", "RT": "ZR", "LS": "Ⓛ", "RS": "Ⓡ",
}


def button_labels_for(family, mapped):
    """Return physical keycap legends for the input codes received from this pad."""
    if family in ("ps3", "ps4", "ps5"):
        return PLAYSTATION_BUTTON_LABELS
    if family in ("switch-pro", "joycon-pair"):
        # SDL uses positional west/north. With no SDL mapping, hid-nintendo
        # reports BTN_X for the printed X and BTN_Y for the printed Y.
        return SWITCH_BUTTON_LABELS if mapped else {**SWITCH_BUTTON_LABELS, "X": "X", "Y": "Y"}
    if family == "joycon-left":
        if mapped:
            # A solo Joy-Con's SDL layout is horizontal, with both rail buttons
            # as shoulders. The arrows point away from the diamond's center.
            return {"A": "↓", "B": "→", "X": "←", "Y": "↑",
                    "LB": "SL", "RB": "SR", "LS": "Ⓛ"}
        return {"LB": "L", "RB": "SL", "LT": "ZL", "RT": "SR", "LS": "Ⓛ"}
    if family == "joycon-right":
        if mapped:
            # Rotating the right unit puts A at the bottom and X on the right.
            # SDL assigns its only stick to the logical left-stick slot.
            return {"A": "A", "B": "X", "X": "B", "Y": "Y",
                    "LB": "SL", "RB": "SR", "LS": "Ⓡ"}
        return {**SWITCH_BUTTON_LABELS, "X": "X", "Y": "Y", "LB": "SL", "LT": "SR"}
    return {}


# A GameCube-style pad may speak Switch or XInput. Some exact SDL mappings
# identify this shell more specifically than Valve's protocol family does.
def artwork_for_device(device, mapping=""):
    fields = mapping.split(",", 2)
    model = fields[1].casefold() if len(fields) == 3 else ""
    if "gamecube" in model:
        return "gamecube"
    # A combined pair can retain the left Joy-Con's USB product ID.
    pair_names = ("nintendo switch combined joy-cons", "joy-con (l/r)")
    if model in pair_names or device.get_name().casefold() in pair_names:
        return "joycon-pair"

    guid = device.get_guid() if hasattr(device, "get_guid") else None
    if guid and len(guid) == 32:
        try:
            raw = bytes.fromhex(guid)
        except ValueError:
            raw = b""
        vendor = int.from_bytes(raw[4:6], "little")
        product = int.from_bytes(raw[8:10], "little")
        if vendor and product:
            hardware_id = vendor << 16 | product
            return next(
                (family for family, ids in DEVICE_IDS.items() if hardware_id in ids),
                "generic",
            )

    # Without a VID/PID, accept explicit model names only. Driver names such
    # as "Generic X-Box pad" describe a protocol shared by many manufacturers.
    models = {
        "nintendo switch pro controller": "switch-pro",
        "ps4 controller": "ps4",
        "dualshock 4": "ps4",
        "dualsense wireless controller": "ps5",
        "xbox 360 controller": "xbox-360",
        "xbox one controller": "xbox-one",
        "steam controller": "steam",
        "nintendo gamecube controller": "gamecube",
        "joy-con (l)": "joycon-left",
        "nintendo switch left joy-con": "joycon-left",
        "joy-con (r)": "joycon-right",
        "nintendo switch right joy-con": "joycon-right",
    }
    return models.get(model) or models.get(device.get_name().casefold(), "generic")


def physical_button_code(code, mapped):
    # libmanette reports SDL west ("x") as BTN_Y and north ("y") as BTN_X.
    # Raw xpad input uses the opposite ordering. Both the diagram and saved
    # bindings use the same positional convention (west = Pad_X).
    if mapped and code in (0x133, 0x134):
        return 0x134 if code == 0x133 else 0x133
    return code


def normalize_stick(x, y):
    """Project the artwork's signed 16-bit stick coordinates onto a unit disc."""
    nx = x / (32768 if x < 0 else 32767)
    ny = y / (32768 if y < 0 else 32767)
    length = max(1.0, hypot(nx, ny))
    return nx / length, ny / length


class TriggerAxes:
    """Resolve physical trigger travel independently of digital button events."""

    AXIS_NAMES = {2: "LT", 5: "RT"}

    def __init__(self, mapping):
        self.sources = {}
        for field in mapping.split(",")[2:]:
            match = re.fullmatch(r"(lefttrigger|righttrigger):([+-]?)a(\d+)(~?)", field)
            if match:
                target, half, index, inverted = match.groups()
                name = "LT" if target == "lefttrigger" else "RT"
                self.sources.setdefault(int(index), []).append((name, half, inverted))

    def raw_values(self, index, value):
        # SDL can assign both halves of one hardware axis to two triggers.
        # Emit the resting half as well, so a direct crossover releases it.
        for name, half, inverted in self.sources.get(index, ()):
            travel = -value if half == "-" else value
            if not half:
                travel = (travel + 1) / 2
            if travel < 0:
                travel = 0
            elif inverted:
                travel = 1 - travel
            yield name, max(0.0, min(1.0, travel))

    def available(self, device, mapped):
        if mapped:
            return {name for entries in self.sources.values() for name, _, _ in entries}
        return {name for axis, name in self.AXIS_NAMES.items() if device.has_input(3, axis)}


class PreviewInputs:
    def __init__(self, mapped, mapping="", analog_triggers=()):
        self.mapped = mapped
        self.buttons = [False] * 26
        self.axes = [0] * 6
        self.triggers = TriggerAxes(mapping)
        self.analog_triggers = set(analog_triggers)
        for entries in self.triggers.sources.values():
            self.analog_triggers.update(4 if name == "LT" else 5 for name, _, _ in entries)

    def raw_axis(self, index, value):
        for name, travel in self.triggers.raw_values(index, value):
            self.axes[4 if name == "LT" else 5] = round(travel * 32767)
        return index in self.triggers.sources

    def button(self, code, pressed):
        code = physical_button_code(code, self.mapped)
        if code in BUTTON_INDICES:
            self.buttons[BUTTON_INDICES[code]] = pressed
        elif code in (0x138, 0x139):  # Digital shoulder triggers.
            slot = 4 if code == 0x138 else 5
            if slot not in self.analog_triggers:
                self.axes[slot] = 32767 if pressed else 0

    def axis(self, code, value):
        if code in STICK_AXES:
            self.axes[STICK_AXES[code]] = round(value * (32768 if value < 0 else 32767))
        elif code in (2, 5):
            # libmanette reports evdev absolute axes on [-1, 1], including
            # analog triggers whose physical resting position is the minimum.
            self.axes[4 if code == 2 else 5] = round((value + 1) * 32767 / 2)
        elif code in (16, 17):
            negative, positive = (13, 14) if code == 16 else (11, 12)
            self.buttons[negative] = value < 0
            self.buttons[positive] = value > 0
