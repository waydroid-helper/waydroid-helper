"""Local per-device mapping profiles and the lifetime of a single edit session."""

from __future__ import annotations

import json
import math
import os
import re
from copy import deepcopy
from dataclasses import dataclass
from gettext import gettext as _
from pathlib import Path
from tempfile import NamedTemporaryFile
from uuid import uuid4

from waydroid_helper.util.log import logger


class ProfileLibrary:
    INPUTS = ("keyboard", "gamepad")

    def __init__(self, root: Path, package: str, kind: str):
        if (
            kind not in self.INPUTS
            or not re.fullmatch(r"[\w.]+", package)
            or package in (".", "..")
        ):
            raise ValueError("Invalid mapping profile scope")
        self.kind = kind
        self.folder = root / package / kind

    @staticmethod
    def write(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, delete=False
        ) as f:
            temp = Path(f.name)
            try:
                json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)
                f.flush()
                os.fsync(f.fileno())
                f.close()
                os.replace(temp, path)
            finally:
                temp.unlink(missing_ok=True)

    def path(self, ident):
        if not re.fullmatch("[a-f0-9]{32}", ident):
            raise ValueError("Invalid profile identifier")
        return self.folder / (ident + ".json")

    def read(self, ident):
        return self.validate(json.loads(self.path(ident).read_text(encoding="utf-8")))

    @staticmethod
    def validate(data):
        if not isinstance(data, dict) or not isinstance(data.get("widgets"), list):
            raise ValueError(_("Invalid mapping layout"))
        resolution = data.get("screen_resolution") or {}
        if not isinstance(resolution, dict) or any(
            type(size) not in (float, int) or not math.isfinite(size) or size <= 0
            for size in resolution.values()
        ):
            raise ValueError(_("Invalid mapping layout"))
        if not isinstance(data.get("profile", {}), dict):
            raise ValueError(_("Invalid mapping layout"))
        for item in data["widgets"]:
            if not isinstance(item, dict) or not isinstance(item.get("type"), str):
                raise ValueError(_("Invalid mapping layout"))
            bindings = item.get("default_keys", [])
            directions = item.get("direction_keys", {})
            if not isinstance(bindings, list) or not isinstance(directions, dict):
                raise ValueError(_("Invalid mapping layout"))
            for combo in [*bindings, *directions.values()]:
                if not isinstance(combo, list) or not all(
                    isinstance(k, str) for k in combo
                ):
                    raise ValueError(_("Invalid mapping layout"))
            for field in ("x", "y", "width", "height"):
                value = item.get(field, 100)
                if type(value) not in (int, float) or not math.isfinite(value):
                    raise ValueError(_("Invalid mapping layout"))
                if field in ("width", "height") and value <= 0:
                    raise ValueError(_("Invalid mapping layout"))
            if not isinstance(item.get("config", {}), dict) or not all(
                isinstance(cfg, dict) for cfg in item.get("config", {}).values()
            ):
                raise ValueError(_("Invalid mapping layout"))
        return data

    def entries(self):
        entries = []
        for path in self.folder.glob("*.json"):
            try:
                data = self.read(path.stem)
                info = data["profile"]
                if not isinstance(info["name"], str):
                    raise ValueError("Invalid profile name")
                entries.append((path.stem, info["name"], bool(info.get("pinned"))))
            except (KeyError, ValueError, TypeError, OSError):
                logger.warning("Unreadable mapping profile %s", path, exc_info=True)
        return sorted(entries, key=lambda p: (not p[2], p[1].casefold(), p[0]))

    def save(self, name, layout, ident=None, pinned=False):
        if not name.strip():
            raise ValueError(_("Enter a profile name"))
        ident = ident or uuid4().hex
        layout = self.validate(layout)
        info = dict(
            layout.get("profile", {}),
            name=name.strip(),
            pinned=bool(pinned),
            input=self.kind,
        )
        data = dict(layout, profile=info)
        self.write(self.path(ident), data)
        return ident

    def select(self, ident):
        if ident is not None:
            self.read(ident)
        self.write(self.folder / "active", ident)

    def active(self):
        try:
            ident = json.loads((self.folder / "active").read_text(encoding="utf-8"))
            return ident if ident and self.path(ident).is_file() else None
        except FileNotFoundError:
            return None
        except (ValueError, TypeError, OSError):
            logger.warning(
                "Unreadable profile selection in %s", self.folder, exc_info=True
            )
            return None


GAMEPAD_CONTROLS = frozenset(
    {
        "singleclick",
        "repeatedclick",
        "swipe",
        "analogstick",
        "rightstick",
        "triggerslider",
        "dualstagetrigger",
        "gamepadskillcasting",
        "gamepadcancelcasting",
        "macro",
    }
)


def supports_control(kind, control):
    if kind == "gamepad":
        return control in GAMEPAD_CONTROLS
    return control not in {"analogstick", "rightstick", "triggerslider", "dualstagetrigger", "gamepadskillcasting", "gamepadcancelcasting"}


def layout_for_input(data, kind):
    """Read old mixed JSON layouts without assigning foreign keys to this device."""
    ProfileLibrary.validate(data)
    declared = data.get("profile", {}).get("input")
    if declared and declared != kind:
        raise ValueError(_("This profile belongs to the other input device"))
    result = deepcopy(data)
    widgets = []
    for item in result["widgets"]:
        if kind == "gamepad" and item["type"] == "skillcasting":
            # The old widget already used its placed diameter for the guest
            # touch range. Keep that geometry and binding, and discard only
            # settings that described the mouse projection and cast timing.
            item["type"] = "gamepadskillcasting"
            item["config"] = {k: v for k, v in item.get("config", {}).items()
                              if k in ("show_hint", "hint_note")}
        elif kind == "gamepad" and item["type"] == "cancelcasting":
            item["type"] = "gamepadcancelcasting"
        if not supports_control(kind, item["type"]):
            continue
        combos = item.get("default_keys", [])
        if combos:
            local = [
                combo
                for combo in combos
                if combo
                and all(
                    isinstance(key, str)
                    and key.startswith("Pad_") == (kind == "gamepad")
                    for key in combo
                )
            ]
            if not local:
                continue
            if local != combos:
                item.pop("text", None)
            item["default_keys"] = local
        if kind == "keyboard" and "direction_keys" in item:
            for side, keys in item["direction_keys"].items():
                if any(key.startswith("Pad_") for key in keys):
                    item["direction_keys"][side] = []
        widgets.append(item)
    if data["widgets"] and not widgets:
        raise ValueError(_("This layout has no controls for this input device"))
    result["widgets"] = widgets
    return result


@dataclass
class ProfileEdit:
    ident: str | None
    name: str
    initial_name: str
    initial: dict
    previous: dict


class ProfileWorkspace:
    """One foreground application, one input family and at most one editor."""

    def __init__(self, window, root):
        self.window = window
        self.root = root
        self.package = "home"
        self.kind = self.preferred_input(self.package)
        self.edit = None

    def library(self, kind=None):
        return ProfileLibrary(self.root, self.package, kind or self.kind)

    def capture(self):
        return self.window.layout_service.serialize_layout(
            self.window.workspace_manager.iter_widgets()
        )

    def restore(self, data):
        return self.window.layout_service.restore_layout(
            deepcopy(data),
            self.window.widget_factory,
            lambda: self.window.on_clear_widgets(None),
            self.window.attach_widget_at_position,
        )

    def load_initial(self):
        lib = self.library()
        ident = lib.active()
        try:
            data = (
                layout_for_input(lib.read(ident), self.kind)
                if ident
                else {"widgets": []}
            )
            if self.restore(data) != len(data["widgets"]):
                raise ValueError(_("Could not load every control in this profile"))
        except (ValueError, OSError, TypeError, KeyError):
            logger.exception(
                "Could not restore %s profile for %s", self.kind, self.package
            )
            self.restore({"widgets": []})

    def preferred_input(self, package):
        # Profiles use the Android package name, not the transient task ID.
        # Two tasks of one app therefore share selection across relaunches.
        path = ProfileLibrary(self.root, package, "keyboard").folder.parent / "input"
        try:
            kind = json.loads(path.read_text(encoding="utf-8"))
            if kind in ProfileLibrary.INPUTS:
                return kind
        except FileNotFoundError:
            pass
        except (ValueError, OSError):
            logger.warning(
                "Could not read input device selection for %s", package, exc_info=True
            )
        return "keyboard"

    def switch(self, package, kind=None):
        if self.edit:
            return False
        selected = kind or self.preferred_input(package)
        if (package, selected) == (self.package, self.kind):
            return False
        library = ProfileLibrary(self.root, package, selected)
        if kind is not None:
            ProfileLibrary.write(library.folder.parent / "input", kind)
        self.package, self.kind = package, selected
        self.load_initial()
        return True

    def apply(self, ident):
        if self.edit:
            return
        lib = self.library()
        data = layout_for_input(lib.read(ident), self.kind)
        previous = self.capture()
        self.window._release_mapping_input()
        try:
            if self.restore(data) != len(data["widgets"]):
                raise ValueError(_("Could not load every control in this profile"))
            lib.select(ident)
        except Exception:
            self.restore(previous)
            raise

    def begin_edit(self, new=False, ident=None):
        if self.edit:
            return
        lib = self.library()
        previous = self.capture()
        target = None if new else ident or lib.active()
        if target:
            data = layout_for_input(lib.read(target), self.kind)
            name = data["profile"]["name"]
            if ident is not None and self.restore(data) != len(data["widgets"]):
                self.restore(previous)
                raise ValueError(_("Could not load every control in this profile"))
        else:
            names = {entry[1] for entry in lib.entries()}
            number = 1
            while _("Custom profile (%d)") % number in names:
                number += 1
            name = _("Custom profile (%d)") % number
            if new:
                self.restore({"widgets": []})
        self.edit = ProfileEdit(target, name, name, self.capture(), previous)

    def dirty(self):
        return self.edit is not None and (
            self.edit.name != self.edit.initial_name
            or self.capture()["widgets"] != self.edit.initial["widgets"]
        )

    def finish(self, save):
        edit = self.edit
        if edit is None:
            return
        if save and self.dirty():
            lib = self.library()
            previous_file = lib.read(edit.ident) if edit.ident else None
            info = previous_file["profile"] if previous_file else {}
            layout = dict(self.capture(), profile=info)
            ident = lib.save(edit.name, layout, edit.ident, info.get("pinned", False))
            if lib.active() != ident:
                # Saving the document and selecting it update separate files.
                # Roll back the document when selection fails so Retry cannot
                # create duplicates and Cancel still restores the original.
                try:
                    lib.select(ident)
                except (OSError, ValueError):
                    if previous_file is None:
                        lib.path(ident).unlink()
                    else:
                        lib.write(lib.path(ident), previous_file)
                    raise
        elif not save or not edit.ident:
            self.restore(edit.previous)
        elif edit.ident:
            self.library().select(edit.ident)
        self.edit = None
