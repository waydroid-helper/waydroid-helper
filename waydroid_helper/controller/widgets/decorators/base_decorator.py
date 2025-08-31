#!/usr/bin/env python3
"""
组件装饰器基类
提供装饰器模式的基础接口
"""

from functools import wraps
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from waydroid_helper.controller.widgets.base.base_widget import BaseWidget


class WidgetDecorator: 
    """组件装饰器基类"""

    def __init__(self, widget: "BaseWidget", **kwargs):
        """初始化装饰器，包装原始组件"""
        self._wrapped_widget: "BaseWidget" = widget
        self._decorator_kwargs = kwargs
        self._setup_decorator()

    def _setup_decorator(self):
        """设置装饰器的具体功能 - 子类重写"""

    def __getattr__(self, name):
        """代理所有未定义的属性和方法到被包装的组件"""
        return getattr(self._wrapped_widget, name)

    def get_wrapped_widget(self):
        """获取被包装的组件"""
        return self._wrapped_widget


def widget_decorator(decorator_class):
    """装饰器工厂函数，用于创建类装饰器"""

    def class_decorator(widget_class):
        """类装饰器"""
        original_init = widget_class.__init__

        @wraps(original_init)
        def new_init(self, *args, **kwargs):
            # 先调用原始的初始化
            original_init(self, *args, **kwargs)

            # 创建装饰器实例并应用
            decorator_instance = decorator_class(self)

            # 将装饰器的方法和属性添加到实例中
            self._apply_decorator(decorator_instance)

        def _apply_decorator(self, decorator):
            """将装饰器的功能应用到当前实例"""
            # 获取装饰器的所有方法和属性
            for attr_name in dir(decorator):
                if not attr_name.startswith("_") and attr_name != "get_wrapped_widget":
                    attr_value = getattr(decorator, attr_name)
                    if callable(attr_value):
                        # 绑定方法到当前实例
                        setattr(self, attr_name, attr_value)
                    else:
                        # 复制属性
                        setattr(self, attr_name, attr_value)

        widget_class.__init__ = new_init
        widget_class._apply_decorator = _apply_decorator
        return widget_class

    return class_decorator


def parameterized_widget_decorator(decorator_class):
    """参数化装饰器工厂函数，支持带参数的装饰器"""

    def decorator_factory(*args, **kwargs):
        """装饰器工厂，可以带参数调用，也可以不带参数调用"""

        # 如果第一个参数是类，说明是不带参数的装饰器使用
        if len(args) == 1 and len(kwargs) == 0 and isinstance(args[0], type):
            # 不带参数的使用方式: @SomeDecorator
            widget_class = args[0]
            return _create_parameterized_decorator(decorator_class, {})(widget_class)
        else:
            # 带参数的使用方式: @SomeDecorator(param1=value1, param2=value2)
            def parametrized_decorator(widget_class):
                return _create_parameterized_decorator(decorator_class, kwargs)(
                    widget_class
                )

            return parametrized_decorator

    return decorator_factory


def _create_parameterized_decorator(decorator_class, decorator_kwargs):
    """创建参数化装饰器的内部函数"""

    def class_decorator(widget_class):
        """类装饰器"""
        original_init = widget_class.__init__

        @wraps(original_init)
        def new_init(self, *args, **kwargs):
            # 先调用原始的初始化
            original_init(self, *args, **kwargs)

            # 创建装饰器实例并应用，传入参数
            decorator_instance = decorator_class(self, **decorator_kwargs)

            # 将装饰器的方法和属性添加到实例中
            self._apply_decorator(decorator_instance)

        def _apply_decorator(self, decorator):
            """将装饰器的功能应用到当前实例"""
            # 获取装饰器的所有方法和属性
            for attr_name in dir(decorator):
                if not attr_name.startswith("_") and attr_name != "get_wrapped_widget":
                    attr_value = getattr(decorator, attr_name)
                    if callable(attr_value):
                        # 绑定方法到当前实例
                        setattr(self, attr_name, attr_value)
                    else:
                        # 复制属性
                        setattr(self, attr_name, attr_value)

        widget_class.__init__ = new_init
        widget_class._apply_decorator = _apply_decorator
        return widget_class

    return class_decorator
