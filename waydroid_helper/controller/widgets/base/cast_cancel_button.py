from gettext import pgettext
from typing import TYPE_CHECKING

from waydroid_helper.controller.widgets.base import control_art as art

if TYPE_CHECKING:
    from waydroid_helper.controller.widgets.base.base_widget import EditableRegion

from waydroid_helper.controller.core import (
    ControllerRuntimeContext,
    KeyCombination,
)
from waydroid_helper.controller.widgets.base.base_widget import BaseWidget
from waydroid_helper.controller.widgets.decorators import Editable


@Editable
class CastCancelButton(BaseWidget):
    """取消施法按钮组件"""

    # 组件元数据
    WIDGET_NAME = pgettext("Controller Widgets", "Cancel Casting")
    PLACED_HINT = pgettext(
        "Controller Widgets",
        "Place this over the game's cancel target and bind a key or button to cancel a cast",
    )
    WIDGET_DESCRIPTION = pgettext(
        "Controller Widgets",
        "Drag the key to the cancel casting position. While casting a spell, hold down the cancel cast button to cancel the cast.",
    )

    # 禁止通过右键菜单创建
    ALLOW_CONTEXT_MENU_CREATION = False

    # 映射模式固定尺寸
    MAPPING_MODE_HEIGHT = 30

    @property
    def MAPPING_MODE_WIDTH(self):
        """根据文字长度计算映射模式宽度，与draw_mapping_mode_background的逻辑保持一致"""
        if self.text:
            # 估算文字宽度：对于12px的Arial字体
            # 英文数字字符平均约7-8px，为保险起见用8px
            # 中文字符约12px，这里简化统一按8px估算（略保守）
            estimated_text_width = len(self.text) * 8

            # 加上左右内边距 (padding_x = 8 * 2 = 16)
            padding_x = 8
            rect_width = estimated_text_width + 2 * padding_x

            # 确保最小宽度 24，与draw_mapping_mode_background一致
            rect_width = max(rect_width, 24)

            # 为了保险起见，再加4px缓冲，确保不会被截断
            return rect_width + 4
        else:
            # 无文字时的默认宽度，与draw_mapping_mode_background的default保持一致
            return 24 + 4  # 24是最小宽度，+4是缓冲

    def __init__(
        self,
        x: int = 0,
        y: int = 0,
        width: int = 50,
        height: int = 50,
        text: str = "",
        default_keys: "set[KeyCombination] | None" = None,
        *,
        runtime_context: ControllerRuntimeContext,
    ):
        # 初始化基类
        super().__init__(
            x,
            y,
            50,
            50,
            pgettext("Controller Widgets", "Cancel Casting"),
            text,
            default_keys,
            min_width=25,
            min_height=25,
            runtime_context=runtime_context,
        )

    def draw_widget_content(self, cr, width, height):
        super().draw_widget_content(cr, width, height)
        art.caption(cr, width / 2, height * .76, "×", 10)

    def on_key_released(self, key_combination=None, event=None):
        """按键释放时不做任何操作"""
        return True

    def get_editable_regions(self) -> list["EditableRegion"]:
        return [
            {
                "id": "default",
                "name": "按键映射",
                "bounds": (0, 0, self.width, self.height),
                "get_keys": lambda: self.final_keys.copy(),
                "set_keys": lambda keys: setattr(
                    self, "final_keys", set(keys) if keys else set()
                ),
            }
        ]

    @property
    def center_x(self):
        return self.x + self.width / 2

    @property
    def center_y(self):
        return self.y + self.height / 2
