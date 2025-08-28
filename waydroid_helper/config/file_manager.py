import json
import os
from pathlib import Path
from typing import Any, Dict, Optional
from gi.repository import GLib

from waydroid_helper.util.log import logger


class ConfigFileManager:
    """配置文件管理器 - 无状态的文件读写类"""
    
    DEFAULT_CONFIG_DIR = Path(GLib.get_user_config_dir()) / "waydroid-helper"
    DEFAULT_CONFIG_FILE = "config.json"
    
    def __init__(self, config_dir: Optional[Path] = None):
        """
        初始化配置文件管理器
        
        Args:
            config_dir: 配置文件目录，默认为 ~/.config/waydroid-helper/
        """
        self.config_dir = config_dir or self.DEFAULT_CONFIG_DIR
        self.config_file = self.config_dir / self.DEFAULT_CONFIG_FILE
        
    def _ensure_config_dir(self) -> bool:
        """确保配置目录存在"""
        try:
            self.config_dir.mkdir(parents=True, exist_ok=True)
            return True
        except Exception as e:
            logger.error(f"无法创建配置目录 {self.config_dir}: {e}")
            return False
    
    def load_config(self) -> Dict[str, Any]:
        """
        从文件加载配置
        
        Returns:
            配置字典，如果文件不存在或读取失败则返回空字典
        """
        if not self.config_file.exists():
            logger.info(f"配置文件不存在: {self.config_file}")
            return {}
        
        try:
            with open(self.config_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
                logger.debug(f"成功加载配置文件: {self.config_file}")
                return config
        except json.JSONDecodeError as e:
            logger.error(f"配置文件 JSON 格式错误: {e}")
            return {}
        except Exception as e:
            logger.error(f"读取配置文件失败: {e}")
            return {}
    
    def save_config(self, config: Dict[str, Any]) -> bool:
        """
        将配置保存到文件
        
        Args:
            config: 要保存的配置字典
            
        Returns:
            保存是否成功
        """
        if not self._ensure_config_dir():
            return False
        
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
                logger.debug(f"成功保存配置文件: {self.config_file}")
                return True
        except Exception as e:
            logger.error(f"保存配置文件失败: {e}")
            return False
    
    def get_value(self, key: str, default: Any = None) -> Any:
        """
        获取配置值
        
        Args:
            key: 配置键，支持点分隔的嵌套键，如 "cage.enabled"
            default: 默认值
            
        Returns:
            配置值或默认值
        """
        config = self.load_config()
        return self._get_nested_value(config, key, default)
    
    def set_value(self, key: str, value: Any) -> bool:
        """
        设置配置值
        
        Args:
            key: 配置键，支持点分隔的嵌套键，如 "cage.enabled"
            value: 配置值
            
        Returns:
            设置是否成功
        """
        config = self.load_config()
        self._set_nested_value(config, key, value)
        return self.save_config(config)
    
    def delete_value(self, key: str) -> bool:
        """
        删除配置值
        
        Args:
            key: 配置键，支持点分隔的嵌套键
            
        Returns:
            删除是否成功
        """
        config = self.load_config()
        if self._delete_nested_value(config, key):
            return self.save_config(config)
        return False
    
    def _get_nested_value(self, config: Dict[str, Any], key: str, default: Any = None) -> Any:
        """获取嵌套配置值"""
        keys = key.split('.')
        current = config
        
        for k in keys:
            if not isinstance(current, dict) or k not in current:
                return default
            current = current[k]
        
        return current
    
    def _set_nested_value(self, config: Dict[str, Any], key: str, value: Any) -> None:
        """设置嵌套配置值"""
        keys = key.split('.')
        current = config
        
        # 创建嵌套结构
        for k in keys[:-1]:
            if k not in current:
                current[k] = {}
            elif not isinstance(current[k], dict):
                current[k] = {}
            current = current[k]
        
        # 设置最终值
        current[keys[-1]] = value
    
    def _delete_nested_value(self, config: Dict[str, Any], key: str) -> bool:
        """删除嵌套配置值"""
        keys = key.split('.')
        current = config
        
        # 找到父级对象
        for k in keys[:-1]:
            if not isinstance(current, dict) or k not in current:
                return False
            current = current[k]
        
        # 删除最终键
        if isinstance(current, dict) and keys[-1] in current:
            del current[keys[-1]]
            return True
        
        return False
    
    def backup_config(self, backup_suffix: str = ".backup") -> bool:
        """
        备份当前配置文件
        
        Args:
            backup_suffix: 备份文件后缀
            
        Returns:
            备份是否成功
        """
        if not self.config_file.exists():
            logger.warning("配置文件不存在，无法备份")
            return False
        
        backup_file = self.config_file.with_suffix(self.config_file.suffix + backup_suffix)
        
        try:
            import shutil
            shutil.copy2(self.config_file, backup_file)
            logger.info(f"配置文件已备份到: {backup_file}")
            return True
        except Exception as e:
            logger.error(f"备份配置文件失败: {e}")
            return False
    
    def restore_config(self, backup_suffix: str = ".backup") -> bool:
        """
        从备份恢复配置文件
        
        Args:
            backup_suffix: 备份文件后缀
            
        Returns:
            恢复是否成功
        """
        backup_file = self.config_file.with_suffix(self.config_file.suffix + backup_suffix)
        
        if not backup_file.exists():
            logger.error(f"备份文件不存在: {backup_file}")
            return False
        
        try:
            import shutil
            shutil.copy2(backup_file, self.config_file)
            logger.info(f"配置文件已从备份恢复: {backup_file}")
            return True
        except Exception as e:
            logger.error(f"恢复配置文件失败: {e}")
            return False
