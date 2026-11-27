import asyncio
from unittest.mock import AsyncMock

import pytest
from gi.repository import GLib

from waydroid_helper.controller.app import emulator_location as gps
from waydroid_helper.controller.app.emulator_location import coordinate_pair


class Preferences(dict):
    def get_value(self, key):
        return self.get(key, GLib.Variant("a(sddddd)", []))

    def get_boolean(self, key):
        return self.get(key, False)

    set_value = set_boolean = dict.__setitem__


def test_wgs84_boundaries_and_gnss_wire_format():
    assert coordinate_pair("London, UK") is None
    assert coordinate_pair("-90，180").coordinates[:2] == (-90, 180)
    assert gps.Place("", 90, -180, -2, 0, 359.5).gps_property() == (
        "Fix,gps,90.0000000,-180.0000000,-2.00,0.00,5.0,359.50,0,1.0,90.0,0"
    )
    for text in ("nan,0", "90.1,0", "0,-181", "0,inf"):
        with pytest.raises(ValueError):
            coordinate_pair(text)


def test_active_location_and_history_are_per_instance_and_restored(monkeypatch):
    sessions = {}
    serials = {"a": "192.0.2.1:5555", "b": "192.0.2.2:5555"}

    async def prop(*args, instance):
        sessions[serials[instance]] = args[-1]

    async def adb(serial, *args):
        assert serial in serials.values()
        if args[-1] == gps._CHECK_HAL:
            return b"f" * 64 + b"  /vendor/bin/hw/android.hardware.gnss-service.example"
        if args[-1] == "is-location-enabled":
            return b"true"
        if args[1] == "getprop":
            return sessions[serial].encode()
        return b""

    monkeypatch.setattr(gps, "waydroid_output", prop)
    monkeypatch.setattr(gps, "device_command", adb)

    async def run():
        a = gps.VirtualLocation("a", Preferences())
        b = gps.VirtualLocation("b", Preferences())
        await a.attach(serials["a"])
        await b.attach(serials["b"])
        original = gps.Place("First", -30, 140)
        updated = gps.Place("Updated", -30, 140, 150, 3, 35)
        other = gps.Place("Second", 37, -122)
        await a.set(original)
        await b.set(other)
        await a.set(updated)
        assert a.history == [updated] and b.history == [other]
        await a.detach()
        a = gps.VirtualLocation("a", a.settings)
        await a.attach(serials["a"])
        assert sessions[serials["a"]] == updated.gps_property()
        await a.clear()
        assert a.history == [updated] and not a.enabled
        assert sessions[serials["a"]] == ""
        assert sessions[serials["b"]] == other.gps_property() and b.enabled
    asyncio.run(run())


def test_guest_rejection_keeps_previous_location_and_history(monkeypatch):
    service = gps.VirtualLocation("default", Preferences())
    service.serial = "test"
    monkeypatch.setattr(service, "_apply", AsyncMock(side_effect=RuntimeError("Location off")))
    with pytest.raises(RuntimeError):
        asyncio.run(service.set(gps.Place("Point", 0, 0)))
    assert not service.enabled and not service.history


def test_missing_hal_never_writes_location_or_enables_mock_provider(monkeypatch):
    service = gps.VirtualLocation("second", Preferences())
    adb = AsyncMock(return_value=b"no")
    prop = AsyncMock()
    monkeypatch.setattr(gps, "device_command", adb)
    monkeypatch.setattr(gps, "waydroid_output", prop)

    async def run():
        await service.attach("second:5555")
        with pytest.raises(RuntimeError, match="GNSS"):
            await service.set(gps.Place("Test", 10, 20))
        assert not service.enabled and not service.history
        service.settings.set_boolean("emulator-location-enabled", True)
        await service.clear()
        assert not service.enabled
    asyncio.run(run())
    prop.assert_not_awaited()
    assert all(call.args == ("second:5555", "shell", gps._CHECK_HAL) for call in adb.await_args_list)


def test_gnss_installer_checks_package_before_writing_and_preserves_conflicts(tmp_path, monkeypatch):
    import hashlib
    import io
    import zipfile
    from waydroid_helper import gnss_install

    stream = io.BytesIO()
    files = {"bin/hw/gnss": b"service", "lib64/dependency.so": b"library", gnss_install.INIT_RC: b"init"}
    with zipfile.ZipFile(stream, "w") as archive:
        for name, data in files.items():
            archive.writestr(name, data)
    package = stream.getvalue()
    monkeypatch.setitem(gnss_install.DIGESTS, "x86_64", hashlib.sha256(package).hexdigest())
    vendor = tmp_path / "overlay/vendor"
    vendor.mkdir(parents=True)
    with pytest.raises(ValueError, match="checksum"):
        gnss_install.install(tmp_path, "x86_64", package + b"corruption")
    assert not list(vendor.iterdir())

    collision = vendor / "lib64/dependency.so"
    collision.parent.mkdir()
    collision.write_bytes(b"other extension")
    with pytest.raises(FileExistsError):
        gnss_install.install(tmp_path, "x86_64", package)
    assert collision.read_bytes() == b"other extension"
    assert not (vendor / gnss_install.INIT_RC).exists() and not (vendor / "bin/hw/gnss").exists()

    collision.unlink()
    gnss_install.install(tmp_path, "x86_64", package)
    gnss_install.install(tmp_path, "x86_64", package)
    assert all((vendor / name).read_bytes() == data for name, data in files.items())
    assert (vendor / "bin/hw/gnss").stat().st_mode & 0o111 == 0o111


def test_legacy_driver_is_usable_until_upgrade_and_rechecked_after_restart(monkeypatch):
    old = gps.gnss_install.LEGACY_SERVICES["x86_64"].encode()
    current = b"f" * 64
    adb = AsyncMock(side_effect=[old, current])
    monkeypatch.setattr(gps, "device_command", adb)
    service = gps.VirtualLocation("default", Preferences())

    async def run():
        await service.attach("test")
        assert await service.has_driver() and service.needs_driver_update
        await service.detach()
        await service.attach("test")
        assert await service.has_driver() and not service.needs_driver_update
    asyncio.run(run())


def test_upgrade_only_replaces_known_service_after_checking_all_files(tmp_path, monkeypatch):
    import hashlib
    import io
    import zipfile
    from waydroid_helper import gnss_install

    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as out:
        out.writestr(gnss_install.SERVICE, b"new")
        out.writestr("lib64/gnss.so", b"unchanged library")
        out.writestr(gnss_install.INIT_RC, b"init")
    package = archive.getvalue()
    monkeypatch.setitem(gnss_install.DIGESTS, "arm64", hashlib.sha256(package).hexdigest())
    monkeypatch.setitem(gnss_install.LEGACY_SERVICES, "arm64", hashlib.sha256(b"old").hexdigest())
    vendor = tmp_path / "overlay/vendor"
    service, init = vendor / gnss_install.SERVICE, vendor / gnss_install.INIT_RC
    service.parent.mkdir(parents=True)
    init.parent.mkdir(parents=True)
    service.write_bytes(b"old")
    service.chmod(0o755)
    dependency = vendor / "lib64/gnss.so"
    dependency.parent.mkdir()
    dependency.write_bytes(b"unchanged library")
    dependency.chmod(0o755)
    init.write_bytes(b"conflict")
    with pytest.raises(FileExistsError):
        gnss_install.install(tmp_path, "arm64", package)
    assert service.read_bytes() == b"old"
    init.write_bytes(b"init")
    gnss_install.install(tmp_path, "arm64", package)
    assert service.read_bytes() == b"new"
    service.write_bytes(b"unknown")
    with pytest.raises(FileExistsError):
        gnss_install.install(tmp_path, "arm64", package)
    assert service.read_bytes() == b"unknown"


def test_denied_gnss_authorization_leaves_instance_running(monkeypatch, tmp_path):
    from unittest.mock import Mock
    from waydroid_helper.controller.app import emulator_location_setup as setup

    auth = tmp_path / "pkexec"
    auth.write_text("#!/bin/sh\nexit 126\n")
    auth.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))
    window, location, show_map = Mock(), Mock(), Mock()
    location.has_driver = AsyncMock(return_value=False)
    location.serial, location.instance = "test:5555", "test"
    provision = setup.LocationSetup(window, location, show_map)
    monkeypatch.setattr(provision, "_confirm", AsyncMock(return_value=True))
    monkeypatch.setattr(setup, "guest_arch", AsyncMock(return_value="x86_64"))
    monkeypatch.setattr(setup, "download", AsyncMock(return_value=b"verified"))
    asyncio.run(provision._open())
    window.restart_now.assert_not_called()
    show_map.assert_not_called()
    assert "authorization" in window.show_notification.call_args.args[0]
