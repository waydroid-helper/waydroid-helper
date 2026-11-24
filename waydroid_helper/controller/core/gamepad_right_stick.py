"""Exclusive routing of one controller's right stick during a held skill."""

from collections.abc import Callable
from math import hypot
from typing import Protocol

from waydroid_helper.controller.core.key_system import KeyCombination


class SkillAim(Protocol):
    def aim_at(self, x: float, y: float) -> None: ...
    def cancel_at(self, x: float, y: float) -> None: ...
    def stop_gesture(self) -> None: ...


class GamepadRightStick:
    def __init__(self, stop_normal: Callable[[], None]):
        self.stop_normal = stop_normal
        self.position = (0.0, 0.0)
        self.owner: SkillAim | None = None
        self.binding: KeyCombination | None = None
        self.wait_for_center = False

    def claim(self, skill: SkillAim, binding: KeyCombination) -> bool:
        if self.owner is not None:
            return False
        self.owner = skill
        self.binding = binding
        # End the existing Android camera/movement contact before the skill
        # puts down its finger. Keep the real vector for a pre-aimed cast.
        self.stop_normal()
        return True

    def update(self, x: float, y: float) -> bool:
        self.position = (x, y)
        if self.owner is not None:
            self.owner.aim_at(x, y)
            return True
        if self.wait_for_center:
            self.wait_for_center = hypot(x, y) > .12
            return True
        return False

    def release(self, skill: SkillAim) -> None:
        if self.owner is skill:
            self.owner = self.binding = None
            # Do not turn the tail of this aiming motion into a camera pan.
            # Another skill can still claim the current position immediately.
            self.wait_for_center = hypot(*self.position) > .12

    def cancel_at(self, x: float, y: float) -> bool:
        if self.owner is None:
            return False
        self.owner.cancel_at(x, y)
        return True

    def reset(self) -> None:
        if self.owner is not None:
            self.owner.stop_gesture()
        self.position = (0.0, 0.0)
        self.wait_for_center = False
