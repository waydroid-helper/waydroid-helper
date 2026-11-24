#!/usr/bin/env python3
"""
可调整大小装饰器
为组件添加调整大小的功能
"""

import gi

gi.require_version('Gdk', '4.0')
from waydroid_helper.util.log import logger
from waydroid_helper.controller.widgets.base.draw_overlay import (
    add_decorator_draw_overlay,
)
from waydroid_helper.controller.widgets.base.decorator_contracts import (
    ResizableWidgetBehavior,
)

from .base_decorator import WidgetDecorator, parameterized_widget_decorator
from .resize_geometry import (
    ResizeGeometryCalculator,
    ResizeSnapshot,
    ResizeStrategy,
)


class ResizableDecorator(WidgetDecorator, ResizableWidgetBehavior):
    """可调整大小装饰器"""

    BEHAVIOR_CONTRACTS = (ResizableWidgetBehavior,)
    
    # 缩放策略常量
    RESIZE_NORMAL = ResizeStrategy.NORMAL
    RESIZE_CENTER = ResizeStrategy.CENTER
    RESIZE_SYMMETRIC = ResizeStrategy.SYMMETRIC
    
    def __init__(self, widget, **kwargs):
        """初始化装饰器"""
        # 从参数中获取缩放策略，默认为普通缩放
        self.resize_strategy = kwargs.get('resize_strategy', self.RESIZE_NORMAL)
        self._geometry = ResizeGeometryCalculator()
        
        # 初始化调整大小状态变量
        self.is_resizing_flag = False
        self.resize_direction = None
        self._resize_snapshot = ResizeSnapshot(0, 0, 0, 0, 0, 0)
        self.global_start_x = 0
        self.global_start_y = 0
        self.current_resize_strategy = self._strategy_for(widget)
        
        super().__init__(widget, **kwargs)
    
    def _setup_decorator(self):
        """设置可调整大小的功能"""
        # 立即Hook绘制函数
        self._hook_draw_function()
        
        logger.debug(f"ResizableDecorator applied to {type(self._wrapped_widget).__name__}")
        logger.debug(f"Resizable Hook draw function: {self._wrapped_widget.draw_func}")
    
    def _strategy_for(self, widget):
        strategy = self.resize_strategy
        return ResizeStrategy(strategy(widget) if callable(strategy) else strategy)

    def can_resize_at_position(self, x, y, width, height):
        """检查指定位置是否可以调整大小，返回调整方向"""
        return self._geometry.hit_test(x, y, width, height)
    
    def check_resize_direction(self, x, y):
        """检查鼠标位置对应的调整方向"""
        width = self._wrapped_widget.get_allocated_width()
        height = self._wrapped_widget.get_allocated_height()
        return self.can_resize_at_position(x, y, width, height)
    
    def start_resize(self, x, y, resize_direction):
        """开始调整大小"""
        self.is_resizing_flag = True
        self.resize_direction = resize_direction
        # A configurable control may change actions between drags. Resolve its
        # strategy once per gesture, alongside the original bounds.
        self.current_resize_strategy = self._strategy_for(self._wrapped_widget)
        
        # 获取全局坐标
        parent = self._wrapped_widget.get_parent()
        if parent:
            widget_x, widget_y = parent.get_child_position(self._wrapped_widget)
            self._resize_snapshot = ResizeSnapshot(
                width=self._wrapped_widget.width,
                height=self._wrapped_widget.height,
                x=self._wrapped_widget.x,
                y=self._wrapped_widget.y,
                min_width=self._wrapped_widget.min_width,
                min_height=self._wrapped_widget.min_height,
            )
            self.global_start_x = widget_x + x
            self.global_start_y = widget_y + y
    
    def is_resizing(self):
        """检查是否正在调整大小"""
        return self.is_resizing_flag
    
    def on_resize_release(self):
        """调整大小释放事件"""
        self.is_resizing_flag = False
        self.resize_direction = None
    
    def handle_resize_motion(self, global_x, global_y):
        """处理调整大小的鼠标移动"""
        if not self.is_resizing_flag or not self.resize_direction:
            return
            
        # 计算全局坐标的变化量
        global_dx = global_x - self.global_start_x
        global_dy = global_y - self.global_start_y
        
        # 使用缩放策略处理调整大小
        resize_result = self._geometry.calculate(
            self.resize_direction,
            global_dx,
            global_dy,
            self._resize_snapshot,
            self.current_resize_strategy,
        )
        
        # 应用变化
        self._wrapped_widget.width = resize_result.width
        self._wrapped_widget.height = resize_result.height
        self._wrapped_widget.x = resize_result.x
        self._wrapped_widget.y = resize_result.y
        self._wrapped_widget.set_size_request(resize_result.width, resize_result.height)
        self._wrapped_widget.set_content_height(resize_result.height)
        self._wrapped_widget.set_content_width(resize_result.width)

        parent = self._wrapped_widget.get_parent()
        if parent:
            parent.move(self._wrapped_widget, resize_result.x, resize_result.y)
        
        self._wrapped_widget.queue_draw()
    
    def _hook_draw_function(self):
        """Hook绘制函数，在原绘制完成后添加调整大小装饰"""
        def resize_draw(cr, width, height):
            if self._wrapped_widget.is_selected and not self._wrapped_widget.mapping_mode:
                self.draw_resize_decorations(cr, width, height)

        add_decorator_draw_overlay(self._wrapped_widget, resize_draw)
    
    def draw_resize_decorations(self, cr, width, height):
        """绘制调整大小的装饰元素（手柄等）"""
        self.draw_resize_handles(cr, width, height)
    
    def draw_resize_handles(self, cr, width, height):
        """绘制调整大小的手柄"""
        size = self._geometry.HANDLE_SIZE
        for _, x, y in self._geometry.handles(width, height):
            cr.rectangle(x-size/2, y-size/2, size, size)
            cr.set_source_rgba(.82, .86, .9, .88)
            cr.fill()


# 创建参数化装饰器函数
Resizable = parameterized_widget_decorator(ResizableDecorator)
