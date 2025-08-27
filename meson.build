project('waydroid-helper',
          version: '0.2.7',
    meson_version: '>= 0.62.0',
  default_options: [ 'warning_level=2', 'werror=false', ],
)

i18n = import('i18n')
gnome = import('gnome')
pkgdatadir = get_option('prefix') / get_option('datadir') / meson.project_name()


subdir('data')
subdir('waydroid_helper')
subdir('po')
subdir('dbus')
subdir('systemd')

gnome.post_install(
     glib_compile_schemas: true,
    gtk_update_icon_cache: true,
  update_desktop_database: true,
)
