# -*- mode: python ; coding: utf-8 -*-
"""Description PyInstaller de EasyGhost.app (macOS).  Voir tools/build_macos.sh."""

import tomllib
from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

ROOT = Path(SPECPATH).parent
VERSION = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
ICON = ROOT / "easyghost" / "icons" / "AppIcon.icns"

# Modules Qt / Python inutiles à EasyGhost : les exclure garde l'application légère.
EXCLUDES = [
    "tkinter", "pytest",
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "PySide6.QtWebEngineQuick",
    "PySide6.QtWebChannel", "PySide6.QtWebSockets", "PySide6.QtWebView",
    "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtQuickWidgets", "PySide6.QtQuick3D",
    "PySide6.QtQuickControls2", "PySide6.Qt3DCore", "PySide6.Qt3DRender", "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic", "PySide6.Qt3DAnimation", "PySide6.Qt3DExtras",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtBluetooth", "PySide6.QtNfc",
    "PySide6.QtSql", "PySide6.QtNetwork", "PySide6.QtPositioning", "PySide6.QtLocation",
    "PySide6.QtCharts", "PySide6.QtDataVisualization", "PySide6.QtGraphs", "PySide6.QtSensors",
    "PySide6.QtSerialPort", "PySide6.QtSerialBus", "PySide6.QtTest", "PySide6.QtDesigner",
    "PySide6.QtHelp", "PySide6.QtPdfWidgets", "PySide6.QtRemoteObjects", "PySide6.QtScxml",
    "PySide6.QtTextToSpeech", "PySide6.QtSpatialAudio", "PySide6.QtStateMachine",
    "PySide6.QtHttpServer", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtConcurrent",
]

a = Analysis(
    [str(ROOT / "packaging" / "launcher.py")],
    pathex=[str(ROOT)],
    datas=[(str(ROOT / "easyghost" / "icons"), "easyghost/icons")],   # SVG, licence et icône
    hiddenimports=collect_submodules("easyghost"),                     # formats importés à la demande
    excludes=EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="EasyGhost",
    console=False,           # application graphique : pas de fenêtre de terminal
    icon=str(ICON),
)
coll = COLLECT(exe, a.binaries, a.datas, name="EasyGhost")

app = BUNDLE(
    coll,
    name="EasyGhost.app",
    icon=str(ICON),
    bundle_identifier="com.easyghost.app",
    version=VERSION,
    info_plist={
        "CFBundleName": "EasyGhost",
        "CFBundleDisplayName": "EasyGhost",
        "CFBundleShortVersionString": VERSION,
        "LSMinimumSystemVersion": "11.0",
        "NSHighResolutionCapable": True,
        "NSHumanReadableCopyright": "EasyGhost",
        "CFBundleDocumentTypes": [
            {   # le format natif : EasyGhost est l'application par défaut
                "CFBundleTypeName": "Carte EasyGhost",
                "CFBundleTypeExtensions": ["easyghost"],
                "CFBundleTypeRole": "Editor",
                "LSHandlerRank": "Owner",
            },
            {   # formats importés : EasyGhost peut les ouvrir sans prendre la place des autres applications
                "CFBundleTypeName": "Carte SimpleMind",
                "CFBundleTypeExtensions": ["smmx"],
                "CFBundleTypeRole": "Viewer",
                "LSHandlerRank": "Alternate",
            },
            {
                "CFBundleTypeName": "Carte FreeMind",
                "CFBundleTypeExtensions": ["mm"],
                "CFBundleTypeRole": "Viewer",
                "LSHandlerRank": "Alternate",
            },
        ],
    },
)
