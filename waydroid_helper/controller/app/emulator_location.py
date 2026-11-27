"""Virtual GPS for one emulator instance, independent of the map window."""

import asyncio
import math
import re
from dataclasses import astuple, dataclass
from gettext import gettext as _

from gi.repository import GLib

from waydroid_helper import gnss_install
from waydroid_helper.controller.app.emulator_display import device_command
from waydroid_helper.waydroid_instance import waydroid_output


@dataclass(frozen=True)
class Place:
    name: str
    latitude: float
    longitude: float
    altitude: float = 0
    speed: float = 0
    bearing: float = 0

    def __post_init__(self):
        if not (all(math.isfinite(v) for v in self.coordinates)
                and -90 <= self.latitude <= 90 and -180 <= self.longitude <= 180
                and self.speed >= 0 and 0 <= self.bearing < 360):
            raise ValueError(_("Invalid GPS coordinates."))

    @property
    def coordinates(self):
        return self.latitude, self.longitude, self.altitude, self.speed, self.bearing

    def gps_property(self):
        lat, lon, alt, speed, bearing = self.coordinates
        return f"Fix,gps,{lat:.7f},{lon:.7f},{alt:.2f},{speed:.2f},5.0,{bearing:.2f},0,1.0,90.0,0"


def coordinate_pair(text):
    parts = text.replace("，", ",").split(",")
    if len(parts) != 2:
        return None
    try:
        lat, lon = map(float, parts)
    except ValueError:
        return None  # A comma can also separate a street address and city.
    return Place("", lat, lon)


# The property belongs to the optional Waydroid GNSS implementation. Android
# accepts arbitrary persist.* keys even if no service consumes them. Check the
# registered HAL and its implementation before writing any location.
_PROPERTY = "persist.waydroid.fake_gps"
_CHECK_HAL = (
    f"driver=/vendor/{gnss_install.SERVICE}; "
    "if service check android.hardware.gnss.IGnss/default | grep -q ': found'; then "
    "if strings $driver 2>/dev/null | grep -qxF persist.waydroid.fake_gps; then sha256sum $driver; "
    "else echo other; fi; "
    "elif [ -x $driver ]; then echo inactive; else echo no; fi"
)


class VirtualLocation:
    def __init__(self, instance, settings):
        self.instance = instance
        self.settings = settings
        self.serial = None
        self._native = None
        self.needs_driver_update = False
        self.attached = asyncio.Event()
        self._lock = asyncio.Lock()

    @property
    def history(self):
        return [Place(*row) for row in self.settings.get_value("emulator-location-history").unpack()]

    @property
    def enabled(self):
        return self.settings.get_boolean("emulator-location-enabled")

    async def attach(self, serial):
        async with self._lock:
            self.serial = serial
            self._native = None
            self.needs_driver_update = False
            self.attached.set()
            if self.enabled and self.history:
                await self._apply(self.history[0])

    async def detach(self):
        async with self._lock:
            self.serial = None
            self._native = None
            self.needs_driver_update = False
            self.attached.clear()

    async def set(self, place):
        async with self._lock:
            await self._apply(place)
            history = [p for p in self.history if p.coordinates[:2] != place.coordinates[:2]]
            rows = [astuple(p) for p in [place, *history[:19]]]
            self.settings.set_value("emulator-location-history", GLib.Variant("a(sddddd)", rows))
            self.settings.set_boolean("emulator-location-enabled", True)

    async def clear(self):
        async with self._lock:
            if await self.has_driver():
                await self._write_property("")
            self.settings.set_boolean("emulator-location-enabled", False)

    async def has_driver(self):
        if self.serial is None:
            raise RuntimeError(_("Start Android to set a virtual location."))
        if not self._native:
            result = await device_command(self.serial, "shell", _CHECK_HAL)
            if result.strip() == b"other":
                raise RuntimeError(_("This device already uses a different GNSS driver."))
            if result.strip() == b"inactive":
                raise RuntimeError(_("The GNSS driver did not start on this device."))
            digest = result.decode().split()
            if result.strip() == b"no":
                self._native = False
                return False
            if not digest or not re.fullmatch(r"[0-9a-f]{64}", digest[0]):
                raise RuntimeError(_("Could not check the GNSS driver."))
            self.needs_driver_update = digest[0] in gnss_install.LEGACY_SERVICES.values()
            self._native = True
        return self._native

    async def _write_property(self, value):
        await waydroid_output("prop", "set", _PROPERTY, value, instance=self.instance)
        if (await device_command(self.serial, "shell", "getprop", _PROPERTY)).decode().strip() != value:
            raise RuntimeError(_("Android did not save the virtual location."))

    async def _apply(self, place):
        if not await self.has_driver():
            raise RuntimeError(_("Open Virtual location to install the GNSS driver for this device."))
        if (await device_command(self.serial, "shell", "cmd", "location", "is-location-enabled")).strip() != b"true":
            raise RuntimeError(_("Turn on Location in Android settings first."))
        await self._write_property(place.gps_property())
