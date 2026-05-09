from __future__ import annotations

import re
from pathlib import Path


CONTROLLER_ROOT = Path("waydroid_helper/controller")


def iter_controller_sources():
    return CONTROLLER_ROOT.rglob("*.py")


def test_controller_does_not_use_global_screen_info():
    combined = "\n".join(path.read_text(encoding="utf-8") for path in iter_controller_sources())

    assert "ScreenInfo(" not in combined
    assert "_screen_info" not in combined


def test_skill_casting_has_no_bare_except():
    source = Path(
        "waydroid_helper/controller/widgets/components/skill_casting.py"
    ).read_text(encoding="utf-8")

    assert re.search(r"except\s*:", source) is None


def test_editable_decorator_does_not_reach_into_session_state():
    source = Path(
        "waydroid_helper/controller/widgets/decorators/editable.py"
    ).read_text(encoding="utf-8")

    forbidden_state = (
        "self.is_editing",
        "self.current_edit_region",
        "self.original_keys",
        "self.realtime_keys",
        "self.original_text",
    )
    for pattern in forbidden_state:
        assert pattern not in source
