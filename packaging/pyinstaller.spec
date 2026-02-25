# -*- mode: python ; coding: utf-8 -*-

import os
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

BINARY_NAME = "EscaladaServer"

# NOTE: PyInstaller does not guarantee `__file__` is set when executing the spec.
# Use an explicit env var (set by build scripts) and fall back to current working directory.
API_DIR = Path(os.environ.get("ESCALADA_API_DIR", os.getcwd())).resolve()
MODE = os.environ.get("ESCALADA_PYI_MODE", "onedir").strip().lower()
ONEFILE = MODE == "onefile"

if not (API_DIR / "escalada").exists():
    raise SystemExit(f"ESCALADA_API_DIR does not look like escalada-api: {API_DIR}")

frontend_index = API_DIR / "frontend_dist" / "index.html"
if not frontend_index.exists():
    raise SystemExit(f"Missing frontend bundle: {frontend_index}")

datas = []
for src, dest in [
    (API_DIR / "frontend_dist", "frontend_dist"),
    (API_DIR / "escalada" / "resources", "escalada/resources"),
    (API_DIR / "DejaVuSans.ttf", "."),
    (API_DIR / "escalada" / "FreeSans.ttf", "escalada"),
]:
    if src.exists():
        datas.append((str(src), dest))

hiddenimports = [
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
]
hiddenimports += collect_submodules("escalada")

a = Analysis(
    [str(API_DIR / "escalada" / "launcher.py")],
    pathex=[str(API_DIR)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)

pyz = PYZ(a.pure)

if ONEFILE:
    exe = EXE(
        pyz,
        a.scripts,
        a.binaries,
        a.zipfiles,
        a.datas,
        [],
        name=BINARY_NAME,
        debug=False,
        strip=False,
        upx=True,
        console=True,
    )
else:
    exe = EXE(
        pyz,
        a.scripts,
        [],
        exclude_binaries=True,
        name=BINARY_NAME,
        debug=False,
        strip=False,
        upx=True,
        console=True,
    )

    coll = COLLECT(
        exe,
        a.binaries,
        a.zipfiles,
        a.datas,
        strip=False,
        upx=True,
        name=BINARY_NAME,
    )
