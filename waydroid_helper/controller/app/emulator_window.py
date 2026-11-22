"""Decorated emulator window sharing the existing mapping workspace."""

import asyncio
from gettext import gettext as _

from gi.repository import Gdk, Gio, GLib, Gtk

from waydroid_helper.controller.android.input import AKeyEventAction
from waydroid_helper.controller.app.embedded_session import (
    EmbeddedSession,
    compositor_type,
    session_status,
    stop_confirmed_session,
    waydroid_output,
)
from waydroid_helper.controller.app.emulator_display import (
    DisplayMode,
    DisplaySettings,
    apply_android_mode,
    device_command,
    read_mode,
    stage_mode,
)
from waydroid_helper.controller.app.emulator_gamepad import GamepadInput
from waydroid_helper.controller.app.input_recording import InputRecording
from waydroid_helper.controller.app.emulator_tools import EmulatorTools
from waydroid_helper.controller.app.emulator_toolbar import EmulatorToolbar
from waydroid_helper.controller.app.emulator_viewport import EmulatorViewport
from waydroid_helper.controller.app.window import MappingWindow
from waydroid_helper.compat_widget import MessageDialog
from waydroid_helper.controller.core.control_msg import InjectKeycodeMsg
from waydroid_helper.controller.core.event_bus import Event, EventType
from waydroid_helper.util.log import logger


class EmulatorWindow(MappingWindow):
    embedded = True

    def build_canvas(self, overlay):
        self.session = EmbeddedSession()
        self.compositor = compositor_type()(socket=self.session.socket)
        self.compositor.set_can_target(False)
        self.compositor.set_focusable(False)
        overlay.add_overlay(self.fixed)
        overlay.set_focusable(True)

    def setup_window(self):
        self.set_title(_("Waydroid Emulator"))
        self.viewport = EmulatorViewport(self.compositor, self.canvas)
        self.screen_geometry.set_host_resolution(*self.viewport.mapping_size)
        self.notification_box.set_margin_top(12)
        self.preferences = Gio.Settings.new("com.jaoushingan.WaydroidHelper")
        self.restarting = False
        self.restart_dialog = None
        self.close_dialog = None
        self.display_dialog = None
        self.tools = EmulatorTools(self)
        self.recorder = InputRecording(self)
        self.gamepad = GamepadInput(self)
        self.mini_width = None
        self._pending_resize = 0
        self.toolbar = EmulatorToolbar(self)
        self.status_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=6,
            halign=Gtk.Align.CENTER,
            valign=Gtk.Align.CENTER,
        )
        self.status_box.add_css_class("emulator-status")
        self.status = Gtk.Label(
            wrap=True, max_width_chars=44, justify=Gtk.Justification.CENTER
        )
        self.status_box.append(self.status)
        self.retry = Gtk.Button(label=_("Retry"), halign=Gtk.Align.CENTER)
        self.retry.connect("clicked", lambda *_: self._start_if_idle())
        self.status_box.append(self.retry)
        frame = Gtk.Overlay()
        frame.set_child(self.viewport)
        frame.add_overlay(self.status_box)

        self.exit_fullscreen = Gtk.Button(
            icon_name="view-restore-symbolic",
            tooltip_text=_("Exit fullscreen (F11)"),
            halign=Gtk.Align.END,
            valign=Gtk.Align.START,
            margin_top=6,
            margin_end=6,
            visible=False,
        )
        self.exit_fullscreen.connect("clicked", lambda *_: self.toggle_fullscreen())
        frame.add_overlay(self.exit_fullscreen)
        motion = Gtk.EventControllerMotion()
        motion.connect("motion", self._reveal_fullscreen_control)
        frame.add_controller(motion)

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)
        box.append(self.toolbar)
        box.append(frame)
        decoration = Gtk.Overlay()
        decoration.set_child(box)
        self.resize_handles = self._add_resize_handles(decoration)
        self.set_content(decoration)
        self.viewport.set_name("emulator-display")
        self.style_manager.add_custom_style("""
            #emulator-display { background: black; }
            #emulator-display #mode-notification-box { padding: 5px 12px; border-radius: 14px; }
            #emulator-display #mode-notification-label { font-size: 13px; font-weight: 500; }
            .emulator-header { min-height: 36px; padding: 0 6px; }
            .emulator-header button { min-width: 28px; min-height: 26px; padding: 2px 4px; }
            .emulator-header .editing > button { background: alpha(@accent_color, .18); }
            .emulator-status { color: white; background: alpha(black, .75); }
            .emulator-status { padding: 8px 14px; border-radius: 8px; }

        """)
        self.set_resizable(False)
        remembered = self.preferences.get_int("emulator-window-width")
        self._set_width(
            remembered
            if self.preferences.get_boolean("emulator-remember-size") and remembered > 0
            else self.viewport.DEFAULT_WINDOW_SIZE[0]
        )
        self._update_resize_handles()
        self.preferences.connect(
            "changed::emulator-lock-size", self._update_resize_handles
        )
        self.connect("notify::maximized", self._update_resize_handles)
        self.connect("notify::fullscreened", self._fullscreen_changed)
        keys = Gtk.EventControllerKey()
        keys.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        keys.connect("key-pressed", self._on_shortcut)
        self.add_controller(keys)
        self.pending_control = None
        click = Gtk.GestureClick(button=Gdk.BUTTON_PRIMARY)
        click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        click.connect("pressed", self._on_canvas_press)
        self.canvas.add_controller(click)
        self.resolution_refresh = None
        self.viewport.connect("output-resized", self._queue_resolution_refresh)
        self.startup = None
        self.connect("map", self._on_map)

    def _on_map(self, *_):
        if self.startup is None:
            mode = self._selected_mode()
            if mode:
                scale = self.get_surface().get_scale()
                self.viewport.set_configured_output(
                    (
                        max(1, round(mode.width / scale)),
                        max(1, round(mode.height / scale)),
                    )
                )
                self.screen_geometry.set_host_resolution(*self.viewport.mapping_size)
                self._set_width(self.windowed_width)
            self.get_surface().connect("notify::scale", self._queue_resolution_refresh)
            self._start_if_idle()

    def _queue_resolution_refresh(self, *_):
        if not self.server.connected_event.is_set() or self._is_closing:
            return
        if self.resolution_refresh:
            self.resolution_refresh.cancel()
        self.resolution_refresh = asyncio.create_task(self._refresh_device_resolution())

    async def _refresh_device_resolution(self):
        # The Android input geometry can lag behind a native output or scale
        # change. Read the effective dimensions after the display settles.
        scale = self.get_surface().get_scale()
        expected = tuple(int(n * scale) for n in self.viewport.output_size)
        for delay in (0.12, 0.3, 0.7):
            await asyncio.sleep(delay)
            resolution = await self.scrcpy_lifecycle.adb_helper.get_screen_resolution()
            if resolution:
                self.screen_geometry.set_resolution(*resolution)
                if resolution == expected:
                    break

    async def _use_waydroid_geometry(self):
        # Waydroid opts out of maximized xdg configure events when either
        # persistent dimension is set. Fit that user-sized surface as a unit,
        # with the negotiated startup extent filling any unspecified axis.
        width, height = await asyncio.gather(
            waydroid_output("prop", "get", "persist.waydroid.width"),
            waydroid_output("prop", "get", "persist.waydroid.height"),
        )
        configured = [
            int(value) if value.isdecimal() else 0 for value in (width, height)
        ]
        guest_w, guest_h = self.viewport.output_size
        size = (
            (configured[0] or guest_w, configured[1] or guest_h)
            if any(configured)
            else None
        )
        if size != self.viewport.configured_output:
            self.viewport.set_configured_output(size)
            self.screen_geometry.set_host_resolution(*self.viewport.mapping_size)
            self._set_width(self.windowed_width)

    def _start_if_idle(self):
        if self.startup is None or self.startup.done():
            self.canvas.grab_focus()
            self.startup = asyncio.create_task(self._start())

    async def _confirm_session_switch(self, previous):
        decision = asyncio.get_running_loop().create_future()
        dialog = MessageDialog(
            heading=_("Session Will Be Stopped"),
            body=_(
                "Opening the emulator will restart the current Waydroid session. Open Android apps will close."
            ),
            parent=self,
        )
        dialog.add_response(Gtk.ResponseType.CANCEL, _("Cancel"))
        dialog.add_response(Gtk.ResponseType.OK, _("Continue"))
        dialog.set_response_appearance(Gtk.ResponseType.OK, "destructive-action")
        dialog.set_default_response(Gtk.ResponseType.CANCEL)

        def respond(_dialog, response):
            if not decision.done():
                decision.set_result(
                    response in (Gtk.ResponseType.OK, Gtk.ResponseType.OK.value_nick)
                )

        dialog.connect("response", respond)
        dialog.present()
        if not await decision:
            return False
        await stop_confirmed_session(previous.get("Wayland display"))
        return True

    async def _start(self):
        self.status.set_label(_("Starting Waydroid…"))
        self.status_box.set_visible(True)
        self.retry.set_visible(False)
        try:
            status = await session_status()
            if (
                status.get("Session") != "STOPPED"
                and status.get("Wayland display") != self.session.socket
            ):
                if not await self._confirm_session_switch(status):
                    self.request_shutdown()
                    return
            address = await self.session.start()
            await self._use_waydroid_geometry()
            self.status.set_label(_("Connecting input controls…"))
            service = self.scrcpy_lifecycle
            service.adb_helper.serial = f"{address}:5555"
            mode = self._selected_mode()
            if mode:
                if not await service.adb_helper.connect():
                    raise RuntimeError(_("Android display information is unavailable."))
                # A TCP transport can be connected while adbd is still
                # offline immediately after restarting the container.
                await device_command(service.adb_helper.serial, "wait-for-device")
                await apply_android_mode(service.adb_helper.serial, mode)
            if not await service.setup():
                raise RuntimeError(
                    _("Could not connect the Android input controls over ADB.")
                )
            await asyncio.wait_for(self.server.connected_event.wait(), 20)
            self._queue_resolution_refresh()
            self.status_box.set_visible(False)
            self.switch_mode(self.MAPPING_MODE)
            self.canvas.grab_focus()
            logger.info(
                "Emulator ready on %s with Android output %s",
                self.session.socket,
                self.screen_geometry.get_resolution(),
            )
            await self.server.disconnected_event.wait()
            raise ConnectionError(_("Android input disconnected."))
        except Exception as error:
            logger.exception("Embedded display on %s: %s", self.session.socket, error)
            self.status.set_label(str(error) or _("Timed out waiting for Waydroid."))
            self.status_box.set_visible(True)
            self.retry.set_visible(True)

    def send_key(self, keycode):
        if not self.server.connected_event.is_set():
            self.show_notification(_("Android input is not connected."))
            return
        for action in (AKeyEventAction.DOWN, AKeyEventAction.UP):
            message = InjectKeycodeMsg(action, keycode, 0, 0)
            self.event_bus.emit(Event(EventType.CONTROL_MSG, self, message))

    def toggle_mapping(self):
        self.switch_mode(self.mode_controller.toggle(self.current_mode))

    def begin_placement(self, kind):
        self.switch_mode(self.EDIT_MODE)
        self.pending_control = kind
        self.canvas.grab_focus()
        self.canvas.set_cursor_from_name("crosshair")
        name = self.widget_factory.get_widget_metadata(kind)["name"]
        self.show_notification(_("Click to place %s · Esc to cancel") % name)

    def _cancel_placement(self):
        self.pending_control = None
        self.canvas.set_cursor(None)

    def _on_canvas_press(self, gesture, count, x, y):
        if self.pending_control is None:
            if self.current_mode == self.MAPPING_MODE:
                self.canvas.grab_focus()
            return
        widget = self.widget_factory.create_widget(self.pending_control)
        self._cancel_placement()
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        if widget:
            width, height = self.screen_geometry.get_host_resolution()
            left = max(0, min(x - widget.width / 2, width - widget.width))
            top = max(0, min(y - widget.height / 2, height - widget.height))
            self.create_widget_at_position(widget, round(left), round(top))
            widget.grab_focus()

    def _on_mode_changed(self, widget, pspec):
        self._cancel_placement()
        super()._on_mode_changed(widget, pspec)
        self.set_title(_("Waydroid Emulator"))
        self.toolbar.sync_mode()

    def _on_shortcut(self, controller, keyval, keycode, state):
        if keyval == Gdk.KEY_Escape and self.pending_control:
            self._cancel_placement()
            return True
        if keyval == Gdk.KEY_F9:
            self.tools.screenshot()
            return True
        if keyval == Gdk.KEY_0 and state & Gdk.ModifierType.CONTROL_MASK:
            self.toolbar.volume.popup()
            return True
        if keyval in (Gdk.KEY_g, Gdk.KEY_G) and state == Gdk.ModifierType.ALT_MASK:
            self.toggle_mini()
            return True
        if keyval == Gdk.KEY_F11:
            self.toggle_fullscreen()
            return True
        return False

    def _reveal_fullscreen_control(self, frame_motion, x, y):
        self.exit_fullscreen.set_visible(self.is_fullscreen() and y < 54)

    def toggle_fullscreen(self):
        self._cancel_pending_resize()
        if self.is_fullscreen():
            self.unfullscreen()
        else:
            # A non-resizable xdg toplevel advertises a maximum size equal to
            # its natural size. Drop that constraint before GNOME configures
            # the fullscreen surface, then restore it on leaving fullscreen.
            self.set_resizable(True)
            self.viewport.set_size_request(-1, -1)
            self.fullscreen()

    def _fullscreen_changed(self, *_):
        fullscreen = self.is_fullscreen()
        self.toolbar.set_visible(not fullscreen)
        self.exit_fullscreen.set_visible(fullscreen)
        if not fullscreen:
            self.set_resizable(False)
            self._set_width(self.windowed_width)
        self._update_resize_handles()

    def toggle_mini(self):
        if self.is_fullscreen():
            self.unfullscreen()
        if self.mini_width is None:
            self.mini_width = self.windowed_width
            self._set_width(360)
        else:
            width, self.mini_width = self.mini_width, None
            self._set_width(width)

    def _add_resize_handles(self, decoration):
        # Cover the title bar and the display with narrow input-only strips.
        # Add the corners last so a diagonal drag wins where strips meet.
        start, end, fill = Gtk.Align.START, Gtk.Align.END, Gtk.Align.FILL
        handles = []
        for cursor, horizontal, vertical, anchor in (
            ("n", fill, start, "BOTTOM"),
            ("s", fill, end, "TOP"),
            ("w", start, fill, "RIGHT"),
            ("e", end, fill, "LEFT"),
            ("nw", start, start, "BOTTOM_RIGHT"),
            ("ne", end, start, "BOTTOM_LEFT"),
            ("sw", start, end, "TOP_RIGHT"),
            ("se", end, end, "TOP_LEFT"),
        ):
            thickness = 14 if horizontal != fill and vertical != fill else 7
            handle = Gtk.Box(halign=horizontal, valign=vertical)
            handle.set_size_request(
                -1 if horizontal == fill else thickness,
                -1 if vertical == fill else thickness,
            )
            handle.set_cursor_from_name(cursor + "-resize")
            drag = Gtk.GestureDrag(button=Gdk.BUTTON_PRIMARY)
            drag.connect("drag-begin", self._begin_resize, cursor, anchor)
            drag.connect("drag-update", self._resize, cursor)
            handle.add_controller(drag)
            decoration.add_overlay(handle)
            handles.append(handle)
        return handles

    def _begin_resize(self, gesture, x, y, edge, anchor):
        self._cancel_pending_resize()
        self._drag_width = self.viewport.get_width()
        self._drag_height = self.viewport.get_height()
        self._drag_origin = gesture.get_current_event().get_position()[1:]
        self._resize_frame = None
        if hasattr(self, "set_gravity"):
            self.set_gravity(getattr(Gtk.WindowGravity, anchor))
        gesture.set_state(Gtk.EventSequenceState.CLAIMED)
        logger.debug("Emulator resize from %s at width %d", edge, self._drag_width)

    def _resize(self, gesture, offset_x, offset_y, edge):
        # GTK synthesizes untimed motion events when a layout moves the
        # resize handle under a stationary pointer. Replaying their stale
        # surface coordinates after changing gravity causes a resize loop.
        event = gesture.get_current_event()
        if event is None or event.get_time() == Gdk.CURRENT_TIME:
            return
        # Pointer coordinates are relative to the current surface. On a west
        # or north drag the compositor shifts its origin to keep the opposite
        # edge fixed. Subtract the committed size delta to recover the
        # pointer displacement relative to the start of the gesture.
        ok, x, y = event.get_position()
        if ok:
            map_w, map_h = self.viewport.mapping_size

            def width_at(origin):
                dx, dy = x - self._drag_origin[0], y - self._drag_origin[1]
                if hasattr(self, "set_gravity"):
                    if "w" in edge:
                        dx -= origin[0] - self._drag_width
                    if "n" in edge:
                        dy -= origin[1] - self._drag_height
                return self.viewport.drag_width(
                    self._drag_width, map_h / map_w, edge, dx, dy
                )

            self._cancel_pending_resize()
            width = width_at((self.viewport.get_width(), self.viewport.get_height()))
            clock = self.get_frame_clock()
            if self._resize_frame is not None:
                timings = clock.get_timings(self._resize_frame)
                if timings is None or not timings.get_complete():
                    # The last motion before a pause may precede presentation
                    # of the new origin. Keep both projections and select the
                    # matching frame once the compositor reports its time.
                    previous = width_at(self._previous_drag_size)
                    self._pending_resize = GLib.timeout_add(
                        30, self._finish_drag_sample, event.get_time(), previous, width
                    )
                    return
            self._apply_drag_width(width)

    def _finish_drag_sample(self, timestamp, previous, current):
        self._pending_resize = 0
        timings = self.get_frame_clock().get_timings(self._resize_frame)
        presented = timings.get_presentation_time() if timings else 0
        # GDK event times are unsigned 32-bit milliseconds. Frame times
        # use the same monotonic clock in microseconds with a wider counter.
        after_present = presented and (timestamp - presented // 1000) % 2**32 < 2**31
        self._apply_drag_width(current if after_present else previous)
        return GLib.SOURCE_REMOVE

    def _apply_drag_width(self, width):
        if round(width) != self.windowed_width:
            self._previous_drag_size = (
                self.viewport.get_width(),
                self.viewport.get_height(),
            )
            self._set_width(width, dragging=True)
            self._resize_frame = self.get_frame_clock().get_frame_counter() + 1

    def _cancel_pending_resize(self):
        if self._pending_resize:
            GLib.source_remove(self._pending_resize)
            self._pending_resize = 0

    def _update_resize_handles(self, *_):
        enabled = not self.preferences.get_boolean("emulator-lock-size")
        for handle in self.resize_handles:
            handle.set_visible(
                enabled and not self.is_fullscreen() and not self.is_maximized()
            )

    def open_display_settings(self):
        if self.display_dialog:
            self.display_dialog.present()
            return
        self.run_device_action(self._open_display_settings)

    def _selected_mode(self):
        values = self.preferences.get_value("emulator-display-mode").unpack()
        return DisplayMode(*values) if all(n > 0 for n in values) else None

    async def _open_display_settings(self):
        mode = self._selected_mode() or await read_mode(
            self.scrcpy_lifecycle.adb_helper.serial
        )
        if self.display_dialog is None:
            self.display_dialog = DisplaySettings(self, mode)
            self.display_dialog.connect(
                "destroy", lambda *_: setattr(self, "display_dialog", None)
            )
        self.display_dialog.present()

    def run_device_action(self, callback):
        if not self.server.connected_event.is_set() or self.restarting:
            self.show_notification(_("Android input is not connected."))
            return

        async def execute():
            try:
                await callback()
            except Exception as error:
                logger.exception("Emulator device action failed")
                self.show_notification(str(error))

        asyncio.create_task(execute())

    async def apply_display_mode(self, mode):
        value = GLib.Variant("(iii)", (mode.width, mode.height, mode.dpi))
        await stage_mode(
            mode,
            self.get_surface().get_scale(),
            lambda: self.preferences.set_value("emulator-display-mode", value),
        )
        logger.info("Staged embedded Android display mode %s", mode)

    def request_restart(self, message=None):
        if self.restarting or self._is_closing or self.restart_dialog:
            return
        dialog = self.restart_dialog = MessageDialog(
            heading=_("Restart device"),
            body=message or _("Open Android apps will close."),
            parent=self,
        )
        dialog.add_response(Gtk.ResponseType.CANCEL, _("Later"))
        dialog.add_response(Gtk.ResponseType.OK, _("Restart"))
        dialog.set_default_response(Gtk.ResponseType.CANCEL)

        def respond(_dialog, response):
            self.restart_dialog = None
            if (
                response in (Gtk.ResponseType.OK, Gtk.ResponseType.OK.value_nick)
                and not self.restarting
            ):
                self.restarting = True
                self.start_restart = asyncio.create_task(self._restart())

        dialog.connect("response", respond)
        dialog.present()

    async def _restart(self):
        try:
            if self.startup:
                self.startup.cancel()
                await asyncio.gather(self.startup, return_exceptions=True)
            self.recorder.stop()
            await self.tools.finish()
            await self.cleanup_scrcpy()
            await self.session.close()
            if self.server.connected_event.is_set():
                await asyncio.wait_for(self.server.disconnected_event.wait(), 10)
            self.startup = None
            self._start_if_idle()
        except Exception as error:
            logger.exception("Could not restart embedded Waydroid")
            self.status.set_label(str(error))
            self.status_box.set_visible(True)
            self.retry.set_visible(True)
        finally:
            self.restarting = False

    def restore_size(self):
        self.mini_width = None
        if self.is_fullscreen():
            self.unfullscreen()
        self._set_width(self.viewport.DEFAULT_WINDOW_SIZE[0])

    def _set_width(self, width, *, dragging=False):
        if not dragging:
            self._cancel_pending_resize()
            if hasattr(self, "set_gravity"):
                self.set_gravity(Gtk.WindowGravity.TOP_LEFT)
        monitor = (
            self.get_display().get_monitor_at_surface(self.get_surface())
            if self.get_surface()
            else None
        )
        map_w, map_h = self.viewport.mapping_size
        max_width = self.viewport.DEFAULT_WINDOW_SIZE[0] * 4
        if monitor:
            geometry = monitor.get_geometry()
            max_width = min(
                geometry.width - 24, (geometry.height - 100) * map_w // map_h
            )
        min_width = max(360, self.toolbar.measure(Gtk.Orientation.HORIZONTAL, -1)[0])
        self.windowed_width = max(min_width, min(round(width), max_width))
        height = round(self.windowed_width * map_h / map_w)
        # GTK/Wayland has no aspect-ratio hint for an interactive toplevel
        # resize. Pin both content dimensions in one allocation so even an
        # intermediate frame fits the guest without stretching or black bars.
        self.viewport.set_size_request(self.windowed_width, height)
        self.set_default_size(1, 1)

    def _on_close_request(self, window):
        if self._is_closing:
            return True
        if not self.preferences.get_boolean("emulator-confirm-close"):
            self.request_shutdown()
            return True
        if self.close_dialog is not None:
            self.close_dialog.present()
            return True
        dialog = self.close_dialog = MessageDialog(
            heading=_("Close Waydroid?"),
            body=_("Open Android apps will close."),
            parent=self,
        )
        skip = Gtk.CheckButton(label=_("Do not ask again"))
        if isinstance(dialog, Gtk.MessageDialog):
            dialog.get_message_area().append(skip)
        else:
            dialog.set_extra_child(skip)
        dialog.add_response(Gtk.ResponseType.CANCEL, _("Cancel"))
        dialog.add_response(Gtk.ResponseType.OK, _("Close"))
        dialog.set_default_response(Gtk.ResponseType.CANCEL)
        dialog.set_response_appearance(Gtk.ResponseType.OK, "destructive-action")

        def respond(_dialog, response):
            self.close_dialog = None
            if response in (Gtk.ResponseType.OK, Gtk.ResponseType.OK.value_nick):
                if skip.get_active():
                    self.preferences.set_boolean("emulator-confirm-close", False)
                self.request_shutdown()

        dialog.connect("response", respond)
        dialog.present()
        return True

    async def _shutdown(self):
        self._cancel_pending_resize()
        self.gamepad.close()
        if self.preferences.get_boolean("emulator-remember-size"):
            self.preferences.set_int(
                "emulator-window-width", self.mini_width or self.windowed_width
            )
        if self.restarting:
            self.start_restart.cancel()
            await asyncio.gather(self.start_restart, return_exceptions=True)
        if self.resolution_refresh:
            self.resolution_refresh.cancel()
        if self.startup:
            self.startup.cancel()
            await asyncio.gather(self.startup, return_exceptions=True)
        self.on_clear_widgets(None)
        try:
            self.recorder.stop()
            await self.tools.finish()
            await self.cleanup_scrcpy()
            await self.close_server()
        finally:
            try:
                await self.session.close()
            except Exception:
                logger.exception("Failed to close session on %s", self.session.socket)
            finally:
                self.viewport.detach()
                self.destroy()
