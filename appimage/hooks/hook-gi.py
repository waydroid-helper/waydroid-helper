from PyInstaller.utils.hooks.gi import GiModuleInfo

binaries, datas, hiddenimports = [], [], []
for name, version in (("Vte", "3.91"), ("Shumate", "1.0")):
    module_info = GiModuleInfo(name, version)
    if module_info.available:
        libraries, files, imports = module_info.collect_typelib_data()
        binaries.extend(libraries)
        datas.extend(files)
        hiddenimports.extend(imports)
