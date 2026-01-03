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

### Universal Blue / Bazzite

对于 Universal Blue、Bazzite 或其他 rpm-ostree 系统：

1. 下载 justfile：
   ```bash
   wget https://raw.githubusercontent.com/waydroid-helper/waydroid-helper/main/just/waydroid-helper.just
   ```

2. 从 COPR 安装（推荐）：
   ```bash
   just --justfile waydroid-helper.just install-waydroid-helper
   ```

3. 更新到最新版本：
   ```bash
   just --justfile waydroid-helper.just update-waydroid-helper
   ```

### 从发布版本安装
1. 前往[发布页面](https://github.com/waydroid-helper/waydroid-helper/releases)
2. 下载适合您发行版的软件包
3. 安装软件包


### 手动构建和安装

对于手动安装，您需要安装依赖项并使用 Meson 构建项目。

#### Arch、Manjaro 和 EndeavourOS 基础发行版
1. 安装依赖项：

    ```bash
    sudo pacman -S gtk4 libadwaita meson ninja
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
    sudo apt install libgtk-4-1 libgtk-4-dev libadwaita-1-dev libadwaita-1-0 libgirepository1.0-dev gcc libcairo2-dev pkg-config python3-dev gir1.2-gtk-4.0 gir1.2-adw-1 gettext ninja-build fakeroot libdbus-1-dev desktop-file-utils software-properties-common -y
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
    sudo dnf install gtk4 gtk4-devel libadwaita libadwaita-devel gobject-introspection-devel gcc cairo-devel pkgconf-pkg-config python3-devel gobject-introspection gtk4-devel libadwaita-devel gettext ninja-build fakeroot dbus-devel desktop-file-utils -y
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
