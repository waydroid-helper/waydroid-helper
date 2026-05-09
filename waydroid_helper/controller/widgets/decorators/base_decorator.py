#!/usr/bin/env python3
"""
组件装饰器基类
提供装饰器模式的基础接口
"""

from functools import wraps
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from waydroid_helper.controller.widgets.base.base_widget import BaseWidget
    from waydroid_helper.controller.widgets.base.decorator_contracts import (
        WidgetDecoratorBehavior,
    )


class WidgetDecorator: 
    """组件装饰器基类"""

    BEHAVIOR_CONTRACTS: tuple[type["WidgetDecoratorBehavior"], ...] = ()

    def __init__(self, widget: "BaseWidget", **kwargs):
        """初始化装饰器，包装原始组件"""
        self._wrapped_widget: "BaseWidget" = widget
        self._decorator_kwargs = kwargs
        self._setup_decorator()

    def _setup_decorator(self):
        """设置装饰器的具体功能 - 子类重写"""

    def get_wrapped_widget(self):
        """获取被包装的组件"""
        return self._wrapped_widget

    def iter_behavior_contracts(self):
        return self.BEHAVIOR_CONTRACTS


def _apply_widget_decorator(widget, decorator: WidgetDecorator) -> None:
    for contract in decorator.iter_behavior_contracts():
        widget.register_widget_behavior(contract, decorator)


def widget_decorator(decorator_class):
    """装饰器工厂函数，用于创建类装饰器"""

    def class_decorator(widget_class):
        """类装饰器"""
        original_init = widget_class.__init__

        @wraps(original_init)
        def new_init(self, *args, **kwargs):
            # 先调用原始的初始化
            original_init(self, *args, **kwargs)

            decorator_instance = decorator_class(self)
            _apply_widget_decorator(self, decorator_instance)

        widget_class.__init__ = new_init
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

            decorator_instance = decorator_class(self, **decorator_kwargs)
            _apply_widget_decorator(self, decorator_instance)

        widget_class.__init__ = new_init
        return widget_class

    return class_decorator
