"""Export de la carte en image : PNG, SVG, PDF (rendu de la scène, sans sélection)."""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import QMarginsF, QPointF, QRectF, QSize, QSizeF
from PySide6.QtGui import QColor, QImage, QPageSize, QPainter, QPdfWriter
from PySide6.QtSvg import QSvgGenerator

MARGIN = 30.0
MAX_PIXELS = 100_000_000  # ~400 Mo en ARGB32 : au-delà on réduit l'échelle
MAX_PDF_POINTS = 14_000.0  # limite pratique d'une page PDF (≈ 200 pouces)
BACKGROUND = QColor("white")


class _Prepared:
    """Fige la scène (animation terminée, rien de sélectionné) puis la restaure."""

    def __init__(self, scene) -> None:
        self.scene = scene

    def __enter__(self) -> QRectF:
        scene = self.scene
        self._selected = [it for it in scene.selectedItems()]
        scene.clearSelection()
        self._animated = scene.animated
        scene.animated = False
        scene.relayout(animate=False)  # positions finales, sans animation en cours
        rect = scene.itemsBoundingRect().adjusted(-MARGIN, -MARGIN, MARGIN, MARGIN)
        if rect.isEmpty():
            raise ValueError("la carte est vide")
        return rect

    def __exit__(self, *exc) -> None:
        self.scene.animated = self._animated
        for it in self._selected:
            it.setSelected(True)


def _paint(scene, painter: QPainter, target: QRectF, source: QRectF) -> None:
    painter.setRenderHints(
        QPainter.RenderHint.Antialiasing
        | QPainter.RenderHint.TextAntialiasing
        | QPainter.RenderHint.SmoothPixmapTransform
    )
    painter.fillRect(target, BACKGROUND)
    scene.render(painter, target, source)


def export_png(scene, path: str | Path, scale: float = 2.0) -> None:
    with _Prepared(scene) as source:
        w, h = source.width() * scale, source.height() * scale
        if w * h > MAX_PIXELS:
            shrink = (MAX_PIXELS / (w * h)) ** 0.5
            w, h = w * shrink, h * shrink
        size = QSize(max(1, round(w)), max(1, round(h)))
        image = QImage(size, QImage.Format.Format_ARGB32)
        if image.isNull():
            raise OSError("image trop grande pour la mémoire disponible")
        painter = QPainter(image)
        try:
            _paint(scene, painter, QRectF(QPointF(0, 0), QSizeF(size)), source)
        finally:
            painter.end()
        if not image.save(str(path), "PNG"):
            raise OSError(f"impossible d'écrire {path}")


def export_svg(scene, path: str | Path, title: str = "") -> None:
    with _Prepared(scene) as source:
        size = QSize(round(source.width()), round(source.height()))
        generator = QSvgGenerator()
        generator.setFileName(str(path))
        generator.setSize(size)
        generator.setViewBox(QRectF(0, 0, size.width(), size.height()))
        generator.setTitle(title or "Carte mentale")
        painter = QPainter(generator)
        try:
            _paint(scene, painter, QRectF(0, 0, size.width(), size.height()), source)
        finally:
            painter.end()
    _fix_svg(Path(path), size)


_FONT_STACK = "Helvetica Neue, Helvetica, Arial, sans-serif"


def _fix_svg(path: Path, size: QSize) -> None:
    """Rend le SVG portable : taille en pixels (Qt l'écrit en mm) et police générique
    (Qt écrit le nom de la police système, ex. « Sans Serif », inconnu des navigateurs)."""
    text = path.read_text(encoding="utf-8")
    text = re.sub(r'font-family="[^"]*"', f'font-family="{_FONT_STACK}"', text)
    text = re.sub(
        r'(<svg\s[^>]*?)width="[^"]*"\s+height="[^"]*"',
        rf'\1width="{size.width()}" height="{size.height()}"',
        text,
        count=1,
    )
    path.write_text(text, encoding="utf-8")


def export_pdf(scene, path: str | Path, title: str = "") -> None:
    with _Prepared(scene) as source:
        shrink = min(1.0, MAX_PDF_POINTS / max(source.width(), source.height()))
        w, h = source.width() * shrink, source.height() * shrink
        writer = QPdfWriter(str(path))
        writer.setResolution(72)  # 1 unité de dessin = 1 point
        writer.setPageSize(QPageSize(QSizeF(w, h), QPageSize.Unit.Point))
        writer.setPageMargins(QMarginsF(0, 0, 0, 0))
        writer.setTitle(title or "Carte mentale")
        painter = QPainter(writer)
        try:
            _paint(scene, painter, QRectF(0, 0, w, h), source)
        finally:
            painter.end()


IMAGE_FORMATS = {
    "png": ("PNG", ".png", export_png),
    "svg": ("SVG", ".svg", export_svg),
    "pdf": ("PDF", ".pdf", export_pdf),
}
