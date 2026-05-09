#!/usr/bin/env python3
"""Source-neutral key model and registry."""

from dataclasses import dataclass
from enum import Enum
from typing import Protocol


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
    keyval: int  # Source-neutral code; GTK adapters currently use keysyms.
    key_type: KeyType  # 按键类型

    def __str__(self) -> str:
        return self.name

    def __repr__(self) -> str:
        return f"Key({self.name})"


class KeySymbolResolver(Protocol):
    """Optional adapter for source-specific key symbol lookup."""

    def name_from_code(self, code: int) -> str | None:
        ...

    def code_from_name(self, name: str) -> int | None:
        ...


STANDARD_KEY_SYMBOLS: dict[str, int] = {
    "Ctrl_L": 0xFFE3,
    "Ctrl_R": 0xFFE4,
    "Alt_L": 0xFFE9,
    "Alt_R": 0xFFEA,
    "Shift_L": 0xFFE1,
    "Shift_R": 0xFFE2,
    "Super_L": 0xFFEB,
    "Super_R": 0xFFEC,
    "Enter": 0xFF0D,
    "Escape": 0xFF1B,
    "Backspace": 0xFF08,
    "Delete": 0xFFFF,
    "Tab": 0xFF09,
    "Home": 0xFF50,
    "End": 0xFF57,
    "PageUp": 0xFF55,
    "PageDown": 0xFF56,
    "Insert": 0xFF63,
    "Left": 0xFF51,
    "Right": 0xFF53,
    "Up": 0xFF52,
    "Down": 0xFF54,
    "Space": 0x20,
}


class KeyRegistry:
    """按键注册表 - 管理所有标准按键"""

    def __init__(self, symbol_resolver: KeySymbolResolver | None = None):
        self._symbol_resolver = symbol_resolver
        self._keys: dict[int, Key] = {}  # keyval -> Key
        self._names: dict[str, Key] = {}  # name -> Key
        self._init_standard_keys()

    def _init_standard_keys(self):
        """初始化标准按键"""
        # 修饰键
        self.register_symbol_key("Ctrl_L", KeyType.MODIFIER)
        self.register_symbol_key("Ctrl_R", KeyType.MODIFIER)
        self.register_symbol_key("Alt_L", KeyType.MODIFIER)
        self.register_symbol_key("Alt_R", KeyType.MODIFIER)
        self.register_symbol_key("Shift_L", KeyType.MODIFIER)
        self.register_symbol_key("Shift_R", KeyType.MODIFIER)
        self.register_symbol_key("Super_L", KeyType.MODIFIER)
        self.register_symbol_key("Super_R", KeyType.MODIFIER)

        # 功能键
        self.register_symbol_key("Enter", KeyType.FUNCTION)
        self.register_symbol_key("Escape", KeyType.FUNCTION)
        self.register_symbol_key("Backspace", KeyType.FUNCTION)
        self.register_symbol_key("Delete", KeyType.FUNCTION)
        self.register_symbol_key("Tab", KeyType.FUNCTION)
        self.register_symbol_key("Home", KeyType.FUNCTION)
        self.register_symbol_key("End", KeyType.FUNCTION)
        self.register_symbol_key("PageUp", KeyType.FUNCTION)
        self.register_symbol_key("PageDown", KeyType.FUNCTION)
        self.register_symbol_key("Insert", KeyType.FUNCTION)
        self.register_symbol_key("Left", KeyType.FUNCTION)
        self.register_symbol_key("Right", KeyType.FUNCTION)
        self.register_symbol_key("Up", KeyType.FUNCTION)
        self.register_symbol_key("Down", KeyType.FUNCTION)

        # F键
        for i in range(1, 13):
            self.register_key(f"F{i}", 0xFFBD + i, KeyType.FUNCTION)

        # 特殊键
        self.register_symbol_key("Space", KeyType.SPECIAL)

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

    def register_symbol_key(self, name: str, key_type: KeyType) -> None:
        """Register a well-known symbolic key without importing a toolkit."""
        keyval = self._resolve_code_from_name(name)
        if keyval is None:
            keyval = STANDARD_KEY_SYMBOLS[name]
        self.register_key(name, keyval, key_type)

    def register_key(self, name: str, keyval: int, key_type: KeyType) -> Key:
        """注册一个按键"""
        key = Key(name, keyval, key_type)
        self._keys[keyval] = key
        self._names[name] = key
        return key

    def get_by_keyval(self, keyval: int) -> Key | None:
        """通过keyval获取按键"""
        return self._keys.get(keyval)

    def get_by_name(self, name: str) -> Key | None:
        """通过名称获取按键"""
        return self._names.get(name)

    def create_from_keyval(self, keyval: int, state: int = 0) -> Key | None:
        """从keyval和state创建按键（支持动态创建）"""
        return self.create_from_symbol(self._resolve_name_from_code(keyval), keyval)

    def create_from_symbol(
        self,
        key_name: str | None,
        keyval: int,
        key_type: KeyType | None = None,
    ) -> Key | None:
        """Create or reuse a key from a source-specific symbolic name/code."""
        key = self.get_by_keyval(keyval)
        if key:
            return key

        if key_name:
            key = self.get_by_name(key_name)
            if key:
                return key

        # 处理可打印字符
        if 32 <= keyval <= 126:
            char = chr(keyval).upper()
            return self.register_key(char, keyval, KeyType.CHARACTER)

        # 处理未知按键
        key_name = key_name or f"Key{keyval}"
        return self.register_key(key_name, keyval, key_type or KeyType.SPECIAL)

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

    def deserialize_key(self, key_name: str) -> Key | None:
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
        elif key_name.startswith("Mouse_Button"):
            try:
                button_num = int(key_name.removeprefix("Mouse_Button"))
                key_created = Key(key_name, -button_num, KeyType.MOUSE)
            except ValueError:
                pass

        # 对于其他按键，尝试通过 source-specific resolver 获取 code
        else:
            keyval = self._resolve_code_from_name(key_name)
            if keyval is not None:
                key_created = self.create_from_symbol(key_name, keyval)

        # 如果还是无法创建，创建一个临时按键（用于向后兼容）
        if not key_created:
            key_created = Key(key_name, 0, KeyType.SPECIAL)

        if key_created:
            # 将动态创建的按键添加到注册表中，避免重复创建
            self.register_key(
                key_created.name, key_created.keyval, key_created.key_type
            )
        return key_created

    def _resolve_code_from_name(self, name: str) -> int | None:
        if self._symbol_resolver is None:
            return None
        return self._symbol_resolver.code_from_name(name)

    def _resolve_name_from_code(self, code: int) -> str | None:
        if self._symbol_resolver is None:
            return None
        return self._symbol_resolver.name_from_code(code)

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
