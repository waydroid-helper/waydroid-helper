"""GNOME device manager for the default and named Waydroid instances."""

import asyncio
from gettext import gettext as _
from pathlib import Path

from gi.events import GLibEventLoopPolicy
from gi.repository import Adw, Gio, GLib, GObject, Gtk, Pango

from waydroid_helper.compat_widget import MessageDialog, ToolbarView
from waydroid_helper.controller.app.emulator_device_settings import DeviceSettings
from waydroid_helper.controller.app.emulator_display import PRESETS, startup_display_mode
from waydroid_helper.instance_manager_backend import InstanceService
from waydroid_helper.util.log import logger
from waydroid_helper.waydroid_instance import DEFAULT_INSTANCE, device_metadata, emulator_settings


class DeviceRow(Adw.PreferencesRow):
    def __init__(self, manager, device):
        super().__init__(activatable=False, selectable=False, use_markup=False, css_classes=["card"])
        self.manager = manager
        self.device = device
        self.metadata = device_metadata(device.ident)
        self.preferences = emulator_settings(device.ident)
        self._settings_handlers = [
            (self.metadata, self.metadata.connect("changed", self._settings_changed)),
            (self.preferences, self.preferences.connect("changed::emulator-display-mode", self._settings_changed)),
            (self.preferences, self.preferences.connect("changed::emulator-last-display-mode", self._settings_changed)),
        ]
        card = Gtk.Box(spacing=18, css_classes=["device-card"])
        self.set_child(card)
        self.preview = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, width_request=154, height_request=88,
                               valign=Gtk.Align.CENTER, overflow=Gtk.Overflow.HIDDEN, css_classes=["device-preview"])
        if device.ident != DEFAULT_INSTANCE:
            self.preview.add_css_class("violet")
        emblem = Gtk.Image(icon_name="waydroid", pixel_size=36, halign=Gtk.Align.END,
                           margin_end=10, margin_top=7)
        if not Gtk.IconTheme.get_for_display(self.get_display()).has_icon("waydroid"):
            emblem.set_from_icon_name("com.jaoushingan.WaydroidHelper")
        self.preview.append(emblem)
        card.append(self.preview)
        self.status = Gtk.Label(css_classes=["caption-heading"])
        status_box = Gtk.Box(spacing=5, halign=Gtk.Align.START, valign=Gtk.Align.END,
                             margin_start=8, margin_bottom=8, vexpand=True, css_classes=["device-status"])
        self.dot = Gtk.Box(width_request=6, height_request=6, valign=Gtk.Align.CENTER,
                           css_classes=["device-status-dot"])
        status_box.append(self.dot)
        status_box.append(self.status)
        self.preview.append(status_box)

        info = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6, valign=Gtk.Align.CENTER, hexpand=True)
        card.append(info)
        self.device_name = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END, css_classes=["title-3"])
        info.append(self.device_name)
        tags = Gtk.Box(spacing=6)
        info.append(tags)
        self.version = Gtk.Label(css_classes=["caption", "device-tag"])
        self.form_factor = Gtk.Label(css_classes=["caption", "device-tag"])
        tags.append(self.version)
        tags.append(self.form_factor)
        self.geometry = Gtk.Label(xalign=0, ellipsize=Pango.EllipsizeMode.END, css_classes=["dim-label"])
        info.append(self.geometry)
        controls = Gtk.Box(spacing=6, valign=Gtk.Align.CENTER)
        card.append(controls)
        self.open_button = Gtk.Button(css_classes=["circular"])
        self.open_button.connect("clicked", lambda *_: manager.open_device(self.device.ident))
        controls.append(self.open_button)
        self.menu_button = Gtk.MenuButton(icon_name="view-more-symbolic", tooltip_text=_("Device actions"))
        self.menu_button.add_css_class("flat")
        self.menu_button.add_css_class("circular")
        controls.append(self.menu_button)
        self._build_menu()
        self.update(device)

    @property
    def name(self):
        name = self.metadata.get_string("name")
        return name or (_("Default device") if self.device.ident == DEFAULT_INSTANCE else self.device.ident)

    def _build_menu(self):
        self.actions = {}
        group = Gio.SimpleActionGroup()
        self.insert_action_group("device", group)
        model = Gio.Menu()
        for name, label, callback in (
            ("settings", _("Device settings"), lambda: self.manager.open_settings(self)),
            ("clean", _("Clear app caches"), lambda: self.manager.clear_cache(self)),
            ("rename", _("Rename"), lambda: self.manager.rename_device(self)),
            ("duplicate", _("Duplicate"), None),
            ("backup", _("Back Up and Restore"), None),
            ("shortcut", _("Create Desktop Shortcut"), lambda: self.manager.create_shortcut(self)),
        ):
            self._add_action(model, group, name, label, callback)

        lifecycle = Gio.Menu()
        self._add_action(lifecycle, group, "stop", _("Shut Down"), lambda: self.manager.stop_device(self))
        self._add_action(lifecycle, group, "remove", _("Delete"), lambda: self.manager.remove_device(self))
        model.append_section(None, lifecycle)
        self.menu_button.set_menu_model(model)

    def _add_action(self, menu, group, name, label, callback):
        action = Gio.SimpleAction.new(name, None)
        if callback is None:
            action.set_enabled(False)
        else:
            action.connect("activate", lambda *_: callback())
        group.add_action(action)
        self.actions[name] = action
        menu.append(label, f"device.{name}")

    def _settings_changed(self, *_):
        self.update(self.device)
        self.manager.list_box.invalidate_filter()
        self.manager.list_box.invalidate_sort()

    def update(self, device):
        self.device = device
        self.set_title(self.name)
        self.device_name.set_text(self.name)
        self.device_name.set_tooltip_text(device.ident)
        version = self.metadata.get_string("android-version")
        self.version.set_text(_("Android %s") % version if version else "Android")
        mode = startup_display_mode(self.preferences)
        dimensions = (mode.width, mode.height, mode.dpi)
        preset = next((name for name, modes in PRESETS if dimensions in modes), _("Custom"))
        self.form_factor.set_text(preset)
        self.geometry.set_text(f"{mode.width} × {mode.height}  ·  {mode.dpi} DPI")
        self.status.set_label(_("Running") if device.running else _("Powered Off"))
        if device.running:
            self.dot.add_css_class("online")
        else:
            self.dot.remove_css_class("online")
        self.open_button.set_icon_name("window-new-symbolic" if device.running else "media-playback-start-symbolic")
        label = _("Open") if device.running else _("Start")
        self.open_button.set_tooltip_text(label)
        self.open_button.update_property([Gtk.AccessibleProperty.LABEL], [label])
        self.actions["clean"].set_enabled(device.running)
        self.actions["stop"].set_enabled(device.running)
        self.actions["remove"].set_enabled(not device.running and device.ident != DEFAULT_INSTANCE)

    def dispose_settings(self):
        for settings, handler in self._settings_handlers:
            settings.disconnect(handler)
        self._settings_handlers.clear()


class InstanceManager(Adw.ApplicationWindow):
    def __init__(self, app, launcher, service=None):
        super().__init__(application=app, title=_("Android Devices"), default_width=840, default_height=510)
        self._css = Gtk.CssProvider()
        self._css.load_from_resource("/com/jaoushingan/WaydroidHelper/instance-manager.css")
        Gtk.StyleContext.add_provider_for_display(self.get_display(), self._css, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        self.launcher = launcher
        self.service = service or InstanceService()
        self.rows = {}
        self.refresh_task = None
        self.operation = None
        self.version_tasks = {}
        self.version_checked = set()
        self._closed = False
        self._launcher_tasks = set()

        toolbar = ToolbarView()
        header = Adw.HeaderBar()
        brand = Gtk.Box(spacing=8)
        brand.append(Gtk.Image(icon_name="com.jaoushingan.WaydroidHelper", pixel_size=22))
        brand.append(Gtk.Label(label="Waydroid", css_classes=["heading"]))
        header.pack_start(brand)
        header.set_title_widget(Gtk.Box())
        self.new_button = Gtk.Button(child=Adw.ButtonContent(
            icon_name="list-add-symbolic", label=_("New Device")
        ))
        self.new_button.add_css_class("suggested-action")
        self.new_button.connect("clicked", lambda *_: self.create_device())
        self.new_button.add_css_class("pill")
        reload_button = Gtk.Button(icon_name="view-refresh-symbolic", tooltip_text=_("Refresh"))
        reload_button.connect("clicked", self.request_refresh)
        header.pack_end(reload_button)
        search_button = Gtk.ToggleButton(icon_name="system-search-symbolic", tooltip_text=_("Search Devices"))
        header.pack_end(search_button)

        search_bar = Gtk.SearchBar()
        self.search = Gtk.SearchEntry(placeholder_text=_("Search Devices"), hexpand=True)
        search_bar.set_child(self.search)
        search_bar.connect_entry(self.search)
        search_bar.set_key_capture_widget(self)
        search_bar.bind_property("search-mode-enabled", search_button, "active", GObject.BindingFlags.BIDIRECTIONAL)
        search_bar.connect("notify::search-mode-enabled", self._search_visibility)
        bars = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        bars.append(header)
        bars.append(search_bar)
        toolbar.add_top_bar(bars)

        self.list_box = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE, css_classes=["device-library"], valign=Gtk.Align.START)
        self.list_box.set_filter_func(self._filter_row)
        self.list_box.set_sort_func(self._sort_rows)
        self.search.connect("search-changed", lambda *_: self.list_box.invalidate_filter())
        self.status = Adw.StatusPage(icon_name="phone-symbolic", title=_("Loading Devices"))
        self.list_box.set_placeholder(self.status)

        heading = Gtk.Box(spacing=12)
        heading.append(Gtk.Label(label=self.get_title(), xalign=0, hexpand=True, css_classes=["title-1"]))
        heading.append(self.new_button)
        library = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18, valign=Gtk.Align.START,
                          margin_start=18, margin_end=18, margin_top=18, margin_bottom=24)
        library.append(heading)
        library.append(self.list_box)
        clamp = Adw.Clamp(maximum_size=800, tightening_threshold=680, child=library)
        self.compact = None
        if hasattr(Adw, "Breakpoint"):
            self.set_size_request(340, 260)
            self.compact = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 540sp"))
            self.add_breakpoint(self.compact)
        scroll = Gtk.ScrolledWindow(hscrollbar_policy=Gtk.PolicyType.NEVER, child=clamp)
        toolbar.set_content(scroll)
        self.toasts = Adw.ToastOverlay(child=toolbar)
        self.set_content(self.toasts)
        self.connect("close-request", self._close)
        self.poll_source = GLib.timeout_add_seconds(4, self.request_refresh)
        self.request_refresh()

    def _search_visibility(self, bar, _param):
        if not bar.get_search_mode_enabled():
            self.search.set_text("")

    def _filter_row(self, row):
        query = self.search.get_text().strip().casefold()
        return query in f"{row.name} {row.device.ident}".casefold()

    @staticmethod
    def _sort_rows(row_a, row_b):
        def key(row):
            return row.device.ident != DEFAULT_INSTANCE, row.name.casefold(), row.device.ident

        a, b = key(row_a), key(row_b)
        return (a > b) - (a < b)

    def request_refresh(self, *_):
        if self.refresh_task is None:
            self.refresh_task = asyncio.create_task(self._refresh())
        return GLib.SOURCE_CONTINUE

    async def _refresh(self):
        try:
            devices = await self.service.list_devices()
        except (OSError, RuntimeError, ValueError, TimeoutError) as error:
            logger.warning("Could not list Waydroid devices: %s", error)
            self.status.set_title(_("Could Not Load Devices"))
            self.status.set_description(str(error))
            return
        finally:
            self.refresh_task = None

        ids = {device.ident for device in devices}
        for ident in self.rows.keys() - ids:
            row = self.rows.pop(ident)
            row.dispose_settings()
            self.list_box.remove(row)
        for device in devices:
            if device.ident in self.rows:
                self.rows[device.ident].update(device)
            else:
                row = self.rows[device.ident] = DeviceRow(self, device)
                self.list_box.append(row)
                if self.compact:
                    self.compact.add_setter(row.preview, "width-request", 72)
                    self.compact.add_setter(row.preview, "height-request", 72)
            self._refresh_version(device)
        self.status.set_title(_("No Matching Devices") if devices else _("No Devices"))
        self.status.set_description("")

    def _refresh_version(self, device):
        ident = device.ident
        if not device.running:
            self.version_checked.discard(ident)
            return
        if ident not in self.version_tasks and ident not in self.version_checked:
            self.version_tasks[ident] = asyncio.create_task(self._read_version(ident))

    async def _read_version(self, ident):
        try:
            version = await self.service.android_version(ident)
            row = self.rows.get(ident)
            if version and row and row.device.running:
                row.metadata.set_string("android-version", version)
                self.version_checked.add(ident)
        except (OSError, RuntimeError, TimeoutError) as error:
            logger.debug("Android version unavailable for %s: %s", ident, error)
        finally:
            self.version_tasks.pop(ident, None)

    def _close(self, *_):
        if self.operation:
            return True
        self._closed = True
        Gtk.StyleContext.remove_provider_for_display(self.get_display(), self._css)
        GLib.source_remove(self.poll_source)
        if self.refresh_task:
            self.refresh_task.cancel()
        for task in self.version_tasks.values():
            task.cancel()
        for row in self.rows.values():
            row.dispose_settings()
        return False

    def _toast(self, message):
        if not self._closed:
            self.toasts.add_toast(Adw.Toast(title=message))

    def open_settings(self, row):
        if row.device.running:
            self.open_device(row.device.ident, settings=True)
            return
        # The powered-off editor belongs to the library window. It shares
        # the same preferences and dialog as the running emulator, without
        # constructing a compositor, starting a session or contacting ADB.
        dialog = DeviceSettings(self, row.preferences)
        dialog.stack.set_visible_child_name("display")
        dialog.present()

    def open_device(self, ident, *, settings=False):
        # A separate GApplication per instance owns the live window. Spawning
        # the launcher also forwards Open or Settings to an existing window.
        mode = "--emulator-settings" if settings else "--emulator"
        task = asyncio.create_task(self._launch(mode, ident))
        self._launcher_tasks.add(task)
        task.add_done_callback(self._launcher_tasks.discard)

    async def _launch(self, mode, ident):
        try:
            process = await asyncio.create_subprocess_exec(self.launcher, mode, "--instance", ident)
            if await process.wait():
                raise RuntimeError(_("Could not open the emulator."))
        except (OSError, RuntimeError) as error:
            logger.warning("Could not open %s for %s: %s", mode, ident, error)
            self._toast(str(error))

    def _perform(self, callback, success=None):
        if self.operation is not None:
            return
        self.operation = asyncio.create_task(self._run_operation(callback, success))

    async def _run_operation(self, callback, success):
        try:
            await callback()
            if success:
                self._toast(success)
        except (OSError, RuntimeError, ValueError, TimeoutError) as error:
            logger.warning("Device operation failed: %s", error)
            self._toast(str(error))
        finally:
            self.operation = None
            self.request_refresh()

    def _dialog(self, title, body, action, callback, *, value=None, destructive=False):
        dialog = MessageDialog(heading=title, body=body, parent=self)
        dialog.add_response(Gtk.ResponseType.CANCEL, _("Cancel"))
        dialog.add_response(Gtk.ResponseType.OK, action)
        dialog.set_default_response(Gtk.ResponseType.CANCEL if destructive else Gtk.ResponseType.OK)
        dialog.set_response_appearance(
            Gtk.ResponseType.OK, "destructive-action" if destructive else "suggested-action"
        )

        if value is not None:
            entry = Gtk.Entry(text=value, activates_default=True)
            if isinstance(dialog, Gtk.MessageDialog):
                dialog.get_message_area().append(entry)
            else:
                dialog.set_extra_child(entry)

        def responded(_dialog, response):
            if response in (Gtk.ResponseType.OK, Gtk.ResponseType.OK.value_nick):
                if value is None:
                    callback()
                else:
                    callback(entry.get_text().strip())

        dialog.connect("response", responded)
        dialog.present()

    def create_device(self):
        self._dialog(
            _("New Device"), _("Enter a unique ID using lowercase letters, digits or hyphens."),
            _("Create"), lambda ident: self._perform(lambda: self.service.create(ident)), value="",
        )

    def rename_device(self, row):
        def rename(name):
            if not name:
                self._toast(_("Enter a device name."))
            elif not row.metadata.set_string("name", name):
                self._toast(_("Could not save the device name."))

        self._dialog(_("Rename Device"), _("Choose a display name."), _("Rename"), rename, value=row.name)

    def stop_device(self, row):
        self._dialog(
            _("Shut Down Device?"), _("Open Android apps will close."), _("Shut Down"),
            lambda: self._perform(lambda: self.service.stop(row.device.ident)),
        )

    def clear_cache(self, row):
        self._dialog(
            _("Clear App Caches?"), _("Android will remove cached files for installed apps."),
            _("Clear"), lambda: self._perform(lambda: self.service.clear_cache(row.device.ident), _("App caches cleared.")),
        )

    def remove_device(self, row):
        async def remove():
            await self.service.remove(row.device.ident)
            for key in row.metadata.props.settings_schema.list_keys():
                row.metadata.reset(key)
            for key in row.preferences.props.settings_schema.list_keys():
                row.preferences.reset(key)

        self._dialog(
            _("Delete Device?"), _("“%s” and its Android apps and data will be permanently deleted.") % row.name,
            _("Delete"), lambda: self._perform(remove), destructive=True,
        )

    def create_shortcut(self, row):
        directory = Path(GLib.get_user_special_dir(GLib.UserDirectory.DIRECTORY_DESKTOP) or Path.home() / "Desktop")
        path = directory / f"waydroid-{row.device.ident}.desktop"
        # The Desktop Entry Exec field has its own escaping rules and never
        # goes through a shell. Quote the launcher path, then escape any
        # literal percent sign so it cannot be interpreted as a field code.
        launcher = "".join("\\" + char if char in '\\`"$' else char for char in self.launcher)
        entry = GLib.KeyFile()
        group = "Desktop Entry"
        entry.set_string(group, "Name", row.name)
        entry.set_string(group, "Type", "Application")
        entry.set_string(group, "Icon", "com.jaoushingan.WaydroidHelper")
        entry.set_string(group, "Exec", f'"{launcher.replace("%", "%%")}" --emulator --instance {row.device.ident}')
        entry.set_boolean(group, "Terminal", False)
        try:
            directory.mkdir(parents=True, exist_ok=True)
            with path.open("x", encoding="utf-8") as shortcut:
                shortcut.write(entry.to_data()[0])
            path.chmod(0o755)
        except OSError as error:
            logger.warning("Could not create desktop shortcut %s: %s", path, error)
            self._toast(str(error))
        else:
            self._toast(_("Desktop shortcut created."))


def run(launcher):
    asyncio.set_event_loop_policy(GLibEventLoopPolicy())
    app = Adw.Application(application_id="com.jaoushingan.WaydroidHelper.Devices")

    def activate(application):
        window = application.get_active_window() or InstanceManager(application, launcher)
        window.present()

    app.connect("activate", activate)
    return app.run([])
