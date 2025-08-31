import gi
gi.require_version("Gtk", "4.0")

from gi.repository import GObject, GLib
from typing import Any

from .file_manager import ConfigManager
from waydroid_helper.util.log import logger

class CageConfig(GObject.Object):
    
    enabled = GObject.Property(type=bool, default=False)
    executable_path = GObject.Property(type=str, default="")
    window_width = GObject.Property(type=int, default=1920)
    window_height = GObject.Property(type=int, default=1080)
    logical_width = GObject.Property(type=int, default=1920)
    logical_height = GObject.Property(type=int, default=1080)
    scale = GObject.Property(type=int, default=100)
    socket_name = GObject.Property(type=str, default="waydroid-0")


class RootConfig(GObject.Object):
    
    cage = GObject.Property(type=object)
    
    def __init__(self):
        super().__init__()
        self._file_manager = ConfigManager()
        self.cage = CageConfig()
        self.load_from_file()
    
    def load_from_file(self) -> None:
        config = self._file_manager.load_config()
        
        if not config:
            logger.info("Config file not found or empty, creating default configuration")
            self.save_to_file()
            return
        
        self._unmarshal_to_object(self, config)
    
    def save_to_file(self) -> bool:
        try:
            config = self._marshal_from_object(self)
            return self._file_manager.save_config(config)
        except Exception as e:
            logger.error(f"Failed to save configuration: {e}")
            return False
    
    def _marshal_from_object(self, obj: Any) -> Any:
        if isinstance(obj, GObject.Object):
            result = {}
            for prop_spec in obj.list_properties():
                prop_name = prop_spec.name.replace('-', '_')
                value = obj.get_property(prop_name)
                
                if isinstance(value, GObject.Object):
                    result[prop_name] = self._marshal_from_object(value)
                elif isinstance(value, GLib.Variant):
                    if value.get_type_string() == 'as':
                        result[prop_name] = value.unpack()
                else:
                    result[prop_name] = value
            return result
        else:
            return obj
    
    def _unmarshal_to_object(self, obj: Any, data: Any) -> None:
        if isinstance(obj, GObject.Object) and isinstance(data, dict):
            for prop_spec in obj.list_properties():
                prop_name = prop_spec.name.replace('-', '_')
                if prop_name in data:
                    value = data[prop_name]
                    current_value = obj.get_property(prop_name)
                    
                    if isinstance(current_value, GObject.Object):
                        self._unmarshal_to_object(current_value, value)
                    elif prop_spec.value_type == GObject.TYPE_VARIANT:
                        if isinstance(value, list):
                            obj.set_property(prop_name, GLib.Variant('as', value))
                    else:
                        obj.set_property(prop_name, value)