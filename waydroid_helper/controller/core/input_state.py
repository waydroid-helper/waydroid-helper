#!/usr/bin/env python3
"""Android editable-focus state used to gate key mapping only."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AndroidInputState:
    """Latest state reported by the Android companion accessibility service."""

    is_input_active: bool
    reason: str = ""
    package_name: str = ""
    class_name: str = ""

