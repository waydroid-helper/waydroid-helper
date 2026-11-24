# -*- mode: python ; coding: utf-8 -*-

from argparse import ArgumentParser
from platform import system

parser = ArgumentParser()
parser.add_argument("--binary", action="store_true")
options = parser.parse_args()

a = Analysis(
    ["waydroid-helper"],
    binaries=[
        ('usr/bin/fakeroot-real', 'bin'),
        ('usr/bin/fakeroot', 'bin'),
        ('usr/bin/faked', 'bin'),
        ('usr/lib/libfakeroot', 'lib/libfakeroot'),
        ('usr/bin/waydroid-cli', 'bin'),
        ('usr/bin/adb', 'bin')
    ],
    pathex=["usr/share/waydroid-helper"],
    datas=[
        ("LICENSE", "."),
        ("usr/share/glib-2.0", "share/glib-2.0"),
        ("usr/share/icons", "share/icons"),
        ("usr/share/locale", "share/locale"),
        ("usr/share/polkit-1", "share/polkit-1"),
        ("usr/share/dbus-1", "share/dbus-1"),
        ("usr/lib/systemd", "lib/systemd"),
        ("usr/share/waydroid-helper/data", "share/waydroid-helper/data"),
        ("usr/share/waydroid-helper/waydroid-helper.gresource", "share/waydroid-helper/"),
        ("usr/share/waydroid-helper/waydroid_helper/controller/third_party/scrcpy-server", "share/waydroid-helper/waydroid_helper/controller/third_party/"),
    ],
    hiddenimports=[ 'gi' ],
    hookspath=['hooks'],
    hooksconfig={
        "gi": {
            "icons": ["Adwaita"],
            "themes": ["Adwaita"],
            "module-versions": {"Gtk": "4.0", "Rsvg": "2.0"},
        }
    },
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

if system() == "Linux":
    if not options.binary:
        exe = EXE(
            pyz,
            a.scripts,
            [],
            exclude_binaries=True,
            name="waydroid-helper",
            debug=False,
            bootloader_ignore_signals=False,
            strip=False,
            upx=True,
            console=False,
            disable_windowed_traceback=False,
            argv_emulation=False,
            target_arch=None,
            codesign_identity=None,
            entitlements_file=None,
            contents_directory='usr',
        )
        coll = COLLECT(
            exe,
            a.binaries,
            a.datas,
            strip=False,
            upx=True,
            upx_exclude=[],
            name="waydroid-helper",
        )
    else:
        exe = EXE(
            pyz,
            a.scripts,
            a.binaries,
            a.datas,
            [],
            name="waydroid-helper",
            debug=False,
            bootloader_ignore_signals=False,
            strip=False,
            upx=True,
            upx_exclude=[],
            runtime_tmpdir=None,
            console=False,
            disable_windowed_traceback=False,
            argv_emulation=False,
            target_arch=None,
            codesign_identity=None,
            entitlements_file=None,
            contents_directory='usr',
        )
