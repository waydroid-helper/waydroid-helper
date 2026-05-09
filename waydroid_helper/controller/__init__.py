__all__ = ["TransparentWindow"]

def __getattr__(name: str):
    """Expose app-level window lazily so controller leaf modules stay light."""
    if name == "TransparentWindow":
        from .app.window import TransparentWindow

        return TransparentWindow

    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
