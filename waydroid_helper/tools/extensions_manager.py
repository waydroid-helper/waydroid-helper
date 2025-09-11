# pyright: reportAny=false
# pyright: reportUnannotatedClassAttribute=false
# pyright: reportUnknownVariableType=false
# pyright: reportUnknownMemberType=false
# pyright: reportUnknownArgumentType=false
import asyncio
import json
import os
import re
import xml.etree.ElementTree as ET
from collections.abc import Coroutine, Iterable
from enum import IntEnum
from gettext import gettext as _
from typing import Any, TypedDict, TypeGuard

import aiofiles
import httpx
import yaml
from gi.repository import GLib, GObject

from waydroid_helper.util.abx_reader import AbxReader
from waydroid_helper.util.arch import host
from waydroid_helper.util.log import logger
from waydroid_helper.util.subprocess_manager import SubprocessManager
from waydroid_helper.util.task import Task
from waydroid_helper.waydroid import Waydroid, WaydroidState


class ExtensionManagerState(IntEnum):
    UNINITIALIZED = 0
    READY = 1


class PackageInfo(TypedDict):
    name: str
    description: str
    version: str
    path: str
    android_version: str
    files: list[str]
    provides: list[str]
    conflicts: list[str]
    source: list[str]
    md5sums: list[str]
    sha256sums: list[str]
    source_x86: list[str]
    md5sums_x86: list[str]
    sha256sums_x86: list[str]
    source_x86_64: list[str]
    md5sums_x86_64: list[str]
    sha256sums_x86_64: list[str]
    source_arm: list[str]
    md5sums_arm: list[str]
    sha256sums_arm: list[str]
    source_arm64: list[str]
    md5sums_arm64: list[str]
    sha256sums_arm64: list[str]
    installed_files: list[str]
    props: list[str]
    install: str


# 包含一个包的新旧版本
class PackageListItem(TypedDict):
    path: str
    list: list[PackageInfo]


class VariantListItem(TypedDict):
    name: str
    description: str
    path: str
    list: list[PackageListItem]


class PackageClassListItem(TypedDict):
    name: str
    description: str
    path: str
    list: list[VariantListItem] | list[PackageListItem]


def bash_var_replacement_regex(command: str, var_dict: dict[str, str]) -> str:
    def replace_match(match: re.Match[str]):
        var = match.group(1)
        return var_dict.get(
            var, match.group(0)
        )  # 如果找不到对应的变量，返回原始的匹配值

    return re.sub(r"\$(\w+)", replace_match, command)


# TODO
#      1. 避免多次重启
#      2. 进度条, 完成提醒
#      3. prop 修改放在 yaml 里, 不要单独文件了
class PackageManager(GObject.Object):
    __gsignals__ = {
        "installation-started": (GObject.SignalFlags.RUN_FIRST, None, (str, str)),
        # 'installation-progress': (GObject.SignalFlags.RUN_FIRST, None, (str, float)),
        "installation-completed": (GObject.SignalFlags.RUN_FIRST, None, (str, str)),
        "uninstallation-started": (GObject.SignalFlags.RUN_FIRST, None, (str, str)),
        "uninstallation-completed": (GObject.SignalFlags.RUN_FIRST, None, (str, str)),
    }
    state = GObject.Property(type=object)
    waydroid: Waydroid = GObject.Property(
        type=Waydroid
    )  # pyright: ignore[reportAssignmentType]
    available_extensions: dict[str, PackageInfo] = {}
    installed_packages: dict[str, PackageInfo] = {}
    arch = host()
    remote = "https://github.com/waydroid-helper/extensions/raw/master/"
    extensions_json: list[PackageClassListItem] = []
    storage_dir = os.path.join(
        GLib.get_user_data_dir(), os.getenv("PROJECT_NAME", "waydroid-helper")
    )
    cache_dir = os.path.join(
        GLib.get_user_cache_dir(), os.getenv("PROJECT_NAME", "waydroid-helper")
    )
    _task = Task()
    _subprocess = SubprocessManager()
    # TODO 同时安装多个扩展的问题, 最好做到可以并发下载, 串行安装
    _package_lock = asyncio.Lock()

    async def fetch_snapshot(self, name: str, version: str):
        logger.info(self.available_extensions[f"{name}-{version}"])

    async def fetch_extension_json(self) -> Any:
        async with httpx.AsyncClient(follow_redirects=True) as client:
            try:
                response = await client.get(self.remote + "extensions.json")
                if response.status_code == 200:
                    return response.json()
                else:
                    logger.error(
                        f"Failed to fetch JSON from, status code: {response.status_code}"
                    )
                    return None
            except AssertionError as e:
                logger.error(e)

    async def save_extension_json(self):
        json_path = os.path.join(self.storage_dir, "extensions.json")
        # json_cache_path = os.path.join(self.cache_dir, "extensions.json")
        os.makedirs(os.path.dirname(json_path), exist_ok=True)
        async with aiofiles.open(json_path, "w") as f:
            json_str = json.dumps(self.extensions_json, ensure_ascii=False, indent=4)
            await f.write(json_str)

        # await self._subprocess.run(
        #     f"pkexec waydroid-cli mkdir  {os.path.dirname(json_path)}"
        # )

        # await self._subprocess.run(
        #     f"pkexec waydroid-cli copy {json_cache_path} {json_path}"
        # )

    async def update_extension_json(self):
        extensions = await self.fetch_extension_json()
        self.extensions_json = extensions
        logger.info("extension json has been updated")
        if extensions:
            self._task.create_task(self.save_extension_json())

    def is_installed(self, name: str, version: str):
        package: PackageInfo | None = self.installed_packages.get(name)
        if package is None:
            return False
        return package.get("version") == version

    async def init_manager(self):
        json_path = os.path.join(self.storage_dir, "extensions.json")
        if not os.path.exists(json_path):
            await self.update_extension_json()
        else:
            async with aiofiles.open(json_path, "r") as f:
                self.extensions_json = json.loads(await f.read())
        self.grab_meta()
        await self.load_installed()
        self.state = ExtensionManagerState.READY

    def __init__(self):
        super().__init__()
        self.state = ExtensionManagerState.UNINITIALIZED
        self._task.create_task(self.init_manager())
        os.makedirs(self.storage_dir, exist_ok=True)

    async def load_installed(self):
        directory = os.path.join(self.storage_dir, "local")
        if not os.path.exists(directory):
            return
        for folder_name in os.listdir(directory):
            folder_path = os.path.join(directory, folder_name)

            # 检查是否是文件夹
            if os.path.isdir(folder_path):
                # 指定 desc.json 的路径
                desc_path = os.path.join(folder_path, "desc")

                # 检查 desc.json 文件是否存在
                if os.path.isfile(desc_path):
                    # 读取 desc.json 文件
                    async with aiofiles.open(desc_path, "r") as f:
                        content = await f.read()
                        desc_data = json.loads(content)
                        self.installed_packages[desc_data["name"]] = desc_data

    def get_package_data(self):
        return self.extensions_json

    def grab_meta(self):

        def is_package_info_list_item(item3: Any) -> TypeGuard[PackageListItem]:
            return "list" in item3.keys()

        def is_package_info(item3: Any) -> TypeGuard[PackageInfo]:
            return not is_package_info_list_item(item3)

        for item1 in self.extensions_json:
            for item2 in item1["list"]:
                for item3 in item2["list"]:
                    extension: dict[str, PackageInfo]
                    if is_package_info_list_item(item3):
                        path = f'{item1["path"]}/{item2["path"]}/{item3["path"]}'
                        extensions: list[PackageInfo] = item3["list"]
                        extension = {
                            f'{each["name"]}-{each["version"]}': {
                                **each,
                                "path": f"{path}/{each['path']}",
                            }
                            for each in extensions
                        }
                    elif is_package_info(item3):
                        path = f'{item1["path"]}/{item2["path"]}/{item3["path"]}'
                        extension = {
                            f'{item3["name"]}-{item3["version"]}': {
                                **item3,
                                "path": path,
                            }
                        }
                    else:
                        return None
                    self.available_extensions.update(extension)

    def get_package_info(
        self, name: str, version: str | None = None
    ) -> PackageInfo | None:
        if version is not None:
            package = self.available_extensions.get(f"{name}-{version}")
            return package
        for package in self.available_extensions.values():
            if name in package.get("provides", []):
                return package
        return None

    def check_conflicts(
        self,
        name: str,
        version: str | None = None,
        package_info: PackageInfo | None = None,
    ):
        conflicts: set[str] = set()
        if package_info is None:
            package_info = self.get_package_info(name=name, version=version)
        if package_info is None:
            logger.error(f"Package {name}-{version} not found")
            return conflicts
        for installed_package in self.installed_packages.values():
            # 检查 package_info 的 conflicts 列表
            for conflict in package_info.get("conflicts", []):
                if conflict == installed_package[
                    "name"
                ] or conflict in installed_package.get("provides", []):
                    conflicts.add(installed_package["name"])
            # 检查已安装包的 conflicts 列表
            for conflict in installed_package.get("conflicts", []):
                if conflict == package_info["name"] or conflict in package_info.get(
                    "provides", []
                ):
                    conflicts.add(installed_package["name"])
        return conflicts

    def list_installed(self):
        return self.installed_packages

    # def check_dependencies(self, package_info):
    #     """检查包的依赖"""
    #     missing_dependencies = []
    #     for dependency in package_info.get("dependencies", []):
    #         if dependency not in self.installed_packages.keys() and not any(
    #             dependency in pkg.get("provides", [])
    #             for pkg in self.installed_packages.values()
    #         ):
    #             missing_dependencies.append(dependency)
    #     return missing_dependencies

    async def download_file(
        self,
        client: httpx.AsyncClient,
        url: str,
        dest_path: str,
        sha256: str | None = None,
        md5: str | None = None,
        retries: int = 3,
        delay: int = 2,
    ):
        attempt = 0
        while attempt < retries:
            try:
                response = await client.get(url)
                assert response.content, "Downloaded content is empty"

                if not os.path.exists(os.path.dirname(dest_path)):
                    os.makedirs(os.path.dirname(dest_path))

                async with aiofiles.open(dest_path, mode="wb") as f:
                    await f.write(response.content)

                # Prefer SHA-256 validation; fall back to MD5 if SHA-256 not provided
                if sha256 is not None:
                    result = await self._subprocess.run(
                        f'sha256sum "{dest_path}"', shell=False
                    )
                    actual_sha256 = result["stdout"].split()[0]
                    if actual_sha256 != sha256:
                        raise ValueError(
                            f"SHA256 mismatch: expected {sha256}, got {actual_sha256}"
                        )
                elif md5 is not None:
                    result = await self._subprocess.run(
                        f'md5sum "{dest_path}"', shell=False
                    )
                    actual_md5 = result["stdout"].split()[0]
                    if actual_md5 != md5:
                        raise ValueError(
                            f"MD5 mismatch: expected {md5}, got {actual_md5}"
                        )

                logger.info(f"File downloaded and saved to {dest_path}")
                return
            except Exception as e:
                attempt += 1
                if attempt < retries:
                    logger.warning(
                        f"Attempt {attempt} failed: {e}. Retrying in {delay} seconds..."
                    )
                    await asyncio.sleep(delay)
                else:
                    logger.error(
                        f"All {retries} attempts failed. Could not download the file."
                    )
                    raise ValueError(
                        f"All {retries} attempts failed. Could not download the file."
                    )

    def get_all_files_relative(self, directory: str):
        all_files: list[str] = []
        for root, dirs, files in os.walk(
            directory
        ):  # pyright: ignore[reportUnusedVariable]
            for file in files:
                file_path = os.path.relpath(os.path.join(root, file), directory)
                all_files.append(file_path)
        return all_files

    async def download(self, package_info: PackageInfo):
        async with httpx.AsyncClient(follow_redirects=True) as client:
            tasks: list[Coroutine[Any, Any, None]] = []
            for file in package_info["files"]:
                url = f'{self.remote}{package_info["path"]}/{file}'
                dest = f'{self.cache_dir}/extensions/{package_info["name"]}/{file}'
                tasks.append(self.download_file(client, url, dest))

            # Determine source and checksum lists, preferring SHA-256 over MD5
            if f"source_{self.arch}" in package_info.keys():
                _source = f"source_{self.arch}"
                _sha256sums = f"sha256sums_{self.arch}"
                _md5sums = f"md5sums_{self.arch}"
            else:
                _source = "source"
                _sha256sums = "sha256sums"
                _md5sums = "md5sums"

            if _source not in package_info:
                logger.warning(f"Package {package_info['name']} missing {_source}")
                return

            has_sha256 = _sha256sums in package_info and bool(package_info[_sha256sums])
            has_md5 = _md5sums in package_info and bool(package_info[_md5sums])
            if not has_sha256 and not has_md5:
                logger.warning(
                    f"Package {package_info['name']} missing both {_sha256sums} and {_md5sums}"
                )
                return

            use_sha256 = has_sha256
            sums_key = _sha256sums if use_sha256 else _md5sums

            for source, expected in zip(
                package_info[_source],
                package_info[sums_key],
            ):
                file_name: str = source.split("::")[0]
                url: str = source.split("::")[1]
                file_path = os.path.join(
                    self.cache_dir, "extensions", package_info["name"], file_name
                )
                if os.path.exists(file_path):
                    if use_sha256:
                        result = await self._subprocess.run(
                            f'sha256sum "{file_path}"', shell=False
                        )
                        actual = result["stdout"].split()[0]
                    else:
                        result = await self._subprocess.run(
                            f'md5sum "{file_path}"', shell=False
                        )
                        actual = result["stdout"].split()[0]

                    if actual == expected:
                        continue
                    else:
                        if use_sha256:
                            tasks.append(
                                self.download_file(
                                    client, url, file_path, sha256=expected
                                )
                            )
                        else:
                            tasks.append(
                                self.download_file(client, url, file_path, md5=expected)
                            )
                else:
                    if use_sha256:
                        tasks.append(
                            self.download_file(client, url, file_path, sha256=expected)
                        )
                    else:
                        tasks.append(
                            self.download_file(client, url, file_path, md5=expected)
                        )

            await asyncio.gather(*tasks)

    def get_android_version_to_sdk(self, android_version: str) -> str:
        """将 Android 版本转换为对应的 SDK 版本"""
        # Android 版本到 SDK 版本的映射
        version_to_sdk = {
            "11": "30",  # Android 11
            "12": "31",  # Android 12
            "12L": "32",  # Android 12L
            "13": "33",  # Android 13
            "14": "34",  # Android 14
            "15": "35",  # Android 15
        }

        # 精确匹配
        if android_version in version_to_sdk:
            return version_to_sdk[android_version]

        # 如果找不到精确匹配，返回默认值 30 (Android 11)
        logger.warning(
            f"Unknown Android version: {android_version}, using default SDK 30"
        )
        return "30"

    async def install_package(self, name: str, version: str):
        async with self._package_lock:
            self.emit("installation-started", name, version)
            should_start_session = self.waydroid.state == WaydroidState.RUNNING
            package_info = self.get_package_info(name, version)
            if package_info is None:
                logger.error(f"Package {name} not found.")
                return

            # 检查架构
            if "arch" in package_info.keys() and self.arch not in package_info["arch"]:
                raise ValueError("Hardware architecture mismatch")

            if "android_version" in package_info.keys():
                current_android_version = self.waydroid.get_android_version()
                required_android_version = package_info["android_version"]
                if current_android_version != required_android_version:
                    raise ValueError(
                        _(
                            "Your Android version is not supported. Required version: {0}. Current version: {1}."
                        ).format(required_android_version, current_android_version)
                    )

            # 检查依赖
            # missing_dependencies = self.check_dependencies(package_info)
            # if missing_dependencies:
            #     if install_dependencies:
            #         for dependency in missing_dependencies:
            #             self.install_package(
            #                 dependency, remove_conflicts, install_dependencies
            #             )
            #     else:
            #         print(
            #             f"Package {package_info['name']} is missing dependencies: {', '.join(missing_dependencies)}."
            #         )
            #         return
            await self.download(package_info)

            # 调用 installer
            package_name = package_info["name"]
            package_version = package_info["version"]
            startdir = os.path.join(self.cache_dir, "extensions", package_name)
            pkgdir = os.path.join(startdir, "pkg")
            package = f"{startdir}/{package_name}-{package_version}.tar.gz"
            await self._subprocess.run(
                f'{os.environ["WAYDROID_CLI_PATH"]} call_package "{startdir}" "{package_name}" "{package_version}"',
                env={
                    "CARCH": self.arch,
                    "SDK": self.get_android_version_to_sdk(
                        self.waydroid.get_android_version()
                    ),
                },
                shell=False,
            )
            if "install" in package_info.keys():
                await self.pre_install(package_info)
            await self._subprocess.run(
                f'pkexec {os.environ["WAYDROID_CLI_PATH"]} install "{package}"',
                shell=False,
            )

            installed_files = self.get_all_files_relative(pkgdir)

            # desc_cache_path = os.path.join(startdir, "desc")
            local_dir = os.path.join(self.storage_dir, "local", f"{package_name}")
            desc_path = os.path.join(local_dir, "desc")
            package_info.update({"installed_files": installed_files})
            # 应用 prop
            if os.path.exists(os.path.join(startdir, "prop.json")):
                async with aiofiles.open(
                    os.path.join(startdir, "prop.json"), mode="r"
                ) as f:
                    content = await f.read()
                    props: dict[str, Any] = json.loads(content)
                    success = await self.waydroid.set_extension_props(props)
                    if success:
                        await self.waydroid.upgrade(offline=True)

                package_info["props"] = list(props.keys())

            if "install" in package_info.keys():
                cache_install = os.path.join(startdir, package_info["install"])
                local_install = os.path.join(local_dir, "install")
                await self._subprocess.run(
                    f"install -Dm 755 {cache_install} {local_install}", shell=False
                )

            # 标记已安装包
            # await self._subprocess.run(f"pkexec waydroid-cli mkdir {local_dir}")
            # await self._subprocess.run(
            #     f"pkexec waydroid-cli copy {desc_cache_path} {local_dir}"
            # )

            # post_install
            if "install" in package_info.keys():
                await self.post_install(package_info)

            os.makedirs(local_dir, exist_ok=True)
            async with aiofiles.open(desc_path, mode="w") as f:
                content = json.dumps(package_info)
                await f.write(content)

            self.installed_packages[package_name] = package_info
            logger.info(f"Package {name} installed successfully.")
            await self.waydroid.stop_session()
            if should_start_session:
                await self.waydroid.start_session()
            self.emit("installation-completed", name, version)

    async def execute_post_operations(self, info: PackageInfo, operation_key: str):
        if operation_key.endswith("install"):
            install_path = os.path.join(
                self.cache_dir, "extensions", info["name"], info["install"]
            )
        else:
            install_path = os.path.join(
                self.storage_dir, "local", info["name"], "install"
            )

        async with aiofiles.open(install_path, "r") as f:
            content = await f.read()
            yml = yaml.safe_load(content)

        if operation_key not in yml:
            return

        # commands = []
        operations = yml[operation_key]
        for operation in operations:
            for func_name, args in operation.items():
                commands = await self.generate_command(func_name, args)
                if commands:
                    for cmd in commands:

                        cmd = bash_var_replacement_regex(
                            cmd,
                            {
                                "pkgdir": os.path.join(
                                    self.cache_dir, "extensions", info["name"], "pkg"
                                )
                            },
                        )
                        resp = await self._subprocess.run(cmd, shell=False)
                        logger.info(resp)
                else:
                    logger.error(
                        f"Unsupported function or invalid arguments: {func_name}"
                    )

        # commands_str = ";".join(commands)
        # print(f'pkexec bash -c "{commands_str}"')
        # await self._subprocess.run(
        #     f'pkexec bash -c "{commands_str}"',
        #     env={
        #         "pkgdir": os.path.join(
        #             self.cache_dir, "extensions", info["name"], "pkg"
        #         )
        #     },
        # )

    async def get_apk_path(self, apks: list[str]) -> str:
        paths: list[str] = []
        data_dir = os.path.join(GLib.get_user_data_dir(), "waydroid/data")
        package_path = os.path.join(data_dir, "system/packages.xml")
        async with aiofiles.open(package_path, "rb") as f:
            header = await f.read(4)
            if header == b"ABX\0":
                content = AbxReader(package_path).to_xml_string()
            else:
                await f.seek(0)
                content = await f.read()

        tree = ET.fromstring(content)
        for package in tree.findall("package"):
            name = package.get("name")
            code_path = package.get("codePath", "")
            if name in apks:
                paths.append(f"app/{os.path.basename(os.path.dirname(code_path))}")
                apks.remove(name)
                if len(apks) == 0:
                    break
        paths = ['"' + path + '"' for path in paths]
        return " ".join(paths)

    async def generate_command(self, func_name: str, args: Any):
        command_map = {
            "rm_overlay_rw": "pkexec {cli_path} rm_overlay_rw {paths}",
            "rm_data": "pkexec {cli_path} rm_data {paths}",
            "cp_to_data": 'pkexec {cli_path} cp_to_data "{src}" "{dest}"',
            "rm_apk": "pkexec {cli_path} rm_apk {apks}",
        }

        if func_name in command_map:
            if func_name == "cp_to_data":
                src = args.get("src")
                dest = args.get("dest")
                if src and dest:
                    return [
                        command_map[func_name].format(
                            cli_path=os.environ["WAYDROID_CLI_PATH"], src=src, dest=dest
                        )
                    ]
            elif func_name == "rm_apk":
                apks = " ".join(['"' + apk + '"' for apk in args])

                async def wait_for_running():
                    while True:
                        await self.waydroid.refresh_persist_prop("boot_completed")
                        if (
                            self.waydroid.state == WaydroidState.RUNNING
                            and self.waydroid.persist_props.get_property(
                                "boot_completed"
                            )
                        ):
                            return
                        await asyncio.sleep(0.5)
                if self.waydroid.state == WaydroidState.STOPPED:
                    self._task.create_task(self.waydroid.start_session())
                try:
                    await asyncio.wait_for(wait_for_running(), timeout=30)
                except asyncio.TimeoutError:
                    logger.error("Timeout waiting for waydroid to start")

                commands = [
                    command_map[func_name].format(
                        cli_path=os.environ["WAYDROID_CLI_PATH"], apks=apks
                    )
                ]
                paths = await self.get_apk_path(args)
                if paths.strip() != "":
                    commands.insert(
                        0,
                        command_map["rm_data"].format(
                            cli_path=os.environ["WAYDROID_CLI_PATH"], paths=paths
                        ),
                    )
                return commands

            else:
                paths = " ".join(['"' + path + '"' for path in args])
                return [
                    command_map[func_name].format(
                        cli_path=os.environ["WAYDROID_CLI_PATH"], paths=paths
                    )
                ]

        return None

    async def pre_install(self, info: PackageInfo):
        await self.execute_post_operations(info, "pre_install")

    async def post_install(self, info: PackageInfo):
        await self.execute_post_operations(info, "post_install")

    async def post_remove(self, info: PackageInfo):
        await self.execute_post_operations(info, "post_remove")

    async def remove_package(self, package_name: str):
        """移除包"""
        async with self._package_lock:
            if package_name in self.installed_packages:
                should_start_session = self.waydroid.state == WaydroidState.RUNNING
                version = self.installed_packages[package_name]["version"]
                self.emit("uninstallation-started", package_name, version)
                await self._subprocess.run(
                    f'pkexec {os.environ["WAYDROID_CLI_PATH"]} rm_overlay {" ".join(self.installed_packages[package_name]["installed_files"])}',
                    shell=False,
                )
                # await self._subprocess.run(
                #     f"pkexec waydroid-cli rm {os.path.join(self.storage_dir, 'local', package_name)}"
                # )
                if "props" in self.installed_packages[package_name].keys():
                    success = await self.waydroid.remove_extension_props(
                        self.installed_packages[package_name]["props"]
                    )
                    if success:
                        _ = await self.waydroid.upgrade(offline=True)
                if "install" in self.installed_packages[package_name].keys():
                    await self.post_remove(self.installed_packages[package_name])
                await self._subprocess.run(
                    f"rm -rf {os.path.join(self.storage_dir, 'local', package_name)}",
                    shell=False,
                )
                # await asyncio.gather(coro1, coro2, coro3)

                del self.installed_packages[package_name]
                logger.info(f"Package {package_name} removed successfully.")
                await self.waydroid.stop_session()
                if should_start_session:
                    await self.waydroid.start_session()
                self.emit("uninstallation-completed", package_name, version)
            else:
                logger.warning(f"Package {package_name} is not installed.")

    async def remove_packages(self, package_names: Iterable[str]):
        for pkg in package_names:
            logger.info(f"remove {pkg}")
            await self.remove_package(pkg)
