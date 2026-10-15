"""Génère easyghost/icons/AppIcon.icns : un fantôme dont les branches forment une carte mentale.

    .venv/bin/python tools/make_icon.py [sortie.icns]

Dessin 100 % original, tracé avec Qt ; la palette est modifiable ci-dessous. Nécessite
macOS (`iconutil`) pour assembler le fichier .icns.
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QGuiApplication,
    QImage,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)

# --- palette : violet / indigo ------------------------------------------------
BG_TOP, BG_BOTTOM = "#FAF8FF", "#E2D9FF"       # fond de la tuile (clair)
GHOST_TOP, GHOST_BOTTOM = "#7357FF", "#3E2BC2"  # corps du fantôme (violet profond)
BRANCH = "#C4B8FF"                              # branches et nœuds (lavande)
BRANCH_EDGE = "#9A88F5"
EYE_WHITE = "#FFFFFF"
EYE_DARK = "#241A6E"

SIZE = 1024
TILE = QRectF(100, 100, 824, 824)   # gabarit des icônes macOS : marge de 100 px
RADIUS = 186


def _tile_path() -> QPainterPath:
    path = QPainterPath()
    path.addRoundedRect(TILE, RADIUS, RADIUS)
    return path


def _ghost_path() -> QPainterPath:
    left, right, top, hem = 332.0, 692.0, 250.0, 700.0
    width = right - left
    radius = width / 2
    bump = width / 3
    path = QPainterPath(QPointF(left, top + radius))
    path.arcTo(QRectF(left, top, width, width), 180, -180)     # tête arrondie
    path.lineTo(right, hem)
    for i in range(3):                                          # trois ondulations en bas
        path.arcTo(QRectF(right - bump * (i + 1), hem - bump / 2, bump, bump), 0, -180)
    path.closeSubpath()
    return path


def draw(size: int = SIZE) -> QImage:
    image = QImage(SIZE, SIZE, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image)
    p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.SmoothPixmapTransform)

    # ombre portée de la tuile
    for i in range(10):
        shadow = QPainterPath()
        shadow.addRoundedRect(TILE.translated(0, 10 + i * 2.2).adjusted(-i, -i, i, i), RADIUS + i, RADIUS + i)
        p.fillPath(shadow, QColor(40, 20, 120, 9))

    # tuile
    bg = QLinearGradient(0, TILE.top(), 0, TILE.bottom())
    bg.setColorAt(0, QColor(BG_TOP))
    bg.setColorAt(1, QColor(BG_BOTTOM))
    p.fillPath(_tile_path(), bg)
    p.setClipPath(_tile_path())

    # branches de la carte mentale (derrière le fantôme)
    pen = QPen(QColor(BRANCH), 30, Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap)
    nodes = [  # (départ sur le fantôme, point de contrôle, centre du nœud, rayon)
        (QPointF(660, 420), QPointF(760, 400), QPointF(790, 318), 46),
        (QPointF(690, 560), QPointF(770, 580), QPointF(800, 640), 36),
        (QPointF(364, 580), QPointF(280, 600), QPointF(238, 540), 40),
        (QPointF(380, 430), QPointF(300, 380), QPointF(268, 312), 26),
    ]
    for start, control, center, _r in nodes:
        branch = QPainterPath(start)
        branch.quadTo(control, center)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawPath(branch)
    for _s, _c, center, r in nodes:
        p.setPen(QPen(QColor(BRANCH_EDGE), 12))
        p.setBrush(QColor(BRANCH))
        p.drawEllipse(center, r, r)

    # fantôme
    ghost = _ghost_path()
    body = QLinearGradient(0, 250, 0, 750)
    body.setColorAt(0, QColor(GHOST_TOP))
    body.setColorAt(1, QColor(GHOST_BOTTOM))
    p.setPen(Qt.PenStyle.NoPen)
    p.fillPath(ghost, body)
    p.save()
    p.setClipPath(ghost)
    shine = QRadialGradient(QPointF(440, 330), 230)             # reflet doux en haut à gauche
    shine.setColorAt(0, QColor(255, 255, 255, 85))
    shine.setColorAt(1, QColor(255, 255, 255, 0))
    p.fillRect(QRectF(300, 230, 420, 420), shine)
    p.restore()

    # yeux et bouche
    for cx in (452, 572):
        p.setBrush(QColor(EYE_WHITE))
        p.drawEllipse(QPointF(cx, 470), 40, 54)
        p.setBrush(QColor(EYE_DARK))
        p.drawEllipse(QPointF(cx + 9, 482), 21, 27)
    p.setBrush(QColor(EYE_DARK))
    p.drawEllipse(QPointF(512, 580), 28, 34)
    p.end()

    return image if size == SIZE else image.scaled(
        size, size, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation
    )


ICONSET = [  # (nom de fichier, taille en pixels)
    ("icon_16x16.png", 16), ("icon_16x16@2x.png", 32),
    ("icon_32x32.png", 32), ("icon_32x32@2x.png", 64),
    ("icon_128x128.png", 128), ("icon_128x128@2x.png", 256),
    ("icon_256x256.png", 256), ("icon_256x256@2x.png", 512),
    ("icon_512x512.png", 512), ("icon_512x512@2x.png", 1024),
]


def build(output: Path, keep_png: Path | None = None) -> None:
    master = draw()
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "AppIcon.iconset"
        iconset.mkdir()
        for name, px in ICONSET:
            image = master if px == SIZE else master.scaled(
                px, px, Qt.AspectRatioMode.IgnoreAspectRatio, Qt.TransformationMode.SmoothTransformation
            )
            if not image.save(str(iconset / name), "PNG"):
                raise OSError(f"écriture impossible : {name}")
        subprocess.run(["iconutil", "-c", "icns", str(iconset), "-o", str(output)], check=True)
    if keep_png:
        master.save(str(keep_png), "PNG")


if __name__ == "__main__":
    app = QGuiApplication([])
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "easyghost" / "icons" / "AppIcon.icns"
    build(target)
    print(f"écrit : {target} ({target.stat().st_size} octets)")
