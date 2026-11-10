# -*- mode: python ; coding: utf-8 -*-
from importlib.util import find_spec
from pathlib import Path

from PyInstaller.utils.hooks import collect_all

datas = [("frontend", "frontend"), ("backend/pyrunner.py", "backend")]
binaries = []
hiddenimports = [path.stem for path in Path("backend").glob("*.py") if path.stem != "__init__"]
for package in ("pandas", "numpy", "duckdb", "openpyxl", "PIL", "fastapi", "uvicorn", "multipart", "dotenv", "google.genai", "anthropic"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas += package_datas
    binaries += package_binaries
    hiddenimports += package_hidden
for package in ("matplotlib", "sklearn"):
    if find_spec(package):
        package_datas, package_binaries, package_hidden = collect_all(package)
        datas += package_datas
        binaries += package_binaries
        hiddenimports += package_hidden

a = Analysis(
    ["desktop_launcher.py"],
    pathex=["backend"],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "tests"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="DataFlowAI",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
