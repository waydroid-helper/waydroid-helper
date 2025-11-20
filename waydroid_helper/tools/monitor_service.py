import ctypes
import ctypes.util
import logging
import os
import select
import signal
import struct
import sys
import re
from enum import IntEnum
from types import FrameType
from typing import final

import dbus

logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s - %(message)s",
    stream=sys.stdout,
)
IN_MODIFY = 0x00000002
EVENT_SIZE = struct.calcsize("iIII")


@final
class InotifyEvent(ctypes.Structure):
    _fields_ = [
        ("wd", ctypes.c_int),
        ("mask", ctypes.c_uint32),
        ("cookie", ctypes.c_uint32),
        ("len", ctypes.c_uint32),
    ]


def send_dbus_signal(user_id: str):
    system_bus = dbus.SystemBus()
    mount_object = system_bus.get_object( # pyright: ignore[reportUnknownMemberType]
        "id.waydro.Mount", "/org/waydro/Mount"
    )
    mount_interface = dbus.Interface(mount_object, "id.waydro.Mount")
    try:
        sources = os.environ.get("SOURCE", "").split(":")
        targets = os.environ.get("TARGET", "").split(":")
        uid = os.getuid()
        gid = os.getgid()
        for source, target in zip(sources, targets):
            logging.info(f"source: {source}, target: {target}")
            if source != "" and target != "" and  os.path.basename(os.path.dirname(target)) == user_id:
                mount_interface.Unmount(target)  # pyright: ignore[reportUnknownMemberType]
                result = mount_interface.BindMount(
                    source,
                    target,
                    dbus.UInt32(uid),
                    dbus.UInt32(gid),
                ) # pyright: ignore[reportUnknownMemberType,reportUnknownVariableType]
                if int(result["returncode"]) == 0: # pyright: ignore[reportUnknownArgumentType]
                    logging.info(f"mount {source} to {target} succeeded")
                else:
                    logging.error(
                        f"mount {source} to {target} failed {result['stderr']}",
                    )
    except Exception as e:
        logging.error(f"Mount error: {e}")


def check_new_content(fd: int):
    leftover = ""

    while True:
        data = os.read(fd, 4096)
        if not data:
            break

        content = leftover + data.decode("utf-8", errors="ignore")
        lines = content.split("\n")

        leftover = lines[-1]

        for line in lines[:-1]:
            user_id = re.search(r"Android with user (\d+) is ready", line)
            if user_id:
                logging.info(f"user_id: {user_id.group(1)}")
                user_id = user_id.group(1)
                send_dbus_signal(user_id)



class Monitor:
    def __init__(self, filename: str = "/var/lib/waydroid/waydroid.log") -> None:
        self.filename: str = filename
        self.inotify_fd: int = -1
        self.file_fd: int = -1
        self.watch_fd: int = -1
        self.libc: ctypes.CDLL = ctypes.CDLL(ctypes.util.find_library("c"))
        self.running: bool = True
        # Create pipe to interrupt select
        self.pipe_r: int
        self.pipe_w: int
        self.pipe_r, self.pipe_w = os.pipe()

    def cleanup(self, signum: int | IntEnum, frame: FrameType | None):
        self.running = False
        # 向管道写入数据以中断 select
        try:
            os.write(self.pipe_w, b"x")
        except:
            pass

    def final_cleanup(self):
        if self.watch_fd >= 0 and self.inotify_fd >= 0:
            try:
                self.libc.inotify_rm_watch(self.inotify_fd, self.watch_fd)
            except:
                pass

        for fd in [self.inotify_fd, self.file_fd, self.pipe_r, self.pipe_w]:
            if fd >= 0:
                try:
                    os.close(fd)
                except:
                    pass

        logging.info("Cleanup completed")
        sys.exit(0)

    def start(self):
        signal.signal(signal.SIGTERM, self.cleanup)
        signal.signal(signal.SIGINT, self.cleanup)

        self.inotify_fd = self.libc.inotify_init()
        if self.inotify_fd < 0:
            logging.error("inotify_init failed")
            return 1

        try:
            self.file_fd = os.open(self.filename, os.O_RDONLY)
        except OSError as e:
            logging.error(f"failed to open file: {e}")
            return 1

        os.lseek(self.file_fd, 0, os.SEEK_END)

        self.watch_fd = self.libc.inotify_add_watch(
            self.inotify_fd, self.filename.encode(), IN_MODIFY
        )
        if self.watch_fd < 0:
            logging.error("inotify_add_watch failed")
            return 1

        logging.info(f"Start monitoring file: {self.filename}")

        try:
            while self.running:
                # wait
                ready, _, _ = select.select([self.inotify_fd, self.pipe_r], [], [], 1.0)
                if not self.running:
                    break
                if ready:
                    for fd in ready: # pyright: ignore[reportAny]
                        if fd == self.inotify_fd:
                            event_data = os.read(self.inotify_fd, EVENT_SIZE + 16)
                            event = InotifyEvent.from_buffer_copy(
                                event_data[:EVENT_SIZE]
                            )

                            if event.mask & IN_MODIFY:  # pyright: ignore[reportAny]
                                check_new_content(self.file_fd)
                        elif fd == self.pipe_r:
                            os.read(self.pipe_r, 1)
                            break

        except Exception as e:
            logging.error(f"Monitoring error: {e}")
        finally:
            self.final_cleanup()


def start():
    monitor = Monitor()
    monitor.start()
