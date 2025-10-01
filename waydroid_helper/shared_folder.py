import asyncio
import os
import re
import dbus
from enum import IntEnum

import aiofiles
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
from gettext import gettext as _

from gi.repository import Adw, Gio, GObject, Gtk

from waydroid_helper.compat_widget import SharedFolderDialog, MessageDialog
from waydroid_helper.util import SubprocessManager, logger


class SharedFolder(GObject.Object):
    def __init__(self, source: str, target: str):
        super().__init__()
        self.source: str = source
        self.target: str = target


class SharedFolderRow(Adw.ActionRow):
    __gsignals__ = {  # pyright: ignore[reportUnannotatedClassAttribute]
        "removed": (GObject.SignalFlags.RUN_FIRST, None, (SharedFolder,))
    }

    def __init__(self, folder: SharedFolder):
        super().__init__()

        self.folder: SharedFolder = folder
        self.set_title(folder.source)
        self.set_subtitle(folder.target)

        button = Gtk.Button(icon_name="user-trash-symbolic")
        button.add_css_class("flat")
        button.connect("clicked", self._on_delete_button_clicked)
        self.add_suffix(button)

    def _on_delete_button_clicked(self, button: Gtk.Button):
        self.emit("removed", self.folder)


class SharedFoldersState(IntEnum):
    UNINITIALIZED = 0
    INITIALIZED = 1


class SharedFoldersWidget(Adw.PreferencesGroup):
    __gtype_name__: str = "SharedFoldersWidget"
    __gsignals__ = {  # pyright: ignore[reportUnannotatedClassAttribute]
        "updated": (GObject.SignalFlags.RUN_FIRST, None, ())
    }

    def __init__(self):
        super().__init__()
        self.state: SharedFoldersState = SharedFoldersState.UNINITIALIZED
        self.set_title(_("Shared Folders"))
        self.listbox: Gtk.ListBox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.listbox.add_css_class("boxed-list")
        self.add(self.listbox)

        self.add_button: Gtk.Button = Gtk.Button()
        self.add_button.set_icon_name("list-add-symbolic")
        self.add_button.add_css_class("flat")
        self.add_button.connect("clicked", self._on_add_button_clicked)

        self.list_store: Gio.ListStore = Gio.ListStore.new(SharedFolder) # pyright: ignore[reportUnknownMemberType]   
        self.list_store.connect("items-changed", self._on_list_updated)

        self.listbox.bind_model(self.list_store, self._create_shared_folder_row)

        self.listbox.append(self.add_button)
        asyncio.create_task(self.read_drop_file())
        self._subprocess: SubprocessManager = SubprocessManager()

    def _on_add_button_clicked(self, button: Gtk.Button):
        self.dialog: SharedFolderDialog = SharedFolderDialog(parent=self.get_root())
        self.dialog.connect("saved", self._on_dialog_saved) # pyright: ignore[reportUnknownMemberType]
        self.dialog.present()

    def _on_dialog_saved(self, dialog:SharedFolderDialog, source:str, target:str):
        folder = SharedFolder(source, target)
        self.list_store.append(folder)
        return True

    async def read_drop_file(self):
        monitor_service_name = "waydroid-monitor.service"
        mount_service_name = "waydroid-mount.service"
        try:
            await self._subprocess.run(
                f"systemctl --user list-unit-files {monitor_service_name}",
                shell=False
            )
            await self._subprocess.run(
                f"systemctl list-unit-files {mount_service_name}",
                shell=False
            )
        except Exception:
            logger.error(
                f"{monitor_service_name} or {monitor_service_name} not exists!"
            )
            self.hide()
            return

        drop_in_dir = os.path.expanduser(
            f"~/.config/systemd/user/{monitor_service_name}.d"
        )
        drop_in_file: str = os.path.join(drop_in_dir, "override.conf")
        sources: list[str] = []
        targets: list[str] = []

        def extract_env_var(env_string: str, var_name: str) -> str | None:
            pattern = rf'Environment="{var_name}=(.*?)"'
            match = re.search(pattern, env_string)
            if match:
                return match.group(1)
            return None

        if os.path.exists(drop_in_file):
            async with aiofiles.open(drop_in_file) as f:
                content = await f.read()
                source_str = extract_env_var(content, "SOURCE")
                target_str = extract_env_var(content, "TARGET")
                if source_str and target_str:
                    sources.extend(source_str.split(":"))
                    targets.extend(target_str.split(":"))

        for s, t in zip(sources, targets):
            item = SharedFolder(s, t)
            self.list_store.append(item)
        self._on_list_updated(None, 0, 0, 0)
        self.state = SharedFoldersState.INITIALIZED

    async def write_drop_file(self):
        service_name = "waydroid-monitor.service"
        drop_in_dir = os.path.expanduser(f"~/.config/systemd/user/{service_name}.d")
        os.makedirs(drop_in_dir, exist_ok=True)
        drop_in_file = os.path.join(drop_in_dir, "override.conf")
        contents = ["[Service]"]
        sources: list[str] = []
        targets: list[str] = []

        for i in range(self.list_store.get_n_items()):
            match self.list_store.get_item(i):
                case SharedFolder() as item:
                    sources.append(os.path.expanduser(item.source))
                    targets.append(os.path.expanduser(item.target))
                case None:
                    logger.error("Failed to get item from list store")
                    return
                case _:
                    logger.error("Invalid item type")
                    return
        contents.append(f"Environment=\"SOURCE={':'.join(sources)}\"")
        contents.append(f"Environment=\"TARGET={':'.join(targets)}\"")

        async with aiofiles.open(drop_in_file, "w") as file:
            await file.write("\n".join(contents))

        self.emit("updated")

    def restart_service(self):
        async def _restart_service():
            try:
                await self._subprocess.run("systemctl --user daemon-reload", shell=False)
                await self._subprocess.run(
                    "systemctl --user restart waydroid-monitor.service",
                    shell=False
                )
            except Exception as e:
                logger.error(e)

        asyncio.create_task(_restart_service())

    def _create_shared_folder_row(self, item:SharedFolder) -> SharedFolderRow:
        row = SharedFolderRow(item)
        row.connect("removed", self._on_folder_removed)
        return row

    def _on_folder_removed(self, row: SharedFolderRow, folder: SharedFolder):
        for i in range(self.list_store.get_n_items()):
            match self.list_store.get_item(i):
                case SharedFolder() as item if item.source == folder.source and item.target == folder.target:
                    self.list_store.remove(i)

                    try:
                        mount_interface = dbus.Interface(
                    dbus.SystemBus().get_object(
                            "id.waydro.Mount",
                            "/org/waydro/Mount"
                            ),
                            "id.waydro.Mount",
                        )
                        mount_interface.Unmount(folder.target)
                    except Exception as e:
                        logger.error(f"Failed to unmount {folder.target}: {e}")
                        error_dialog = MessageDialog(
                            heading=_("Error"),
                            body=_("Failed to unmount {target}:\n\n{error}").format(
                                target=folder.target, error=str(e)
                            ),
                            parent=self.get_root(),
                        )
                        error_dialog.add_response(Gtk.ResponseType.OK, _("OK"))
                        error_dialog.present()
                    break
                case _:
                    continue

    def _on_list_updated(self, model:Gio.ListModel|None, position:int=0, removed:int=0, added:int=0):
        if self.state == SharedFoldersState.INITIALIZED:
            asyncio.create_task(self.write_drop_file())
        if self.list_store.get_n_items() == 0:
            self.set_description(
                _("Use the button below to add your first shared folder. "
                  + "For file sharing to work, you need to have "
                  + "<a href='https://bindfs.org/'>bindfs</a> installed.")
            )
        else:
            self.set_description(None)
