Name:           waydroid-helper
Version:        0.2.9
Release:        0.%(date +%%Y%%m%%d.%%H)%{?dist}
Summary:        A GUI application for Waydroid configuration and extension installation

License:        GPLv3+
URL:            https://github.com/waydroid-helper/waydroid-helper
Source:        {{{ git_dir_pack }}}

%if 0%{?suse_version}
BuildRequires:  ninja
BuildRequires:  dbus-1-devel
Requires:       libvte-2_91-0
Requires:       python3-dbus-python
%else
BuildRequires:  ninja-build
BuildRequires:  dbus-devel
Requires:       vte291-gtk4
Requires:       python3-dbus
%endif
BuildRequires:  meson
BuildRequires:  pkgconfig
BuildRequires:  gcc
BuildRequires:  python3-devel
BuildRequires:  cairo-devel
BuildRequires:  gtk4-devel
BuildRequires:  libadwaita-devel
BuildRequires:  gobject-introspection-devel
BuildRequires:  gettext
BuildRequires:  systemd
BuildRequires:  desktop-file-utils

Requires:       python3
Requires:       gtk4
Requires:       libadwaita
Requires:       waydroid
Requires:       fakeroot
Requires:       python3-aiofiles
Requires:       python3-httpx
Requires:       python3-cairo
Requires:       python3-gobject >= 3.50
Requires:       python3-pywayland
Requires:       python3-yaml
Requires:       android-tools

Recommends:     bindfs

%description
Waydroid Helper is a graphical user interface application that provides
a user-friendly way to configure Waydroid and install extensions,
including Magisk, ARM translation, and various Google services alternatives.

%prep
%autosetup -n %{name}

%build
%meson
%meson_build

%global debug_package %{nil}

%install
%meson_install

%files
%license COPYING
%doc README.md

# Binaries
%{_bindir}/waydroid-helper
%{_bindir}/waydroid-cli

# Application data
%{_datadir}/waydroid-helper/

# Desktop entry and icons
%{_datadir}/applications/com.jaoushingan.WaydroidHelper.desktop
%{_datadir}/icons/hicolor/scalable/apps/com.jaoushingan.WaydroidHelper.svg
%{_datadir}/icons/hicolor/symbolic/apps/com.jaoushingan.WaydroidHelper-symbolic.svg

# Metainfo and schemas
%{_datadir}/metainfo/com.jaoushingan.WaydroidHelper.metainfo.xml
%{_datadir}/glib-2.0/schemas/com.jaoushingan.WaydroidHelper.gschema.xml

# Polkit policy
%{_datadir}/polkit-1/actions/com.jaoushingan.WaydroidHelper.policy

# Localization
%{_datadir}/locale/zh_CN/LC_MESSAGES/waydroid-helper.mo
%{_datadir}/locale/de/LC_MESSAGES/waydroid-helper.mo
%{_datadir}/locale/ru/LC_MESSAGES/waydroid-helper.mo
%{_datadir}/locale/zh_TW/LC_MESSAGES/waydroid-helper.mo

# D-Bus configuration
%{_datadir}/dbus-1/system.d/id.waydro.Mount.conf
%{_datadir}/dbus-1/system-services/id.waydro.Mount.service

# Systemd services
%{_unitdir}/waydroid-mount.service
%{_userunitdir}/waydroid-monitor.service

%changelog
%if 0%{?suse_version}
* Sun Mar 08 2026 Name <ayasa0520@gmail.com>
- Initial build
%else
%autochangelog
%endif
