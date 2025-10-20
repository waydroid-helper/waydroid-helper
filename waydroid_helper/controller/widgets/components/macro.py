#!/usr/bin/env python3
"""
宏组件
一个圆形的半透明灰色按钮，支持单击操作，可以配置宏命令
"""

import asyncio
import math
from abc import ABC, abstractmethod
from gettext import pgettext
from typing import TYPE_CHECKING, NamedTuple, cast

from waydroid_helper.controller.android import AMotionEventAction, AMotionEventButtons
from waydroid_helper.controller.core.control_msg import InjectTouchEventMsg, ScreenInfo
from waydroid_helper.util.log import logger

if TYPE_CHECKING:
    from cairo import Context, Surface
    from gi.repository import Gtk
    from waydroid_helper.controller.widgets.base.base_widget import EditableRegion

from waydroid_helper.controller.core.handler.event_handlers import InputEvent
from waydroid_helper.controller.core.utils import PointerIdManager

from cairo import FontSlant, FontWeight
from waydroid_helper.controller.core import (
    Event,
    EventType,
    KeyCombination,
    EventBus,
    KeyRegistry,
)
from waydroid_helper.controller.widgets.base.base_widget import BaseWidget
from waydroid_helper.controller.widgets.config import create_textarea_config
from waydroid_helper.controller.widgets.decorators import Editable


class MacroCommand(NamedTuple):
    """宏命令数据结构"""

    command_type: str  # "key_press", "key_release", "sleep", "release_all"
    args: list[str]  # 命令参数


# ==================== 命令模式实现 ====================


class Command(ABC):
    """抽象命令接口"""

    @abstractmethod
    async def execute(self, context: "Macro") -> None:
        """执行命令"""

    async def cancel(self, context: "Macro") -> None:
        """取消/释放命令的状态，默认实现为空操作"""


class KeyPressCommand(Command):
    """按键按下命令"""

    def __init__(self, key_names: list[str]):
        self.key_names = key_names

    async def execute(self, context: "Macro") -> None:
        for key_name in self.key_names:
            try:
                key = context.key_registry.deserialize_key(key_name)
                context.event_bus.emit(
                    Event(
                        type=EventType.MACRO_KEY_PRESSED,
                        source=context,
                        data=key,
                    )
                )
            except ValueError:
                pass

    async def cancel(self, context: "Macro") -> None:
        """取消按键按下 - 释放所有由此命令按下的按键"""
        for key_name in self.key_names:
            if key_name in self.key_names:
                try:
                    key = context.key_registry.deserialize_key(key_name)
                    context.event_bus.emit(
                        Event(
                            type=EventType.MACRO_KEY_RELEASED,
                            source=context,
                            data=key,
                        )
                    )
                except ValueError:
                    pass


class KeyReleaseCommand(Command):
    """按键释放命令"""

    def __init__(self, key_names: list[str]):
        self.key_names = key_names

    async def execute(self, context: "Macro") -> None:
        for key_name in self.key_names:
            try:
                key = context.key_registry.deserialize_key(key_name)
                context.event_bus.emit(
                    Event(
                        type=EventType.MACRO_KEY_RELEASED,
                        source=context,
                        data=key,
                    )
                )
            except ValueError:
                pass


class KeySwitchCommand(Command):
    """按键切换命令"""

    def __init__(self, key_names: list[str]):
        self.key_names = key_names
        self.is_pressed = False
        self.press_command = KeyPressCommand(key_names)
        self.release_command = KeyReleaseCommand(key_names)

    async def execute(self, context: "Macro") -> None:
        if self.is_pressed:
            await self.release_command.execute(context)
        else:
            await self.press_command.execute(context)
        self.is_pressed = not self.is_pressed

    async def cancel(self, context: "Macro") -> None:
        """取消按键切换 - 如果当前是按下状态则释放，并重置状态"""
        if self.is_pressed:
            await self.release_command.execute(context)
            self.is_pressed = False


class PressCommand(Command):
    """按下命令 - 处理触摸按下事件"""

    def __init__(self, points: list[str]):
        # ["x,y", "x1,y1"...]
        self.points = points
        # Use deterministic identifiers based on point content for consistent pointer ID management
        self._point_identifiers = [
            self._create_point_identifier(point) for point in points
        ]

    def _create_point_identifier(self, point: str) -> tuple[int, int]:
        """
        Create a deterministic identifier for a point that can be shared across commands.

        Args:
            point: Point string (either "mouse" or "x,y" format)

        Returns:
            str: Deterministic identifier for the point
        """
        # For "mouse", use a special identifier since coordinates change
        if point == "mouse":
            return (-1, -1)  # Use command instance ID for mouse points
        else:
            # For fixed coordinates, use the coordinates as identifier
            x, y = point.split(",")
            x, y = int(x), int(y)
            return (x, y)

    def _parse_coordinates(self, context: "Macro") -> list[tuple[int, int]]:
        """
        Parse all point coordinates once at the beginning.

        Args:
            context: The macro context

        Returns:
            list[tuple[int, int]]: List of (x, y) coordinates
        """
        coordinates: list[tuple[int, int]] = []
        for point in self.points:
            if point == "mouse":
                x, y = context.get_cursor_position()
            else:
                x, y = point.split(",")
                x, y = int(x), int(y)
            coordinates.append((x, y))
        return coordinates

    async def execute(self, context: "Macro") -> None:
        # Parse all coordinates once at the beginning
        coordinates = self._parse_coordinates(context)

        # Get window dimensions once
        w, h = context.screen_info.get_host_resolution()

        # Send DOWN events for all points
        for idx, (x, y) in enumerate(coordinates):
            point_id = self._point_identifiers[idx]
            pointer_id = context.pointer_id_manager.allocate(point_id)
            if pointer_id is None:
                return  # Exit early if allocation fails

            msg = InjectTouchEventMsg(
                action=AMotionEventAction.DOWN,
                pointer_id=pointer_id,
                position=(x, y, w, h),
                pressure=1.0,
                action_button=AMotionEventButtons.PRIMARY,
                buttons=AMotionEventButtons.PRIMARY,
            )
            context.event_bus.emit(Event(EventType.CONTROL_MSG, context, msg))

    async def cancel(self, context: "Macro") -> None:
        """取消按下命令 - 释放所有已分配的触摸指针"""
        # Get window dimensions
        w, h = context.screen_info.get_host_resolution()

        # Parse coordinates for UP events
        coordinates = self._parse_coordinates(context)

        # Send UP events for all points that have allocated pointer IDs
        for idx, (x, y) in enumerate(coordinates):
            point_id = self._point_identifiers[idx]
            pointer_id = context.pointer_id_manager.get_allocated_id(point_id)
            if pointer_id is not None:
                msg = InjectTouchEventMsg(
                    action=AMotionEventAction.UP,
                    pointer_id=pointer_id,
                    position=(x, y, w, h),
                    pressure=0.0,
                    action_button=AMotionEventButtons.PRIMARY,
                    buttons=0,
                )
                context.event_bus.emit(Event(EventType.CONTROL_MSG, context, msg))
                # Release the pointer ID
                context.pointer_id_manager.release(point_id)


class ReleaseCommand(Command):
    """释放命令 - 处理触摸释放事件"""

    def __init__(self, points: list[str]):
        # ["x,y", "x1,y1"...]
        self.points = points
        # Use the same deterministic identifier system as PressCommand
        self._point_identifiers = [
            self._create_point_identifier(point) for point in points
        ]

    def _create_point_identifier(self, point: str) -> tuple[int, int]:
        """
        Create a deterministic identifier for a point that matches PressCommand.

        Note: For "mouse" points, this will create a different identifier than PressCommand
        since each command instance has a different ID. For proper mouse point release,
        the identifier should be shared between PressCommand and ReleaseCommand instances.

        Args:
            point: Point string (either "mouse" or "x,y" format)

        Returns:
            str: Deterministic identifier for the point
        """
        if point == "mouse":
            return (-1, -1)  # This needs to be coordinated with PressCommand
        else:
            x, y = point.split(",")
            x, y = int(x), int(y)
            return (x, y)

    def _parse_coordinates(self, context: "Macro") -> list[tuple[int, int]]:
        """
        Parse all point coordinates once at the beginning.

        Args:
            context: The macro context

        Returns:
            list[tuple[int, int]]: List of (x, y) coordinates
        """
        coordinates: list[tuple[int, int]] = []
        for point in self.points:
            if point == "mouse":
                x, y = context.get_cursor_position()
            else:
                x, y = point.split(",")
                x, y = int(x), int(y)
            coordinates.append((x, y))
        return coordinates

    def set_point_identifiers(self, identifiers: list[tuple[int, int]]) -> None:
        """
        Set point identifiers to match those used by a corresponding PressCommand.
        This enables proper pointer ID sharing between press and release commands.

        Args:
            identifiers: List of point identifiers from PressCommand
        """
        if len(identifiers) != len(self.points):
            return
        self._point_identifiers = identifiers

    async def execute(self, context: "Macro") -> None:
        # Parse all coordinates once at the beginning
        coordinates = self._parse_coordinates(context)

        # Get window dimensions once
        w, h = context.screen_info.get_host_resolution()

        # Send UP events for all points
        for idx, (x, y) in enumerate(coordinates):
            point_id = self._point_identifiers[idx]
            # 打印一下 id(point_id) 红色
            pointer_id = context.pointer_id_manager.get_allocated_id(point_id)
            if pointer_id is None:
                continue  # Continue with other points even if one fails

            msg = InjectTouchEventMsg(
                action=AMotionEventAction.UP,
                pointer_id=pointer_id,
                position=(x, y, w, h),
                pressure=0.0,
                action_button=AMotionEventButtons.PRIMARY,
                buttons=0,
            )
            context.event_bus.emit(Event(EventType.CONTROL_MSG, context, msg))

            # Release the pointer ID after sending UP event
            context.pointer_id_manager.release(point_id)


class SwitchCommand(Command):
    """切换命令 - 处理触摸切换事件，在按下和释放之间切换"""

    def __init__(self, points: list[str]):
        # ["x,y", "x1,y1"...]
        self.points = points
        self.is_pressed = False
        # 创建内部的 press 和 release 命令
        self.press_command = PressCommand(points)
        self.release_command = ReleaseCommand(points)

    async def execute(self, context: "Macro") -> None:
        if self.is_pressed:
            # 当前是按下状态，执行释放
            await self.release_command.execute(context)
        else:
            # 当前是释放状态，执行按下
            await self.press_command.execute(context)
        # 切换状态
        self.is_pressed = not self.is_pressed

    async def cancel(self, context: "Macro") -> None:
        """取消触摸切换 - 如果当前是按下状态则释放，并重置状态"""
        if self.is_pressed:
            await self.release_command.execute(context)
            self.is_pressed = False


class ClickCommand(Command):
    """点击命令 - 组合按下和释放命令"""

    def __init__(self, points: list[str]):
        # ["x,y", "x1,y1"...]
        self.points = points
        # Create press and release commands
        self.press_command = PressCommand(points)
        self.release_command = ReleaseCommand(points)

    async def execute(self, context: "Macro") -> None:
        # Execute press command (DOWN events)
        await self.press_command.execute(context)

        # Wait 0.05 seconds between DOWN and UP events
        await asyncio.sleep(0.05)

        # Execute release command (UP events)
        await self.release_command.execute(context)


class SleepCommand(Command):
    """延迟命令"""

    def __init__(self, sleep_time: float):
        self.sleep_time = sleep_time

    async def execute(self, context: "Macro") -> None:
        if self.sleep_time > 0:
            await asyncio.sleep(self.sleep_time)

class ReleaseAllCommand(Command):
    """释放所有按键命令"""

    async def execute(self, context: "Macro") -> None:
        context.event_bus.emit(
            Event(type=EventType.MACRO_RELEASE_ALL, source=context, data=None)
        )


class EnterStaringCommand(Command):
    """进入瞄准模式命令"""

    async def execute(self, context: "Macro") -> None:

        context.event_bus.emit(
            Event(
                type=EventType.ENTER_STARING,
                source=context,
                data=None,
            )
        )

    async def cancel(self, context: "Macro") -> None:
        """取消进入瞄准模式 - 发送退出瞄准模式事件"""
        context.event_bus.emit(
            Event(
                type=EventType.EXIT_STARING,
                source=context,
                data=None,
            )
        )


class ExitStaringCommand(Command):
    """退出瞄准模式命令"""

    async def execute(self, context: "Macro") -> None:

        context.event_bus.emit(
            Event(
                type=EventType.EXIT_STARING,
                source=context,
                data=None,
            )
        )


class SwipeholdRadiusCommand(Command):
    """滑动半径设置命令"""

    # 参数是倍数(float), 如 0.5
    def __init__(self, factor: float):
        self.factor = factor

    async def execute(self, context: "Macro") -> None:
        context.event_bus.emit(
            Event(
                type=EventType.SWIPEHOLD_RADIUS,
                source=context,
                data=self.factor,
            )
        )

    async def cancel(self, context: "Macro") -> None:
        """取消滑动半径设置 - 重置为默认半径"""
        # 重置为默认半径 (1.0)
        context.event_bus.emit(
            Event(
                type=EventType.SWIPEHOLD_RADIUS,
                source=context,
                data=1.0,
            )
        )


class SwipeholdRadiusSwitchCommand(Command):
    """滑动半径增加切换命令"""

    # 参数是倍数(float), 如 0.5
    def __init__(self, factor: float):
        self.factor = factor
        self.is_enabled = False

    async def execute(self, context: "Macro") -> None:
        if self.is_enabled:
            context.event_bus.emit(
                Event(
                    type=EventType.SWIPEHOLD_RADIUS,
                    source=context,
                    data=1,
                )
            )
        else:
            context.event_bus.emit(
                Event(
                    type=EventType.SWIPEHOLD_RADIUS,
                    source=context,
                    data=self.factor,
                )
            )
        self.is_enabled = not self.is_enabled

    async def cancel(self, context: "Macro") -> None:
        """取消滑动半径切换 - 重置为默认半径并重置状态"""
        if self.is_enabled:
            # 重置为默认半径 (1.0)
            context.event_bus.emit(
                Event(
                    type=EventType.SWIPEHOLD_RADIUS,
                    source=context,
                    data=1.0,
                )
            )
            self.is_enabled = False


class ToggleGroupCommand(Command):
    """切换命令组 - 在两组命令之间切换执行"""

    def __init__(self, command_groups: list[str]):
        if len(command_groups) != 2:
            return
        self.current_group = 0  # 跟踪当前应该执行的命令组 (0 或 1)
        
        # 解析两组命令，重用 CommandParser 的逻辑
        self.command_group_a = CommandParser.parse_command_lines(command_groups[0].strip().split(';'))
        self.command_group_b = CommandParser.parse_command_lines(command_groups[1].strip().split(';'))
        self.command_groups = [self.command_group_a, self.command_group_b]

    async def execute(self, context: "Macro") -> None:
        # 执行当前命令组中的所有命令
        for command in self.command_groups[self.current_group]:
            await command.execute(context)
        
        # 切换到另一个命令组
        self.current_group = 1 - self.current_group

    async def cancel(self, context: "Macro") -> None:
        """取消切换执行 - 重置状态到第一个命令组，并取消所有命令状态"""
        self.current_group = 0
        # 取消所有命令组中的命令状态
        for command_group in self.command_groups:
            for command in command_group:
                await command.cancel(context)


class OtherCommand(Command):
    """其他命令占位符"""

    def __init__(self, args: list[str]):
        self.args = args

    async def execute(self, context: "Macro") -> None:
        pass  # 可以在这里扩展其他命令


# ==================== 命令解析器 ====================


class CommandParser:
    """命令解析器 - 负责解析命令字符串为命令对象"""

    @staticmethod
    def parse_command_lines(lines: list[str]) -> list[Command]:
        """解析命令行列表为Command对象列表"""
        commands = []

        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            parts = line.split(" ", 1)
            command_type = parts[0].lower()
            args_str = parts[1] if len(parts) > 1 else ""

            # 处理参数
            if command_type in ["key_press", "key_release", "key_switch"] and args_str:
                args = [k.strip() for k in args_str.split(",")]
            elif command_type in ["click", "press", "release", "switch"] and args_str:
                args = args_str.split()
            elif command_type == "toggle_group" and args_str:
                args = [args_str]  # toggle_group 需要保持完整字符串，在工厂中再分割
            elif command_type == "sleep" and args_str:
                args = [args_str]
            else:
                args = [args_str] if args_str else []

            # 使用工厂创建命令
            command = CommandFactory.create_command(command_type, args)
            if command:
                commands.append(command)

        return commands


# ==================== 命令工厂 ====================


class CommandFactory:
    """命令工厂 - 负责创建具体的命令对象"""

    @staticmethod
    def create_command(command_type: str, args: list[str]) -> Command | None:
        """根据命令类型和参数创建命令对象"""

        if command_type == "key_press":
            if args:
                return KeyPressCommand(args)
            else:
                return None

        elif command_type == "key_release":
            if args:
                return KeyReleaseCommand(args)
            else:
                return None

        elif command_type == "sleep":
            if args:
                try:
                    sleep_time = int(args[0]) / 1000
                    return SleepCommand(sleep_time)
                except ValueError:
                    return None
            else:
                return None

        elif command_type == "release_all":
            return ReleaseAllCommand()
        elif command_type == "key_switch":
            if args:
                return KeySwitchCommand(args)
            else:
                return None
        elif command_type == "click":
            if args:
                return ClickCommand(args)
            else:
                return None
        elif command_type == "press":
            if args:
                return PressCommand(args)
            else:
                return None
        elif command_type == "release":
            if args:
                return ReleaseCommand(args)
            else:
                return None
        elif command_type == "switch":
            if args:
                return SwitchCommand(args)
            else:
                return None
        elif command_type == "enter_staring":
            return EnterStaringCommand()
        elif command_type == "exit_staring":
            return ExitStaringCommand()
        elif command_type == "swipehold_radius":
            if args:
                return SwipeholdRadiusCommand(float(args[0]))
            else:
                return None
        elif command_type == "swipehold_radius_switch":
            if args:
                return SwipeholdRadiusSwitchCommand(float(args[0]))
            else:
                return None
        elif command_type == "toggle_group":
            if len(args) == 1:
                # args[0] 包含完整的命令字符串，用 | 分割
                command_groups = [group.strip() for group in args[0].split("|")]
                if len(command_groups) == 2:
                    return ToggleGroupCommand(command_groups)
            return None

        elif command_type == "other_command":
            return OtherCommand(args)

        else:
            return None


@Editable
class Macro(BaseWidget):
    """宏按钮组件 - 圆形半透明按钮"""

    # 组件元数据
    WIDGET_NAME = pgettext("Controller Widgets", "Macro")
    WIDGET_DESCRIPTION = pgettext(
        "Controller Widgets",
        "Execute macro commands when triggered.",
    )

    # 映射模式固定尺寸
    MAPPING_MODE_HEIGHT = 30
    MAPPING_MODE_WIDTH = 30
    SETTINGS_PANEL_AUTO_HIDE = False

    def __init__(
        self,
        x: int = 0,
        y: int = 0,
        width: int = 50,
        height: int = 50,
        text: str = "",
        default_keys: set[KeyCombination] | None = None,
        event_bus: EventBus | None = None,
        pointer_id_manager: PointerIdManager | None = None,
        key_registry: KeyRegistry | None = None,
    ):
        # 初始化基类，传入默认按键
        super().__init__(
            x,
            y,
            50,
            50,
            pgettext("Controller Widgets", "Macro"),
            text,
            default_keys,
            min_width=50,  # 固定大小
            min_height=50,  # 固定大小
            event_bus=event_bus,
            pointer_id_manager=pointer_id_manager,
            key_registry=key_registry,
        )
        # 存储预解析的宏命令对象
        self.press_commands: list[Command] = []
        self.release_commands: list[Command] = []

        # 设置宏命令配置
        self.setup_config()
        self.triggered: bool = False

        # 任务管理
        self.current_press_task: asyncio.Task[None] | None = None
        self.current_release_task: asyncio.Task[None] | None = None

        # 按键状态跟踪 - 记录已按下但未释放的按键
        # self.pressed_keys: set[str] = set()
        self._cursor_position: tuple[int, int] = (0, 0)

        self.event_bus.subscribe(EventType.MACRO_RELEASE_ALL, self.trigger_release_all)
        self.screen_info = ScreenInfo()

    def get_cursor_position(self) -> tuple[int, int]:
        return self._cursor_position

    def setup_config(self) -> None:
        """设置配置项"""
        # 添加宏命令配置
        macro_config = create_textarea_config(
            key="macro_command",
            label=pgettext("Controller Widgets", "Macro Command"),
            value="",  # 初始为空，后续通过配置加载
            description=pgettext(
                "Controller Widgets",
                "The macro commands to execute when triggered. Supported commands:\n"
                "- key_press <key1,key2,...>: Press keys\n"
                "- key_release <key1,key2,...>: Release keys\n"
                "- key_switch <key1,key2,...>: Switch keys (toggle between press/release)\n"
                "- click <x,y> [x1,y1] ...: Click at coordinates (combines press and release)\n"
                "- press <x,y> [x1,y1] ...: Press at coordinates (DOWN events only)\n"
                "- release <x,y> [x1,y1] ...: Release at coordinates (UP events only)\n"
                "- switch <x,y> [x1,y1] ...: Switch at coordinates (toggle between press/release)\n"
                "- toggle_group <command_group_1> | <command_group_2>: Toggle between two command groups (use ';' to separate commands within a group)\n"
                "- sleep <milliseconds>: Delay execution\n"
                "- release_all: Release all currently pressed keys\n"
                "- enter_staring: Enter staring/aiming mode\n"
                "- exit_staring: Exit staring/aiming mode\n"
                "- swipehold_radius <factor>: Set swipehold radius\n"
                "- swipehold_radius_switch <factor>: Set swipehold radius and switch\n"
                "- Use 'release_actions' to separate press and release commands\n"
                "- Lines starting with # are comments\n"
                "- Use 'mouse' as coordinate to use current cursor position",
            ),
            event_bus=self.event_bus
        )
        self.add_config_item(macro_config)
        # self.add_config_change_callback("macro_command", self.on_macro_command_changed)
        self.config_manager.connect("confirmed", self.on_macro_command_changed)
        self.event_bus.subscribe(EventType.MOUSE_MOTION, self.on_mouse_motion)

    def on_mouse_motion(self, event: Event[InputEvent]):
        if event.data.position is None:
            return
        self._cursor_position = event.data.position

    def on_macro_command_changed(self, config_manager):
        """当宏命令文本框内容改变时，解析并存储预解析的命令对象"""
        parts = self.config_manager.get_value("macro_command").split(
            "release_actions", 1
        )

        # 解析按下命令
        self.press_commands = CommandParser.parse_command_lines(parts[0].strip().splitlines())

        # 解析释放命令
        if len(parts) > 1:
            self.release_commands = CommandParser.parse_command_lines(
                parts[1].strip().splitlines()
            )
        else:
            self.release_commands = []

    def draw_widget_content(self, cr: "Context[Surface]", width: int, height: int):
        """绘制圆形按钮的具体内容"""
        # 计算圆心和半径
        center_x = width / 2
        center_y = height / 2
        radius = min(width, height) / 2 - 5  # 留出边距

        # 绘制圆形背景
        cr.set_source_rgba(0.5, 0.5, 0.5, 0.6)

        cr.arc(center_x, center_y, radius, 0, 2 * math.pi)
        cr.fill()

        # 绘制圆形边框
        cr.set_source_rgba(0.3, 0.3, 0.3, 0.9)
        cr.set_line_width(2)
        cr.arc(center_x, center_y, radius, 0, 2 * math.pi)
        cr.stroke()

    def draw_text_content(self, cr: "Context[Surface]", width: int, height: int):
        if self.text:
            center_x = width / 2
            center_y = height / 2

            cr.set_source_rgba(1, 1, 1, 1)  # 白色文字
            cr.select_font_face("Arial", FontSlant.NORMAL, FontWeight.BOLD)
            cr.set_font_size(12)
            text_extents = cr.text_extents(self.text)
            x = center_x - text_extents.width / 2
            y = center_y + text_extents.height / 2
            cr.move_to(x, y)
            cr.show_text(self.text)

            # 清除路径，避免影响后续绘制
            cr.new_path()

    def draw_selection_border(self, cr: "Context[Surface]", width: int, height: int):
        center_x = width / 2
        center_y = height / 2
        radius = min(width, height) / 2 - 5

        # 绘制圆形选择边框
        cr.set_source_rgba(0.2, 0.6, 1.0, 0.8)
        cr.set_line_width(3)
        cr.arc(center_x, center_y, radius + 3, 0, 2 * math.pi)
        cr.stroke()

    def draw_mapping_mode_background(
        self, cr: "Context[Surface]", width: int, height: int
    ):
        pass

    def draw_mapping_mode_content(
        self, cr: "Context[Surface]", width: int, height: int
    ):
        pass

    def on_key_triggered(
        self,
        key_combination: KeyCombination | None = None,
        event: "InputEvent|None" = None,
    ) -> bool:
        """当映射的按键被触发时的行为 - 执行预先解析好的按下宏命令"""
        if self.current_release_task and not self.current_release_task.done():
            return True

        if self.current_press_task and not self.current_press_task.done():
            return True

        if self.press_commands:
            self.current_press_task = asyncio.create_task(
                self._execute_commands_async(self.press_commands, "press")
            )
        return True

    def on_key_released(
        self,
        key_combination: KeyCombination | None = None,
        event: "InputEvent|None" = None,
    ) -> bool:
        """当映射的按键被弹起时的行为 - 执行预先解析好的弹起宏命令"""
        # 如果当前有 release task 在执行，直接返回 True
        # if self.current_release_task and not self.current_release_task.done():
        #     logger.debug("宏按键有 release task 在执行，跳过新的 release 触发")
        #     return True

        # 如果没有 release_command 配置，直接返回 True
        if not self.release_commands:
            return True

        # 如果有 release_command 配置，终止当前的 press task（如果有）
        if self.current_press_task and not self.current_press_task.done():
            self.current_press_task.cancel()

        if self.current_release_task and not self.current_release_task.done():
            self.current_release_task.cancel()

        # 创建新的 release task
        self.current_release_task = asyncio.create_task(
            self._execute_commands_async(self.release_commands, "release")
        )
        return True

    async def _execute_commands_async(
        self, commands: list[Command], task_type: str = "unknown"
    ):
        """异步执行预解析的宏命令列表"""
        try:
            for command in commands:
                await command.execute(self)
        except asyncio.CancelledError:
            logger.debug(f"Macro command task cancelled: {task_type}")
            raise
        except Exception as e:
            logger.error(f"Macro command execution exception: {e}")
        finally:
            logger.debug(f"Macro command task completed: {task_type}")

    def trigger_release_all(self, event: Event[None]):
        """触发释放所有命令状态 - 终止当前任务并执行所有命令的取消操作"""
        # 1. 终止当前执行的任务
        if self.current_press_task and not self.current_press_task.done():
            self.current_press_task.cancel()

        if self.current_release_task and not self.current_release_task.done():
            self.current_release_task.cancel()

        # 2. 启动新的异步任务执行取消操作
        asyncio.create_task(self._execute_release_all_async())

    async def _execute_release_all_async(self):
        """异步执行释放所有命令状态的操作"""
        try:
            # 遍历所有命令并执行取消操作
            all_commands = self.press_commands + self.release_commands

            for command in all_commands:
                try:
                    await command.cancel(self)
                except Exception:
                    pass


        except Exception:
            pass

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
    def mapping_start_x(self):
        return int(self.x + self.width / 2)

    @property
    def mapping_start_y(self):
        return int(self.y + self.height / 2)

    @property
    def center_x(self):
        return self.x + self.width / 2

    @property
    def center_y(self):
        return self.y + self.height / 2
