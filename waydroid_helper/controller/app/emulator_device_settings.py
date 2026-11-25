"""Device settings and adaptive navigation for the embedded emulator."""

from gettext import gettext as _

from gi.repository import Adw, Gtk

from waydroid_helper.compat_widget import Dialog, ToolbarView
from waydroid_helper.controller.app.emulator_display import DisplaySettingsPage


def performance_page(settings):
    page = Adw.PreferencesPage()
    group = Adw.PreferencesGroup()
    page.add(group)
    values = ("auto", "gl", "vulkan")
    row = Adw.ComboRow(
        title=_("Window renderer"),
        subtitle=_("The window renderer takes effect the next time you open the emulator."),
        model=Gtk.StringList.new([_("Automatic"), "OpenGL", "Vulkan"]),
    )
    key = "emulator-window-renderer"
    row.set_selected(values.index(settings.get_string(key)))
    row.connect("notify::selected",
                lambda row, _: settings.set_string(key, values[row.get_selected()]))
    group.add(row)
    return page


class DeviceSettings(Dialog):
    def __init__(self, parent):
        super().__init__(
            title=_("Device settings"), parent=parent, content_width=820, content_height=540
        )
        self.parent_window = parent
        # A transient GTK window can unmap before its final reference is
        # released. Clear the owner's reference as soon as it disappears.
        self.connect("unmap" if isinstance(self, Gtk.Window) else "closed", self._closed)

        self.stack = Adw.ViewStack()
        self.display = DisplaySettingsPage(
            self, parent.selected_display_mode(), parent.default_display_mode()
        )
        self.sync_display_mode()
        theme = Gtk.IconTheme.get_for_display(self.get_display())
        for child, name, title, symbolic, fallback in (
            (performance_page(parent.preferences), "performance", _("Performance"),
             "power-profile-performance-symbolic", "utilities-system-monitor"),
            (self.display, "display", _("Display"), "video-display-symbolic", "video-display"),
        ):
            page = self.stack.add_titled(child, name, title)
            page.set_icon_name(symbolic if theme.has_icon(symbolic) else fallback)

        if hasattr(Adw, "ViewSwitcherSidebar"):
            self.set_content(self._split_view())
        else:
            # Older libadwaita versions expose the same stack and pages
            # through their native tab switcher.
            toolbar = ToolbarView()
            header = Adw.HeaderBar()
            header.set_title_widget(Adw.ViewSwitcher(stack=self.stack))
            toolbar.add_top_bar(header)
            toolbar.set_content(self.stack)
            self.set_content(toolbar)

    def _split_view(self):
        def pane(widget, title):
            toolbar = Adw.ToolbarView()
            toolbar.add_top_bar(Adw.HeaderBar())
            toolbar.set_content(widget)
            return Adw.NavigationPage.new(toolbar, title)

        sidebar = Adw.ViewSwitcherSidebar(stack=self.stack)
        content = pane(self.stack, _("Performance"))
        split = Adw.NavigationSplitView(
            sidebar=pane(sidebar, self.get_title()), content=content,
            min_sidebar_width=160, max_sidebar_width=220,
        )
        def update_title(stack, _):
            content.set_title(stack.get_page(stack.get_visible_child()).get_title())

        self.stack.connect("notify::visible-child", update_title)
        # Activation also fires for the already selected page, so a user
        # returning to the narrow navigation list can reopen the same page.
        sidebar.connect("activated", lambda *_: split.set_show_content(True))
        compact = Adw.Breakpoint.new(Adw.BreakpointCondition.parse("max-width: 600sp"))
        compact.add_setter(split, "collapsed", True)
        compact.add_setter(sidebar, "mode", Adw.SidebarMode.PAGE)
        self.set_size_request(320, 200)
        self.add_breakpoint(compact)
        return split

    def sync_display_mode(self):
        self.display.set_runtime_mode(*self.parent_window.display_state())

    def _closed(self, *_):
        self.parent_window.device_settings = None
