# PyInstaller onedir runtime shipped alongside the Tauri host.
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = collect_submodules("cether")

a = Analysis(
    ["src/cether/__main__.py"],
    pathex=["src"],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "playwright"],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="cether-python", console=True)
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name="python-runtime")
