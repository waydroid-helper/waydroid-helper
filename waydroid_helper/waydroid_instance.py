"""Commands and local preferences for a single Waydroid instance."""

import asyncio
import os
import re
from gettext import gettext as _


DEFAULT_INSTANCE = "default"
SCHEMA = "com.jaoushingan.WaydroidHelper"


def instance_name(value):
    # Match Waydroid's CLI grammar. This identifier also goes into the
    # preferences path, profile directory and D-Bus application ID.
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,31}", value):
        raise ValueError(_("Use 1–32 lowercase letters, digits or hyphens, starting with a letter."))
    return value


def waydroid_command(*arguments, instance=DEFAULT_INSTANCE):
    name = instance_name(instance)
    options = () if name == DEFAULT_INSTANCE else ("--instance", name)
    return ("waydroid", *options, *arguments)


async def waydroid_output(*arguments, instance=DEFAULT_INSTANCE):
    process = await asyncio.create_subprocess_exec(
        *waydroid_command(*arguments, instance=instance),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env={**os.environ, "LC_ALL": "C"},
    )
    try:
        out, err = await asyncio.wait_for(process.communicate(), 20)
        if process.returncode:
            raise RuntimeError(err.decode(errors="replace").strip() or out.decode(errors="replace").strip()
                               or f"waydroid {arguments[0]} ({process.returncode})")
        return out.decode(errors="replace").strip()
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


def _settings(schema, instance):
    from gi.repository import Gio

    name = instance_name(instance)
    return Gio.Settings.new_with_path(schema, f"/com/jaoushingan/WaydroidHelper/instances/{name}/")


def emulator_settings(instance=DEFAULT_INSTANCE):
    if instance == DEFAULT_INSTANCE:
        # Keep the original key paths for the default device, including any
        # preferences written by versions which supported only one device.
        from gi.repository import Gio

        return Gio.Settings.new(SCHEMA)
    return _settings(f"{SCHEMA}.Emulator", instance)


def device_metadata(instance):
    return _settings(f"{SCHEMA}.Instance", instance)
