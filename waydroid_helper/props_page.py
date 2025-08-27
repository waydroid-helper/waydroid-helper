# pyright: reportAny=false
# pyright: reportUnknownParameterType=false
# pyright: reportMissingParameterType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportUnknownParameterType=false

import asyncio
from typing import Any, Callable

import gi

from waydroid_helper.gpu_combo_row import GpuComboRow

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

import json
import os
from functools import partial
from gettext import gettext as _

from gi.repository import Adw, GLib, GObject, Gtk

from waydroid_helper.infobar import InfoBar
from waydroid_helper.util import Task, logger, template
from waydroid_helper.waydroid import PropsState, Waydroid


@template(resource_path="/com/jaoushingan/WaydroidHelper/ui/PropsPage.ui")
class PropsPage(Gtk.Box):
    __gtype_name__: str = "PropsPage"

    items: dict[Any, Any] = dict()

    switch_1: Gtk.Switch = Gtk.Template.Child()
    switch_2: Gtk.Switch = Gtk.Template.Child()
    switch_3: Gtk.Switch = Gtk.Template.Child()
    switch_4: Gtk.Switch = Gtk.Template.Child()
    switch_5: Gtk.Switch = Gtk.Template.Child()
    entry_1: Gtk.Entry = Gtk.Template.Child()
    entry_2: Gtk.Entry = Gtk.Template.Child()
    entry_3: Gtk.Entry = Gtk.Template.Child()
    entry_4: Gtk.Entry = Gtk.Template.Child()
    entry_5: Gtk.Entry = Gtk.Template.Child()
    entry_6: Gtk.Entry = Gtk.Template.Child()
    switch_21: Gtk.Switch = Gtk.Template.Child()
    device_combo: Adw.ComboRow = Gtk.Template.Child()
    waydroid_switch_1: Gtk.Switch = Gtk.Template.Child()
    waydroid_switch_2: Gtk.Switch = Gtk.Template.Child()
    waydroid_entry_1: Gtk.Entry = Gtk.Template.Child()
    gpu_combo_row: GpuComboRow = Gtk.Template.Child()
    overlay: Gtk.Overlay | None = None
    waydroid: Waydroid = GObject.Property(
        default=None, type=Waydroid
    )  # pyright:ignore[reportAssignmentType]
    reset_persist_prop_btn: Gtk.Button = Gtk.Template.Child()
    reset_privileged_prop_btn: Gtk.Button = Gtk.Template.Child()
    reset_waydroid_prop_btn: Gtk.Button = Gtk.Template.Child()

    timeout_id: dict[Any, Any] = dict()
    _task: Task = Task()

    # Removed complex signal management - no longer needed with new architecture!

    def __init__(self, waydroid: Waydroid, **kargs):
        super().__init__(**kargs)

        default_dir = os.path.join(
            "/usr/share", os.environ.get("PROJECT_NAME", "waydroid-helper")
        )
        data_dir = os.getenv("PKGDATADIR", default_dir)

        with open(os.path.join(data_dir, "data", "devices.json")) as f:
            self.items = json.load(f)

        self.set_property("waydroid", waydroid)
        self._init_bindings()

        self.on_waydroid_persist_state_changed(self.waydroid.persist_props, None)
        self.on_waydroid_privileged_state_changed(self.waydroid.privileged_props, None)
        self.on_waydroid_waydroid_state_changed(self.waydroid.waydroid_props, None)

        self.waydroid.persist_props.connect(
            "notify::state", self.on_waydroid_persist_state_changed
        )
        self.waydroid.privileged_props.connect(
            "notify::state", self.on_waydroid_privileged_state_changed
        )
        self.waydroid.waydroid_props.connect(
            "notify::state", self.on_waydroid_waydroid_state_changed
        )

        self.save_notification: InfoBar = InfoBar(
            label=_("Restart the session to apply the changes"),
            # cancel_callback=self.on_cancel_button_clicked,
            ok_callback=self.on_restart_button_clicked,
        )
        self.save_privileged_notification: InfoBar = InfoBar(
            label=_("Save and restart the container"),
            cancel_callback=self.on_restore_button_clicked,
            ok_callback=self.on_apply_button_clicked,
        )
        self.save_waydroid_notification: InfoBar = InfoBar(
            label=_("Save and restart the container"),
            cancel_callback=self.on_restore_waydroid_button_clicked,
            ok_callback=self.on_apply_waydroid_button_clicked,
        )

        self.save_waydroid_notification_upgrade: InfoBar = InfoBar(
            label=_("Save and restart the container"),
            cancel_callback=self.on_restore_waydroid_button_clicked,
            ok_callback=partial(self.on_apply_waydroid_button_clicked, upgrade=True),
        )

        model = Gtk.StringList.new(strings=list(self.items["index"].keys()))
        self.device_combo.set_model(model=model)
        self._model_changed: bool = False
        self._brand_changed: bool = False

        # Set up simple, permanent signal connections (no more dynamic connect/disconnect!)
        self._setup_permanent_signal_connections()

        asyncio.create_task(self.init_extra())

        # Set up manual property synchronization (replaces bind_property)
        # self._setup_property_synchronization()

    async def init_extra(self):
        tasks = []
        update_gpu_combo_row = False
        update_device_combo_row = False
        model_changed = False
        brand_changed = False

        def on_gpu_property_changed(obj: GObject.Object, pspec: GObject.ParamSpec):
            """
            model to ui
            """
            nonlocal update_gpu_combo_row
            update_gpu_combo_row = True
            # 相同 index 的 selected-item 不会重复触发
            self.gpu_combo_row.set_selected_value(obj.get_property(pspec.name))
            update_gpu_combo_row = False

        def on_waydroid_combo_row_selected_item(
            comborow: GpuComboRow, GParamObject: GObject.ParamSpec, name: str
        ):
            """
            ui to model
            """
            nonlocal update_gpu_combo_row
            if (
                self.waydroid.waydroid_props.get_property("state") != PropsState.READY
                or update_gpu_combo_row
            ):
                return

            new_value = comborow.get_selected_value()

            self.waydroid._controller.property_model.set_property(name, new_value)

            self.set_reveal(self.save_waydroid_notification_upgrade, True)

        async def init_gpu_combo_row():
            nonlocal update_gpu_combo_row
            await self.gpu_combo_row.load_gpu_info()
            self.gpu_combo_row.connect(
                "notify::selected-item",
                partial(
                    on_waydroid_combo_row_selected_item,
                    name=self.gpu_combo_row.get_name(),
                ),
            )
            update_gpu_combo_row = True
            self.gpu_combo_row.set_selected_value(
                self.waydroid.waydroid_props.get_property(self.gpu_combo_row.get_name())
            )
            update_gpu_combo_row = False
            self.waydroid._controller.property_model.connect(
                "notify::gpu", on_gpu_property_changed
            )

        def check_both_properties_changed():
            nonlocal model_changed, brand_changed
            if model_changed and brand_changed:
                model_changed = False
                brand_changed = False
                on_device_info_changed()

        def __on_model_changed():
            nonlocal model_changed
            model_changed = True
            check_both_properties_changed()

        def __on_brand_changed():
            nonlocal brand_changed
            brand_changed = True
            check_both_properties_changed()

        # waydroid prop to selected
        def on_device_info_changed():
            product_brand = self.waydroid.privileged_props.get_property(
                "ro-product-brand"
            )
            product_model = self.waydroid.privileged_props.get_property(
                "ro-product-model"
            )
            device = f"{product_brand} {product_model}"

            current = ""
            match self.device_combo.get_selected_item():
                case None:
                    current = ""
                case Gtk.StringObject() as item:
                    current = item.get_string()
                case _:
                    current = ""

            if device == current:
                return
            if device in self.items["index"].keys():
                self.device_combo.set_selected(self.items["index"][device])
            else:
                self.device_combo.set_selected(0)

        def on_adw_combo_row_selected_item(
            comborow: Adw.ComboRow, GParamObject: GObject.ParamSpec
        ):
            """Handle combo box selection - now with simple state checking"""
            # Simple state check - no more complex connect/disconnect needed!
            if (
                self.waydroid.privileged_props.get_property("state") != PropsState.READY
                or update_device_combo_row
            ):
                return

            self.set_reveal(self.save_privileged_notification, True)
            match comborow.get_selected_item():
                case None:
                    logger.info("No device selected")
                    return
                case Gtk.StringObject() as selected_item:
                    self.waydroid.privileged_props.set_device_info(
                        self.items["devices"][
                            self.items["index"][selected_item.get_string()]
                        ]["properties"]
                    )
                case _:
                    return

        async def init_device_combo_row():
            nonlocal update_device_combo_row
            self.device_combo.connect(
                "notify::selected-item", on_adw_combo_row_selected_item
            )
            update_device_combo_row = True
            on_device_info_changed()
            update_device_combo_row = False
            self.waydroid.privileged_props.connect(
                "notify::ro-product-brand", __on_brand_changed
            )
            self.waydroid.privileged_props.connect(
                "notify::ro-product-model", __on_model_changed
            )

        tasks.append(init_gpu_combo_row())
        tasks.append(init_device_combo_row())
        await asyncio.gather(*tasks)

    def _init_bindings(self):
        self.waydroid.bind(
            self.entry_1.get_name(),
            self.entry_1,
            "text",
            GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.BIDIRECTIONAL,
        )
        self.waydroid.bind(
            self.entry_2.get_name(),
            self.entry_2,
            "text",
            GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.BIDIRECTIONAL,
        )
        self.waydroid.bind(
            self.entry_3.get_name(),
            self.entry_3,
            "text",
            GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.BIDIRECTIONAL,
        )
        self.waydroid.bind(
            self.entry_4.get_name(),
            self.entry_4,
            "text",
            GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.BIDIRECTIONAL,
        )
        self.waydroid.bind(
            self.entry_5.get_name(),
            self.entry_5,
            "text",
            GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.BIDIRECTIONAL,
        )
        self.waydroid.bind(
            self.entry_6.get_name(),
            self.entry_6,
            "text",
            GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.BIDIRECTIONAL,
        )
        self.waydroid.bind(
            self.switch_1.get_name(),
            self.switch_1,
            "active",
            GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.BIDIRECTIONAL,
        )
        self.waydroid.bind(
            self.switch_2.get_name(),
            self.switch_2,
            "active",
            GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.BIDIRECTIONAL,
        )
        self.waydroid.bind(
            self.switch_3.get_name(),
            self.switch_3,
            "active",
            GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.BIDIRECTIONAL,
        )
        self.waydroid.bind(
            self.switch_4.get_name(),
            self.switch_4,
            "active",
            GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.BIDIRECTIONAL,
        )
        self.waydroid.bind(
            self.switch_5.get_name(),
            self.switch_5,
            "active",
            GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.BIDIRECTIONAL,
        )
        self.waydroid.bind(
            self.switch_21.get_name(),
            self.switch_21,
            "active",
            GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.BIDIRECTIONAL,
        )
        # self.waydroid.persist_props.bind_property(self.device_combo.get_name(), self.device_combo, "selected-item", GObject.BindingFlags.SYNC_CREATE|GObject.BindingFlags.BIDIRECTIONAL)
        self.waydroid.bind(
            self.waydroid_switch_1.get_name(),
            self.waydroid_switch_1,
            "active",
            GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.BIDIRECTIONAL,
        )
        self.waydroid.bind(
            self.waydroid_switch_2.get_name(),
            self.waydroid_switch_2,
            "active",
            GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.BIDIRECTIONAL,
        )
        self.waydroid.bind(
            self.waydroid_entry_1.get_name(),
            self.waydroid_entry_1,
            "text",
            GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.BIDIRECTIONAL,
        )
        # self.waydroid.waydroid_props.bind_property(self.gpu_combo_row.get_name(), self.gpu_combo_row, "selected-item", GObject.BindingFlags.SYNC_CREATE|GObject.BindingFlags.BIDIRECTIONAL)

    def _setup_permanent_signal_connections(self):
        """Set up permanent signal connections - no more complex connect/disconnect logic!"""

        # Connect persist property controls - these stay connected permanently
        # The handlers will check if the state is ready before acting
        self.entry_1.connect(
            "notify::text",
            partial(self.on_persist_text_changed, name=self.entry_1.get_name()),
        )
        self.entry_2.connect(
            "notify::text",
            partial(self.on_persist_text_changed, name=self.entry_2.get_name()),
        )
        self.entry_3.connect(
            "notify::text",
            partial(
                self.on_persist_text_changed, name=self.entry_3.get_name(), flag=True
            ),
        )
        self.entry_4.connect(
            "notify::text",
            partial(
                self.on_persist_text_changed, name=self.entry_4.get_name(), flag=True
            ),
        )
        self.entry_5.connect(
            "notify::text",
            partial(
                self.on_persist_text_changed, name=self.entry_5.get_name(), flag=True
            ),
        )
        self.entry_6.connect(
            "notify::text",
            partial(
                self.on_persist_text_changed, name=self.entry_6.get_name(), flag=True
            ),
        )

        self.switch_1.connect(
            "notify::active",
            partial(self.on_perisit_switch_clicked, name=self.switch_1.get_name()),
        )
        self.switch_2.connect(
            "notify::active",
            partial(self.on_perisit_switch_clicked, name=self.switch_2.get_name()),
        )
        self.switch_3.connect(
            "notify::active",
            partial(self.on_perisit_switch_clicked, name=self.switch_3.get_name()),
        )
        self.switch_4.connect(
            "notify::active",
            partial(self.on_perisit_switch_clicked, name=self.switch_4.get_name()),
        )
        self.switch_5.connect(
            "notify::active",
            partial(self.on_perisit_switch_clicked, name=self.switch_5.get_name()),
        )

        # Connect privileged property controls
        # self.device_combo.connect("notify::selected-item", self.on_adw_combo_row_selected_item)
        self.switch_21.connect(
            "notify::active",
            partial(self.on_privileged_switch_clicked, name=self.switch_21.get_name()),
        )

        # Connect waydroid config property controls
        self.waydroid_switch_1.connect(
            "notify::active",
            partial(
                self.on_waydroid_switch_clicked, name=self.waydroid_switch_1.get_name()
            ),
        )
        self.waydroid_switch_2.connect(
            "notify::active",
            partial(
                self.on_waydroid_switch_clicked, name=self.waydroid_switch_2.get_name()
            ),
        )
        self.waydroid_entry_1.connect(
            "notify::text",
            partial(
                self.on_waydroid_text_changed, name=self.waydroid_entry_1.get_name()
            ),
        )


    def on_waydroid_privileged_state_changed(
        self, w: GObject.Object, param: GObject.ParamSpec
    ):
        """Improved state handling with ERROR state recovery"""
        state = w.get_property("state")
        is_ready = state == PropsState.READY
        is_error = state == PropsState.ERROR

        # Enable/disable all privileged property controls
        self.switch_21.set_sensitive(is_ready)
        self.device_combo.set_sensitive(is_ready)
        self.reset_privileged_prop_btn.set_sensitive(is_ready)

        # If in ERROR state, try to recover after a short delay
        if is_error:
            logger.warning(
                "Privileged properties in ERROR state, attempting recovery..."
            )
            self._show_error_notification(
                _("Privileged properties in ERROR state, attempting recovery...")
            )
            GLib.timeout_add_seconds(2, self._retry_load_privileged_properties)

    def on_waydroid_waydroid_state_changed(
        self, w: GObject.Object, param: GObject.ParamSpec
    ):
        """Improved state handling for waydroid config properties with ERROR recovery"""
        state = w.get_property("state")
        is_ready = state == PropsState.READY
        is_error = state == PropsState.ERROR

        # Enable/disable waydroid config controls
        self.waydroid_switch_1.set_sensitive(is_ready)
        self.waydroid_switch_2.set_sensitive(is_ready)
        self.waydroid_entry_1.set_sensitive(is_ready)
        self.gpu_combo_row.set_sensitive(is_ready)
        self.reset_waydroid_prop_btn.set_sensitive(is_ready)

        # If in ERROR state, try to recover after a short delay
        if is_error:
            logger.warning("Waydroid properties in ERROR state, attempting recovery...")
            self._show_error_notification(
                _("Waydroid properties in ERROR state, attempting recovery...")
            )
            GLib.timeout_add_seconds(2, self._retry_load_waydroid_properties)

    def on_waydroid_persist_state_changed(
        self, w: GObject.Object, param: GObject.ParamSpec
    ):
        """Simplified state handling - just enable/disable UI elements"""
        state = w.get_property("state")
        is_ready = state == PropsState.READY

        # Enable/disable all persist property controls
        controls = [
            self.switch_1,
            self.switch_2,
            self.switch_3,
            self.switch_4,
            self.switch_5,
            self.entry_1,
            self.entry_2,
            self.entry_3,
            self.entry_4,
            self.entry_5,
            self.entry_6,
            self.reset_persist_prop_btn,
        ]

        for control in controls:
            control.set_sensitive(is_ready)

    def set_reveal(self, widget: InfoBar, reveal_child: bool):
        if (
            reveal_child == True
            and not self.save_notification.get_reveal_child()
            and not self.save_privileged_notification.get_reveal_child()
            and not self.save_waydroid_notification.get_reveal_child()
            and not self.save_waydroid_notification_upgrade.get_reveal_child()
        ):
            if self.overlay:
                self.remove(self.overlay)
            self.overlay = Gtk.Overlay.new()
            self.append(self.overlay)
            if widget == self.save_notification:
                self.overlay.set_child(self.save_notification)
                self.overlay.add_overlay(self.save_privileged_notification)
                self.overlay.add_overlay(self.save_waydroid_notification)
                self.overlay.add_overlay(self.save_waydroid_notification_upgrade)
            elif widget == self.save_privileged_notification:
                self.overlay.set_child(self.save_privileged_notification)
                self.overlay.add_overlay(self.save_notification)
                self.overlay.add_overlay(self.save_waydroid_notification)
                self.overlay.add_overlay(self.save_waydroid_notification_upgrade)
            elif widget == self.save_waydroid_notification:
                self.overlay.set_child(self.save_waydroid_notification)
                self.overlay.add_overlay(self.save_notification)
                self.overlay.add_overlay(self.save_privileged_notification)
                self.overlay.add_overlay(self.save_waydroid_notification_upgrade)
            else:
                self.overlay.set_child(self.save_waydroid_notification_upgrade)
                self.overlay.add_overlay(self.save_notification)
                self.overlay.add_overlay(self.save_privileged_notification)
                self.overlay.add_overlay(self.save_waydroid_notification)
        widget.set_reveal_child(reveal_child)

    def on_privileged_switch_clicked(
        self, a: Gtk.Switch, b: GObject.ParamSpec, name: str
    ):
        if self.waydroid.privileged_props.get_property("state") != PropsState.READY:
            return

        # new_value = a.get_active()

        # self.waydroid._controller.property_model.set_property(name, new_value)

        self.set_reveal(self.save_privileged_notification, True)

    def on_waydroid_switch_clicked(
        self, a: Gtk.Switch, b: GObject.ParamSpec, name: str
    ):
        if self.waydroid.waydroid_props.get_property("state") != PropsState.READY:
            return

        # new_value = a.get_active()

        # self.waydroid._controller.property_model.set_property(name, new_value)

        self.set_reveal(self.save_waydroid_notification, True)

    def on_waydroid_text_changed(self, a: Gtk.Entry, b: GObject.ParamSpec, name: str):
        """Handle waydroid text changes - now with simple state checking"""
        # Simple state check - no more complex connect/disconnect needed!
        if self.waydroid.waydroid_props.get_property("state") != PropsState.READY:
            return

        # # Update the model with the new value
        # new_value = a.get_text()

        # # Update the model
        # self.waydroid._controller.property_model.set_property(name, new_value)

        # Show notification for waydroid config changes
        self.set_reveal(self.save_waydroid_notification, True)

    def __on_persist_text_changed(self, entry: Gtk.Entry, name: str):
        # new_value = entry.get_text()

        # self.waydroid._controller.property_model.set_property(name, new_value)

        _ = self._task.create_task(self.waydroid.save_persist_prop(name))
        self.timeout_id[name] = None

    def on_persist_text_changed(
        self, a: Gtk.Entry, b: GObject.ParamSpec, name: str, flag: bool = False
    ):
        """Handle persist text changes - now with simple state checking"""
        # Simple state check - no more complex connect/disconnect needed!
        if self.waydroid.persist_props.get_property("state") != PropsState.READY:
            return

        if self.timeout_id.get(name) is not None:
            GLib.source_remove(self.timeout_id[name])

        self.timeout_id[name] = GLib.timeout_add(
            1000, partial(self.__on_persist_text_changed, a, name)
        )
        if flag:
            self.set_reveal(self.save_notification, True)

    def on_perisit_switch_clicked(self, a: Gtk.Switch, b: GObject.ParamSpec, name: str):
        if self.waydroid.persist_props.get_property("state") != PropsState.READY:
            return

        # new_value = a.get_active()

        # self.waydroid._controller.property_model.set_property(name, new_value)

        self.set_reveal(self.save_notification, True)
        self._task.create_task(self.waydroid.save_persist_prop(name))

    # def on_cancel_button_clicked(self, button):
    #     self.set_reveal(self.save_notification, False)
    # self.save_notification.set_reveal_child(False)

    def on_restart_button_clicked(self, button: Gtk.Button):
        # self.set_reveal(self.save_notification, False)
        # self.save_notification.set_reveal_child(False)
        self._task.create_task(self.waydroid.restart_session())

    def on_restore_button_clicked(self, button: Gtk.Button):
        # self.set_reveal(self.save_privileged_notification, False)
        # self.save_privileged_notification.set_reveal_child(False)
        self._task.create_task(self.waydroid.restore_privileged_props())

    def on_apply_button_clicked(self, button: Gtk.Button):
        # self.set_reveal(self.save_privileged_notification, False)
        # self.save_privileged_notification.set_reveal_child(False)
        self._task.create_task(self.waydroid.save_privileged_props())

    def on_restore_waydroid_button_clicked(self, button: Gtk.Button):
        # Restore waydroid config properties from file
        self._task.create_task(self.waydroid.restore_waydroid_props())

    def on_apply_waydroid_button_clicked(
        self, button: Gtk.Button, upgrade: bool = False
    ):
        # Save waydroid config properties
        self._task.create_task(self.waydroid.save_waydroid_props(upgrade=upgrade))

    @Gtk.Template.Callback()
    def on_reset_persist_clicked(self, button: Gtk.Button):
        self._task.create_task(self.waydroid.reset_persist_props())

    @Gtk.Template.Callback()
    def on_reset_privileged_clicked(self, button: Gtk.Button):
        self._task.create_task(self.waydroid.reset_privileged_props())

    @Gtk.Template.Callback()
    def on_reset_waydroid_clicked(self, button: Gtk.Button):
        self._task.create_task(self.waydroid.reset_waydroid_props())

    def _retry_load_privileged_properties(self) -> bool:
        """Retry loading privileged properties (called from GLib timeout)"""
        try:
            self._task.create_task(self.waydroid.retry_load_privileged_properties())
        except Exception as e:
            logger.error(f"Failed to retry loading privileged properties: {e}")
        return False  # Don't repeat the timeout

    def _retry_load_waydroid_properties(self) -> bool:
        """Retry loading waydroid properties (called from GLib timeout)"""
        try:
            self._task.create_task(self.waydroid.retry_load_waydroid_properties())
        except Exception as e:
            logger.error(f"Failed to retry loading waydroid properties: {e}")
        return False  # Don't repeat the timeout

    def _show_error_notification(self, message: str):
        """Show a temporary error notification to the user"""
        try:
            # Create a temporary InfoBar for error notification
            error_notification = InfoBar(
                label=message, ok_callback=lambda x: None  # Do nothing on OK
            )

            # Show the notification temporarily
            if self.overlay:
                self.overlay.add_overlay(error_notification)
                error_notification.set_reveal_child(True)

                # Auto-hide after 5 seconds
                GLib.timeout_add_seconds(
                    5, lambda: error_notification.set_reveal_child(False)
                )
        except Exception as e:
            logger.error(f"Failed to show error notification: {e}")
