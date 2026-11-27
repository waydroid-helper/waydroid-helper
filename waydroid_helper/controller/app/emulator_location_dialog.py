"""Map picker for the embedded emulator's Virtual location menu item."""

import asyncio
from dataclasses import replace
from gettext import gettext as _

import gi
import httpx

gi.require_version("Shumate", "1.0")
from gi.repository import Adw, GObject, Gtk, Pango, Shumate

from waydroid_helper.compat_widget import ToolbarView
from waydroid_helper.controller.app.emulator_location import Place, coordinate_pair
from waydroid_helper.controller.app.emulator_preferences import add_spin

_AGENT = "Waydroid-Helper (https://github.com/waydroid-helper/waydroid-helper)"


async def search_places(query):
    # Submit only explicit address searches. Map picks and manually entered
    # WGS84 coordinate pairs need no geocoder and work without network access.
    async with httpx.AsyncClient(timeout=10, headers={"User-Agent": _AGENT}) as client:
        response = await client.get("https://photon.komoot.io/api/", params={"q": query, "limit": 6})
        response.raise_for_status()
        features = response.json()["features"]
    results = []
    for feature in features:
        if feature["geometry"]["type"] != "Point":
            continue
        lon, lat = feature["geometry"]["coordinates"]
        info = feature["properties"]
        name = ", ".join(dict.fromkeys(info[key] for key in ("name", "city", "state", "country") if info.get(key)))
        results.append(Place(name, lat, lon))
    return results


class VirtualLocationWindow(Adw.Window):
    def __init__(self, parent, service):
        super().__init__(application=parent.get_application(), transient_for=parent,
                         destroy_with_parent=True, title=_("Virtual location"),
                         default_width=760, default_height=540)
        self.service = service
        self.selection = None
        self.search_task = None
        self.busy = False
        self.closed = False
        self.connect("close-request", lambda *_: self.busy)
        self.connect("unrealize", self._dismissed)
        self.toasts = Adw.ToastOverlay()
        self.set_content(self.toasts)
        view = ToolbarView()
        self.toasts.set_child(view)
        header = Adw.HeaderBar()
        view.add_top_bar(header)

        self.search = Gtk.SearchEntry(placeholder_text=_("Search places or enter latitude, longitude"),
                                      width_chars=32, hexpand=True)
        self.search.connect("activate", self._search)
        self.search.connect("changed", self._cancel_search)
        header.set_title_widget(self.search)
        self.results = Gtk.Popover(autohide=True)
        self.results.set_parent(self.search)
        self.history_popover = Gtk.Popover()
        history_button = Gtk.MenuButton(icon_name="document-open-recent-symbolic",
                                       tooltip_text=_("Location history"), popover=self.history_popover)
        header.pack_end(history_button)
        self.history_popover.connect("show", self._show_history)

        Shumate.set_user_agent(_AGENT)
        self.map = Shumate.SimpleMap.new()
        registry = Shumate.MapSourceRegistry.new_with_defaults()
        self.map.set_map_source(registry.get_by_id(Shumate.MAP_SOURCE_OSM_MAPNIK))
        self.map.set_show_zoom_buttons(True)
        self.loading = Gtk.Spinner(visible=False)
        map_widget = self.map.get_map()
        map_widget.connect("notify::state", self._map_state)
        # Older Shumate releases still display cached tiles and the picker
        # accepts direct coordinates even when the tile service is offline.
        if hasattr(self.map, "get_base_map_layer"):
            layer = self.map.get_base_map_layer()
            if GObject.signal_lookup("map-loaded", layer):
                layer.connect("map-loaded", self._map_loaded)
        viewport = self.map.get_viewport()
        viewport.set_zoom_level(2)
        self.map.get_map().center_on(20, 0)
        self.layer = Shumate.MarkerLayer.new(viewport)
        self.map.add_overlay_layer(self.layer)
        self.marker = Shumate.Marker.new()
        pin = Gtk.Button(icon_name="mark-location-symbolic", can_target=False, focusable=False)
        pin.add_css_class("suggested-action")
        pin.add_css_class("circular")
        self.marker.set_child(pin)
        self.marker.set_visible(False)
        self.layer.add_marker(self.marker)
        click = Gtk.GestureClick(button=1, propagation_phase=Gtk.PropagationPhase.CAPTURE)
        click.connect("pressed", self._press)
        click.connect("stopped", self._discard_press)
        click.connect("released", self._map_click)
        self.map.get_map().add_controller(click)
        self.press = None
        view.set_content(self.map)

        footer = Gtk.Box(spacing=8, margin_top=8, margin_bottom=8, margin_start=12, margin_end=12)
        self.summary = Gtk.Label(xalign=0, hexpand=True, ellipsize=Pango.EllipsizeMode.END)
        footer.append(self.loading)
        footer.append(self.summary)
        details = Gtk.Popover()
        group = Adw.PreferencesGroup()
        group.set_size_request(280, -1)
        self.alt = add_spin(group, _("Altitude (m)"), 0, -12000, 100000, 1, 1)
        self.speed = add_spin(group, _("Speed (m/s)"), 0, 0, 10000, .1, 2)
        self.bearing = add_spin(group, _("Bearing (°)"), 0, 0, 359.99, 1, 2)
        details.set_child(group)
        footer.append(Gtk.MenuButton(icon_name="preferences-system-symbolic",
                                     tooltip_text=_("GPS details"), popover=details))
        self.clear_button = Gtk.Button(label=_("Clear virtual location"))
        self.clear_button.connect("clicked", lambda *_: self._change(False))
        footer.append(self.clear_button)
        self.apply_button = Gtk.Button(label=_("Set location"))
        self.apply_button.add_css_class("suggested-action")
        self.apply_button.connect("clicked", lambda *_: self._change(True))
        footer.append(self.apply_button)
        view.add_bottom_bar(footer)
        if service.history:
            self._select(service.history[0], center=True)
        self._sync()

    def _dismissed(self, *_):
        if self.closed:
            return
        self.closed = True
        self._cancel_search()
        self.results.unparent()

    def _cancel_search(self, *_):
        if self.search_task:
            self.search_task.cancel()
            self.search_task = None
        self.results.popdown()

    def _search(self, *_):
        self._cancel_search()
        query = self.search.get_text().strip()
        if not query:
            return
        try:
            coordinates = coordinate_pair(query)
        except ValueError as error:
            self._toast(str(error))
            return
        if coordinates:
            self._select(coordinates, center=True)
            return
        self.search_task = asyncio.create_task(self._find(query))

    async def _find(self, query):
        try:
            places = await search_places(query)
        except (httpx.HTTPError, ValueError, KeyError):
            self._toast(_("Place search is unavailable. You can still enter coordinates."))
            return
        if self.search.get_text().strip() == query:
            self._choices(self.results, places, _("No places found"))
            self.results.popup()

    def _show_history(self, _popover):
        self._choices(self.history_popover, self.service.history, _("No recent locations"))

    def _choices(self, popover, places, empty):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        if not places:
            box.append(Gtk.Label(label=empty, margin_top=8, margin_bottom=8))
        for place in places:
            text = place.name or self._coordinates(place)
            label = Gtk.Label(label=text, xalign=0, max_width_chars=42, ellipsize=Pango.EllipsizeMode.END)
            button = Gtk.Button(child=label, tooltip_text=text)
            button.add_css_class("flat")
            button.connect("clicked", lambda _, p=place: (self._select(p, center=True), popover.popdown()))
            box.append(button)
        scroll = Gtk.ScrolledWindow(max_content_height=290, propagate_natural_height=True,
                                    propagate_natural_width=True, hscrollbar_policy=Gtk.PolicyType.NEVER)
        scroll.set_child(box)
        popover.set_child(scroll)

    def _map_state(self, map_widget, _property):
        loading = map_widget.get_state() == Shumate.State.LOADING
        self.loading.set_spinning(loading)
        self.loading.set_visible(loading)

    def _map_loaded(self, layer, errors):
        if errors and not self.closed:
            toast = Adw.Toast.new(_("Some map tiles could not be loaded."))
            if hasattr(layer, "retry_failed"):
                toast.set_button_label(_("Retry"))
                toast.connect("button-clicked", lambda *_: layer.retry_failed())
            self.toasts.add_toast(toast)

    def _press(self, _gesture, count, x, y):
        self.press = (x, y) if count == 1 else None

    def _discard_press(self, *_):
        self.press = None

    def _map_click(self, gesture, count, x, y):
        if self.press is not None and count == 1 and not gesture.get_widget().drag_check_threshold(
                int(self.press[0]), int(self.press[1]), int(x), int(y)):
            lat, lon = self.map.get_viewport().widget_coords_to_location(self.map.get_map(), x, y)
            self._select(Place("", lat, lon), center=False)
        self.press = None

    @staticmethod
    def _coordinates(place):
        return f"{place.latitude:.6f}, {place.longitude:.6f}"

    def _select(self, place, *, center):
        self.selection = place
        self.marker.set_location(place.latitude, place.longitude)
        self.marker.set_visible(True)
        if center:
            self.map.get_viewport().set_zoom_level(13)
            self.map.get_map().center_on(place.latitude, place.longitude)
        for spin, number in zip((self.alt, self.speed, self.bearing), place.coordinates[2:]):
            spin.set_value(number)
        self._sync()

    def _sync(self):
        place = self.selection
        summary = self._coordinates(place) if place else _("Select a point on the map")
        if place and self.service.enabled and self.service.history and place == self.service.history[0]:
            summary = _("Current location · %s") % summary
        self.summary.set_label(summary)
        self.summary.set_tooltip_text(place.name if place and place.name else summary)
        self.apply_button.set_sensitive(place is not None and not self.busy)
        self.clear_button.set_sensitive(self.service.enabled and not self.busy)

    def _toast(self, text):
        if not self.closed:
            self.toasts.add_toast(Adw.Toast.new(text))

    def _change(self, enable):
        if self.busy:
            return
        place = self.selection
        if enable:
            place = replace(place, altitude=self.alt.get_value(), speed=self.speed.get_value(),
                            bearing=self.bearing.get_value())
        self.busy = True
        self._sync()
        asyncio.create_task(self._save(place if enable else None))

    async def _save(self, place):
        try:
            if place is None:
                await self.service.clear()
                self._toast(_("Virtual location cleared"))
            else:
                await self.service.set(place)
                if self.selection and self.selection.coordinates[:2] == place.coordinates[:2]:
                    self.selection = place
                self._toast(_("Virtual location set"))
        except Exception as error:
            self._toast(str(error))
        finally:
            self.busy = False
            self._sync()
