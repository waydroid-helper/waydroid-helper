from unittest.mock import MagicMock

import pytest

gi = pytest.importorskip("gi")
gi.require_version("Gtk", "4.0")
gi.require_version("Gdk", "4.0")
gi.require_version("Adw", "1")
from gi.repository import Adw, Gdk, Gtk

from waydroid_helper.controller.app.emulator_tabs import EmulatorTabs
from waydroid_helper.controller.app.emulator_toolbar import EmulatorToolbar


@pytest.fixture
def adwaita():
    if not Gtk.init_check() or not Gdk.Display.get_default():
        pytest.skip("GTK display unavailable")
    Adw.init()


@pytest.fixture
def tab_strip(adwaita):
    actions = []
    tabs = EmulatorTabs(
        lambda: actions.append("home"), lambda *args: actions.append(args)
    )
    return tabs, actions


def descendants(widget):
    yield widget
    child = widget.get_first_child()
    while child:
        yield from descendants(child)
        child = child.get_next_sibling()


def test_android_focus_keeps_order_and_separate_tasks_for_one_package(tab_strip):
    tabs, actions = tab_strip
    first = {"id": 1, "package": "test.documents"}
    second = {"id": 2, "package": "test.documents"}
    tabs.update_tasks([first], 1)
    original = tabs.pages[1]
    tabs.update_tasks([second, first], 2)
    tabs.update_tasks([first, second], 1)
    assert tabs.view.get_n_pages() == 3
    assert tabs.view.get_nth_page(1) == original == tabs.view.get_selected_page()
    assert tabs.view.get_nth_page(2) == tabs.pages[2]
    assert actions == []
    tabs.view.set_selected_page(tabs.pages[2])
    tabs.view.set_selected_page(tabs.home_page)
    assert actions == [("focus", 2), "home"]


def test_close_waits_for_android_and_keeps_home(tab_strip):
    tabs, actions = tab_strip
    app = {"id": 7, "package": "test.missing.launcher"}
    tabs.update_tasks([app], 7)
    tabs.view.close_page(tabs.pages[7])
    assert actions == [("close", 7)]
    assert tabs.view.get_selected_page() == tabs.pages[7]
    tabs.update_tasks([], 0)
    tabs.view.close_page(tabs.home_page)
    assert tabs.view.get_n_pages() == 1
    assert tabs.view.get_selected_page() == tabs.home_page
    assert actions == [("close", 7)]


def test_home_tab_displays_its_native_caption(tab_strip):
    tabs, _ = tab_strip
    tabs.update_tasks([{"id": 4, "package": "test.app"}], 4)
    assert tabs.home_page.get_title() == "Waydroid"
    assert any(
        isinstance(widget, Gtk.Label)
        and widget.get_text() == "Waydroid"
        and widget.is_visible()
        for widget in descendants(tabs.tab_bar)
    )


@pytest.mark.parametrize("app_count", [1, 2, 4, 8])
def test_home_and_application_tabs_share_allocation(tab_strip, app_count):
    tabs, actions = tab_strip
    apps = [{"id": index + 1, "package": "test.app"} for index in range(app_count)]
    tabs.update_tasks(apps, 1)
    for width in (360, 580, 900):
        tabs.bar.allocate(width, 46, -1, None)
        native_tabs = [
            widget
            for widget in descendants(tabs.tab_bar)
            if widget.get_accessible_role() == Gtk.AccessibleRole.TAB
        ]
        assert len(native_tabs) == app_count + 1
        widths = [tab.get_width() for tab in native_tabs]
        assert min(widths) > native_tabs[0].get_height()
        assert max(widths) - min(widths) <= 1
        assert len({tab.get_height() for tab in native_tabs}) == 1
    assert actions == []


def test_reordering_keeps_home_first_and_the_selected_task(tab_strip):
    tabs, actions = tab_strip
    apps = [{"id": i, "package": "test.app"} for i in (1, 2)]
    tabs.update_tasks(apps, 2)
    tabs.view.reorder_page(tabs.home_page, 2)
    assert tabs.view.get_nth_page(0) == tabs.home_page
    tabs.view.reorder_page(tabs.pages[2], 0)
    assert tabs.view.get_nth_page(0) == tabs.home_page
    assert tabs.view.get_nth_page(1) == tabs.pages[2]
    assert tabs.view.get_selected_page() == tabs.pages[2]
    assert actions == []


def test_compact_picker_reserves_space_across_guest_launch_and_exit(tab_strip):
    tabs, actions = tab_strip
    tabs.set_compact(True)
    assert tabs.menu.get_visible() and not tabs.menu.get_sensitive()
    tabs.update_tasks([{"id": 4, "package": "test.app"}], 4)
    assert tabs.menu.get_visible() and tabs.menu.get_sensitive()
    assert tabs.tab_bar.get_visible()
    assert tabs.view.get_nth_page(0) == tabs.home_page
    assert tabs.view.get_n_pinned_pages() == 0
    assert tabs.home_page.get_icon().get_names()[0] == "waydroid"
    tabs.update_tasks([], 0)
    assert tabs.menu.get_visible() and not tabs.menu.get_sensitive()
    tabs.set_compact(False)
    assert tabs.tab_bar.get_visible()
    assert actions == []


def test_narrow_header_keeps_one_row_and_the_selected_page(adwaita):
    toolbar = EmulatorToolbar(MagicMock())
    toolbar.tabs.update_tasks([{"id": 3, "package": "test.app"}], 3)
    page = toolbar.tabs.view.get_selected_page()
    for width, compact in ((904, False), (390, True), (904, False)):
        toolbar.set_compact(compact)
        height = toolbar.widget.measure(Gtk.Orientation.VERTICAL, width).natural
        toolbar.widget.allocate(width, height, -1, None)
        _, tabs = toolbar.tabs.bar.compute_bounds(toolbar.widget)
        _, controls = toolbar.header.compute_bounds(toolbar.widget)
        assert tabs.get_y() == controls.get_y()
        assert tabs.get_x() + tabs.get_width() <= controls.get_x() + 1
        assert toolbar.tabs.view.get_selected_page() == page
        assert toolbar.back.get_visible() == (not compact)
        assert toolbar.fullscreen_button.get_visible() == (not compact)
