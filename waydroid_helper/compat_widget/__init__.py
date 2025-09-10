import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GLib, Gtk

from .animation_target import PropertyAnimationTarget
from .dialog import Dialog
from .file_dialog import FileDialog
from .header_bar import HeaderBar
from .message_dialog import MessageDialog
from .navigation_page import NavigationPage
from .navigation_view import NavigationView
from .shared_folder_dialog import SharedFolderDialog
from .spinner import Spinner
from .toolbar_view import ToolbarView

GTK_VERSION = Gtk.get_major_version(), Gtk.get_minor_version(), Gtk.get_micro_version()
ADW_VERSION = Adw.get_major_version(), Adw.get_minor_version(), Adw.get_micro_version()
GLIB_VERSION = GLib.MAJOR_VERSION, GLib.MINOR_VERSION, GLib.MICRO_VERSION

__all__ = [
    "NavigationView",
    "NavigationPage",
    "ToolbarView",
    "Spinner",
    "MessageDialog",
    "Dialog",
    "HeaderBar",
    "FileDialog",
    "SharedFolderDialog",
    "GTK_VERSION",
    "ADW_VERSION",
    "GLIB_VERSION",
    "PropertyAnimationTarget"
]
