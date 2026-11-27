# Waydroid Helper

**语言**: [English](README.md) | [中文](README_zh.md) | [Русский](README_ru.md)

Waydroid Helper 是一个使用 Python 和 PyGObject 编写的图形用户界面应用程序。它提供了一种用户友好的方式来配置 Waydroid 并安装扩展，包括 Magisk 和 ARM 兼容层。

## 功能特性

- 配置 Waydroid 设置
- **按键映射系统**：为 Android 应用和游戏提供键盘和鼠标映射
  - 多种控制组件（按钮、方向键盘、瞄准控制、宏）
  - 可自定义的按键绑定和布局
  - 支持复杂的游戏场景（FPS、MOBA）
  - 查看[按键映射指南](docs/KEY_MAPPING_zh.md)获取详细说明
- 为 Waydroid 安装扩展
  - [Magisk](https://github.com/HuskyDG/magisk-files/)
  - [libhoudini](https://github.com/supremegamers/vendor_intel_proprietary_houdini)
  - [libndk](https://github.com/supremegamers/vendor_google_proprietary_ndk_translation-prebuilt)
  - [OpenGapps](https://sourceforge.net/projects/opengapps/)
  - [MindTheGapps](https://github.com/MindTheGapps)
  - [MicroG](https://microg.org/)
  - [SmartDock](https://github.com/axel358/smartdock)

## 安装

### Arch

对于 Arch 用户，Waydroid Helper 在 AUR 中可用：
```
yay -S waydroid-helper
```

### Debian

##### 对于 **Debian Unstable** 运行以下命令：

```
echo 'deb http://download.opensuse.org/repositories/home:/CuteNeko:/waydroid-helper/Debian_Unstable/ /' | sudo tee /etc/apt/sources.list.d/home:CuteNeko:waydroid-helper.list
curl -fsSL https://download.opensuse.org/repositories/home:CuteNeko:waydroid-helper/Debian_Unstable/Release.key | gpg --dearmor | sudo tee /etc/apt/trusted.gpg.d/home_CuteNeko_waydroid-helper.gpg > /dev/null
echo -e "Package: python3-pywayland\nPin: origin \"download.opensuse.org\"\nPin-Priority: 1001" | sudo tee /etc/apt/preferences.d/99-pywayland.pref
sudo apt update
sudo apt install waydroid-helper
```

##### 对于 **Debian Testing** 运行以下命令

```
echo 'deb http://download.opensuse.org/repositories/home:/CuteNeko:/waydroid-helper/Debian_Testing/ /' | sudo tee /etc/apt/sources.list.d/home:CuteNeko:waydroid-helper.list
curl -fsSL https://download.opensuse.org/repositories/home:CuteNeko:waydroid-helper/Debian_Testing/Release.key | gpg --dearmor | sudo tee /etc/apt/trusted.gpg.d/home_CuteNeko_waydroid-helper.gpg > /dev/null
echo -e "Package: python3-pywayland\nPin: origin \"download.opensuse.org\"\nPin-Priority: 1001" | sudo tee /etc/apt/preferences.d/99-pywayland.pref
sudo apt update
sudo apt install waydroid-helper
```

##### 对于 **Debian 12** 运行以下命令：

```
echo 'deb http://download.opensuse.org/repositories/home:/CuteNeko:/waydroid-helper/Debian_12/ /' | sudo tee /etc/apt/sources.list.d/home:CuteNeko:waydroid-helper.list
curl -fsSL https://download.opensuse.org/repositories/home:CuteNeko:waydroid-helper/Debian_12/Release.key | gpg --dearmor | sudo tee /etc/apt/trusted.gpg.d/home_CuteNeko_waydroid-helper.gpg > /dev/null
echo -e "Package: python3-pywayland\nPin: origin \"download.opensuse.org\"\nPin-Priority: 1001" | sudo tee /etc/apt/preferences.d/99-pywayland.pref
sudo apt update
sudo apt install waydroid-helper
```

##### 对于 **Debian 13** 运行以下命令：

```
echo 'deb http://download.opensuse.org/repositories/home:/CuteNeko:/waydroid-helper/Debian_13/ /' | sudo tee /etc/apt/sources.list.d/home:CuteNeko:waydroid-helper.list
curl -fsSL https://download.opensuse.org/repositories/home:CuteNeko:waydroid-helper/Debian_13/Release.key | gpg --dearmor | sudo tee /etc/apt/trusted.gpg.d/home_CuteNeko_waydroid-helper.gpg > /dev/null
echo -e "Package: python3-pywayland\nPin: origin \"download.opensuse.org\"\nPin-Priority: 1001" | sudo tee /etc/apt/preferences.d/99-pywayland.pref
sudo apt update
sudo apt install waydroid-helper
```

### Fedora

```
sudo dnf copr enable cuteneko/waydroid-helper
sudo dnf install waydroid-helper
```

### Ubuntu

```
sudo add-apt-repository ppa:ichigo666/ppa
echo -e "Package: python3-pywayland\nPin: origin \"ppa.launchpadcontent.net\"\nPin-Priority: 1001" | sudo tee /etc/apt/preferences.d/99-ichigo666-ppa.pref
sudo apt update
sudo apt install waydroid-helper
```

### 从发布版本安装
1. 前往[发布页面](https://github.com/waydroid-helper/waydroid-helper/releases)
2. 下载适合您发行版的软件包
3. 安装软件包


### 嵌入式模拟器窗口

在实例详情的「按键映射器」区域选择「打开模拟器」，也可以运行 `waydroid-helper --emulator`。Android 画面和键位映射在同一窗口内显示。已有会话运行时，窗口会询问是否重启 Android。关闭模拟器也会结束该窗口启动的会话。

从 Android 桌面打开应用后，标题栏会出现对应的任务标签。点击标签可回到应用原先的页面，点击关闭按钮可结束该任务，点击固定的 Waydroid 标签可返回主屏幕。即使已开启 Waydroid 桌面多窗口模式，嵌入窗口也会自动将自由窗口中的应用铺满 Android 画面，使用同一套标签。

标题栏的键盘按钮可以加载已有 JSON 方案、编辑或添加键位。选择一种键位后，点击游戏画面即可放置。F1 切换编辑和游玩，F12 在游玩时显示或隐藏键位。拖动窗口的任意边或角都可以调整大小，拖动过程中画面始终保持 Android 的宽高比。按 F11 切换全屏。打开「更多 → 设备设置 → 显示」，可以选择平板、手机或超宽屏预设，也可以自定义宽、高和 DPI。重启 Android 后生效。拖动窗口和 F11 全屏只会等比缩放画面和映射层，Android 分辨率与密度保持不变。

[MuMu 菜单对照与全屏实测](docs/EMULATOR_MENUS_zh.md)

嵌入显示使用 Casilda 及其 `Casilda-1.0` 类型库，输入控制使用 ADB。项目附带的 Casilda 修正了 Waydroid 壁纸等图层的裁剪。使用系统 Casilda 时，需要其包含相应修复才能正确显示这些图层。也可以使用 Meson 1.8 或更高版本、GTK 4.24 开发文件、wlroots 0.20 和 GObject Introspection 构建项目固定版本的 Casilda。

```sh
meson setup .build/embedded -Dbundle_casilda=true
meson compile -C .build/embedded
```

在手柄方案的「管理方案 → 已连接的手柄」中，每只手柄都有一个「配置」按钮，可查看按键的实时高亮。嵌入构建使用应用私有的 libmanette，以便在手柄断开时停止读取设备。构建它需要 libevdev、hidapi-hidraw 和 GObject Introspection 的开发文件。使用单独安装的 Casilda 时，也可以通过 `-Dbundle_manette=enabled` 显式启用。

### 手动构建和安装

对于手动安装，您需要安装依赖项并使用 Meson 构建项目。

#### Arch、Manjaro 和 EndeavourOS 基础发行版
1. 安装依赖项：

    ```bash
    sudo pacman -S gtk4 libadwaita libshumate meson ninja
    ```

2. 克隆仓库：
    ```
    git clone https://github.com/waydroid-helper/waydroid-helper.git
    cd waydroid-helper
    ```
3. 使用 Meson 构建和安装：
    ```
    python3 -m venv .venv
    source .venv/bin/activate
    pip install -r requirements.txt
    meson setup --prefix /usr build
    sudo ninja -C build install
    
    # 卸载 waydroid helper
    # sudo ninja -C build uninstall
    ```

#### Debian 和 Ubuntu 基础发行版
1. 安装依赖项：

    ```bash
    sudo apt install libgtk-4-1 libgtk-4-dev libadwaita-1-dev libadwaita-1-0 libgirepository1.0-dev gcc libcairo2-dev pkg-config python3-dev gir1.2-gtk-4.0 gir1.2-adw-1 gir1.2-shumate-1.0 gettext ninja-build fakeroot libdbus-1-dev desktop-file-utils software-properties-common -y
    ```

2. 克隆仓库：
    ```
    git clone https://github.com/waydroid-helper/waydroid-helper.git
    cd waydroid-helper
    ```
3. 使用 Meson 构建和安装：
    ```
    python3 -m venv .venv
    source .venv/bin/activate
    pip install meson
    pip install -r requirements.txt
    meson setup --prefix /usr build
    sudo ninja -C build install
    
    # 卸载 waydroid helper
    # sudo ninja -C build uninstall
    ```

#### RHEL、Fedora 和 Rocky 基础发行版
1. 安装依赖项：

    ```bash
    sudo dnf install gtk4 gtk4-devel libadwaita libshumate libadwaita-devel gobject-introspection-devel gcc cairo-devel pkgconf-pkg-config python3-devel gobject-introspection gtk4-devel libadwaita-devel gettext ninja-build fakeroot dbus-devel desktop-file-utils -y
    ```

2. 克隆仓库：
    ```
    git clone https://github.com/waydroid-helper/waydroid-helper.git
    cd waydroid-helper
    ```
3. 使用 Meson 构建和安装：
    ```
    python3 -m venv .venv
    source .venv/bin/activate
    pip install meson
    pip install -r requirements.txt
    meson setup --prefix /usr build
    sudo ninja -C build install
    
    # 卸载 waydroid helper
    # sudo ninja -C build uninstall
    ```

## 截图

![image-20241125011305536](assets/img/README/1_en.png)

![](./assets/img/README/2_en.png)
![](./assets/img/README/3_en.png)

## 文档

- **[按键映射指南](docs/KEY_MAPPING_zh.md)**：使用按键映射系统通过键盘和鼠标控制 Android 应用和游戏的综合指南

## 故障排除

### 共享文件夹不工作
启用 systemd 服务
```
systemctl --user enable waydroid-monitor.service --now
sudo systemctl enable waydroid-mount.service --now
```

对于 AppImage 用户，您需要手动将 D-Bus 配置文件和 systemd 单元文件复制到各自的系统位置以启用正确的功能。建议的文件结构如下：

```
usr
├── lib
│   └── systemd
│       ├── system
│       │   └── waydroid-mount.service
│       └── user
│           └── waydroid-monitor.service
└── share
    ├── dbus-1
    │   ├── system.d
    │   │   └── id.waydro.Mount.conf
    │   └── system-services
    │       └── id.waydro.Mount.service

```
### 安装 microg 或 gapps 后 waydroid 无法启动
如果在安装 microg 或 gapps 后遇到 waydroid 无法启动的问题，请尝试以下解决方案：

1. **确保使用 vanilla 镜像**：确认您正在使用 vanilla 的 image 而不是 gapps 版本
2. **完全重置数据**：如果上述方法仍然无法解决问题，请完全清除 `~/.local/share/waydroid/data` 目录，然后重新执行 `sudo waydroid init -f`. **注意**：此操作将删除所有 waydroid 数据，请确保已备份重要信息。


## 致谢

特别感谢 [scrcpy](https://github.com/Genymobile/scrcpy) 项目。本项目使用了 scrcpy 的服务器组件来实现对 Waydroid 中 Android 设备的无缝控制。scrcpy 提供的强大通信协议和设备交互能力为我们的按键映射奠定了基础。
