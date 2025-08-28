import os
import asyncio
from typing import cast
import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Pango", "1.0")
from gi.repository import Gtk, Adw, GObject, Gio, Pango
from waydroid_helper.util.subprocess_manager import SubprocessManager


class OptionItem(GObject.Object):
    label = GObject.Property(type=str, default="")
    value = GObject.Property(type=str, default="")

    def __init__(self, label: str = "", value: str = ""):
        super().__init__()
        self.label = label
        self.value = value


class GpuComboRow(Adw.ComboRow):
    __gtype_name__ = "GpuComboRow"

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.store = Gio.ListStore(item_type=OptionItem)
        self._subprocess_manager = SubprocessManager()

        # 创建自定义的factory来为每个选项添加tooltip
        factory = Gtk.SignalListItemFactory()
        _ = factory.connect("setup", self._on_factory_setup)
        _ = factory.connect("bind", self._on_factory_bind)
        
        self.set_model(self.store)
        self.set_factory(factory)
        
        # _ = asyncio.create_task(self.load_gpu_info())

    def _on_factory_setup(self, factory, list_item):
        """设置每个列表项的UI"""
        label = Gtk.Label()
        label.set_xalign(0.0)  # 左对齐
        label.set_ellipsize(Pango.EllipsizeMode.END)  # 文本过长时显示省略号
        list_item.set_child(label)

    def _on_factory_bind(self, factory, list_item):
        """绑定数据到每个列表项"""
        item = list_item.get_item()
        label = list_item.get_child()
        
        if item and label:
            label.set_text(item.label)

    async def load_gpu_info(self):
        self.add_option("", "")
        waydroid_cli_path = os.environ.get("WAYDROID_CLI_PATH")
        result = await self._subprocess_manager.run(
            command=f"{waydroid_cli_path} get_gpu_info", shell=False
        )
        # 解析 stdout，按 : 分割，加入 option
        if result and result["stdout"]:
            lines = result["stdout"].strip().splitlines()
            for line in lines:
                if ":" in line:
                    path, label = line.split(":", 1)
                    path = path.strip()
                    label = label.strip()
                    self.add_option(label=label, value=path)

    def add_option(self, label: str, value: str):
        item = OptionItem(label=label, value=value)
        self.store.append(item)
        return self

    def add_options(self, options: list[tuple[str, str]] | list[dict[str, str]]):
        for option in options:
            if isinstance(option, (list, tuple)):
                label, value = option
            elif isinstance(option, dict):
                label = option["label"]
                value = option["value"]
            else:
                raise ValueError(
                    "Option must be a (label, value) tuple or a dictionary with 'label' and 'value' keys"
                )

            self.add_option(label, value)
        return self

    def clear_options(self):
        self.store.remove_all()
        return self

    def find_index_by_value(self, value: str):
        n_items = self.store.get_n_items()
        for i in range(n_items):
            item = self.store.get_item(i)
            item = cast(OptionItem, item)
            if item.value == value:
                return i
        return Gtk.INVALID_LIST_POSITION

    def find_label_by_value(self, value: str):
        n_items = self.store.get_n_items()
        for i in range(n_items):
            item = self.store.get_item(i)
            item = cast(OptionItem, item)
            if item.value == value:
                return item.label
        return None

    def find_value_by_label(self, label: str):
        n_items = self.store.get_n_items()
        for i in range(n_items):
            item = self.store.get_item(i)
            item = cast(OptionItem, item)
            if item.label == label:
                return item.value
        return None

    def get_selected_value(self):
        selected_index = self.get_selected()
        if selected_index != Gtk.INVALID_LIST_POSITION:
            item = self.store.get_item(selected_index)
            item = cast(OptionItem, item)
            return item.value
        return None

    def get_selected_label(self):
        selected_index = self.get_selected()
        if selected_index != Gtk.INVALID_LIST_POSITION:
            item = self.store.get_item(selected_index)
            item = cast(OptionItem, item)
            return item.label
        return None

    def set_selected_value(self, value: str):
        index = self.find_index_by_value(value)
        if index != Gtk.INVALID_LIST_POSITION:
            self.set_selected(index)
            return True
        return False

    def set_selected_label(self, label: str):
        value = self.find_value_by_label(label)
        if value is not None:
            return self.set_selected_value(value)
        return False
