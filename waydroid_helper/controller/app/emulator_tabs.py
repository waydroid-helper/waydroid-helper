"""Native title-bar tabs sharing one Android compositor and key-mapping canvas."""

from gettext import gettext as _

from gi.repository import Adw, Gio, GLib, Gtk

try:
    from gi.repository.GioUnix import DesktopAppInfo
except ImportError:  # GLib before 2.80 exposes this type in Gio.
    from gi.repository.Gio import DesktopAppInfo


class EmulatorTabs:
    def __init__(self, home, task_action):
        self.home = home
        self.task_action = task_action
        self.pages = {}
        self.compact = False

        # The pages provide identities for the native tab bar. The actual
        # Android surface stays in the viewport across task switches, so no
        # page owns or reparents the compositor or its input overlay.
        self.view = Adw.TabView(visible=False)
        if hasattr(self.view, "set_shortcuts"):
            self.view.set_shortcuts(Adw.TabViewShortcuts(0))
        # Native pinned pages are allocated in a separate, icon-sized strip.
        # Keep Home in the ordinary page group so the same layout pass divides
        # the available width among Home and the Android tasks.
        self.home_page = self.view.append(Gtk.Box())
        self.home_page.set_title("Waydroid")
        self.home_page.set_tooltip(_("Android Home"))
        self.home_page.set_icon(
            Gio.ThemedIcon.new_from_names(
                ["waydroid", "com.jaoushingan.WaydroidHelper"]
            )
        )
        self.tab_bar = Adw.TabBar(
            view=self.view, autohide=False, expand_tabs=False, hexpand=True
        )
        self.tab_bar.add_css_class("inline")
        self._hide_home_close_button(self.tab_bar)
        self.bar = Gtk.Box(spacing=2, hexpand=True)
        self.bar.append(self.view)
        self.bar.append(self.tab_bar)

        self.menu = Gtk.Box(visible=False)
        self.popover = Gtk.Popover()
        self.popover.connect("show", lambda *_: self._populate_menu())
        if hasattr(Adw, "TabButton"):
            self.picker = Adw.TabButton(view=self.view)
            self.picker.connect("clicked", lambda *_: self.popover.popup())
            self.menu.append(self.picker)
            self.menu.append(self.popover)
        else:  # AdwTabButton was introduced in libadwaita 1.3.
            self.picker = Gtk.MenuButton(icon_name="pan-down-symbolic")
            self.picker.set_popover(self.popover)
            self.menu.append(self.picker)
        self.picker.set_tooltip_text(_("Open applications"))
        self.bar.append(self.menu)

        self.selected_handler = self.view.connect(
            "notify::selected-page", self._selected
        )
        self.view.connect("close-page", self._close_requested)
        self.view.connect("page-reordered", self._keep_home_first)
        self.tab_bar.connect("notify::is-overflowing", lambda *_: self._update_picker())

        # Home and Recents share a guest task. A second click on the selected
        # Home tab must still send KEYCODE_HOME, even without a page change.
        click = Gtk.GestureClick(button=1)
        click.set_propagation_phase(Gtk.PropagationPhase.CAPTURE)
        click.connect("pressed", self._press_selected_home)
        self.tab_bar.add_controller(click)

    def _hide_home_close_button(self, widget):
        # AdwTabPage has no per-page close-button property. Only Home exists
        # when the bar is created. Suppress its close affordance independently
        # of the close-page veto, which also covers middle-click and shortcuts.
        if widget.has_css_class("tab-close-button"):
            widget.set_visible(False)
            widget.connect(
                "notify::visible", lambda button, _: button.set_visible(False)
            )
            return True
        child = widget.get_first_child()
        while child:
            if self._hide_home_close_button(child):
                return True
            child = child.get_next_sibling()
        return False

    def _keep_home_first(self, view, page, position):
        if view.get_nth_page(0) != self.home_page:
            view.reorder_page(self.home_page, 0)

    def _press_selected_home(self, gesture, count, x, y):
        if count != 1 or self.view.get_selected_page() != self.home_page:
            return
        target = self.tab_bar.pick(x, y, Gtk.PickFlags.DEFAULT)
        while target and target != self.tab_bar:
            if target.get_accessible_role() == Gtk.AccessibleRole.TAB:
                if target.get_state_flags() & Gtk.StateFlags.SELECTED:
                    self.home()
                break
            target = target.get_parent()

    def _selected(self, view, _pspec):
        page = view.get_selected_page()
        if page == self.home_page:
            self.home()
        elif page:
            self.task_action("focus", page.task_id)

    def _close_requested(self, view, page):
        if page == self.home_page:
            view.close_page_finish(page, False)
            return True
        if page.task_id not in self.pages:
            return False  # Android confirmed removal. Finish the native close.
        # Closing Android tasks is asynchronous. Leave the tab usable if the
        # command fails; remove it only when it disappears from a guest snapshot.
        view.close_page_finish(page, False)
        self.task_action("close", page.task_id)
        return True

    def set_compact(self, compact):
        if self.compact == compact:
            return
        self.compact = compact
        self._update_picker()

    def _update_picker(self):
        self.menu.set_visible(self.compact or self.tab_bar.get_is_overflowing())
        self.menu.set_sensitive(bool(self.pages))

    def _populate_menu(self):
        rows = Gtk.ListBox(selection_mode=Gtk.SelectionMode.NONE)
        rows.add_css_class("boxed-list")
        rows.set_size_request(256, -1)
        for index in range(self.view.get_n_pages()):
            page = self.view.get_nth_page(index)
            row = Adw.ActionRow(
                title=GLib.markup_escape_text(page.get_title()), activatable=True
            )
            row.set_title_lines(1)
            row.add_prefix(Gtk.Image(gicon=page.get_icon(), pixel_size=20))
            if page == self.view.get_selected_page():
                row.add_suffix(Gtk.Image(icon_name="object-select-symbolic"))
            if page != self.home_page:
                close = Gtk.Button(
                    icon_name="window-close-symbolic",
                    tooltip_text=_("Close %s") % page.get_title(),
                    valign=Gtk.Align.CENTER,
                    focus_on_click=False,
                )
                close.add_css_class("flat")
                close.add_css_class("circular")
                close.connect(
                    "clicked", lambda _button, p=page: self._menu_action(p, True)
                )
                row.add_suffix(close)
            row.connect("activated", lambda _row, p=page: self._menu_action(p, False))
            rows.append(row)
        scroll = Gtk.ScrolledWindow(
            hscrollbar_policy=Gtk.PolicyType.NEVER,
            max_content_height=320,
            propagate_natural_height=True,
        )
        scroll.set_child(rows)
        self.popover.set_child(scroll)

    def _menu_action(self, page, close):
        self.popover.popdown()
        if close:
            self.view.close_page(page)
        elif page == self.home_page and page == self.view.get_selected_page():
            self.home()
        else:
            self.view.set_selected_page(page)

    def update_tasks(self, apps, active):
        # AdwTabView automatically selects a neighbour when removing a page.
        # Reconcile the entire snapshot with notifications blocked so Android
        # never receives a focus request as a side effect of its own update.
        with self.view.handler_block(self.selected_handler):
            ids = {app["id"] for app in apps}
            for task_id in self.pages.keys() - ids:
                self.view.close_page(self.pages.pop(task_id))
            for app in reversed(apps):
                task_id, package = app["id"], app["package"]
                if task_id in self.pages:
                    continue
                try:
                    entry = DesktopAppInfo.new(f"waydroid.{package}.desktop")
                except TypeError:  # A task may have no exported launcher entry.
                    entry = None
                page = self.view.append(Gtk.Box())
                page.task_id = task_id
                page.set_title(entry.get_display_name() if entry else package)
                page.set_icon(
                    (entry.get_icon() if entry else None)
                    or self.view.get_default_icon()
                )
                self.pages[task_id] = page
            self.view.set_selected_page(self.pages.get(active, self.home_page))
        self._update_picker()
        if self.popover.get_visible():
            self._populate_menu()
