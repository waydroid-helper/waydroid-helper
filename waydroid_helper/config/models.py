import gi
gi.require_version("Gtk", "4.0")

from gi.repository import GObject, Gtk
from typing import Any, Optional

from .file_manager import ConfigFileManager
from waydroid_helper.util.log import logger


class BaseConfigModel(GObject.Object):
    """基础配置模型类"""
    
    def __init__(self, config_prefix: str):
        """
        初始化基础配置模型
        
        Args:
            config_prefix: 配置前缀，用于在配置文件中区分不同模块
        """
        super().__init__()
        self.config_prefix = config_prefix
        self._file_manager = ConfigFileManager()
    
    def load_from_file(self) -> None:
        """从配置文件加载所有属性"""
        config = self._file_manager.load_config()
        
        # 获取这个模型的配置部分
        model_config = config.get(self.config_prefix, {})
        
        # 更新所有属性
        for prop_spec in self.list_properties():
            prop_name = prop_spec.name.replace('-', '_')
            if prop_name in model_config:
                self.set_property(prop_name, model_config[prop_name])
                logger.debug(f"加载配置: {self.config_prefix}.{prop_name} = {model_config[prop_name]}")
    
    def save_to_file(self) -> bool:
        """将所有属性保存到配置文件"""
        try:
            # 加载现有配置
            config = self._file_manager.load_config()
            
            # 确保模型配置部分存在
            if self.config_prefix not in config:
                config[self.config_prefix] = {}
            
            # 保存所有属性
            for prop_spec in self.list_properties():
                prop_name = prop_spec.name.replace('-', '_')
                value = self.get_property(prop_name)
                config[self.config_prefix][prop_name] = value
                logger.debug(f"保存配置: {self.config_prefix}.{prop_name} = {value}")
            
            return self._file_manager.save_config(config)
        except Exception as e:
            logger.error(f"保存配置失败: {e}")
            return False
    



class CageConfigModel(BaseConfigModel):
    """Cage 配置模型"""
    
    # 定义 GObject 属性
    __gproperties__ = {
        'enabled': (
            bool,                    # 类型
            'Enable Cage',           # 昵称
            'Enable cage functionality',  # 描述
            True,                    # 默认值
            GObject.ParamFlags.READWRITE
        ),
        'opacity': (
            float,
            'Cage Opacity',
            'Opacity of the cage overlay',
            0.0,                     # 最小值
            1.0,                     # 最大值
            0.8,                     # 默认值
            GObject.ParamFlags.READWRITE
        ),
        'size': (
            int,
            'Cage Size',
            'Size of the cage in pixels',
            10,                      # 最小值
            1000,                    # 最大值
            100,                     # 默认值
            GObject.ParamFlags.READWRITE
        ),
    }
    
    def __init__(self):
        super().__init__("cage")
        self._enabled = True
        self._opacity = 0.8
        self._size = 100
    
    def do_get_property(self, prop):
        """GObject 属性 getter"""
        if prop.name == 'enabled':
            return self._enabled
        elif prop.name == 'opacity':
            return self._opacity
        elif prop.name == 'size':
            return self._size
        else:
            raise AttributeError(f'未知属性: {prop.name}')
    
    def do_set_property(self, prop, value):
        """GObject 属性 setter"""
        if prop.name == 'enabled':
            self._enabled = value
        elif prop.name == 'opacity':
            self._opacity = value
        elif prop.name == 'size':
            self._size = value
        else:
            raise AttributeError(f'未知属性: {prop.name}')
    



class AppConfigModel(BaseConfigModel):
    """应用程序配置模型"""
    
    __gproperties__ = {
        'auto_start': (
            bool,
            'Auto Start',
            'Start application automatically',
            False,
            GObject.ParamFlags.READWRITE
        ),
        'minimize_to_tray': (
            bool,
            'Minimize to Tray',
            'Minimize to system tray when closed',
            True,
            GObject.ParamFlags.READWRITE
        ),
        'language': (
            str,
            'Language',
            'Application language',
            'zh_CN',
            GObject.ParamFlags.READWRITE
        ),
        'theme': (
            str,
            'Theme',
            'Application theme',
            'auto',
            GObject.ParamFlags.READWRITE
        ),
    }
    
    def __init__(self):
        super().__init__("app")
        self._auto_start = False
        self._minimize_to_tray = True
        self._language = 'zh_CN'
        self._theme = 'auto'
    
    def do_get_property(self, prop):
        """GObject 属性 getter"""
        if prop.name == 'auto_start':
            return self._auto_start
        elif prop.name == 'minimize_to_tray':
            return self._minimize_to_tray
        elif prop.name == 'language':
            return self._language
        elif prop.name == 'theme':
            return self._theme
        else:
            raise AttributeError(f'未知属性: {prop.name}')
    
    def do_set_property(self, prop, value):
        """GObject 属性 setter"""
        if prop.name == 'auto_start':
            self._auto_start = value
        elif prop.name == 'minimize_to_tray':
            self._minimize_to_tray = value
        elif prop.name == 'language':
            self._language = value
        elif prop.name == 'theme':
            self._theme = value
        else:
            raise AttributeError(f'未知属性: {prop.name}')
    



# 全局配置模型实例
_app_config_instance: Optional[AppConfigModel] = None
_cage_config_instance: Optional[CageConfigModel] = None


def get_app_config() -> AppConfigModel:
    """获取应用程序配置模型实例（单例）"""
    global _app_config_instance
    if _app_config_instance is None:
        _app_config_instance = AppConfigModel()
        _app_config_instance.load_from_file()
    return _app_config_instance


def get_cage_config() -> CageConfigModel:
    """获取 Cage 配置模型实例（单例）"""
    global _cage_config_instance
    if _cage_config_instance is None:
        _cage_config_instance = CageConfigModel()
        _cage_config_instance.load_from_file()
    return _cage_config_instance
