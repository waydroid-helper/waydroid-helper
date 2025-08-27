#!/usr/bin/env python3
"""
按键映射管理器
负责管理和处理所有的按键映射订阅和触发
"""
import itertools
from typing import TYPE_CHECKING, Any, Callable

from waydroid_helper.controller.core.event_bus import (Event, EventType,
                                                       EventBus)
from waydroid_helper.controller.core.handler.event_handlers import InputEvent
from waydroid_helper.controller.core.key_system import Key, KeyCombination

if TYPE_CHECKING:
    from gi.repository import Gtk


class KeySubscription:
    """按键订阅信息"""

    def __init__(
        self,
        widget: "Gtk.Widget",
        key_combination: KeyCombination,
        condition: Callable[[], bool] | None = None,
        required_states: list[str] | None = None,
        reentrant: bool = False,
    ):
        self.widget: "Gtk.Widget" = widget
        self.key_combination: KeyCombination = key_combination
        self.callback: str = "on_key_triggered"
        self.release_callback: str = "on_key_released"
        self.condition: Callable[[], bool] | None = condition
        self.required_states: list[str] = required_states or []
        self.reentrant: bool = reentrant  # 是否支持重入（长按重复触发）


class KeyMappingManager:
    """按键映射管理器 - 单例"""

    def __init__(self, event_bus: EventBus):
        # 防止重复初始化
        self._key_subscriptions: dict[KeyCombination, list[KeySubscription]] = {}
        self._pressed_keys: set[Key] = set()
        self._triggered_mappings: dict[KeyCombination, set[Key]] = {}

        # 为了检查依赖状态，需要一个对widget状态的引用，暂时留空
        self._widget_states: dict[int, dict[str, Any]] = {}
        self.event_bus = event_bus

        self.event_bus.subscribe(EventType.MACRO_KEY_PRESSED, self._on_macro_key_pressed)
        self.event_bus.subscribe(EventType.MACRO_KEY_RELEASED, self._on_macro_key_released)

    def _on_macro_key_pressed(self, event: Event[Key]):
        self.handle_key_press(InputEvent(event_type="key_press", key=event.data))

    def _on_macro_key_released(self, event: Event[Key]):
        self.handle_key_release(InputEvent(event_type="key_release", key=event.data))

    def subscribe(
        self,
        widget: "Gtk.Widget",
        key_combination: KeyCombination,
        condition: Callable[[], bool] | None = None,
        required_states: list[str] | None = None,
        reentrant: bool = False,
    ) -> bool:
        """订阅按键事件"""
        if not key_combination:
            return False

        subscription = KeySubscription(
            widget=widget,
            key_combination=key_combination,
            condition=condition,
            required_states=required_states or [],
            reentrant=reentrant,
        )

        if key_combination not in self._key_subscriptions:
            self._key_subscriptions[key_combination] = []
        self._key_subscriptions[key_combination].append(subscription)

        return True

    def unsubscribe(self, widget: "Gtk.Widget") -> bool:
        """取消widget的所有按键订阅"""
        widget_id = id(widget)
        # 创建一个副本进行迭代，因为我们可能会在循环中修改字典
        for key_combination in list(self._key_subscriptions.keys()):

            # 过滤掉属于该widget的订阅
            self._key_subscriptions[key_combination] = [
                sub
                for sub in self._key_subscriptions[key_combination]
                if id(sub.widget) != widget_id
            ]

            # 如果某个key_combination的订阅列表空了，就从字典中移除它
            if not self._key_subscriptions[key_combination]:
                del self._key_subscriptions[key_combination]

        return True

    def unsubscribe_key(
        self, widget: "Gtk.Widget", key_combination: KeyCombination
    ) -> bool:
        """取消widget的特定按键订阅"""
        widget_id = id(widget)

        if key_combination in self._key_subscriptions:
            self._key_subscriptions[key_combination] = [
                sub
                for sub in self._key_subscriptions[key_combination]
                if not (
                    id(sub.widget) == widget_id
                    and sub.key_combination == key_combination
                )
            ]

            if not self._key_subscriptions[key_combination]:
                del self._key_subscriptions[key_combination]

        return True

    def get_subscriptions(self, widget: "Gtk.Widget") -> list[KeyCombination]:
        """获取widget的所有按键订阅"""
        widget_id = id(widget)
        result: list[KeyCombination] = []

        for key_combination, subscriptions in self._key_subscriptions.items():
            if any(id(sub.widget) == widget_id for sub in subscriptions):
                result.append(key_combination)

        return result

    def handle_key_press(self, event: InputEvent) -> bool:
        """处理按键按下事件，返回事件是否被消费"""
        if event.key:
            self._pressed_keys.add(event.key)

        triggered_new = self._check_and_trigger_mappings(event)

        # 如果触发了新映射，事件肯定被消费
        if triggered_new:
            return True

        # 检查是否有非重入的订阅正在处理这个按键
        # 只有当所有相关的订阅都是可重入的时，才允许事件传递给下一个handler
        for key_combination, triggered_keys in self._triggered_mappings.items():
            if event.key in triggered_keys:
                # 检查这个key_combination是否有非重入的订阅
                if key_combination in self._key_subscriptions:
                    has_non_reentrant = any(
                        not sub.reentrant for sub in self._key_subscriptions[key_combination]
                    )
                    if has_non_reentrant:
                        return True  # 有非重入的订阅在处理，消费事件

        return False

    def handle_key_release(self, event: InputEvent) -> bool:
        """处理按键释放事件，返回事件是否被消费"""
        if event.key not in self._pressed_keys:
            return False

        # 检查释放这个键是否会导致某个映射被释放
        released_a_mapping = self._check_mapping_release(event.key)

        # 从按下的键中移除
        self._pressed_keys.remove(event.key)

        # 在释放一个键后，可能会触发一个新的、更短的组合
        triggered_new_on_release = self._check_and_trigger_mappings(event)

        # 只要释放了旧的映射，或者触发了新的映射，都算事件被消费
        return released_a_mapping or triggered_new_on_release

    def _check_subscription_conditions(self, subscription: KeySubscription) -> bool:
        """检查订阅的触发条件"""
        if subscription.condition and not subscription.condition():
            return False

        if subscription.required_states:
            widget_id = id(subscription.widget)
            widget_states = self._widget_states.get(widget_id, {})
            for state_name in subscription.required_states:
                if not widget_states.get(state_name):
                    return False

        return True

    def _check_and_trigger_mappings(self, event:InputEvent) -> bool:
        """检查并触发匹配的映射"""
        triggered_any = False
        pressed_keys_list = list(self._pressed_keys)

        # 从最长的组合开始检查，以支持 "Ctrl+Shift+A" 优先于 "Ctrl+A"
        for size in range(len(pressed_keys_list), 0, -1):
            for combo_tuple in itertools.combinations(pressed_keys_list, size):
                key_combination = KeyCombination(list(combo_tuple))

                if key_combination in self._key_subscriptions:
                    # 检查此组合是否是其他已触发组合的子集，如果是，则不触发
                    # is_subset_of_triggered = False
                    # for triggered_combo in self._triggered_mappings.keys():
                    #     if key_combination.is_subset_of(triggered_combo):
                    #         is_subset_of_triggered = True
                    #         break
                    # if is_subset_of_triggered:
                    #     continue

                    # 检查是否已经触发过，以及是否有可重入的订阅
                    already_triggered = key_combination in self._triggered_mappings
                    has_reentrant_subscription = any(
                        sub.reentrant for sub in self._key_subscriptions[key_combination]
                    )
                    
                    # 如果已经触发过且没有可重入订阅，则跳过
                    if already_triggered and not has_reentrant_subscription:
                        continue

                    # 如果是第一次触发，预记录到 _triggered_mappings 中
                    if not already_triggered:
                        self._triggered_mappings[key_combination] = set(combo_tuple)
                    
                    combo_triggered_this_time = False
                    try:
                        for subscription in self._key_subscriptions[key_combination]:
                            if not self._check_subscription_conditions(subscription):
                                continue

                            # 如果已经触发过，只处理可重入的订阅
                            if already_triggered and not subscription.reentrant:
                                continue

                            if hasattr(subscription.widget, subscription.callback):
                                callback = getattr(
                                    subscription.widget, subscription.callback
                                )
                                # 假设回调返回True表示事件被处理
                                if callback(key_combination, event):
                                    combo_triggered_this_time = True

                        if combo_triggered_this_time:
                            triggered_any = True
                        elif not already_triggered:
                            # 如果是第一次触发但没有成功，则从 _triggered_mappings 中移除预记录
                            del self._triggered_mappings[key_combination]
                    except Exception as e:
                        # 如果回调函数执行过程中出现异常，确保清理预记录的映射
                        if not already_triggered and key_combination in self._triggered_mappings:
                            del self._triggered_mappings[key_combination]
                        raise

        return triggered_any
    def _check_mapping_release(self, released_key: Key) -> bool:
        """处理映射释放，返回是否有映射被释放"""
        released_any = False
        # 使用 list() 来创建副本，因为我们可能在循环中删除元素
        for mapping_key, related_keys in list(self._triggered_mappings.items()):
            if released_key in related_keys:
                if mapping_key in self._key_subscriptions:
                    for subscription in self._key_subscriptions[mapping_key]:
                        if hasattr(subscription.widget, subscription.release_callback):
                            callback = getattr(
                                subscription.widget, subscription.release_callback
                            )
                            # 假设释放回调也返回布尔值
                            if callback(mapping_key):
                                released_any = True

                del self._triggered_mappings[mapping_key]
        return released_any

    def print_mappings(self):
        """Print current key mappings (for debugging)"""

        if not self._key_subscriptions:
            pass
        else:
            for key_combo, subscriptions in self._key_subscriptions.items():
                for sub in subscriptions:
                    widget_name = type(sub.widget).__name__
                    widget_id = id(sub.widget)
                    conditions = []
                    if sub.condition:
                        conditions.append("custom condition")
                    if sub.required_states:
                        conditions.append(f"required states: {sub.required_states}")
                    if sub.reentrant:
                        conditions.append("reentrant")
                    conditions_str = f" ({', '.join(conditions)})" if conditions else ""

    def clear(self) -> None:
        """清空所有订阅和状态"""
        self._key_subscriptions.clear()
        self._pressed_keys.clear()
        self._triggered_mappings.clear()


# # 全局实例
# key_mapping_manager = KeyMappingManager()
