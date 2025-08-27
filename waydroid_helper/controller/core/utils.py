#!/usr/bin/env python3
"""
工具函数
"""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any, TypedDict

if TYPE_CHECKING:
    pass


def generate_random_position(
    min_x: int = 50, max_x: int = 600, min_y: int = 100, max_y: int = 400
) -> tuple[int, int]:
    """生成随机位置"""
    x = random.randint(min_x, max_x)
    y = random.randint(min_y, max_y)
    return x, y


def clamp(value: float, min_value: float, max_value: float) -> float:
    """限制数值在指定范围内"""
    return max(min_value, min(value, max_value))


def is_point_in_rect(
    point_x: int|float,
    point_y: int|float,
    rect_x: int|float,
    rect_y: int|float,
    rect_width: int|float,
    rect_height: int|float,
) -> bool:
    """检查点是否在矩形内"""
    return (
        point_x >= rect_x
        and point_x <= rect_x + rect_width
        and point_y >= rect_y
        and point_y <= rect_y + rect_height
    )


class PointerIdManagerStatus(TypedDict):
    """PointerIdManager 状态（用于调试）"""

    available_ids: list[int]
    allocated_count: int
    allocated_ids: dict[int, int]


class PointerIdManager:
    def __init__(self):
        # pointer_id 范围是 1-10
        self._available_ids: set[int] = set(range(1, 11))
        self._allocated_ids: dict[Any, int] = {}  # widget_id -> pointer_id


    def allocate(self, widget:Any) -> int | None:
        """为 widget 分配一个 pointer_id"""
        # widget_id = id(widget)
        widget_id = widget

        # 如果该 widget 已经有分配的 pointer_id，直接返回
        if widget_id in self._allocated_ids:
            return self._allocated_ids[widget_id]

        # 分配新的 pointer_id
        if not self._available_ids:
            return None

        pointer_id = self._available_ids.pop()
        self._allocated_ids[widget_id] = pointer_id

        return pointer_id

    def release(self, widget: Any) -> bool:
        """释放 widget 的 pointer_id"""
        # widget_id = id(widget)
        widget_id = widget

        if widget_id not in self._allocated_ids:
            return False

        pointer_id = self._allocated_ids.pop(widget_id)
        self._available_ids.add(pointer_id)


        return True

    def get_allocated_id(self, widget: Any) -> int | None:
        """获取 widget 当前分配的 pointer_id"""
        # widget_id = id(widget)
        widget_id = widget
        return self._allocated_ids.get(widget_id)

    def get_status(self) -> PointerIdManagerStatus:
        """获取当前分配状态（用于调试）"""
        return {
            "available_ids": sorted(self._available_ids),
            "allocated_count": len(self._allocated_ids),
            "allocated_ids": dict(self._allocated_ids),
        }
