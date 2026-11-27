"""Compose a cursor-anchored pinch using stock scrcpy touchscreen messages."""

import math
import re
from dataclasses import dataclass

from waydroid_helper.controller.android.input import AMotionEventAction as Motion
from waydroid_helper.controller.core.control_msg import (
    InjectTouchEventMsg, PointerId, scale_coordinates,
)

PINCH_POINTERS = (PointerId.GENERIC_FINGER, PointerId.VIRTUAL_FINGER)
_RECT = re.compile(r"\[(-?\d+),(-?\d+)\]\[(-?\d+),(-?\d+)\]")
_SKIP = {"NOT_VISIBLE", "NOT_TOUCHABLE", "NO_INPUT_CHANNEL", "SPY"}
_DISPLAY = re.compile(r"^  Display: 0[ \t]*\n(.*?)(?=^    Windows:)", re.M | re.S)
_MATRIX_ROW = re.compile(r"^ +(-?[\d.]+) +(-?[\d.]+) +(-?[\d.]+) *$", re.M)


def _logical_rect(match, matrix):
    left, top, right, bottom = map(int, match.groups())
    a, b, tx, c, d, ty = matrix
    # The dispatcher reports physical window rectangles and a display-wide
    # physical-to-logical transform. scrcpy injects in logical display pixels.
    # Rotations by a quarter turn also exchange the horizontal/vertical axes.
    x0, x1 = a * left + b * top + tx, a * right + b * bottom + tx
    y0, y1 = c * left + d * top + ty, c * right + d * bottom + ty
    return (round(min(x0, x1)), round(min(y0, y1)),
            round(max(x0, x1)), round(max(y0, y1)))


def touch_interval(dump, x, y, width, height):
    """Find the uninterrupted horizontal hit region containing the guest cursor."""
    display = _DISPLAY.search(dump)
    matrix = (1, 0, 0, 0, 1, 0)
    if display:
        header = display.group(1)
        size = re.search(r"logicalSize=(\d+)x(\d+)", header)
        if size and tuple(map(int, size.groups())) != (width, height):
            return None
        rows = _MATRIX_ROW.findall(header)
        if len(rows) >= 2:
            matrix = tuple(float(value) for row in rows[:2] for value in row)
            a, b, _, c, d, _ = matrix
            if not ((a and d and b == c == 0) or (b and c and a == d == 0)):
                return None
        elif header.strip() and "IDENTITY" not in header:
            return None
    left, right = 0, width
    for line in dump.splitlines():
        if "displayId=0," not in line or "touchableRegion=" not in line:
            continue
        if "hasToken=false" in line or "visible=false" in line:
            continue
        flags = line.partition("inputConfig=")[2].partition(",")[0]
        if _SKIP.intersection(flags.split(" | ")):
            continue
        # Android 11 lists windows directly in logical display space, with
        # numeric WindowManager.LayoutParams flags instead of inputConfig.
        if "inputConfig=" not in line:
            legacy_flags = re.search(r"flags=(0x[0-9a-fA-F]+)", line)
            if legacy_flags and int(legacy_flags[1], 16) & 0x10:  # FLAG_NOT_TOUCHABLE
                continue
        frame = _RECT.match(line.partition("frame=")[2])
        region = line.partition("touchableRegion=")[2].partition(", ownerPid=")[0]
        for match in _RECT.finditer(region):
            l, t, r, b = _logical_rect(match, matrix)
            if not t <= y < b:
                continue
            # InputDispatcher lists windows front-to-back. A floating window
            # near the cursor may cover part of the next window's row even
            # though the cursor itself still hits that next window.
            if r <= x:
                left = max(left, r)
            elif l > x:
                right = min(right, l)
            else:
                if frame is None:
                    return None
                fl, ft, fr, fb = _logical_rect(frame, matrix)
                left, right = max(left, l, fl), min(right, r, fr)
                if left <= x < right and ft <= y < fb:
                    return left, right
                return None
    return None


class PinchContacts:
    def __init__(self, cursor, resolution, offsets, pointer_ids):
        self.x, self.y = cursor
        self.resolution = resolution
        self.offsets = offsets
        self.pointer_ids = pointer_ids
        self.last_x = [self.x + offset for offset in offsets]

    @classmethod
    async def at(cls, position, resolution, read_windows, pointer_ids=PINCH_POINTERS):
        x, y, w, h = scale_coordinates(*position, resolution)
        if not (0 <= x < w and 0 <= y < h):
            return None
        hit = touch_interval(await read_windows(), x, y, w, h)
        if hit is None:
            return None
        left, right = hit
        # Keep both DOWNs in the same target. Android retains the touch focus
        # when a later MOVE crosses its boundary. Horizontal motion also leaves
        # no downward displacement for the system's top-edge swipe listener.
        radius = min((right - left - 1) // 4, h // 4)
        if radius < 1:
            return None
        if x - left < radius:
            offsets = (0, 2 * radius)
        elif right - 1 - x < radius:
            offsets = (0, -2 * radius)
        else:
            offsets = (-radius, radius)
        # Near a corner there is too little space for a symmetric inward pinch.
        # Keep one finger on the cursor and scale the other about that same
        # fixed point. Gesture-aware views can combine scale and translation.
        return cls((x, y), (w, h), offsets, pointer_ids)

    def _message(self, finger, action):
        return InjectTouchEventMsg(
            action, self.pointer_ids[finger],
            (self.last_x[finger], self.y, *self.resolution), self.resolution,
            0.0 if action == Motion.UP else 1.0, 0, 0,
        )

    def down(self):
        return [self._message(i, Motion.DOWN) for i in (0, 1)]

    def move(self, scale):
        if not math.isfinite(scale) or scale <= 0:
            return []
        messages = []
        for i, offset in enumerate(self.offsets):
            # Wire positions are signed int32. Keep the trajectory continuous
            # through window and display edges rather than wrapping negatives.
            x = round(max(-(2**31), min(2**31 - 1, self.x + offset * scale)))
            if x != self.last_x[i]:
                self.last_x[i] = x
                messages.append(self._message(i, Motion.MOVE))
        return messages

    def up(self):
        # Upstream scrcpy frees an individual pointer slot on UP. A CANCEL
        # would cancel unrelated mapped contacts and leave this slot allocated.
        return [self._message(i, Motion.UP) for i in (1, 0)]


@dataclass
class RecordedPinch:
    """Logical pinch records written by earlier Helper builds."""
    action: int
    position: tuple[int, int, int, int]
    device_resolution: tuple[int, int]
    scale: float

    def __post_init__(self):
        if (self.action not in (Motion.DOWN, Motion.MOVE, Motion.UP, Motion.CANCEL)
                or len(self.position) != 4 or len(self.device_resolution) != 2
                or self.position[2] <= 0 or self.position[3] <= 0
                or not math.isfinite(self.scale) or self.scale <= 0):
            raise ValueError("Invalid recorded pinch")
