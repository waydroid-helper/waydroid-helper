import asyncio
from unittest.mock import AsyncMock, Mock

import pytest

from waydroid_helper.controller.app import embedded_session


def test_running_foreign_session_is_never_started_or_stopped(monkeypatch):
    session = embedded_session.EmbeddedSession()
    status = AsyncMock(return_value={"Session": "RUNNING", "Wayland display": "wayland-0"})
    command = AsyncMock()
    monkeypatch.setattr(embedded_session, "session_status", status)
    monkeypatch.setattr(embedded_session, "waydroid_output", command)
    with pytest.raises(RuntimeError):
        asyncio.run(session.start())

    # The user can switch sessions independently while our window is still
    # open. Releasing the old launcher must never stop the new display.
    session.launcher = Mock(returncode=0, wait=AsyncMock())
    asyncio.run(session.close())
    command.assert_not_awaited()


def test_close_stops_the_session_on_its_own_socket(monkeypatch):
    session = embedded_session.EmbeddedSession()
    session.launcher = Mock(returncode=0, wait=AsyncMock())
    monkeypatch.setattr(
        embedded_session,
        "session_status",
        AsyncMock(return_value={"Wayland display": session.socket}),
    )
    command = AsyncMock()
    monkeypatch.setattr(embedded_session, "waydroid_output", command)
    asyncio.run(session.close())
    command.assert_awaited_once_with("session", "stop")


def test_changed_display_after_confirmation_cannot_stop_another_session(monkeypatch):
    monkeypatch.setattr(
        embedded_session,
        "session_status",
        AsyncMock(return_value={"Session": "RUNNING", "Wayland display": "wayland-2"}),
    )
    command = AsyncMock()
    monkeypatch.setattr(embedded_session, "waydroid_output", command)
    with pytest.raises(RuntimeError):
        asyncio.run(embedded_session.stop_confirmed_session("wayland-0"))
    command.assert_not_awaited()
