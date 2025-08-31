# pyright: reportUnknownMemberType=false
# pyright: reportUnknownParameterType=false
# pyright: reportMissingParameterType=false
# pyright: reportRedeclaration=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownArgumentType=false
# pyright: reportAny=false
# pyright: reportCallIssue=false
# pyright: reportMissingSuperCall=false
# pyright: reportGeneralTypeIssues=false
# pyright: reportUntypedBaseClass=false


import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")


from gi.repository import Adw, GLib, GObject, Gtk

GTK_VERSION = Gtk.get_major_version(), Gtk.get_minor_version(), Gtk.get_micro_version()
ADW_VERSION = Adw.get_major_version(), Adw.get_minor_version(), Adw.get_micro_version()
GLIB_VERSION = GLib.MAJOR_VERSION, GLib.MINOR_VERSION, GLib.MICRO_VERSION


# 根据版本选择基类
if ADW_VERSION >= (1, 5, 0):
    _BaseDialog = Adw.Dialog
else:
    _BaseDialog = Adw.Window


class DialogMeta(type(GObject.Object)):
    def __new__(mcs, name, bases, attrs):
        # 只对 Dialog 基类应用 metaclass 的 __init__，不覆盖子类的 __init__
        if name != "Dialog":
            return super().__new__(mcs, name, bases, attrs)
        if ADW_VERSION >= (1, 5, 0):
            # AdwDialog 版本
            def __init__(
                self,
                title: str = "",
                content_widget: Gtk.Widget | None = None,
                parent: Gtk.Window | None = None,
                modal: bool = True,
                content_height: int = 200,
                content_width: int = 400,
                **kwargs
            ):
                Adw.Dialog.__init__(
                    self,
                    content_height=content_height, 
                    content_width=content_width,
                    **kwargs
                )
                self._parent = parent
                self._content_widget = None
                self._title = title
                
                if title:
                    self.set_title(title)
                
                # 如果提供了内容组件，设置它
                if content_widget:
                    self.set_content(content_widget)

            def set_content(self, widget: Gtk.Widget) -> None:
                if self._content_widget:
                    Adw.Dialog.set_child(self, None)
                
                self._content_widget = widget
                Adw.Dialog.set_child(self, widget)

            def present(self) -> None:
                if self._parent:
                    Adw.Dialog.present(self, self._parent)
                else:
                    # 尝试获取活动窗口
                    app = Gtk.Application.get_default()
                    if app:
                        try:
                            active_window = getattr(app, 'get_active_window', lambda: None)()
                            if active_window:
                                Adw.Dialog.present(self, active_window)
                        except (AttributeError, TypeError):
                            pass

        else:
            # AdwWindow 版本
            def __init__(
                self,
                title: str = "",
                content_widget: Gtk.Widget | None = None,
                parent: Gtk.Window | None = None,
                modal: bool = True,
                content_height: int = 200,
                content_width: int = 400,
                **kwargs
            ):
                Adw.Window.__init__(
                    self,
                    title=title,
                    transient_for=parent,
                    modal=modal,
                    **kwargs
                )
                self._parent = parent
                self._content_widget = None
                
                # 设置默认大小和样式
                self.set_default_size(content_width, content_height)
                self.add_css_class("dialog")
                
                # 如果提供了内容组件，设置它
                if content_widget:
                    self.set_content(content_widget)

            def set_content(self, widget: Gtk.Widget) -> None:
                if self._content_widget:
                    Adw.Window.set_content(self, None)
                
                self._content_widget = widget
                Adw.Window.set_content(self, widget)

            def present(self) -> None:
                Adw.Window.present(self)

        def get_content(self) -> Gtk.Widget | None:
            return self._content_widget

        def close(self) -> None:
            _BaseDialog.close(self)

        attrs["__init__"] = __init__
        attrs["set_content"] = set_content
        attrs["get_content"] = get_content
        attrs["present"] = present
        attrs["close"] = close

        return super().__new__(mcs, name, bases, attrs)


class Dialog(_BaseDialog, metaclass=DialogMeta):
    __gtype_name__: str = "Dialog"
    
    def __init__(
        self,
        title: str = "",
        content_widget: Gtk.Widget | None = None,
        parent: Gtk.Window | None = None,
        modal: bool = True,
        content_height: int = 200,
        content_width: int = 400,
        **kwargs
    ):
        pass

    def set_content(self, widget: Gtk.Widget) -> None:
        pass

    def get_content(self) -> Gtk.Widget | None:
        pass

    def present(self) -> None:
        pass

    def close(self) -> None:
        pass
