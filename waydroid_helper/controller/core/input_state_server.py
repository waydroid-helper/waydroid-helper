#!/usr/bin/env python3
"""Socket server for Android editable-focus state reports."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from waydroid_helper.controller.core.event_bus import Event, EventBus, EventType
from waydroid_helper.controller.core.input_state import AndroidInputState
from waydroid_helper.util.log import logger

ANDROID_INPUT_STATE_PORT = 27123
ANDROID_INPUT_STATE_MESSAGE_TYPE = "text_input_state"


class AndroidInputStateServer:
    """Receives newline-delimited JSON reports from the Android companion app."""

    def __init__(
        self,
        event_bus: EventBus,
        host: str = "0.0.0.0",
        port: int = ANDROID_INPUT_STATE_PORT,
    ) -> None:
        self.event_bus = event_bus
        self.host = host
        self.port = port
        self.server: asyncio.Server | None = None
        self.started_event = asyncio.Event()
        self.server_task: asyncio.Task[None] = asyncio.create_task(self.start_server())

    async def start_server(self) -> None:
        try:
            self.server = await asyncio.start_server(self._handle_client, self.host, self.port)
            addrs = ", ".join(str(sock.getsockname()) for sock in self.server.sockets)
            logger.info("Android input-state server listening on %s", addrs)
            self.started_event.set()
            async with self.server:
                await self.server.serve_forever()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Failed to start Android input-state server")
            self.started_event.set()

    async def wait_started(self) -> None:
        await self.started_event.wait()

    async def close(self) -> None:
        if not self.server:
            return

        self.server.close()
        await self.server.wait_closed()
        if not self.server_task.done():
            self.server_task.cancel()
            try:
                await self.server_task
            except asyncio.CancelledError:
                pass
        logger.info("Android input-state server closed")

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        addr = writer.get_extra_info("peername")
        logger.info("Android input-state reporter connected from %r", addr)
        last_state: AndroidInputState | None = None
        try:
            while line := await reader.readline():
                state = self._decode_state(line)
                if state is None:
                    continue
                logger.info(
                    "Android input state: active=%s reason=%s package=%s class=%s",
                    state.is_input_active,
                    state.reason,
                    state.package_name,
                    state.class_name,
                )
                last_state = state
                self.event_bus.emit(
                    Event(EventType.ANDROID_INPUT_STATE_CHANGED, self, state)
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Android input-state client failed")
        finally:
            if last_state and last_state.is_input_active:
                self.event_bus.emit(
                    Event(
                        EventType.ANDROID_INPUT_STATE_CHANGED,
                        self,
                        AndroidInputState(
                            is_input_active=False,
                            reason="reporter-disconnected",
                        ),
                    )
                )
            writer.close()
            await writer.wait_closed()
            logger.info("Android input-state reporter disconnected from %r", addr)

    def _decode_state(self, line: bytes) -> AndroidInputState | None:
        try:
            payload = json.loads(line.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            logger.warning("Ignore malformed Android input-state report: %r", line[:160])
            return None

        if not isinstance(payload, dict):
            logger.warning("Ignore non-object Android input-state report: %r", payload)
            return None

        message_type = payload.get("type")
        if message_type is not None and message_type != ANDROID_INPUT_STATE_MESSAGE_TYPE:
            logger.warning("Ignore unknown Android input-state message type: %r", payload)
            return None

        active_value = (
            payload.get("active")
            if "active" in payload
            else payload.get("inputActive")
        )
        if active_value is None:
            logger.warning("Ignore Android input-state report without active flag: %r", payload)
            return None
        if not isinstance(active_value, (bool, str, int)):
            logger.warning(
                "Ignore Android input-state report with invalid active flag: %r",
                payload,
            )
            return None

        return AndroidInputState(
            is_input_active=self._as_bool(active_value),
            reason=self._as_str(payload.get("reason")),
            package_name=self._as_str(payload.get("packageName")),
            class_name=self._as_str(payload.get("className")),
        )

    def _as_bool(self, value: Any) -> bool:
        if isinstance(value, bool):
            return value
        if isinstance(value, str):
            return value.lower() in {"1", "true", "yes", "active"}
        return bool(value)

    def _as_str(self, value: Any) -> str:
        return value if isinstance(value, str) else ""
