# pyright: reportAny=false
# pyright: reportAttributeAccessIssue=false,reportUnknownArgumentType=false,reportUnknownMemberType=false

"""
Clean Model Layer for Waydroid Helper

This module implements a clean separation between data models and business logic,
eliminating the complex signal management issues in the original implementation.
"""

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

import asyncio
import enum
from typing import Any
from functools import partial
from gettext import gettext as _

from gi.repository import GObject

from waydroid_helper.util import logger


class ModelState(enum.IntEnum):
    """State of a model component"""
    UNINITIALIZED = 1
    LOADING = 2
    READY = 3
    ERROR = 4


class SessionState(enum.IntEnum):
    """Waydroid session state"""
    LOADING = 0x01
    UNINITIALIZED = 0x02
    STOPPED = 0x04
    RUNNING = 0x08
    CONNECTED = 0x10


class PropertyCategory (enum.IntEnum):
    """Type of a property"""
    PRIVILEGED = 1
    PERSIST = 2
    WAYDROID = 3

def _str_to_bool(s: str) -> bool:
    """Convert string to boolean"""
    s = s.strip().lower()
    return s in ("true", "1", "yes", "on")

def _bool_to_str(b: bool, flag: int = 0) -> str:
    """Convert boolean to string with different formats"""
    if flag == 0:
        return "True" if b else "False"
    elif flag == 1:
        return "true" if b else "false"
    elif flag == 2:
        return "1" if b else "0"
    return str(b)

def categorized_property(*, category=None, transform_in=None, transform_out=None, **kwargs):
    """
    包装 GObject.Property，增加 category 字段
    """
    prop = GObject.Property(**kwargs)
    prop._category = category
    prop._transform_in = transform_in if transform_in is not None else lambda x: x
    prop._transform_out = transform_out if transform_out is not None else lambda x: str(x)
    return prop


class PropertyModel(GObject.Object):
    """
    Clean property model that holds property state without circular dependencies.
    
    This model:
    - Holds the current state of all properties
    - Emits signals when properties change
    - Validates property changes
    - Has no knowledge of UI or SDK layers
    """
    
    state = GObject.Property(type=object)  # For persist props
    privileged_state = GObject.Property(type=object)  # For privileged props
    waydroid_state = GObject.Property(type=object)  # For waydroid config props
    multi_windows = categorized_property(
        type=bool,
        default=False,
        nick="persist.waydroid.multi_windows",
        blurb=_("Enable window integration with the desktop"),
        category=PropertyCategory.PERSIST,
        transform_in=_str_to_bool,
        transform_out=partial(_bool_to_str, flag=1),
   )
    cursor_on_subsurface = categorized_property(
        type=bool,
        default=False,
        nick="persist.waydroid.cursor_on_subsurface",
        blurb=_("Workaround for showing the cursor in multi_windows mode on some compositors"),
        category=PropertyCategory.PERSIST,
        transform_in=_str_to_bool,
        transform_out=partial(_bool_to_str, flag=1),
    )
    invert_colors = categorized_property(
        type=bool,
        default=False,
        nick="persist.waydroid.invert_colors",
        blurb=_("Swaps the color space from RGBA to BGRA"),
        category=PropertyCategory.PERSIST,
        transform_in=_str_to_bool,
        transform_out=partial(_bool_to_str, flag=1),
    )
    suspend = categorized_property(
        type=bool,
        default=False,
        nick="persist.waydroid.suspend",
        blurb=_("Let the Waydroid container sleep when no apps are active"),
        category=PropertyCategory.PERSIST,
        transform_in=_str_to_bool,
        transform_out=partial(_bool_to_str, flag=1),
    )
    uevent = categorized_property(
        type=bool,
        default=False,
        nick="persist.waydroid.uevent",
        blurb=_("Allow android direct access to hotplugged devices"),
        category=PropertyCategory.PERSIST,
        transform_in=_str_to_bool,
        transform_out=partial(_bool_to_str, flag=1),
    )
    fake_touch = categorized_property(
        type=str,
        default="",
        nick="persist.waydroid.fake_touch",
        blurb=_("Interpret mouse inputs as touch inputs"),
        category=PropertyCategory.PERSIST,
    )
    
    fake_wifi = categorized_property(
        type=str,
        default="",
        nick="persist.waydroid.fake_wifi",
        blurb=_("Make the Apps appear as if connected to WiFi"),
        category=PropertyCategory.PERSIST,
    )

    height_padding = categorized_property(
        type=str,
        default="",
        nick="persist.waydroid.height_padding",
        blurb=_("Adjust height padding"),
        category=PropertyCategory.PERSIST,
    )
    
    width_padding = categorized_property(
        type=str,
        default="",
        nick="persist.waydroid.width_padding",
        blurb=_("Adjust width padding"),
        category=PropertyCategory.PERSIST,
    )
    
    height = categorized_property(
        type=str,
        default="",
        nick="persist.waydroid.height",
        blurb=_("Used for user to override desired resolution"),
        category=PropertyCategory.PERSIST,
    )
    
    width = categorized_property(
        type=str,
        default="",
        nick="persist.waydroid.width",
        blurb=_("Used for user to override desired resolution"),
        category=PropertyCategory.PERSIST,
    )
    
    # 其实不是 persist, 但是先放这里
    boot_completed = categorized_property(
        type=bool,
        default=False,
        nick="sys.boot_completed",
        blurb=_("Enable window integration with the desktop"),
        category=PropertyCategory.PERSIST,
        transform_in=_str_to_bool,
        transform_out=partial(_bool_to_str, flag=2),
    )

    qemu_hw_mainkeys = categorized_property(
        type=bool,
        default=False,
        nick="qemu.hw.mainkeys",
        blurb=_("Hide navbar"),
        category=PropertyCategory.PRIVILEGED,
        transform_in=_str_to_bool,
        transform_out=partial(_bool_to_str, flag=2),
    )

    ro_product_brand = categorized_property(
        type=str,
        default="",
        nick="ro.product.brand",
        blurb=_("Brand of the product"),
        category=PropertyCategory.PRIVILEGED,
    )

    ro_product_manufacturer = categorized_property(
        type=str,
        default="",
        nick="ro.product.manufacturer",
        blurb=_("Manufacturer of the product"),
        category=PropertyCategory.PRIVILEGED,
    )
    
    ro_product_model = categorized_property(
        type=str,
        default="",
        nick="ro.product.model",
        blurb=_("Model of the product"),
        category=PropertyCategory.PRIVILEGED,
    )
    
    ro_product_device = categorized_property(
        type=str,
        default="",
        nick="ro.product.device",
        blurb=_("Device of the product"),
        category=PropertyCategory.PRIVILEGED,
    )

    mount_overlays = categorized_property(
        type=bool,
        default=True,
        nick="mount_overlays",
        blurb=_("Enable overlay mounting"),
        category=PropertyCategory.WAYDROID,
        transform_in=_str_to_bool,
        transform_out=partial(_bool_to_str, flag=0),
    )
    
    auto_adb = categorized_property(
        type=bool,
        default=False,
        nick="auto_adb",
        blurb=_("Enable automatic ADB connection"),
        category=PropertyCategory.WAYDROID,
        transform_in=_str_to_bool,
        transform_out=partial(_bool_to_str, flag=0),
    )

    images_path = categorized_property(
        type=str,
        default="/etc/waydroid-extra/images",
        nick="images_path",
        blurb=_("Path to Waydroid images"),
        category=PropertyCategory.WAYDROID,
    )

    gpu = categorized_property(
        type=str,
        default="",
        nick="drm_device",
        blurb=_("Choose which GPU should be used by Waydroid"),
        category=PropertyCategory.WAYDROID,
    )

    def __init__(self):
        super().__init__()
        # self._properties: Dict[str, Any] = {}
        # self._property_definitions: Dict[str, PropertyDefinition] = {}
        # self._change_listeners: Set[Callable[[str, Any], None]] = set()
        self.set_property("state", ModelState.UNINITIALIZED)
        self.set_property("privileged-state", ModelState.UNINITIALIZED)
        self.set_property("waydroid-state", ModelState.UNINITIALIZED)
        # self._setup_property_definitions()
    
    
    def get_property_raw_value(self, name: str) -> Any:
        """Get current property value"""
        prop = self.get_property(name)
        attr_name = name.replace("-", "_")
        prop_obj = getattr(PropertyModel, attr_name, None)
        if prop_obj is None:
            logger.warning(f"Unknown property: {name}")
            return None
        return prop_obj._transform_out(prop)
    
    def set_property_raw_value(self, name: str, raw_value: str) -> bool:
        """
        Set property value and emit change signal.
        Returns True if value was changed, False if it was the same.
        """

        attr_name = name.replace("-", "_")
        prop_obj = getattr(PropertyModel, attr_name, None)
        if prop_obj is None:
            logger.warning(f"Unknown property: {name}")
            return False
        self.set_property(name, prop_obj._transform_in(raw_value))
        return True
    
    # def _emit_property_changed(self, name: str, value: Any):
    #     """Emit property changed signal to all listeners"""
    #     for listener in self._change_listeners:
    #         try:
    #             listener(name, value)
    #         except Exception as e:
    #             logger.error(f"Error in property change listener: {e}")
    
    # def add_change_listener(self, listener: Callable[[str, Any], None]):
    #     """Add a listener for property changes"""
    #     self._change_listeners.add(listener)
    
    # def remove_change_listener(self, listener: Callable[[str, Any], None]):
    #     """Remove a property change listener"""
    #     self._change_listeners.discard(listener)
    
    def get_persist_properties(self):
        """Get all persist properties (non-privileged)"""

        props = self.list_properties()
        result = []
        for prop in props:
            attr_name = prop.name.replace("-", "_")
            prop_obj = getattr(PropertyModel, attr_name, None)
            if prop_obj is not None and getattr(prop_obj, "_category", None) == PropertyCategory.PERSIST:
                result.append(prop)
        return result
    
    def get_privileged_properties(self):
        """Get all privileged properties"""
        props = self.list_properties()
        result = []
        for prop in props:
            attr_name = prop.name.replace("-", "_")
            prop_obj = getattr(PropertyModel, attr_name, None)
            if prop_obj is not None and getattr(prop_obj, "_category", None) == PropertyCategory.PRIVILEGED:
                result.append(prop)
        return result

    def get_waydroid_properties(self):
        """Get all waydroid config properties"""
        props = self.list_properties()
        result = []
        for prop in props:
            attr_name = prop.name.replace("-", "_")
            prop_obj = getattr(PropertyModel, attr_name, None)
            if prop_obj is not None and getattr(prop_obj, "_category", None) == PropertyCategory.WAYDROID:
                result.append(prop)
        return result

    def reset_to_defaults(self, category: PropertyCategory):
        props = self.list_properties()
        for prop in props:
            attr_name = prop.name.replace("-", "_")
            prop_obj = getattr(PropertyModel, attr_name, None)
            if prop_obj is not None and getattr(prop_obj, "_category", None) == category:
                self.set_property(prop.name, prop.get_default_value())


class SessionModel(GObject.Object):
    """
    Model for Waydroid session state.
    
    This model:
    - Tracks session state (running, stopped, etc.)
    - Emits signals when session state changes
    - Has no knowledge of UI or SDK layers
    """
    
    state = GObject.Property(type=object)
    # FIXME why android version is here?
    android_version = GObject.Property(type=str, default="")
    
    def __init__(self):
        super().__init__()
        # self._change_listeners: Set[Callable[[SessionState], None]] = set()
        self.set_property("state", SessionState.LOADING)
    
    def set_session_state(self, new_state: SessionState):
        """Set session state and emit change signal if different"""
        old_state = self.get_property("state")
        if old_state != new_state:
            self.set_property("state", new_state)