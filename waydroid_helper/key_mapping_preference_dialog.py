import gi

from waydroid_helper.util.log import logger
from waydroid_helper.util.weak_ref import connect_weakly

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gtk, GObject  # type: ignore
from gettext import gettext as _

from waydroid_helper.compat_widget.dialog import Dialog, ADW_VERSION
from waydroid_helper.compat_widget.header_bar import HeaderBar
from waydroid_helper.compat_widget.file_dialog import FileDialog
from waydroid_helper.config.models import RootConfig


class KeyMappingPreferenceDialog(Dialog):
    KEYBOARD_INJECT_MODE_VALUES = ("mixed", "text", "raw")

    def __init__(self, title: str, parent: Gtk.Window, config: RootConfig, **kwargs):
        super().__init__(
            title=title or _("Key Mapping Preferences"),
            parent=parent,
            content_width=600,
            content_height=400,
            **kwargs
        )

        # 获取配置模型
        self.config: RootConfig = config
        self.enable_switch: Gtk.Switch
        self.executable_entry: Gtk.Entry
        self.window_width_spin: Gtk.SpinButton
        self.window_height_spin: Gtk.SpinButton
        self.logical_width_spin: Gtk.SpinButton
        self.logical_height_spin: Gtk.SpinButton
        self.scale_spin: Gtk.SpinButton
        self.refresh_rate_spin: Gtk.SpinButton
        self.socket_name_entry: Gtk.Entry
        self.hide_titlebar_switch: Gtk.Switch
        self.confine_pointer_switch: Gtk.Switch
        self.keyboard_inject_mode_row: Adw.ComboRow
        self.mouse_natural_scroll_switch: Gtk.Switch
        self.mouse_hover_switch: Gtk.Switch
        self._updating_keyboard_inject_mode = False

        self._setup_ui()
        self._setup_signals()
        self._setup_bindings()
        self._setup_close_handlers()

    def _setup_ui(self):
        """设置用户界面"""
        # 创建主容器
        main_box = Gtk.Box.new(orientation=Gtk.Orientation.VERTICAL, spacing=0)

        # 创建 HeaderBar
        header_bar = self._create_header_bar()
        main_box.append(header_bar)

        # 创建 AdwPreferencesPage
        preferences_page = self._create_preferences_page()
        main_box.append(preferences_page)

        # 设置内容
        self.set_content(main_box)

        # 根据当前enable状态设置其他控件的初始敏感性
        self._update_controls_sensitivity()

    def _create_header_bar(self):
        """创建 HeaderBar，包含取消和确认按钮"""
        header_bar = HeaderBar()

        # 左侧取消按钮
        cancel_button = Gtk.Button.new_with_label(_("Cancel"))
        cancel_button.add_css_class("text-button")
        connect_weakly(cancel_button, "clicked", self._on_cancel_clicked)
        header_bar.pack_start(cancel_button)

        # 右侧确认按钮
        confirm_button = Gtk.Button.new_with_label(_("Confirm"))
        confirm_button.add_css_class("suggested-action")
        connect_weakly(confirm_button, "clicked", self._on_confirm_clicked)
        header_bar.pack_end(confirm_button)

        return header_bar

    def _create_preferences_page(self):
        """创建 AdwPreferencesPage"""
        preferences_page = Adw.PreferencesPage.new()

        # Default handler 设置组
        default_handler_group = self._create_default_handler_group()
        preferences_page.add(default_handler_group)

        # Cage 设置组
        cage_group = self._create_cage_group()
        preferences_page.add(cage_group)

        return preferences_page

    def _create_default_handler_group(self):
        """创建默认输入处理器设置组"""
        group = Adw.PreferencesGroup.new()
        group.set_title(_("Default Input Handler"))
        group.set_description(_("Configure default keyboard and mouse input behavior"))

        self.keyboard_inject_mode_row = Adw.ComboRow.new()
        self.keyboard_inject_mode_row.set_title(_("Keyboard Inject Mode"))
        self.keyboard_inject_mode_row.set_subtitle(_("Keyboard injection mode"))
        inject_mode_model = Gtk.StringList.new(
            strings=[
                _("Mixed"),
                _("Text"),
                _("Raw"),
            ]
        )
        self.keyboard_inject_mode_row.set_model(inject_mode_model)
        group.add(self.keyboard_inject_mode_row)

        natural_scroll_row = Adw.ActionRow.new()
        natural_scroll_row.set_title(_("Natural Scroll"))
        natural_scroll_row.set_subtitle(_("Use natural mouse wheel scrolling"))

        self.mouse_natural_scroll_switch = Gtk.Switch.new()
        self.mouse_natural_scroll_switch.set_valign(Gtk.Align.CENTER)
        natural_scroll_row.add_suffix(self.mouse_natural_scroll_switch)
        natural_scroll_row.set_activatable_widget(self.mouse_natural_scroll_switch)

        group.add(natural_scroll_row)

        hover_row = Adw.ActionRow.new()
        hover_row.set_title(_("Mouse Hover"))
        hover_row.set_subtitle(_("Enabling hover may affect key mapping"))

        self.mouse_hover_switch = Gtk.Switch.new()
        self.mouse_hover_switch.set_valign(Gtk.Align.CENTER)
        hover_row.add_suffix(self.mouse_hover_switch)
        hover_row.set_activatable_widget(self.mouse_hover_switch)

        group.add(hover_row)

        return group

    def _create_cage_group(self):
        """创建 Cage 设置组"""
        group = Adw.PreferencesGroup.new()
        group.set_title(_("Cage Settings"))
        group.set_description(
            _(
                "Configure cage functionality. You can download prebuilt cage from: <a href='https://github.com/waydroid-helper/cage/releases'>https://github.com/waydroid-helper/cage/releases</a>"
            )
        )

        # 启用 Cage 开关
        enable_row = Adw.ActionRow.new()
        enable_row.set_title(_("Enable Cage"))
        enable_row.set_subtitle(_("Enable cage for key mapping"))

        self.enable_switch = Gtk.Switch.new()
        self.enable_switch.set_valign(Gtk.Align.CENTER)
        enable_row.add_suffix(self.enable_switch)
        enable_row.set_activatable_widget(self.enable_switch)

        group.add(enable_row)

        # Cage 可执行文件路径
        executable_row = Adw.ActionRow.new()
        executable_row.set_title(_("Cage Executable"))
        executable_row.set_subtitle(_("Path to cage executable"))

        # 创建水平布局容器来放置输入框和文件选择器按钮
        executable_box = Gtk.Box.new(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        # 可执行文件路径输入框
        self.executable_entry = Gtk.Entry.new()
        self.executable_entry.set_hexpand(True)
        self.executable_entry.set_size_request(200, 24)  # 设置宽度和高度
        self.executable_entry.set_valign(Gtk.Align.CENTER)  # 垂直居中对齐

        # 文件选择器按钮
        self.file_chooser_button = Gtk.Button.new()
        self.file_chooser_button.set_icon_name("document-open-symbolic")
        self.file_chooser_button.set_tooltip_text(_("Choose executable file"))
        self.file_chooser_button.set_size_request(32, 24)  # 设置按钮大小
        self.file_chooser_button.set_valign(Gtk.Align.CENTER)

        executable_box.append(self.executable_entry)
        executable_box.append(self.file_chooser_button)

        executable_row.add_suffix(executable_box)

        group.add(executable_row)

        # Cage 窗口大小
        window_size_row = Adw.ActionRow.new()
        window_size_row.set_title(_("Window Size"))
        window_size_row.set_subtitle(_("Cage window size"))

        # 创建水平布局容器来放置宽度和高度输入框
        window_size_box = Gtk.Box.new(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        # 宽度输入框
        width_label = Gtk.Label.new("W:")
        self.window_width_spin = Gtk.SpinButton.new_with_range(1, 10000, 1)
        self.window_width_spin.set_size_request(80, 24)  # 减小高度
        self.window_width_spin.set_valign(Gtk.Align.CENTER)  # 垂直居中对齐

        # 高度输入框
        height_label = Gtk.Label.new("H:")
        self.window_height_spin = Gtk.SpinButton.new_with_range(1, 10000, 1)
        self.window_height_spin.set_size_request(80, 24)  # 减小高度
        self.window_height_spin.set_valign(Gtk.Align.CENTER)  # 垂直居中对齐

        window_size_box.append(width_label)
        window_size_box.append(self.window_width_spin)
        window_size_box.append(height_label)
        window_size_box.append(self.window_height_spin)

        window_size_row.add_suffix(window_size_box)

        group.add(window_size_row)

        # Cage 逻辑分辨率
        logical_resolution_row = Adw.ActionRow.new()
        logical_resolution_row.set_title(_("Logical Resolution"))
        logical_resolution_row.set_subtitle(_("Cage logical resolution"))

        # 创建水平布局容器来放置宽度和高度输入框
        logical_resolution_box = Gtk.Box.new(
            orientation=Gtk.Orientation.HORIZONTAL, spacing=6
        )

        # 宽度输入框
        logical_width_label = Gtk.Label.new("W:")
        self.logical_width_spin = Gtk.SpinButton.new_with_range(1, 10000, 1)
        self.logical_width_spin.set_size_request(80, 24)  # 减小高度
        self.logical_width_spin.set_valign(Gtk.Align.CENTER)  # 垂直居中对齐

        # 高度输入框
        logical_height_label = Gtk.Label.new("H:")
        self.logical_height_spin = Gtk.SpinButton.new_with_range(1, 10000, 1)
        self.logical_height_spin.set_size_request(80, 24)  # 减小高度
        self.logical_height_spin.set_valign(Gtk.Align.CENTER)  # 垂直居中对齐

        logical_resolution_box.append(logical_width_label)
        logical_resolution_box.append(self.logical_width_spin)
        logical_resolution_box.append(logical_height_label)
        logical_resolution_box.append(self.logical_height_spin)

        logical_resolution_row.add_suffix(logical_resolution_box)

        group.add(logical_resolution_row)

        # Cage 缩放比例
        scale_row = Adw.ActionRow.new()
        scale_row.set_title(_("Scale"))
        scale_row.set_subtitle(_("Cage display scale percentage"))

        # 创建水平布局容器来放置缩放输入框和百分比标签
        scale_box = Gtk.Box.new(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        # 缩放输入框
        self.scale_spin = Gtk.SpinButton.new_with_range(1, 500, 1)  # 整数范围，步长为1
        self.scale_spin.set_size_request(80, 24)  # 设置宽度和高度
        self.scale_spin.set_valign(Gtk.Align.CENTER)  # 垂直居中对齐

        # 百分比标签
        percent_label = Gtk.Label.new("%")

        scale_box.append(self.scale_spin)
        scale_box.append(percent_label)

        scale_row.add_suffix(scale_box)

        group.add(scale_row)

        # Cage Refresh Rate
        refresh_rate_row = Adw.ActionRow.new()
        refresh_rate_row.set_title(_("Refresh Rate"))
        refresh_rate_row.set_subtitle(_("Cage display refresh rate (Hz)"))

        refresh_rate_box = Gtk.Box.new(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)

        self.refresh_rate_spin = Gtk.SpinButton.new_with_range(30, 240, 1)  # 范围30-240Hz，步长为1
        self.refresh_rate_spin.set_size_request(80, 24)
        self.refresh_rate_spin.set_valign(Gtk.Align.CENTER)

        hz_label = Gtk.Label.new("Hz")

        refresh_rate_box.append(self.refresh_rate_spin)
        refresh_rate_box.append(hz_label)

        refresh_rate_row.add_suffix(refresh_rate_box)

        group.add(refresh_rate_row)

        # Cage Socket Name
        socket_name_row = Adw.ActionRow.new()
        socket_name_row.set_title(_("Socket Name"))
        socket_name_row.set_subtitle(_("Custom socket name (default: waydroid-0)"))

        self.socket_name_entry = Gtk.Entry.new()
        self.socket_name_entry.set_hexpand(True)
        self.socket_name_entry.set_size_request(200, 24)  # 减小高度
        self.socket_name_entry.set_valign(Gtk.Align.CENTER)  # 垂直居中对齐
        socket_name_row.add_suffix(self.socket_name_entry)

        group.add(socket_name_row)

        # Hide Title Bar
        hide_titlebar_row = Adw.ActionRow.new()
        hide_titlebar_row.set_title(_("Hide Title Bar"))
        hide_titlebar_row.set_subtitle(_("Hide cage window title bar (X11 backend only)"))

        self.hide_titlebar_switch = Gtk.Switch.new()
        self.hide_titlebar_switch.set_valign(Gtk.Align.CENTER)
        hide_titlebar_row.add_suffix(self.hide_titlebar_switch)
        hide_titlebar_row.set_activatable_widget(self.hide_titlebar_switch)

        group.add(hide_titlebar_row)

        # Confine Pointer
        confine_pointer_row = Adw.ActionRow.new()
        confine_pointer_row.set_title(_("Confine Pointer"))
        confine_pointer_row.set_subtitle(_("Confine mouse pointer within cage window"))

        self.confine_pointer_switch = Gtk.Switch.new()
        self.confine_pointer_switch.set_valign(Gtk.Align.CENTER)
        confine_pointer_row.add_suffix(self.confine_pointer_switch)
        confine_pointer_row.set_activatable_widget(self.confine_pointer_switch)

        group.add(confine_pointer_row)

        return group

    def _update_controls_sensitivity(self):
        """根据enable开关状态更新其他控件的敏感性"""
        enabled = self.config.cage.get_property("enabled")

        # 设置所有控件的敏感性
        self.executable_entry.set_sensitive(enabled)
        self.file_chooser_button.set_sensitive(enabled)
        self.window_width_spin.set_sensitive(enabled)
        self.window_height_spin.set_sensitive(enabled)
        self.logical_width_spin.set_sensitive(enabled)
        self.logical_height_spin.set_sensitive(enabled)
        self.scale_spin.set_sensitive(enabled)
        self.refresh_rate_spin.set_sensitive(enabled)
        self.socket_name_entry.set_sensitive(enabled)
        self.hide_titlebar_switch.set_sensitive(enabled)
        self.confine_pointer_switch.set_sensitive(enabled)

    def _setup_signals(self):
        """设置信号连接"""
        # 连接文件选择器按钮信号
        connect_weakly(
            self.file_chooser_button, "clicked", self._on_file_chooser_clicked
        )
        connect_weakly(
            self.keyboard_inject_mode_row,
            "notify::selected",
            self._on_keyboard_inject_mode_selected,
        )

    def _setup_bindings(self):
        self._sync_keyboard_inject_mode_row()

        self.config.default_handler.bind_property(
            "mouse_natural_scroll",
            self.mouse_natural_scroll_switch,
            "active",
            GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.BIDIRECTIONAL,
        )

        self.config.default_handler.bind_property(
            "mouse_hover",
            self.mouse_hover_switch,
            "active",
            GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.BIDIRECTIONAL,
        )

        self.config.cage.bind_property(
            "enabled",
            self.enable_switch,
            "active",
            GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.BIDIRECTIONAL,
        )

        # 绑定其他控件的敏感性到enable开关
        self.config.cage.bind_property(
            "enabled",
            self.executable_entry,
            "sensitive",
            GObject.BindingFlags.SYNC_CREATE,
        )

        self.config.cage.bind_property(
            "enabled",
            self.file_chooser_button,
            "sensitive",
            GObject.BindingFlags.SYNC_CREATE,
        )

        self.config.cage.bind_property(
            "enabled",
            self.window_width_spin,
            "sensitive",
            GObject.BindingFlags.SYNC_CREATE,
        )

        self.config.cage.bind_property(
            "enabled",
            self.window_height_spin,
            "sensitive",
            GObject.BindingFlags.SYNC_CREATE,
        )

        self.config.cage.bind_property(
            "enabled",
            self.logical_width_spin,
            "sensitive",
            GObject.BindingFlags.SYNC_CREATE,
        )

        self.config.cage.bind_property(
            "enabled",
            self.logical_height_spin,
            "sensitive",
            GObject.BindingFlags.SYNC_CREATE,
        )

        self.config.cage.bind_property(
            "enabled", self.scale_spin, "sensitive", GObject.BindingFlags.SYNC_CREATE
        )

        self.config.cage.bind_property(
            "enabled",
            self.refresh_rate_spin,
            "sensitive",
            GObject.BindingFlags.SYNC_CREATE,
        )

        self.config.cage.bind_property(
            "enabled",
            self.socket_name_entry,
            "sensitive",
            GObject.BindingFlags.SYNC_CREATE,
        )

        self.config.cage.bind_property(
            "executable_path",
            self.executable_entry,
            "text",
            GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.BIDIRECTIONAL,
        )

        self.config.cage.bind_property(
            "window_width",
            self.window_width_spin,
            "value",
            GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.BIDIRECTIONAL,
        )

        self.config.cage.bind_property(
            "window_height",
            self.window_height_spin,
            "value",
            GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.BIDIRECTIONAL,
        )

        self.config.cage.bind_property(
            "logical_width",
            self.logical_width_spin,
            "value",
            GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.BIDIRECTIONAL,
        )

        self.config.cage.bind_property(
            "logical_height",
            self.logical_height_spin,
            "value",
            GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.BIDIRECTIONAL,
        )

        self.config.cage.bind_property(
            "scale",
            self.scale_spin,
            "value",
            GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.BIDIRECTIONAL,
        )

        self.config.cage.bind_property(
            "refresh_rate",
            self.refresh_rate_spin,
            "value",
            GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.BIDIRECTIONAL,
        )

        self.config.cage.bind_property(
            "socket_name",
            self.socket_name_entry,
            "text",
            GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.BIDIRECTIONAL,
        )

        self.config.cage.bind_property(
            "enabled",
            self.hide_titlebar_switch,
            "sensitive",
            GObject.BindingFlags.SYNC_CREATE,
        )

        self.config.cage.bind_property(
            "hide_titlebar",
            self.hide_titlebar_switch,
            "active",
            GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.BIDIRECTIONAL,
        )

        self.config.cage.bind_property(
            "enabled",
            self.confine_pointer_switch,
            "sensitive",
            GObject.BindingFlags.SYNC_CREATE,
        )

        self.config.cage.bind_property(
            "confine_pointer",
            self.confine_pointer_switch,
            "active",
            GObject.BindingFlags.SYNC_CREATE | GObject.BindingFlags.BIDIRECTIONAL,
        )

    def _setup_close_handlers(self):
        # 根据 ADW 版本选择正确的信号
        if ADW_VERSION >= (1, 5, 0):
            # AdwDialog 版本使用 "closed" 信号
            connect_weakly(self, "closed", self._on_dialog_closed)
        else:
            # AdwWindow 版本使用 "close-request" 信号
            connect_weakly(self, "close-request", self._on_dialog_closed)

    def _on_file_chooser_clicked(self, button):
        """文件选择器按钮点击处理"""
        file_dialog = FileDialog(
            parent=self.get_root(), title=_("Choose Cage Executable"), modal=True
        )

        def on_file_selected(success: bool, file_path: str | None):
            if success and file_path:
                self.executable_entry.set_text(file_path)
            else:
                pass

        file_dialog.open_file(on_file_selected)

    def _on_dialog_closed(self, *args):
        self.config.load_from_settings()

    def _on_cancel_clicked(self, button):
        self.close()

    def _sync_keyboard_inject_mode_row(self):
        inject_mode = self.config.default_handler.keyboard_inject_mode
        try:
            selected = self.KEYBOARD_INJECT_MODE_VALUES.index(inject_mode)
        except ValueError:
            logger.error(f"Unknown keyboard inject mode in preferences: {inject_mode!r}")
            selected = 0

        self._updating_keyboard_inject_mode = True
        try:
            self.keyboard_inject_mode_row.set_selected(selected)
        finally:
            self._updating_keyboard_inject_mode = False

    def _on_keyboard_inject_mode_selected(self, row: Adw.ComboRow, pspec):
        if self._updating_keyboard_inject_mode:
            return

        selected = row.get_selected()
        if selected >= len(self.KEYBOARD_INJECT_MODE_VALUES):
            logger.error(f"Invalid keyboard inject mode selection: {selected}")
            return

        self.config.default_handler.keyboard_inject_mode = (
            self.KEYBOARD_INJECT_MODE_VALUES[selected]
        )

    def _on_confirm_clicked(self, button):
        if self.config.save_to_settings():
            pass
        else:
            logger.error("Config save failed!")

        self.close()

    def __del__(self):
        pass
