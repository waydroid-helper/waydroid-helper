#!/usr/bin/env python3
"""Layout serialization and restoration for controller widgets."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable, Iterable

from waydroid_helper.controller.app.widget_layout_key_codec import (
    WidgetLayoutKeyCodec,
)
from waydroid_helper.controller.core.runtime import ControllerRuntimeContext
from waydroid_helper.controller.widgets.base import BaseWidget
from waydroid_helper.util.log import logger

if TYPE_CHECKING:
    from waydroid_helper.controller.widgets.factory import WidgetFactory


class WidgetLayoutService:
    """Owns layout file shape so menu code stays UI-only."""

    def __init__(self, runtime_context: ControllerRuntimeContext) -> None:
        self.runtime_context = runtime_context
        self._key_codec = WidgetLayoutKeyCodec(runtime_context.key_registry)

    def save_layout(self, file_path: str, widgets: Iterable[BaseWidget]) -> None:
        try:
            layout_data = self.serialize_layout(widgets)
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(layout_data, f, indent=2, ensure_ascii=False)
        except Exception:
            logger.exception("Failed to save layout to %s", file_path)

    def serialize_layout(self, widgets: Iterable[BaseWidget]) -> dict[str, Any]:
        screen_width, screen_height = (
            self.runtime_context.screen_geometry.get_host_resolution()
        )
        return {
            "version": BaseWidget.WIDGET_VERSION,
            "screen_resolution": {"width": screen_width, "height": screen_height},
            "widgets": [self._serialize_widget(widget) for widget in widgets],
            "created_at": str(Path().absolute()),
        }

    def _serialize_widget(self, widget: BaseWidget) -> dict[str, Any]:
        widget_type = type(widget).__name__.lower()
        widget_data: dict[str, Any] = {
            "type": widget_type,
            "x": float(widget.x),
            "y": float(widget.y),
            "width": float(widget.width),
            "height": float(widget.height),
        }

        if widget.text:
            widget_data["text"] = str(widget.text)

        widget_data.update(self._key_codec.serialize_widget_keys(widget_type, widget))

        config_manager = widget.get_config_manager()
        if config_manager.configs:
            widget_data["config"] = config_manager.serialize()

        return widget_data

    def load_layout(
        self,
        file_path: str,
        widget_factory: "WidgetFactory",
        clear_widgets: Callable[[], None],
        create_widget_at_position: Callable[[BaseWidget, int, int], None],
    ) -> int:
        try:
            layout_data = self._read_layout(file_path)
            if layout_data is None:
                return 0

            if layout_data.get("version") != BaseWidget.WIDGET_VERSION:
                logger.warning(
                    "Layout file version mismatch: %s != %s",
                    layout_data.get("version"),
                    BaseWidget.WIDGET_VERSION,
                )

            scale_x, scale_y = self._calculate_scale(layout_data)
            clear_widgets()
            return self._create_widgets(
                layout_data,
                widget_factory,
                create_widget_at_position,
                scale_x,
                scale_y,
            )
        except Exception:
            logger.exception("Failed to load layout from %s", file_path)
            return 0

    def _read_layout(self, file_path: str) -> dict[str, Any] | None:
        path = Path(file_path)
        if not path.exists():
            logger.error("Layout file does not exist: %s", file_path)
            return None

        with open(path, "r", encoding="utf-8") as f:
            layout_data = json.load(f)

        if "widgets" not in layout_data:
            logger.error("Invalid layout file format: missing widgets")
            return None

        return layout_data

    def _calculate_scale(self, layout_data: dict[str, Any]) -> tuple[float, float]:
        current_width, current_height = (
            self.runtime_context.screen_geometry.get_host_resolution()
        )
        saved_resolution = layout_data.get("screen_resolution") or {}
        saved_width = saved_resolution.get("width") or current_width or 1
        saved_height = saved_resolution.get("height") or current_height or 1
        return current_width / saved_width, current_height / saved_height

    def _create_widgets(
        self,
        layout_data: dict[str, Any],
        widget_factory: "WidgetFactory",
        create_widget_at_position: Callable[[BaseWidget, int, int], None],
        scale_x: float,
        scale_y: float,
    ) -> int:
        widgets_created = 0
        for widget_data in layout_data["widgets"]:
            try:
                widget = self._create_widget(
                    widget_data,
                    widget_factory,
                    scale_x,
                    scale_y,
                )
                if widget is None:
                    continue

                x = int(widget_data.get("x", 0) * scale_x)
                y = int(widget_data.get("y", 0) * scale_y)
                create_widget_at_position(widget, x, y)

                if "config" in widget_data:
                    widget.get_config_manager().deserialize(widget_data["config"])

                widgets_created += 1
            except Exception:
                logger.exception("Failed to create widget from layout: %r", widget_data)

        return widgets_created

    def _create_widget(
        self,
        widget_data: dict[str, Any],
        widget_factory: "WidgetFactory",
        scale_x: float,
        scale_y: float,
    ) -> BaseWidget | None:
        widget_type = widget_data.get("type", "")
        width = int(widget_data.get("width", 100) * scale_x)
        height = int(widget_data.get("height", 100) * scale_y)
        create_kwargs: dict[str, Any] = {
            "width": width,
            "height": height,
            "text": widget_data.get("text", ""),
        }

        self._key_codec.apply_widget_keys_to_create_kwargs(
            widget_type,
            widget_data,
            create_kwargs,
        )
        self._scale_macro_command(widget_type, widget_data, scale_x, scale_y)
        return widget_factory.create_widget(widget_type, **create_kwargs)

    def _scale_macro_command(
        self,
        widget_type: str,
        widget_data: dict[str, Any],
        scale_x: float,
        scale_y: float,
    ) -> None:
        if widget_type != "macro" or scale_x == 1.0 and scale_y == 1.0:
            return

        config = widget_data.get("config")
        if not isinstance(config, dict) or "macro_command" not in config:
            return

        macro_cfg = config["macro_command"]
        value = macro_cfg.get("value")
        if not isinstance(value, str):
            return

        def _scale_coords(match: re.Match) -> str:
            x_str, y_str = match.group(1), match.group(2)
            try:
                x = float(x_str)
                y = float(y_str)
            except ValueError:
                return match.group(0)
            return f"{int(x * scale_x)},{int(y * scale_y)}"

        macro_cfg["value"] = re.sub(r"(\d+)\s*,\s*(\d+)", _scale_coords, value)
