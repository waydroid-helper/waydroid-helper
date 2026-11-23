import asyncio
from unittest.mock import AsyncMock, Mock

import httpx
import pytest

from waydroid_helper.controller.app import desktop_ime_setup as setup


def test_corrupt_download_never_reaches_package_manager(monkeypatch):
    monkeypatch.setattr(setup, "installed_release", AsyncMock(return_value=False))
    adb = AsyncMock()
    monkeypatch.setattr(setup, "device_command", adb)
    transport = httpx.MockTransport(lambda _request: httpx.Response(200, content=b"partial APK"))
    client = httpx.AsyncClient(transport=transport)
    monkeypatch.setattr(httpx, "AsyncClient", lambda **_options: client)

    with pytest.raises(ValueError, match="integrity"):
        asyncio.run(setup.install_release("serial", "0"))
    adb.assert_not_awaited()


def test_setup_waits_for_guest_ack_before_remembering_consent(monkeypatch):
    monkeypatch.setattr(setup, "install_release", AsyncMock())
    monkeypatch.setattr(setup, "_android_user", AsyncMock(return_value="10"))

    async def run():
        attached, accepted = asyncio.Event(), asyncio.Event()

        async def serve(serial, user, package, connected, *, legacy):
            assert (serial, user, package, legacy) == ("serial", "10", setup.PACKAGE, False)
            attached.set()
            await accepted.wait()
            connected()
            await asyncio.Event().wait()

        window, bridge = Mock(), Mock()
        bridge.serve = serve
        manager = setup.DesktopImeSetup(window, bridge)
        manager.serial = "serial"
        task = asyncio.create_task(manager._enable(install=True))
        try:
            await asyncio.wait_for(attached.wait(), 2)
            window.preferences.set_boolean.assert_not_called()
            accepted.set()
            await asyncio.wait_for(task, 2)
            window.preferences.set_boolean.assert_called_once_with(setup.PREFERENCE, True)
        finally:
            await manager.detach()

    asyncio.run(run())
