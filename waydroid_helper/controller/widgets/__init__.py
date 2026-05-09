"""
组件模块
"""

__all__ = ["BaseWidget", "Resizable", "WidgetDecorator", "Editable"]

def __getattr__(name: str):
    """Lazily expose widget conveniences without importing the whole stack.

    Importing submodules such as ``controller.widgets.config`` should not pull in
    BaseWidget, decorators, and their GTK-heavy dependencies. Attribute-level
    loading keeps the public convenience API while making leaf modules easier to
    test and reuse.
    """
    if name == "BaseWidget":
        from .base import BaseWidget

        return BaseWidget

    if name in {"Editable", "Resizable", "WidgetDecorator"}:
        from .decorators import Editable, Resizable, WidgetDecorator

        exports = {
            "Editable": Editable,
            "Resizable": Resizable,
            "WidgetDecorator": WidgetDecorator,
        }
        return exports[name]

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
