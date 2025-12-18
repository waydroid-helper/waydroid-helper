import ctypes
import ctypes.util
import logging
import os
import select
import signal
import struct
import sys
import threading
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



class Monitor:
    def __init__(self, filename: str = "/var/lib/waydroid/waydroid.log") -> None:
        self.filename: str = filename
        self.inotify_fd: int = -1
        self.file_fd: int = -1
        self.watch_fd: int = -1
        self.libc: ctypes.CDLL = ctypes.CDLL(ctypes.util.find_library("c"))
        self.running: bool = True
        self.pipe_r: int
        self.pipe_w: int
        self.pipe_r, self.pipe_w = os.pipe()
        self.current_state: str = ""
        self.current_user_id: str = ""
        self.monitor_thread = None
        self.stop_thread_event = threading.Event()
        self.system_bus = dbus.SystemBus()
        self.mount_object = self.system_bus.get_object("id.waydro.Mount", "/org/waydro/Mount")
        self.mount_interface = dbus.Interface(self.mount_object, "id.waydro.Mount")

    def get_mount_pairs_for_user(self, user_id: str):
        if not user_id:
            return []
        sources = os.environ.get("SOURCE", "").split(":")
        targets = os.environ.get("TARGET", "").split(":")
        pairs = []
        for source, target in zip(sources, targets):
            if source != "" and target != "" and os.path.basename(os.path.dirname(target)) == user_id:
                pairs.append((source, target))
        return pairs

    def unmount_for_user(self, user_id: str):
        try:
            pairs = self.get_mount_pairs_for_user(user_id)
            for source, target in pairs:
                logging.info(f"Unmounting {target} for user {user_id}")
                result = self.mount_interface.Unmount(target)
                if int(result["returncode"]) == 0:
                    logging.info(f"unmount {target} succeeded")
                else:
                    logging.error(f"unmount {target} failed {result['stderr']}")
        except Exception as e:
            logging.error(f"Unmount error: {e}")

    def mount_for_user(self, user_id: str):
        try:
            pairs = self.get_mount_pairs_for_user(user_id)
            uid = os.getuid()
            gid = os.getgid()
            for source, target in pairs:
                logging.info(f"Mounting {source} to {target} for user {user_id}")
                result = self.mount_interface.BindMount(source, target, dbus.UInt32(uid), dbus.UInt32(gid))
                if int(result["returncode"]) == 0:
                    logging.info(f"mount {source} to {target} succeeded")
                else:
                    logging.error(f"mount {source} to {target} failed {result['stderr']}")
        except Exception as e:
            logging.error(f"Mount error: {e}")

    def get_current_user_via_dbus(self):
        try:
            result = self.mount_interface.GetCurrentUser()
            if result and result.strip():
                return str(result).strip()
            return None
        except Exception as e:
            logging.error(f"Failed to get current user via dbus: {e}")
            return None

    def user_monitor_thread(self):
        logging.info("User monitor thread started")
        while not self.stop_thread_event.is_set():
            try:
                user_id = self.get_current_user_via_dbus()
                if user_id and user_id != self.current_user_id:
                    logging.info(f"User ID changed from '{self.current_user_id}' to '{user_id}'")
                    if self.current_user_id:
                        self.unmount_for_user(self.current_user_id)
                    self.current_user_id = user_id
                    self.unmount_for_user(user_id)
                    self.mount_for_user(user_id)
            except Exception as e:
                logging.error(f"Error in user monitor thread: {e}")
            self.stop_thread_event.wait(1)
        
        logging.info("User monitor thread stopped")

    def stop_monitor_thread(self):
        if self.monitor_thread and self.monitor_thread.is_alive():
            logging.info("Stopping user monitor thread...")
            self.stop_thread_event.set()
            self.monitor_thread.join(timeout=3)
            if self.monitor_thread.is_alive():
                logging.warning("User monitor thread did not stop in time")
            else:
                logging.info("User monitor thread stopped successfully")
        if self.current_user_id:
            logging.info(f"Unmounting directories for user {self.current_user_id}")
            self.unmount_for_user(self.current_user_id)
            self.current_user_id = ""
        self.monitor_thread = None
        self.stop_thread_event.clear()

    def start_monitor_thread(self):
        self.stop_monitor_thread()
        self.current_user_id = ""
        self.stop_thread_event.clear()
        self.monitor_thread = threading.Thread(target=self.user_monitor_thread, daemon=True)
        self.monitor_thread.start()
        logging.info("User monitor thread started")

    def check_new_content(self):
        leftover = ""
        while True:
            data = os.read(self.file_fd, 4096)
            if not data:
                break
            content = leftover + data.decode("utf-8", errors="ignore")
            lines = content.split("\n")
            leftover = lines[-1]
            for line in lines[:-1]:
                if "STOPPED" in line:
                    if self.current_state != "STOPPED":
                        logging.info("Status changed to STOPPED")
                        self.current_state = "STOPPED"
                        self.stop_monitor_thread()
                elif "RUNNING" in line:
                    if self.current_state != "RUNNING":
                        logging.info("Status changed to RUNNING")
                        self.current_state = "RUNNING"
                        self.start_monitor_thread()

    def cleanup(self, signum: int | IntEnum, frame: FrameType | None):
        self.running = False
        self.stop_monitor_thread()
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
                ready, _, _ = select.select([self.inotify_fd, self.pipe_r], [], [], 1.0)
                if not self.running:
                    break
                if ready:
                    for fd in ready:
                        if fd == self.inotify_fd:
                            event_data = os.read(self.inotify_fd, EVENT_SIZE + 16)
                            event = InotifyEvent.from_buffer_copy(event_data[:EVENT_SIZE])
                            if event.mask & IN_MODIFY:
                                self.check_new_content()
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
