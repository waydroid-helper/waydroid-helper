#!/usr/bin/env python3
"""File dialog actions for layout import/export."""

from __future__ import annotations

import os
from gettext import gettext as _
from pathlib import Path
from typing import Callable

from gi.repository import GLib, Gtk

from waydroid_helper.compat_widget.file_dialog import FileDialog
from waydroid_helper.util.log import logger


class LayoutFileActions:
    """Owns GTK file picker plumbing for layout files."""

    def __init__(self, parent_window) -> None:
        self.parent_window = parent_window

    def save_layout(self, callback: Callable[[str], None]) -> None:
        dialog = FileDialog(
            parent=self.parent_window,
            title=_("Save Layout"),
            modal=True,
        )
        dialog.save_file(
            callback=lambda success, path: self._dispatch(success, path, callback),
            suggested_name="layout.json",
            file_filter=self._json_filter(),
            initial_folder=self._default_layouts_dir(),
        )

    def load_layout(self, callback: Callable[[str], None]) -> None:
        dialog = FileDialog(
            parent=self.parent_window,
            title=_("Load Layout"),
            modal=True,
        )
        dialog.open_file(
            callback=lambda success, path: self._dispatch(success, path, callback),
            file_filter=self._json_filter(),
            initial_folder=self._default_layouts_dir(),
        )

    def _dispatch(
        self,
        success: bool,
        file_path: str | None,
        callback: Callable[[str], None],
    ) -> None:
        if success and file_path:
            callback(file_path)

    def saved_layouts(self) -> list[Path]:
        try:
            folder = Path(self._default_layouts_dir())
            return sorted((p for p in folder.glob("*.json") if p.is_file()),
                          key=lambda path: path.stem.casefold())
        except OSError as error:
            logger.warning("Cannot list saved layouts: %s", error)
            return []

    def _json_filter(self) -> Gtk.FileFilter:
        json_filter = Gtk.FileFilter()
        json_filter.set_name(_("JSON files"))
        json_filter.add_pattern("*.json")
        return json_filter

    def _default_layouts_dir(self) -> str:
        config_dir = os.getenv("XDG_CONFIG_HOME", GLib.get_user_config_dir())
        layouts_dir = os.path.join(config_dir, "waydroid-helper", "layouts")
        os.makedirs(layouts_dir, exist_ok=True)
        return layouts_dir
