import json
from types import SimpleNamespace

import pytest

from waydroid_helper.controller.app.mapping_profiles import (
    ProfileLibrary,
    ProfileWorkspace,
    layout_for_input,
)


def test_profile_library_round_trip_and_failed_write(tmp_path):
    library = ProfileLibrary(tmp_path, "com.example.game", "keyboard")
    original = {"widgets": [{"type": "swipe", "width": 80}]}
    ident = library.save("A/B", original)
    other = library.save("Demo", original, pinned=True)
    library.select(ident)
    assert library.entries() == [(other, "Demo", True), (ident, "A/B", False)]
    assert library.active() == ident
    with pytest.raises(ValueError):
        library.save(
            "bad", {"widgets": [{"type": "swipe", "width": float("nan")}]}, ident
        )
    assert library.read(ident)["widgets"] == original["widgets"]
    assert ProfileLibrary(tmp_path, "com.example.game", "gamepad").entries() == []
    assert ProfileLibrary(tmp_path, "home", "keyboard").active() is None
    with pytest.raises(ValueError):
        library.path("../unsafe")


def test_editor_owns_one_device_and_package_until_save_or_cancel(tmp_path):
    state = {"widgets": []}
    workspace = ProfileWorkspace(SimpleNamespace(), tmp_path)
    workspace.capture = lambda: json.loads(json.dumps(state))

    def restore(data):
        state["widgets"] = data["widgets"]
        return len(state["widgets"])

    workspace.restore = restore
    workspace.begin_edit(new=True)
    assert not workspace.dirty()
    state["widgets"] = [{"type": "swipe", "default_keys": [["J"]]}]
    assert workspace.dirty() and not workspace.library().entries()
    assert not workspace.switch("home", "gamepad")
    assert not workspace.switch("com.example.game", "keyboard")
    workspace.edit.name = "Keyboard"
    workspace.finish(save=True)
    active_keyboard = workspace.library().active()
    assert workspace.library().read(active_keyboard)["profile"]["input"] == "keyboard"

    assert workspace.switch("home", "gamepad")
    assert state == {"widgets": []}
    workspace.begin_edit(new=True)
    state["widgets"] = [{"type": "analogstick"}]
    workspace.edit.name = "Stick"
    workspace.finish(save=True)
    assert workspace.library().entries()[0][1] == "Stick"
    workspace.switch("com.example.game")
    assert workspace.kind == "keyboard" and not state["widgets"]
    workspace.switch("home")
    assert workspace.kind == "gamepad" and state["widgets"][0]["type"] == "analogstick"
    assert ProfileWorkspace(SimpleNamespace(), tmp_path).kind == "gamepad"
    workspace.switch("home", "keyboard")
    assert state["widgets"][0]["default_keys"] == [["J"]]
    workspace.begin_edit(new=True)
    assert not state["widgets"]
    workspace.edit.name = "Discard me"
    workspace.finish(save=False)
    assert state["widgets"][0]["default_keys"] == [["J"]]
    assert workspace.library().entries() == [(active_keyboard, "Keyboard", False)]


def test_import_separates_legacy_bindings_and_rejects_foreign_profiles():
    mixed = {
        "widgets": [
            {"type": "singleclick", "default_keys": [["J"], ["Pad_A"]]},
            {"type": "rightstick"},
        ]
    }
    kb = layout_for_input(mixed, "keyboard")
    assert kb["widgets"] == [{"type": "singleclick", "default_keys": [["J"]]}]
    pad = layout_for_input(mixed, "gamepad")
    assert pad["widgets"][0]["default_keys"] == [["Pad_A"]]
    assert pad["widgets"][1]["type"] == "rightstick"
    kb["profile"] = {"input": "keyboard"}
    with pytest.raises(ValueError):
        layout_for_input(kb, "gamepad")
    with pytest.raises(ValueError):
        layout_for_input(
            {"widgets": [{"type": "singleclick", "default_keys": ["J"]}]}, "keyboard"
        )


def test_failed_activation_can_retry_new_profile_without_duplicates(
    tmp_path, monkeypatch
):
    workspace = ProfileWorkspace(SimpleNamespace(), tmp_path)
    state = {"widgets": []}
    workspace.capture = lambda: json.loads(json.dumps(state))
    workspace.restore = lambda _: 0
    workspace.begin_edit(new=True)
    state["widgets"].append({"type": "singleclick"})

    def fail_selection(library, ident):
        raise OSError("selection write failed")

    with monkeypatch.context() as patch:
        patch.setattr(ProfileLibrary, "select", fail_selection)
        with pytest.raises(OSError):
            workspace.finish(save=True)
    assert workspace.dirty() and not workspace.library().entries()
    workspace.finish(save=True)
    assert len(workspace.library().entries()) == 1
    assert workspace.library().active() == workspace.library().entries()[0][0]
