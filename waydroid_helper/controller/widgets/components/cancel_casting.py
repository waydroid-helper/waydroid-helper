"""Cancellation targets placed over the game's cancel area."""

from waydroid_helper.controller.core import Event, EventType, KeyCombination
from waydroid_helper.controller.core.handler.event_handlers import InputEvent, InputEventType
from waydroid_helper.controller.widgets.base.cast_cancel_button import CastCancelButton


class CancelCasting(CastCancelButton):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from waydroid_helper.controller.widgets.components.skill_casting import SkillCasting
        SkillCasting.cancel_button_widget["widget"] = self
        SkillCasting.cancel_button_config.value = True

    def on_key_triggered(
        self,
        key_combination: "KeyCombination | None" = None,
        event: "InputEvent | None" = None,
    ):
        """触发取消施法"""

        # 分配 pointer_id
        pointer_id = self.pointer_id_manager.allocate(self)
        if pointer_id is None:
            return False

        x, y = self.center_x, self.center_y

        # 发送取消施法事件而不是实际的触摸事件
        cancel_data = {
            "source_widget_id": id(self),
            "x": x,
            "y": y,
        }

        self.event_bus.emit(Event(EventType.CANCEL_CASTING, self, cancel_data))
        return True

    def on_delete(self):
        """组件被删除时的清理"""
        super().on_delete()
        
        # 发送销毁通知
        event_data = {
            'widget_class': 'CancelCasting',
            'widget_id': id(self)
        }
        
        from waydroid_helper.controller.widgets.components.skill_casting import SkillCasting
        SkillCasting.cancel_button_widget["widget"] = None
        SkillCasting.cancel_button_config.value = False


class GamepadCancelCasting(CastCancelButton):
    EMBEDDED_ONLY = True

    def on_key_triggered(self, key_combination=None, event=None):
        if (not self.mapping_mode or not event or event.event_type != InputEventType.KEY_PRESS
                or not event.right_stick or not key_combination or event.key not in key_combination):
            return False
        return event.right_stick.cancel_at(self.center_x, self.center_y)
