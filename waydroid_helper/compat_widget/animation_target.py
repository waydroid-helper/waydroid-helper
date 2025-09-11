# pyright: reportUnknownMemberType=false
# pyright: reportUnknownParameterType=false
# pyright: reportMissingParameterType=false
# pyright: reportRedeclaration=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportAny=false
# pyright: reportCallIssue=false
# pyright: reportMissingSuperCall=false
# pyright: reportGeneralTypeIssues=false
# pyright: reportUntypedBaseClass=false


import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GLib, Gtk

GTK_VERSION = Gtk.get_major_version(), Gtk.get_minor_version(), Gtk.get_micro_version()
ADW_VERSION = Adw.get_major_version(), Adw.get_minor_version(), Adw.get_micro_version()
GLIB_VERSION = GLib.MAJOR_VERSION, GLib.MINOR_VERSION, GLib.MICRO_VERSION


def PropertyAnimationTarget(widget: Gtk.Widget, property_name: str)->Adw.AnimationTarget:
    """
    Compatibility wrapper for Adw.PropertyAnimationTarget.
    
    In libadwaita >= 1.2.0, PropertyAnimationTarget is available.
    In older versions, we use CallbackAnimationTarget as a fallback.
    """
    if ADW_VERSION >= (1, 2, 0):
        # Use the native PropertyAnimationTarget
        return Adw.PropertyAnimationTarget.new(widget, property_name)
    else:
        # Fallback for older versions using CallbackAnimationTarget
        def animation_callback(value):
            widget.set_property(property_name, value)
        
        return Adw.CallbackAnimationTarget.new(animation_callback)
