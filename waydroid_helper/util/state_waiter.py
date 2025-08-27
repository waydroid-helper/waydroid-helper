import asyncio

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import GObject
from typing import Any

class StateWaiter:
    """优雅的状态等待工具类 - 支持并发和复用"""
    
    def __init__(self, gobject_instance: GObject.Object, target_state: Any, state_property: str = "state"):
        """
        初始化状态等待器
        
        Args:
            gobject_instance: 支持 GObject 信号的实例 
            target_state: 目标状态
            state_property: 状态属性名，默认为 "state"
        """
        self.gobject_instance: GObject.Object = gobject_instance
        self.target_state = target_state
        self.state_property = state_property
        self._event = asyncio.Event()
        self._signal_id = None
        
    async def __aenter__(self):
        """异步上下文管理器入口"""
        await self._setup_listener()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """异步上下文管理器退出"""
        self._cleanup_listener()
        
    async def _setup_listener(self):
        """设置状态监听器"""
        # 连接信号
        signal_name = f"notify::{self.state_property}"
        self._signal_id = self.gobject_instance.connect(signal_name, self._on_state_changed)
        
        # 检查当前状态是否已经是目标状态
        current_state = self.gobject_instance.get_property(self.state_property)
        if current_state == self.target_state:
            self._event.set()
    
    def _cleanup_listener(self):
        """清理状态监听器"""
        if self._signal_id is not None:
            self.gobject_instance.disconnect(self._signal_id)
            self._signal_id = None
    
    def _on_state_changed(self, instance: GObject.Object, param: Any):
        """处理状态变化"""
        new_state = instance.get_property(self.state_property)
        if new_state == self.target_state:
            self._event.set()
    
    async def wait(self, timeout: float = 30.0) -> bool:
        try:
            await asyncio.wait_for(self._event.wait(), timeout=timeout)
            return True
        except asyncio.TimeoutError:
            return False

async def wait_for_state(
    gobject_instance, target_state, timeout: float = 30.0, state_property: str = "state"
) -> bool:
    async with StateWaiter(gobject_instance, target_state, state_property) as waiter:
        return await waiter.wait(timeout)