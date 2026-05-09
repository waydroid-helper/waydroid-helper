"""
基础组件模块
"""

__all__ = ["BaseWidget"]

def __getattr__(name: str):
    """Expose BaseWidget lazily so helper modules can be imported alone."""
    if name == "BaseWidget":
        from .base_widget import BaseWidget

        return BaseWidget

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
