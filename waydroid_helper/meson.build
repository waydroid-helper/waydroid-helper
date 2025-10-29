moduledir = pkgdatadir / 'waydroid_helper'
utildir = moduledir / 'util'
compatwidgetdir = moduledir / 'compat_widget'
controllerdir = moduledir / 'controller'
toolsdir = moduledir / 'tools'
gnome = import('gnome')

python = import('python')

conf = configuration_data()
conf.set('VERSION', meson.project_version())
conf.set('localedir', get_option('prefix') / get_option('localedir'))
conf.set('pkgdatadir', pkgdatadir)
conf.set('datadir', get_option('prefix') / get_option('datadir'))
conf.set('bindir', get_option('prefix') / get_option('bindir'))
conf.set('project_name',  meson.project_name())
build_appimage = get_option('build_appimage')

if build_appimage 
    conf.set('build_appimage', 'True')
else
    conf.set('build_appimage', 'False')
    conf.set('PYTHON', python.find_installation('python3').path())
endif

configure_file(
    input: 'waydroid-helper.in',
    output: 'waydroid-helper',
    configuration: conf,
    install: true,
    install_dir: get_option('bindir'),
    install_mode: 'rwxr-xr-x',
)

configure_file(
    input: 'waydroid-cli.in',
    output: 'waydroid-cli',
    configuration: conf,
    install: true,
    install_dir: get_option('bindir'),
    install_mode: 'rwxr-xr-x',
)

waydroid_helper_sources = [
    '__init__.py',
    'main.py',
    'window.py',
    'waydroid.py',
    'general_page.py',
    'instance_detail_page.py',
    'gsf_retriever.py',
    'props_page.py',
    'extensions_page.py',
    'infobar.py',
    'extension_row.py',
    'available_version_page.py',
    'shared_folder.py',
    'model_controller.py',
    'models.py',
    'sdk.py',
    'gpu_combo_row.py',
    'key_mapping_preference_dialog.py',
    'scripts_page.py',
]
config_sources = [
    'config/__init__.py',
    'config/file_manager.py',
    'config/models.py',
]
util_sources = [
    'util/__init__.py',
    'util/subprocess_manager.py',
    'util/task.py',
    'util/arch.py',
    'util/log.py',
    'util/weak_ref.py',
    'util/template.py',
    'util/abx_reader.py', 
    'util/adb_helper.py',
    'util/state_waiter.py',
]

tools_sources = [
    'tools/__init__.py',
    'tools/monitor_service.py',
    'tools/extensions_manager.py',
    'tools/mount_service.py',
]

compat_widget_sources = [
    'compat_widget/__init__.py',
    'compat_widget/navigation_view.py',
    'compat_widget/navigation_page.py',
    'compat_widget/toolbar_view.py',
    'compat_widget/spinner.py',
    'compat_widget/message_dialog.py',
    'compat_widget/header_bar.py',
    'compat_widget/file_dialog.py',
    'compat_widget/shared_folder_dialog.py',
    'compat_widget/animation_target.py',
    'compat_widget/dialog.py',
]

# 按子目录分组的 controller 源文件
controller_root_sources = [
    'controller/__init__.py',
]

controller_android_sources = [
    'controller/android/__init__.py',
    'controller/android/input.py',
    'controller/android/keycodes.py',
]

controller_app_sources = [
    'controller/app/window.py',
    'controller/app/workspace_manager.py',
]

controller_scrcpy_sources = [
    'controller/third_party/scrcpy-server',
    'controller/third_party/LICENSE',
]

controller_core_sources = [
    'controller/core/constants.py',
    'controller/core/control_msg.py',
    'controller/core/event_bus.py',
    'controller/core/__init__.py',
    'controller/core/key_system.py',
    'controller/core/server.py',
    'controller/core/types.py',
    'controller/core/utils.py',
]

controller_core_handler_sources = [
    'controller/core/handler/__init__.py',
    'controller/core/handler/event_handlers.py',
]

controller_core_handler_default_sources = [
    'controller/core/handler/default/__init__.py',
    'controller/core/handler/default/default_event_handler.py',
    'controller/core/handler/default/default_key_handler.py',
    'controller/core/handler/default/default_mouse_handler.py',
]

controller_core_handler_mapping_sources = [
    'controller/core/handler/mapping/__init__.py',
    'controller/core/handler/mapping/key_mapping_event_handler.py',
    'controller/core/handler/mapping/key_mapping_manager.py',
]

controller_platform_sources = [
    'controller/platform/__init__.py',
    'controller/platform/base.py',
]

controller_platform_wayland_sources = [
    'controller/platform/wayland/__init__.py',
    'controller/platform/wayland/platform.py',
]

controller_platform_x11_sources = [
    'controller/platform/x11/__init__.py',
    'controller/platform/x11/platform.py',
]

controller_ui_sources = [
    'controller/ui/__init__.py',
    'controller/ui/menus.py',
    'controller/ui/styles.py',
]

controller_widgets_sources = [
    'controller/widgets/__init__.py',
    'controller/widgets/factory.py',
    'controller/widgets/config.py',
]

controller_widgets_base_sources = [
    'controller/widgets/base/__init__.py',
    'controller/widgets/base/base_widget.py',
]

controller_widgets_components_sources = [
    'controller/widgets/components/__init__.py',
    'controller/widgets/components/aim.py',
    'controller/widgets/components/directional_pad.py',
    'controller/widgets/components/fire.py',
    'controller/widgets/components/single_click.py',
    'controller/widgets/components/macro.py',
    'controller/widgets/components/right_click_to_walk.py',
    'controller/widgets/components/skill_casting.py',
    'controller/widgets/components/cancel_casting.py',
    'controller/widgets/components/repeated_click.py',
]

controller_widgets_decorators_sources = [
    'controller/widgets/decorators/__init__.py',
    'controller/widgets/decorators/base_decorator.py',
    'controller/widgets/decorators/editable.py',
    'controller/widgets/decorators/resizable.py',
]

install_data(waydroid_helper_sources, install_dir: moduledir)
install_data(config_sources, install_dir: moduledir / 'config')
install_data(util_sources, install_dir: utildir)
install_data(compat_widget_sources, install_dir: compatwidgetdir)
install_data(tools_sources, install_dir: toolsdir)

# 按子目录结构安装 controller 文件
install_data(controller_root_sources, install_dir: controllerdir)
install_data(controller_android_sources, install_dir: controllerdir / 'android')
install_data(controller_app_sources, install_dir: controllerdir / 'app')
install_data(controller_scrcpy_sources, install_dir: controllerdir / 'third_party')
install_data(controller_core_sources, install_dir: controllerdir / 'core')
install_data(controller_core_handler_sources, install_dir: controllerdir / 'core' / 'handler')
install_data(controller_core_handler_default_sources, install_dir: controllerdir / 'core' / 'handler' / 'default')
install_data(controller_platform_sources, install_dir: controllerdir / 'platform')
install_data(controller_platform_wayland_sources, install_dir: controllerdir / 'platform' / 'wayland')
install_data(controller_platform_x11_sources, install_dir: controllerdir / 'platform' / 'x11')
install_data(controller_ui_sources, install_dir: controllerdir / 'ui')
install_data(controller_widgets_sources, install_dir: controllerdir / 'widgets')
install_data(controller_widgets_base_sources, install_dir: controllerdir / 'widgets' / 'base')
install_data(controller_widgets_components_sources, install_dir: controllerdir / 'widgets' / 'components')
install_data(controller_widgets_decorators_sources, install_dir: controllerdir / 'widgets' / 'decorators')
install_data(controller_core_handler_mapping_sources, install_dir: controllerdir / 'core' / 'handler' / 'mapping')