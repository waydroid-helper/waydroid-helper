# Waydroid Helper

**Языки**: [English](README.md) | [中文](README_zh.md) | [Русский](README_ru.md)

Waydroid Helper - это графическое приложение, написанное на Python с использованием PyGObject. Оно предоставляет удобный способ настройки Waydroid и установки расширений, включая Magisk и трансляцию ARM.

## Особенности

- Настройка параметров Waydroid
- **Привязка клавиш**: Использование клавиатуры и мыши для приложений и игр на Android
  - Множество виджетов управления (кнопки, панель управления направлением, элементы управления прицеливанием, макросы)
  - Настраиваемые привязки клавиш и их расположение
  - Поддержка сложных игровых сценариев (FPS, MOBA)
  - Подробные инструкции см. в [Руководстве по привязке клавиш](docs/KEY_MAPPING.md)
- Установите расширения для Waydroid
  - [Magisk](https://github.com/HuskyDG/magisk-files/)
  - [libhoudini](https://github.com/supremegamers/vendor_intel_proprietary_houdini)
  - [libndk](https://github.com/supremegamers/vendor_google_proprietary_ndk_translation-prebuilt)
  - [OpenGapps](https://sourceforge.net/projects/opengapps/)
  - [MindTheGapps](https://github.com/MindTheGapps)
  - [MicroG](https://microg.org/)
  - [SmartDock](https://github.com/axel358/smartdock)

## Установка

### Arch

Для пользователей Arch-linux, Waydroid Helper доступен в AUR:

```
yay -S waydroid-helper
```

### Debian

#### Для **Debian Unstable** выполните следующие действия:

```
echo 'deb http://download.opensuse.org/repositories/home:/CuteNeko:/waydroid-helper/Debian_Unstable/ /' | sudo tee /etc/apt/sources.list.d/home:CuteNeko:waydroid-helper.list
curl -fsSL https://download.opensuse.org/repositories/home:CuteNeko:waydroid-helper/Debian_Unstable/Release.key | gpg --dearmor | sudo tee /etc/apt/trusted.gpg.d/home_CuteNeko_waydroid-helper.gpg > /dev/null
echo -e "Package: python3-pywayland\nPin: origin \"download.opensuse.org\"\nPin-Priority: 1001" | sudo tee /etc/apt/preferences.d/99-pywayland.pref
sudo apt update
sudo apt install waydroid-helper
```

#### Для **Debian Testing** выполните следующие действия:

```
echo 'deb http://download.opensuse.org/repositories/home:/CuteNeko:/waydroid-helper/Debian_Testing/ /' | sudo tee /etc/apt/sources.list.d/home:CuteNeko:waydroid-helper.list
curl -fsSL https://download.opensuse.org/repositories/home:CuteNeko:waydroid-helper/Debian_Testing/Release.key | gpg --dearmor | sudo tee /etc/apt/trusted.gpg.d/home_CuteNeko_waydroid-helper.gpg > /dev/null
echo -e "Package: python3-pywayland\nPin: origin \"download.opensuse.org\"\nPin-Priority: 1001" | sudo tee /etc/apt/preferences.d/99-pywayland.pref
sudo apt update
sudo apt install waydroid-helper
```

#### Для **Debian 12** выполните следующие действия:

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

### Установка Релизных сборок

1. Перейдите на страницу [releases](https://github.com/waydroid-helper/waydroid-helper/releases)
2. Загрузите соответствующий пакет для вашего дистрибутива
3. Установите пакет

### Ручная сборка и установка

Для ручной установки вам потребуется установить зависимости и создать проект с помощью Meson.

#### Для Arch, Manjaro или EndeavourOS и дистрибьютивах основанных на них

1. Установите зависимости:

   ```bash
   sudo pacman -S gtk4 libadwaita meson ninja
   ```
2. Клонируйте репозиторий:

   ```
   git clone https://github.com/waydroid-helper/waydroid-helper.git
   cd waydroid-helper
   ```
3. Соберите и установите, используя Meson:

   ```
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   meson setup --prefix /usr build
   sudo ninja -C build install

   # Удаление waydroid helper
   # sudo ninja -C build uninstall
   ```

#### Для Debian и Ubuntu, и дистрибьютивах основанных на них

1. Установите зависимости:

   ```bash
   sudo apt install libgtk-4-1 libgtk-4-dev libadwaita-1-dev libadwaita-1-0 libgirepository1.0-dev gcc libcairo2-dev pkg-config python3-dev gir1.2-gtk-4.0 gir1.2-adw-1 gettext ninja-build fakeroot libdbus-1-dev desktop-file-utils software-properties-common -y
   ```
2. Клонируйте репозиторий:

   ```
   git clone https://github.com/waydroid-helper/waydroid-helper.git
   cd waydroid-helper
   ```
3. Соберите и установите, используя Meson:

   ```
   python3 -m venv .venv
   source .venv/bin/activate
   pip install meson
   pip install -r requirements.txt
   meson setup --prefix /usr build
   sudo ninja -C build install

   # Удаление waydroid helper
   # sudo ninja -C build uninstall
   ```

#### Для RHEL, Fedora или Rocky и дистрибьютивах основанных на них

1. Установите зависимости:

   ```bash
   sudo dnf install gtk4 gtk4-devel libadwaita libadwaita-devel gobject-introspection-devel gcc cairo-devel pkgconf-pkg-config python3-devel gobject-introspection gtk4-devel libadwaita-devel gettext ninja-build fakeroot dbus-devel desktop-file-utils -y
   ```
2. Клонируйте репозиторий:

   ```
   git clone https://github.com/waydroid-helper/waydroid-helper.git
   cd waydroid-helper
   ```
3. Соберите и установите, используя Meson:

   ```
   python3 -m venv .venv
   source .venv/bin/activate
   pip install meson
   pip install -r requirements.txt
   meson setup --prefix /usr build
   sudo ninja -C build install

   # Удаление waydroid helper
   # sudo ninja -C build uninstall
   ```

## Скриншоты

![image-20241125011305536](assets/img/README/1_en.png)

![](./assets/img/README/2_en.png)
![](./assets/img/README/3_en.png)

## Документация

- **[Руководство по привязке клавиш](docs/KEY_MAPPING.md)**: Подробное руководство по использованию системы привязки клавиш для управления приложениями и играми Android с помощью клавиатуры и мыши

## Устранение неисправностей

### Общие папки не работают

Включите сервис в systemd

```
systemctl --user enable waydroid-monitor.service --now
sudo systemctl enable waydroid-mount.service --now
```

Пользователям AppImage необходимо вручную скопировать файлы конфигурации D-Bus и юнитов systemd в соответствующие системные папки, чтобы обеспечить надлежащую функциональность. Вот рекомендуемая файловая структура:

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

### Waydroid не запускается после установки microg или gapps

Если у вас возникли проблемы с тем, что waydroid не запускается после установки microg или gapps, попробуйте следующие решения:

1. **Убедитесь, что используется обычный образ**: Убедитесь, что вы используете образ по-умолчанию, а не версию gapps
2. **Очистите кэш пакетов**: Попробуйте воспользоваться функцией очистки кэша пакетов
3. **Полный сброс данных**: Если вышеуказанные методы по-прежнему не устраняют проблему, полностью удалите каталог `~/.local/share/waydroid/data` и повторно запустите `sudo waydroid init -f`. **Примечание**: Эта операция приведет к удалению всех данных waydroid, поэтому, пожалуйста, убедитесь, что вы создали резервную копию всей важной информации.

## Благодарности

Особая благодарность проекту [scrcpy](https://github.com/Genymobile/scrcpy). В этом проекте используются серверные компоненты scrcpy для обеспечения беспрепятственного управления устройствами Android в Waydroid. Надежный протокол связи и возможности взаимодействия с устройствами, предоставляемые scrcpy, составляют основу наших функций привязки клавиш.
