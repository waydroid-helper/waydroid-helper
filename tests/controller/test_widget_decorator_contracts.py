from __future__ import annotations

from waydroid_helper.controller.widgets.base.decorator_contracts import (
    WidgetDecoratorBehavior,
)
from waydroid_helper.controller.widgets.base.draw_overlay import (
    add_decorator_draw_overlay,
)
from waydroid_helper.controller.widgets.decorators.base_decorator import (
    WidgetDecorator,
    widget_decorator,
)


class FakeBehavior(WidgetDecoratorBehavior):
    pass


class FakeDecorator(WidgetDecorator, FakeBehavior):
    BEHAVIOR_CONTRACTS = (FakeBehavior,)

    def _setup_decorator(self):
        self.setup_called = True

    def public_helper_that_must_not_be_copied(self):
        return "leak"


@widget_decorator(FakeDecorator)
class DecoratedFakeWidget:
    def __init__(self):
        self.registered_behaviors = []

    def register_widget_behavior(self, contract, behavior):
        self.registered_behaviors.append((contract, behavior))


def test_widget_decorator_registers_contract_instead_of_copying_public_members():
    widget = DecoratedFakeWidget()

    assert not hasattr(widget, "public_helper_that_must_not_be_copied")
    assert len(widget.registered_behaviors) == 1

    contract, behavior = widget.registered_behaviors[0]
    assert contract is FakeBehavior
    assert isinstance(behavior, FakeDecorator)
    assert behavior.setup_called is True


class FakeDrawWidget:
    def __init__(self):
        self.calls = []
        self.set_draw_func_calls = 0
        self.draw_func = self.original_draw

    def original_draw(self, widget, cr, width, height, user_data):
        self.calls.append(("original", width, height))

    def set_draw_func(self, draw_func, user_data):
        self.set_draw_func_calls += 1
        self.draw_func = draw_func


def test_decorator_draw_overlay_installs_one_wrapper_and_preserves_order():
    widget = FakeDrawWidget()

    add_decorator_draw_overlay(
        widget,
        lambda cr, width, height: widget.calls.append(("first", width, height)),
    )
    add_decorator_draw_overlay(
        widget,
        lambda cr, width, height: widget.calls.append(("second", width, height)),
    )

    widget.draw_func(widget, object(), 10, 20, None)

    assert widget.set_draw_func_calls == 1
    assert widget.calls == [
        ("original", 10, 20),
        ("first", 10, 20),
        ("second", 10, 20),
    ]
