from __future__ import annotations

from waydroid_helper.controller.app.workspace_manager import WorkspaceManager
from waydroid_helper.controller.core.event_bus import Event, EventBus, EventType


class FakeWidget:
    def __init__(self, width: int = 40, height: int = 30, selected: bool = False):
        self.width = width
        self.height = height
        self.is_selected = selected
        self.deleted = False
        self.selection_history: list[bool] = []
        self.clicked: list[tuple[int, int]] = []
        self._parent = None

    def get_allocated_width(self):
        return self.width

    def get_allocated_height(self):
        return self.height

    def get_parent(self):
        return self._parent

    def get_next_sibling(self):
        if self._parent is None:
            return None
        siblings = self._parent.children
        index = siblings.index(self)
        return siblings[index + 1] if index + 1 < len(siblings) else None

    def set_selected(self, selected: bool):
        self.is_selected = selected
        self.selection_history.append(selected)

    def on_delete(self):
        self.deleted = True

    def on_widget_clicked(self, x, y):
        self.clicked.append((x, y))


class ResizeWidget(FakeWidget):
    def __init__(self, width: int = 40, height: int = 30, selected: bool = False):
        super().__init__(width, height, selected)
        self.resize_released = False

    def supports_resizing(self):
        return True

    def on_resize_release(self):
        self.resize_released = True


class FakeFixed:
    def __init__(self):
        self.children: list[FakeWidget] = []
        self.positions: dict[FakeWidget, tuple[int, int]] = {}

    def add(self, widget: FakeWidget, x: int, y: int):
        self.children.append(widget)
        widget._parent = self
        self.positions[widget] = (x, y)

    def put(self, widget: FakeWidget, x: int, y: int):
        self.add(widget, x, y)

    def move(self, widget: FakeWidget, x: int, y: int):
        self.positions[widget] = (x, y)

    def remove(self, widget: FakeWidget):
        self.children.remove(widget)
        self.positions.pop(widget, None)
        widget._parent = None

    def get_first_child(self):
        return self.children[0] if self.children else None

    def get_child_position(self, widget: FakeWidget):
        return self.positions[widget]


class FakeWindow:
    def __init__(self, fixed: FakeFixed):
        self.fixed = fixed
        self.unregistered_widgets: list[FakeWidget] = []
        self.created_widgets: list[tuple[FakeWidget, int, int]] = []

    def unregister_widget_key_mapping(self, widget: FakeWidget):
        self.unregistered_widgets.append(widget)
        return True

    def fixed_put(self, widget: FakeWidget, x: int, y: int):
        self.fixed.put(widget, x, y)

    def fixed_move(self, widget: FakeWidget, x: int, y: int):
        self.fixed.move(widget, x, y)

    def create_widget_at_position(self, widget: FakeWidget, x: int, y: int):
        self.created_widgets.append((widget, x, y))
        self.fixed.add(widget, x, y)

    def get_allocated_width(self):
        return 800

    def get_allocated_height(self):
        return 600

    def set_cursor(self, cursor):
        return None


def make_manager():
    fixed = FakeFixed()
    bus = EventBus()
    window = FakeWindow(fixed)
    manager = WorkspaceManager(window, fixed, bus)
    return manager, fixed, window, bus


def test_hit_testing_prefers_last_matching_widget():
    manager, fixed, _, bus = make_manager()
    bottom = FakeWidget(width=100, height=100)
    top = FakeWidget(width=100, height=100)
    fixed.add(bottom, 0, 0)
    fixed.add(top, 0, 0)

    try:
        assert manager.get_widget_at_position(20, 20) is top
    finally:
        bus.clear()


def test_clear_all_selections_can_keep_current_widget_selected():
    manager, fixed, _, bus = make_manager()
    first = FakeWidget(selected=True)
    current = FakeWidget(selected=True)
    fixed.add(first, 0, 0)
    fixed.add(current, 50, 0)
    manager.selected_widget = first
    manager.pending_resize_direction = "se"

    try:
        manager.clear_all_selections(exclude_widget=current)

        assert first.is_selected is False
        assert current.is_selected is True
        assert manager.selected_widget is None
        assert manager.pending_resize_direction is None
    finally:
        bus.clear()


def test_primary_press_on_blank_space_clears_selection():
    manager, fixed, _, bus = make_manager()
    selected = FakeWidget(selected=True)
    fixed.add(selected, 0, 0)

    try:
        manager.handle_primary_press(n_press=1, x=100, y=100)

        assert selected.is_selected is False
        assert manager.selected_widget is None
    finally:
        bus.clear()


def test_primary_press_on_widget_selects_and_notifies_click():
    manager, fixed, _, bus = make_manager()
    widget = FakeWidget(width=100, height=100)
    fixed.add(widget, 10, 20)

    try:
        manager.handle_primary_press(n_press=1, x=30, y=50)

        assert widget.is_selected is True
        assert widget.clicked == [(20, 30)]
        assert manager.selected_widget is widget
    finally:
        bus.clear()


def test_pointer_release_resets_resize_session():
    manager, fixed, _, bus = make_manager()
    widget = ResizeWidget()
    fixed.add(widget, 0, 0)
    manager.resizing_widget = widget
    manager.resize_direction = "se"

    try:
        manager.handle_pointer_release()

        assert widget.resize_released is True
        assert manager.resizing_widget is None
        assert manager.resize_direction is None
    finally:
        bus.clear()


def test_create_widget_event_validates_payload_and_creates_widget():
    _, fixed, window, bus = make_manager()
    widget = FakeWidget()

    try:
        bus.emit(
            Event(
                EventType.CREATE_WIDGET,
                object(),
                {"widget": widget, "x": 7, "y": 9},
            )
        )

        assert window.created_widgets == [(widget, 7, 9)]
        assert fixed.children == [widget]
    finally:
        bus.clear()


def test_delete_widget_event_removes_specific_widget():
    _, fixed, window, bus = make_manager()
    widget = FakeWidget()
    fixed.add(widget, 0, 0)

    try:
        bus.emit(Event(EventType.DELETE_WIDGET, object(), widget))

        assert fixed.children == []
        assert window.unregistered_widgets == [widget]
        assert widget.deleted is True
    finally:
        bus.clear()


def test_delete_selected_widgets_removes_mappings_and_resets_interaction_state():
    manager, fixed, window, bus = make_manager()
    first = FakeWidget(selected=True)
    second = FakeWidget(selected=False)
    third = FakeWidget(selected=True)
    fixed.add(first, 0, 0)
    fixed.add(second, 50, 0)
    fixed.add(third, 100, 0)
    manager.dragging_widget = first
    manager.resizing_widget = third
    manager.selected_widget = first
    manager.drag_start_x = 5
    manager.drag_start_y = 5
    manager.pending_resize_direction = "se"

    try:
        manager.delete_selected_widgets()

        assert fixed.children == [second]
        assert window.unregistered_widgets == [first, third]
        assert first.deleted is True
        assert third.deleted is True
        assert second.deleted is False
        assert manager.dragging_widget is None
        assert manager.resizing_widget is None
        assert manager.selected_widget is None
        assert manager.drag_start_x == 0
        assert manager.drag_start_y == 0
        assert manager.pending_resize_direction is None
    finally:
        bus.clear()
