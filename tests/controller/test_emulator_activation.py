import os
from pathlib import Path
import shutil
import subprocess
import sys
from unittest.mock import Mock, patch

import pytest


def check_default_window():
    from waydroid_helper.controller.app.window import Gdk, KeyMapper
    from waydroid_helper.controller.app.emulator_window import EmulatorWindow

    # Exercise both the initial unnamed title and a GSettings notification.
    window = Mock()
    window.session.instance = "default"
    window.metadata.get_string.return_value = ""
    EmulatorWindow._sync_title(window)
    window.set_title.assert_called_once_with("Waydroid Emulator")
    window.metadata.get_string.return_value = "Tablet"
    EmulatorWindow._sync_title(window, window.metadata, "name")
    window.set_title.assert_called_with("Tablet")

    app = KeyMapper(Gdk.Display.get_default().get_name(), embedded=True)
    assert app.register(None)
    with patch.object(EmulatorWindow, "build_canvas", side_effect=RuntimeError("injected startup failure")) as build:
        app.activate()
        build.assert_called_once()
    assert app.window is None
    assert not app.get_windows()


def test_default_title_and_failed_activation(tmp_path):
    if not all(shutil.which(tool) for tool in ("xvfb-run", "dbus-run-session")):
        pytest.skip("Requires Xvfb and a private D-Bus session")
    # The mapping-core test suite stubs GUI dependencies. Run the actual GTK
    # application in its own interpreter, display and bus to check ownership.
    env = dict(os.environ, GDK_BACKEND="x11", GSK_RENDERER="cairo", GTK_A11Y="none",
               LC_ALL="C", LANGUAGE="C", WAYDROID_HELPER_EMULATOR="1", GSETTINGS_BACKEND="memory",
               XDG_CACHE_HOME=str(tmp_path), XDG_CONFIG_HOME=str(tmp_path),
               PYTHONPATH=str(Path(__file__).resolve().parents[2]))
    subprocess.run(["xvfb-run", "-a", "dbus-run-session", "--", sys.executable, __file__],
                   env=env, check=True, timeout=20)


if __name__ == "__main__":
    check_default_window()
