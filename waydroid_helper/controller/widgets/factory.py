#!/usr/bin/env python3
"""
动态组件工厂
自动扫描components目录，发现和注册widget类
"""

from __future__ import annotations

import importlib
import inspect
import pkgutil
from typing import TYPE_CHECKING, Any

from waydroid_helper.util.log import logger

if TYPE_CHECKING:
    from types import ModuleType

    from waydroid_helper.controller.widgets.base import BaseWidget
    from waydroid_helper.controller.core.runtime import ControllerRuntimeContext

class WidgetFactory:
    """动态组件工厂类"""
    
    def __init__(self, runtime_context: "ControllerRuntimeContext | None" = None):
        self.runtime_context = runtime_context
        self.widget_classes: dict[str, type["BaseWidget"]] = {}
        self.widget_metadata: dict[str, dict[str, Any]] = {}
        self._discover_widgets()
    
    def _discover_widgets(self):
        """动态发现组件目录中的所有widget类"""
        try:
            # 导入 components 包
            import waydroid_helper.controller.widgets.components as components_package

            # 使用 pkgutil 遍历包中的所有模块
            for _, module_name, ispkg in pkgutil.iter_modules(components_package.__path__):
                if not ispkg:  # 只处理模块，不处理子包
                    self._load_widget_from_module(module_name)

        except ImportError as e:
            logger.error(f"Failed to import components package: {e}")
        except Exception as e:
            logger.error(f"Error during widget discovery: {e}")
    
    def _load_widget_from_module(self, module_name: str):
        """从模块中加载widget类"""
        try:
            # 动态导入模块
            module_path = f"waydroid_helper.controller.widgets.components.{module_name}"
            module = importlib.import_module(module_path)
            
            # 查找模块中的widget类
            for name, obj in inspect.getmembers(module, inspect.isclass):
                if self._is_widget_class(obj, module):
                    widget_type = self._extract_widget_type(name)
                    self.widget_classes[widget_type] = obj
                    self.widget_metadata[widget_type] = self._extract_metadata(obj)
                    
        except Exception as e:
            logger.error(f"Failed to load module {module_name}: {e}")
    
    def _is_widget_class(self, cls: type["BaseWidget"], module: 'ModuleType') -> bool:
        """判断是否为有效的widget类"""
        # 检查类是否定义在当前模块中（不是导入的）
        if cls.__module__ != module.__name__:
            return False
            
        # 检查是否继承了BaseWidget（通过检查方法签名）
        if not hasattr(cls, 'draw_func'):
            return False
            
        # 检查是否有__init__方法
        if not hasattr(cls, '__init__'):
            return False
            
        return True
    
    def _extract_widget_type(self, class_name: str) -> str:
        """从类名提取widget类型"""
        # 直接使用类名，转换为小写
        return class_name.lower()
    
    def _extract_metadata(self, widget_class: type["BaseWidget"]) -> dict[str, Any]:
        """提取组件元数据"""
        metadata = {
            'name': getattr(widget_class, '__doc__', widget_class.__name__).split('\n')[0] if widget_class.__doc__ else widget_class.__name__,
            'description': widget_class.__doc__ or '',
            'class_name': widget_class.__name__,
            'module': widget_class.__module__
        }
        
        # 尝试从类中提取更多元数据
        if hasattr(widget_class, 'WIDGET_NAME'):
            metadata['name'] = widget_class.WIDGET_NAME
        if hasattr(widget_class, 'WIDGET_DESCRIPTION'):
            metadata['description'] = widget_class.WIDGET_DESCRIPTION
            
        return metadata
    
    def create_widget(self, widget_type: str, **kwargs) -> "BaseWidget" | None:
        """创建指定类型的组件"""
        if widget_type not in self.widget_classes:
            available = list(self.widget_classes.keys())
            raise ValueError(f"Unsupported widget type: {widget_type}. Available types: {available}")
        
        widget_class = self.widget_classes[widget_type]
        if self.runtime_context is not None:
            kwargs.setdefault("runtime_context", self.runtime_context)
        
        try:
            widget = widget_class(**kwargs)
            return widget
        except Exception as e:
            logger.error(f"Failed to create widget {widget_type}: {e}")
            return None
    
    
    def get_available_types(self) -> list[str]:
        """获取所有可用的组件类型"""
        return list(self.widget_classes.keys())
    
    def get_widget_metadata(self, widget_type: str):
        """获取组件元数据"""
        if widget_type:
            return self.widget_metadata.get(widget_type, {})
        return self.widget_metadata.copy()
    
    def register_widget_type(self, name: str, widget_class: type[BaseWidget]):
        """手动注册新的组件类型"""
        self.widget_classes[name] = widget_class
        self.widget_metadata[name] = self._extract_metadata(widget_class)
    
    def unregister_widget_type(self, name: str):
        """注销组件类型"""
        if name in self.widget_classes:
            del self.widget_classes[name]
            if name in self.widget_metadata:
                del self.widget_metadata[name]
    
    def reload_widgets(self):
        """重新加载所有组件"""
        self.widget_classes.clear()
        self.widget_metadata.clear()
        self._discover_widgets()
    
    def print_discovered_widgets(self):
        """打印发现的所有组件"""
        logger.info("\n=== Discovered widgets ===")
        for widget_type, metadata in self.widget_metadata.items():
            logger.info(f"Type: {widget_type}")
            logger.info(f"  Name: {metadata['name']}")
            logger.info(f"  Class: {metadata['class_name']}")
            logger.info(f"  Module: {metadata['module']}")
            desc = metadata.get('description', 'No description')
            if len(desc) > 50:
                desc = desc[:47] + "..."
            logger.info(f"  Description: {desc}")
            logger.info("")
