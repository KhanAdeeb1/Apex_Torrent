# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for ApexTorrent.  Build with:  python -m PyInstaller --noconfirm --clean apextorrent.spec
#
# One-directory build on purpose:
#   * starts much faster than --onefile (no unpacking to %TEMP% on every launch)
#   * triggers fewer antivirus false positives than a self-extracting onefile exe
#   * keeps the Qt/PySide6 DLLs as separate files, which is what the LGPL asks of you
import os
import sys
from pathlib import Path

ROOT = Path(SPECPATH)
sys.path.insert(0, str(ROOT))
import version as V  # noqa: E402

IS_WIN = sys.platform == "win32"


# --------------------------------------------------------------------------- libtorrent
def libtorrent_binaries():
    """libtorrent ships as one extension module plus (on Windows wheels) OpenSSL/runtime DLLs sitting next to it
    or in a 'libtorrent*.libs' folder. PyInstaller finds most of them by dependency scanning; this collects the
    rest explicitly so a missing DLL can never be the reason the installed app fails to start."""
    import libtorrent

    found = {}
    mod = Path(libtorrent.__file__).resolve()
    site = mod.parent
    dirs = []
    if mod.name == "__init__.py":                       # package layout
        dirs.append(site)
    else:                                               # single extension module in site-packages
        for d in site.iterdir():
            n = d.name.lower()
            if d.is_dir() and n.startswith("libtorrent") and not n.endswith((".dist-info", ".egg-info")):
                dirs.append(d)
    for d in dirs:
        for f in d.rglob("*"):
            if f.is_file() and (f.suffix.lower() in (".dll", ".pyd", ".so", ".dylib") or ".so." in f.name):
                found[f.name.lower()] = (str(f), ".")
    if IS_WIN:                                          # runtime DLLs dropped in the site-packages root
        for f in site.glob("*.dll"):
            if f.name.lower().startswith(("libssl", "libcrypto", "boost", "zlib", "vcruntime", "msvcp", "concrt")):
                found.setdefault(f.name.lower(), (str(f), "."))
    try:
        from PyInstaller.utils.hooks import collect_dynamic_libs
        for src, dest in collect_dynamic_libs("libtorrent"):
            found.setdefault(Path(src).name.lower(), (src, dest))
    except Exception:
        pass
    return list(found.values())


# --------------------------------------------------------------------------- version resource (Windows)
def write_version_file():
    from PyInstaller.utils.win32.versioninfo import (
        FixedFileInfo, StringFileInfo, StringStruct, StringTable, VarFileInfo, VarStruct, VSVersionInfo)
    nums = [int(x) for x in V.APP_VERSION.split(".")][:3]
    vt = tuple(nums + [0] * (4 - len(nums)))
    vi = VSVersionInfo(
        ffi=FixedFileInfo(filevers=vt, prodvers=vt, mask=0x3F, flags=0x0, OS=0x40004, fileType=0x1,
                          subtype=0x0, date=(0, 0)),
        kids=[
            StringFileInfo([StringTable("040904B0", [
                StringStruct("CompanyName", V.PUBLISHER),
                StringStruct("FileDescription", V.DESCRIPTION),
                StringStruct("FileVersion", V.APP_VERSION),
                StringStruct("InternalName", V.APP_NAME),
                StringStruct("LegalCopyright", V.COPYRIGHT),
                StringStruct("OriginalFilename", V.APP_NAME + ".exe"),
                StringStruct("ProductName", V.APP_NAME),
                StringStruct("ProductVersion", V.APP_VERSION),
            ])]),
            VarFileInfo([VarStruct("Translation", [1033, 1200])]),
        ],
    )
    out = ROOT / "build" / "version_info.txt"
    out.parent.mkdir(exist_ok=True)
    out.write_text(str(vi), encoding="utf-8")
    return str(out)


version_file = write_version_file() if IS_WIN else None
icon_file = str(ROOT / "assets" / "apextorrent.ico") if IS_WIN else None
if IS_WIN and not Path(icon_file).exists():
    raise SystemExit("assets/apextorrent.ico missing: run  python build_assets.py  first")

# --------------------------------------------------------------------------- analysis
a = Analysis(
    [str(ROOT / "app.py")],
    pathex=[str(ROOT)],
    binaries=libtorrent_binaries(),
    datas=[
        (str(ROOT / "assets" / "apextorrent.ico"), "assets"),
        (str(ROOT / "assets" / "apextorrent.png"), "assets"),
        (str(ROOT / "assets" / "torrent.ico"), "assets"),
        (str(ROOT / "LICENSE.txt"), "."),
        (str(ROOT / "THIRD_PARTY_NOTICES.txt"), "."),
    ],
    hiddenimports=["libtorrent", "psutil", "PySide6.QtSvg", "PySide6.QtNetwork"],
    excludes=[
        "tkinter", "matplotlib", "numpy", "PIL", "pytest", "IPython",
        "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
        "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.Qt3DCore", "PySide6.QtMultimedia",
        "PySide6.QtPdf", "PySide6.QtPdfWidgets", "PySide6.QtCharts", "PySide6.QtDataVisualization",
        "PySide6.QtSql", "PySide6.QtTest", "PySide6.QtBluetooth", "PySide6.QtSensors", "PySide6.QtPositioning",
    ],
    noarchive=False,
)

# Fail the build loudly instead of shipping an installer that cannot start.
_names = [str(t[0]).replace("\\", "/").lower() for t in a.binaries]
_qt_platform = {"win32": "qwindows", "linux": "libqxcb", "darwin": "libqcocoa"}.get(sys.platform, "")
if not any("libtorrent" in n for n in _names):
    raise SystemExit("BUILD CHECK FAILED: libtorrent extension module was not collected")
if _qt_platform and not any(_qt_platform in n for n in _names):
    raise SystemExit(f"BUILD CHECK FAILED: Qt platform plugin '{_qt_platform}' was not collected")
for _need in ("qsvg", "qico"):
    if not any(_need in n for n in _names):
        print(f"BUILD WARNING: Qt plugin '{_need}' not collected (SVG/ICO image support)")

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name=V.APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,              # UPX corrupts Qt DLLs and raises antivirus false positives
    console=False,          # windowed: no command prompt when the app starts
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
    version=version_file,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    name=V.APP_NAME,
)
