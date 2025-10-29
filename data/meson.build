application_id = 'com.jaoushingan.WaydroidHelper'

gnome.compile_resources(
    'waydroid-helper',
    '@0@.gresource.xml'.format(application_id),
    gresource_bundle: true,
    install: true,
    install_dir: pkgdatadir,
)

desktop_file = i18n.merge_file(
    input: 'com.jaoushingan.WaydroidHelper.desktop.in',
    output: 'com.jaoushingan.WaydroidHelper.desktop',
    type: 'desktop',
    po_dir: '../po',
    install: true,
    install_dir: get_option('datadir') / 'applications',
)

conf = configuration_data()
conf.set('package_bindir', get_option('prefix') / get_option('bindir'))

configure_file(
    input: 'com.jaoushingan.WaydroidHelper.policy.in',
    output: 'com.jaoushingan.WaydroidHelper.policy',
    configuration: conf,
    install: true,
    install_dir: get_option('datadir') / 'polkit-1' / 'actions',
)

desktop_utils = find_program('desktop-file-validate', required: false)
if desktop_utils.found()
    test('Validate desktop file', desktop_utils, args: [desktop_file])
endif

appstream_file = i18n.merge_file(
    input: 'com.jaoushingan.WaydroidHelper.metainfo.xml.in',
    output: 'com.jaoushingan.WaydroidHelper.metainfo.xml',
    po_dir: '../po',
    install: true,
    install_dir: get_option('datadir') / 'metainfo',
)

appstreamcli = find_program('appstreamcli', required: false, disabler: true)
test(
    'Validate appstream file',
    appstreamcli,
    args: ['validate', '--no-net', '--explain', appstream_file],
)

install_data(
    'com.jaoushingan.WaydroidHelper.gschema.xml',
    install_dir: get_option('datadir') / 'glib-2.0' / 'schemas',
)

data = ['devices.json']
install_data(
    data,
    install_dir: get_option('datadir') / meson.project_name() / 'data',
)

# 安装脚本文件
install_subdir(
    'scripts',
    install_dir: get_option('datadir') / meson.project_name() / 'data',
)

compile_schemas = find_program('glib-compile-schemas', required: false, disabler: true)
test(
    'Validate schema file',
    compile_schemas,
    args: ['--strict', '--dry-run', meson.current_source_dir()],
)

scalable_dir = 'icons' / 'hicolor' / 'scalable' / 'apps'
install_data(
  scalable_dir / ('@0@.svg').format(application_id),
  install_dir: get_option('datadir') / scalable_dir,
)

symbolic_dir = 'icons' / 'hicolor' / 'symbolic' / 'apps'
install_data(
  [
    symbolic_dir / ('@0@-symbolic.svg').format(application_id),
  ],
  install_dir: get_option('datadir') / symbolic_dir,
)
