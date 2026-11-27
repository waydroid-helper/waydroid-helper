#!/usr/bin/python3 -I
"""Install a pinned GNSS release into one stopped Waydroid vendor overlay."""

import configparser
import fcntl
import hashlib
import io
import json
import os
from pathlib import Path
import re
import stat
import sys
import tempfile
import zipfile

# Both the UI and this privileged process verify the entire release archive.
RELEASE_VERSION = "0.0.2"
DIGESTS = {
    "x86_64": "add5cdbd8a66c061893b6e1e050c13c2377fc38575cf84a1ee24e3ed2521e291",
    "arm64": "4b59d35e945a2ad98ebb45836e4fd98cc47ca8e2304721e1102040b51c9d2579",
}
SERVICE = "bin/hw/android.hardware.gnss-service.example"
# Only the service changed since 0.0.1. Identify that release by its actual
# executable, including installations made by the older extension manager.
LEGACY_SERVICES = {
    "x86_64": "92d1293d8713ed3a488e966e20516b5a3f03dabe158fa4721a5a5f1ed56e5c26",
    "arm64": "fa4a7e1a4fafad53bece4801610b84e9de5dc4322bf89e761f209f4c8815a025",
}
MAX_BYTES = 2 * 1024 * 1024
INIT_RC = "etc/init/gnss-default.rc"


def verify(package, arch):
    if hashlib.sha256(package).hexdigest() != DIGESTS[arch]:
        raise ValueError("GNSS package checksum mismatch")


def trusted_directory(path):
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.geteuid() or info.st_mode & 0o022:
        raise PermissionError(f"Expected a protected directory at {path}")


def workspace(instance, uid):
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,31}", instance):
        raise ValueError("Invalid Waydroid instance")
    base = Path("/var/lib/waydroid")
    work = base if instance == "default" else base.with_name(f"waydroid.{instance}")
    trusted_directory(work)
    if instance != "default" and json.loads((work / "instance.json").read_bytes())["uid"] != uid:
        raise PermissionError("This Waydroid instance belongs to another user")
    config = configparser.ConfigParser(interpolation=None)
    with (work / "waydroid.cfg").open() as stream:
        config.read_file(stream)
    if not config.getboolean("waydroid", "mount_overlays", fallback=True):
        raise ValueError("Waydroid vendor overlays are disabled")
    trusted_directory(work / "overlay")
    trusted_directory(work / "overlay/vendor")
    return work


def install(work, arch, package):
    verify(package, arch)
    vendor = work / "overlay/vendor"
    # Never modify an active overlayfs lower layer. Lock the vendor directory,
    # not /var/lib/waydroid, which the instance manager locks for shared images.
    lock = os.open(vendor, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if (work / "rootfs/vendor").is_mount():
            raise RuntimeError("Stop this Waydroid instance before installing GNSS")
        with tempfile.TemporaryDirectory(dir=vendor, prefix=".gnss-") as tmp:
            publish(vendor, Path(tmp), package, arch)
    finally:
        os.close(lock)


def publish(vendor, staging, package, arch):
    # Prepare and check all files before publishing. Existing identical files
    # may come from the extension manager or an interrupted install. Never
    # overwrite a different extension. Publish init's entry last so a retry
    # after an interruption can finish an otherwise inactive installation.
    pending = []
    upgrade = None
    with zipfile.ZipFile(io.BytesIO(package)) as archive:
        for member in archive.infolist():
            dest = vendor / member.filename
            for parent in reversed(dest.parents):
                if vendor in parent.parents:
                    parent.mkdir(exist_ok=True, mode=0o755)
                    trusted_directory(parent)
            if member.is_dir():
                continue
            data = archive.read(member)
            mode = 0o755 if member.filename.startswith("bin/") else 0o644
            if dest.is_symlink():
                raise FileExistsError(f"Conflicting GNSS file: {dest}")
            replacing = dest.exists()
            if replacing:
                info = dest.stat()
                # The 0.0.1 extension unpacked its shared libraries as 0755.
                # They can be reused at either historical mode if their bytes
                # match the pinned archive. Keep their existing ownership/mode.
                modes = (0o644, 0o755) if member.filename.startswith("lib64/") else (mode,)
                if (not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid()
                        or stat.S_IMODE(info.st_mode) not in modes):
                    raise FileExistsError(f"Conflicting GNSS file: {dest}")
                previous = dest.read_bytes()
                if previous == data:
                    continue
                if member.filename != SERVICE or hashlib.sha256(previous).hexdigest() != LEGACY_SERVICES[arch]:
                    raise FileExistsError(f"Conflicting GNSS file: {dest}")
            source = staging / member.filename.replace("/", "_")
            source.write_bytes(data)
            source.chmod(mode)
            if replacing:
                upgrade = (source, dest)
            else:
                pending.append((source, dest))

    created = []
    try:
        for src, dst in sorted(pending, key=lambda pair: pair[1] == vendor / INIT_RC):
            os.link(src, dst)
            created.append(dst)
        # Atomically switch a known old service only after all other files
        # have been verified and installed. A failed upgrade is retryable.
        if upgrade:
            os.replace(*upgrade)
    except BaseException:
        for path in reversed(created):
            path.unlink()
        raise


def main(instance, arch):
    if arch not in DIGESTS or os.geteuid() != 0:
        raise PermissionError("An administrator must install the GNSS driver")
    os.umask(0o022)
    uid = int(os.environ["PKEXEC_UID"])
    work = workspace(instance, uid)
    identity = work.stat()
    # pkexec has now completed authorization. A cancelled prompt or a closed
    # Helper leaves Android running. Only a confirmed shutdown supplies bytes.
    print("READY", flush=True)
    package = sys.stdin.buffer.read(MAX_BYTES + 1)
    if package:
        if not os.path.samestat(identity, workspace(instance, uid).stat()):
            raise RuntimeError("Waydroid instance changed")
        install(work, arch, package)


if __name__ == "__main__":
    try:
        main(*sys.argv[1:])
    except Exception as error:
        sys.exit(str(error))
