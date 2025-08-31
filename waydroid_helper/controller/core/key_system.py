#!/usr/bin/env python3
"""
按键系统模块
提供类型安全、可维护的按键表示和操作
"""

import threading
from dataclasses import dataclass
from enum import Enum

import gi

gi.require_version("Gdk", "4.0")
from gi.repository import Gdk


class KeyType(Enum):
    """按键类型枚举"""

    MODIFIER = "modifier"  # 修饰键：Ctrl, Alt, Shift等
    FUNCTION = "function"  # 功能键：F1-F12, Enter, Escape等
    CHARACTER = "character"  # 字符键：A-Z, 0-9等
    SPECIAL = "special"  # 特殊键：Space, Tab等
    MOUSE = "mouse"  # 鼠标按键：左键、右键、中键等


@dataclass(frozen=True)
class Key:
    """按键数据类 - 不可变、可哈希"""

    name: str  # 显示名称，如 "Ctrl", "A", "F1"
    keyval: int  # GTK keyval
    key_type: KeyType  # 按键类型

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f"Key({self.name})"


class KeyRegistry:
    """按键注册表 - 管理所有标准按键 (严格单例模式)"""


    def __init__(self):
        self._keys: dict[int, Key] = {}  # keyval -> Key
        self._names: dict[str, Key] = {}  # name -> Key
        self._init_standard_keys()


    def _init_standard_keys(self):
        """初始化标准按键"""
        # 修饰键
        self.register_key("Ctrl_L", Gdk.KEY_Control_L, KeyType.MODIFIER)
        self.register_key("Ctrl_R", Gdk.KEY_Control_R, KeyType.MODIFIER)
        self.register_key("Alt_L", Gdk.KEY_Alt_L, KeyType.MODIFIER)
        self.register_key("Alt_R", Gdk.KEY_Alt_R, KeyType.MODIFIER)
        self.register_key("Shift_L", Gdk.KEY_Shift_L, KeyType.MODIFIER)
        self.register_key("Shift_R", Gdk.KEY_Shift_R, KeyType.MODIFIER)
        self.register_key("Super_L", Gdk.KEY_Super_L, KeyType.MODIFIER)
        self.register_key("Super_R", Gdk.KEY_Super_R, KeyType.MODIFIER)

        # 功能键
        self.register_key("Enter", Gdk.KEY_Return, KeyType.FUNCTION)
        self.register_key("Escape", Gdk.KEY_Escape, KeyType.FUNCTION)
        self.register_key("Backspace", Gdk.KEY_BackSpace, KeyType.FUNCTION)
        self.register_key("Delete", Gdk.KEY_Delete, KeyType.FUNCTION)
        self.register_key("Tab", Gdk.KEY_Tab, KeyType.FUNCTION)
        self.register_key("Home", Gdk.KEY_Home, KeyType.FUNCTION)
        self.register_key("End", Gdk.KEY_End, KeyType.FUNCTION)
        self.register_key("PageUp", Gdk.KEY_Page_Up, KeyType.FUNCTION)
        self.register_key("PageDown", Gdk.KEY_Page_Down, KeyType.FUNCTION)
        self.register_key("Insert", Gdk.KEY_Insert, KeyType.FUNCTION)
        self.register_key("Left", Gdk.KEY_Left, KeyType.FUNCTION)
        self.register_key("Right", Gdk.KEY_Right, KeyType.FUNCTION)
        self.register_key("Up", Gdk.KEY_Up, KeyType.FUNCTION)
        self.register_key("Down", Gdk.KEY_Down, KeyType.FUNCTION)

        # F键
        for i in range(1, 13):
            self.register_key(f"F{i}", getattr(Gdk, f"KEY_F{i}"), KeyType.FUNCTION)

        # 特殊键
        self.register_key("Space", Gdk.KEY_space, KeyType.SPECIAL)

        # 字符键 A-Z - 同时注册大写和小写的keyval
        for i in range(26):
            char = chr(ord("A") + i)
            lower_keyval = ord(char.lower())
            upper_keyval = ord(char.upper())

            # 创建一个Key对象
            key = Key(char, upper_keyval, KeyType.CHARACTER)  # 使用大写keyval作为标准

            # 同时用大写和小写keyval注册同一个Key对象
            self._keys[upper_keyval] = key
            self._keys[lower_keyval] = key
            self._names[char] = key

        # 数字键 0-9
        for i in range(10):
            self.register_key(str(i), ord(str(i)), KeyType.CHARACTER)

        # 鼠标按键 - 使用负数作为keyval以避免与键盘按键冲突
        self.register_key("Mouse_Left", -1, KeyType.MOUSE)
        self.register_key("Mouse_Middle", -2, KeyType.MOUSE)
        self.register_key("Mouse_Right", -3, KeyType.MOUSE)
        self.register_key("Mouse_Back", -8, KeyType.MOUSE)
        self.register_key("Mouse_Forward", -9, KeyType.MOUSE)

    def register_key(self, name: str, keyval: int, key_type: KeyType):
        """注册一个按键"""
        key = Key(name, keyval, key_type)
        self._keys[keyval] = key
        self._names[name] = key

    def get_by_keyval(self, keyval: int) -> Key | None:
        """通过keyval获取按键"""
        return self._keys.get(keyval)

    def get_by_name(self, name: str) -> Key | None:
        """通过名称获取按键"""
        return self._names.get(name)

    def create_from_keyval(self, keyval: int, state: int = 0) -> Key | None:
        """从keyval和state创建按键（支持动态创建）"""
        # 先尝试从注册表获取
        key = self.get_by_keyval(keyval)
        if key:
            return key

        # 处理可打印字符
        if 32 <= keyval <= 126:
            char = chr(keyval).upper()
            return Key(char, keyval, KeyType.CHARACTER)

        # 处理未知按键
        key_name = Gdk.keyval_name(keyval) or f"Key{keyval}"
        return Key(key_name, keyval, KeyType.SPECIAL)

    def create_mouse_key(self, button: int) -> Key:
        """创建鼠标按键"""
        mouse_names = {
            1: "Mouse_Left",
            2: "Mouse_Middle",
            3: "Mouse_Right",
            8: "Mouse_Back",
            9: "Mouse_Forward",
        }

        name = mouse_names.get(button, f"Mouse_Button{button}")
        keyval = -button  # 使用负数避免与键盘按键冲突

        # 先检查是否已注册
        existing_key = self.get_by_name(name)
        if existing_key:
            return existing_key

        # 动态创建并注册
        key = Key(name, keyval, KeyType.MOUSE)
        self._keys[keyval] = key
        self._names[name] = key
        return key

    def deserialize_key(self, key_name: str) -> Key|None:
        # 首先尝试从注册表获取
        key = self.get_by_name(key_name)
        if key:
            return key
        # 如果注册表中没有，尝试重新创建
        key_created = None

        # 对于单字符按键，直接从字符创建
        if len(key_name) == 1 and 32 <= ord(key_name) <= 126:
            char = key_name.upper()
            keyval = ord(char)
            key_created = Key(char, keyval, KeyType.CHARACTER)

        # 对于鼠标按键
        elif key_name.startswith("Mouse"):
            try:
                button_num = int(key_name.replace("Mouse", ""))
                key_created = Key(key_name, button_num, KeyType.MOUSE)
            except ValueError:
                pass

        # 对于其他按键，尝试通过 Gdk.keyval_from_name 获取 keyval
        else:
            try:
                keyval = Gdk.keyval_from_name(key_name)
                if keyval != Gdk.KEY_VoidSymbol:  # 如果找到有效的 keyval
                    # 判断按键类型
                    if 32 <= keyval <= 126:
                        key_created = Key(key_name, keyval, KeyType.CHARACTER)
                    else:
                        key_created = Key(key_name, keyval, KeyType.SPECIAL)
            except:
                pass

        # 如果还是无法创建，创建一个临时按键（用于向后兼容）
        if not key_created:
            key_created = Key(key_name, 0, KeyType.SPECIAL)

        if key_created:
            # 将动态创建的按键添加到注册表中，避免重复创建
            self.register_key(
                key_created.name, key_created.keyval, key_created.key_type
            )
        return key_created

@dataclass(frozen=True)
class KeyCombination:
    """按键组合 - 不可变、可哈希、可排序"""

    keys: tuple[Key, ...]  # 按键元组，保持有序

    def __init__(self, keys: list[Key]):
        # 按键类型优先级排序：修饰键 > 功能键 > 特殊键 > 字符键 > 鼠标键
        type_priority = {
            KeyType.MODIFIER: 0,
            KeyType.FUNCTION: 1,
            KeyType.SPECIAL: 2,
            KeyType.CHARACTER: 3,
            KeyType.MOUSE: 4,
        }

        sorted_keys = sorted(keys, key=lambda k: (type_priority[k.key_type], k.name))
        object.__setattr__(self, "keys", tuple(sorted_keys))

    def __str__(self):
        return "+".join(sorted(key.name for key in self.keys))

    def __repr__(self):
        return f"<KeyCombination({self})>"

    def __len__(self):
        return len(self.keys)

    def __iter__(self):
        return iter(self.keys)

    def __contains__(self, key: Key):
        return key in self.keys

    @property
    def display_text(self) -> str:
        """获取显示文本"""
        return str(self)

    @property
    def has_modifiers(self) -> bool:
        """是否包含修饰键"""
        return any(key.key_type == KeyType.MODIFIER for key in self.keys)

    @classmethod
    def from_names(cls, names: list[str], registry: KeyRegistry) -> "KeyCombination":
        """从名称列表创建按键组合"""
        keys: list[Key] = []
        for name in names:
            key = registry.get_by_name(name)
            if key:
                keys.append(key)
        return cls(keys)

    @classmethod
    def from_keyvals(
        cls, keyvals: list[int], registry: KeyRegistry
    ) -> "KeyCombination":
        """从keyval列表创建按键组合"""
        keys: list[Key] = []
        for keyval in keyvals:
            key = registry.create_from_keyval(keyval)
            if key:
                keys.append(key)
        return cls(keys)

    def get_frozen_keys(self) -> frozenset[Key]:
        return frozenset(self.keys)

    def is_subset_of(self, other: "KeyCombination") -> bool:
        """检查此组合是否是另一个组合的子集"""
        return self.get_frozen_keys().issubset(other.get_frozen_keys())

