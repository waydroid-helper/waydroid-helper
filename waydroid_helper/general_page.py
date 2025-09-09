# pyright: reportCallIssue=false
# pyright: reportUnknownVariableType=false
# pyright: reportAny=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false

from gettext import gettext as _

import gi

from waydroid_helper.config.models import RootConfig

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, GObject, Gtk

from waydroid_helper.util import Task, logger, template
from waydroid_helper.waydroid import Waydroid, WaydroidState
from waydroid_helper.instance_detail_page import InstanceDetailPage

@template(resource_path="/com/jaoushingan/WaydroidHelper/ui/GeneralPage.ui")
class GeneralPage(Gtk.Box):
    __gtype_name__: str = "GeneralPage"
    waydroid: Waydroid = GObject.Property(
        default=None, type=Waydroid
    )  # pyright: ignore[reportAssignmentType]
    status: Adw.ActionRow = Gtk.Template.Child()
    status_image: Gtk.Image = Gtk.Template.Child("status-image")
    stop_button: Gtk.Button = Gtk.Template.Child("stop-button")
    start_button: Gtk.Button = Gtk.Template.Child("start-button")
    general_button_stack: Gtk.Stack = Gtk.Template.Child()
    init_button: Gtk.Button = Gtk.Template.Child("init-button")
    updrade_button: Gtk.Button = Gtk.Template.Child()
    show_full_ui_button: Gtk.Button = Gtk.Template.Child("show-full-ui-button")

    _task: Task = Task()
    _navigation_view = None  # Will be set by window

    def update_menu(self, state: WaydroidState):
        if state == WaydroidState.RUNNING:
            self.status.set_title(_("Connected"))
            self.status.set_subtitle(_("Waydroid session is running"))
            self.status_image.set_from_icon_name("normal")
            self.start_button.set_sensitive(False)
            self.stop_button.set_sensitive(True)
            self.general_button_stack.set_visible_child_name("initialized_menu")
            self.updrade_button.set_sensitive(True)
            self.show_full_ui_button.set_sensitive(True)
        elif state == WaydroidState.STOPPED:
            self.status.set_title(_("Stopped"))
            self.status.set_subtitle(_("Waydroid session is stopped"))
            self.status_image.set_from_icon_name("conflicting")
            self.start_button.set_sensitive(True)
            self.stop_button.set_sensitive(False)
            self.general_button_stack.set_visible_child_name("initialized_menu")
            self.updrade_button.set_sensitive(True)
            self.show_full_ui_button.set_sensitive(True)

        elif state == WaydroidState.UNINITIALIZED:
            self.status.set_title(_("Uninitialized"))
            self.status.set_subtitle(_("Waydroid is not initialized"))
            self.status_image.set_from_icon_name("conflicting")
            self.general_button_stack.set_visible_child_name("uninitialized_menu")
            self.init_button.set_sensitive(True)
            self.updrade_button.set_sensitive(False)
            self.show_full_ui_button.set_sensitive(False)
        elif state == WaydroidState.LOADING:
            self.status.set_title(_("Loading"))
            self.status.set_subtitle("")
            self.status_image.set_from_icon_name("")
            self._disable_buttons()

    def on_waydroid_state_changed(self, w: GObject.Object, param: GObject.ParamSpec):
        self.update_menu(w.get_property(param.name))

    def __init__(
        self,
        **kargs  # pyright: ignore[reportMissingParameterType,reportUnknownParameterType]
    ):
        super().__init__(**kargs)
        self.config: RootConfig = RootConfig()
        self.set_property("waydroid", Waydroid())
        self.waydroid.connect("notify::state", self.on_waydroid_state_changed)

    def set_navigation_view(self, navigation_view):
        """Set the navigation view for page navigation"""
        self._navigation_view = navigation_view



    @Gtk.Template.Callback()
    def on_status_row_activated(self, row: Adw.ActionRow):
        """Handle status row click to navigate to instance details"""
        if self._navigation_view:

            # Check if detail page already exists
            detail_page_tag = "instance_detail"
            existing_page = self._navigation_view.find_page(detail_page_tag)

            if existing_page is None:
                # Create new detail page - page instances will be created internally
                detail_page = InstanceDetailPage(
                    self.waydroid,
                    self._navigation_view,
                    self.config
                )
                detail_page.set_tag(detail_page_tag)
                self._navigation_view.add(detail_page)

                # Set app instance if available
                root = self.get_root()
                if root and hasattr(root, 'get_application'):
                    app = root.get_application()
                    if app:
                        detail_page.set_app(app)
            else:
                # 如果页面已存在，确保它是最新的状态
                detail_page = existing_page

            # Navigate to detail page
            self._navigation_view.push_by_tag(detail_page_tag)

    def _get_app_instance(self):
        """Get application instance with delay"""
        try:
            root = self.get_root()
            if root and hasattr(root, 'get_application'):
                self._app = root.get_application()  # pyright: ignore[reportAttributeAccessIssue]
                logger.debug("Successfully get application instance")
        except Exception as e:
            logger.error(f"Get application instance failed: {e}")
        return False  # Do not repeat execution

    def _disable_buttons(self):
        self.start_button.set_sensitive(False)
        self.stop_button.set_sensitive(False)
        self.init_button.set_sensitive(False)
        self.updrade_button.set_sensitive(False)
        self.show_full_ui_button.set_sensitive(False)

    @Gtk.Template.Callback()
    def on_init_button_clicked(self, button: Gtk.Button):
        self._disable_buttons()
        logger.info("waydroid init")
        # TODO

    async def __on_start_button_clicked(self):
        old = self.waydroid.state
        self._disable_buttons()
        await self.waydroid.start_session()
        if old == self.waydroid.state:
            self.update_menu(self.waydroid.state)

    @Gtk.Template.Callback()
    def on_start_button_clicked(self, button: Gtk.Button):
        logger.info("waydroid session start")
        self._task.create_task(self.__on_start_button_clicked())

    async def __on_stop_button_clicked(self):
        old = self.waydroid.state
        self._disable_buttons()
        await self.waydroid.stop_session()
        if old == self.waydroid.state:
            self.update_menu(self.waydroid.state)

    @Gtk.Template.Callback()
    def on_stop_button_clicked(self, button: Gtk.Button):
        logger.info("waydroid session stop")
        self._task.create_task(self.__on_stop_button_clicked())

    @Gtk.Template.Callback()
    def on_show_full_ui_button_clicked(self, button: Gtk.Button):
        logger.info("waydroid show-full-ui")
        self._task.create_task(self.waydroid.show_full_ui())

    async def __on_start_upgrade_offline_clicked(self):
        old = self.waydroid.state
        self._disable_buttons()
        await self.waydroid.upgrade(True)
        if old == self.waydroid.state:
            self.update_menu(self.waydroid.state)

    @Gtk.Template.Callback()
    def on_start_upgrade_offline_clicked(self, button: Gtk.Button):
        logger.info("sudo waydroid upgrade -o")
        self._task.create_task(self.__on_start_upgrade_offline_clicked())


