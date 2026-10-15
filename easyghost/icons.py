"""Rendu des icônes : SVG Lucide (intégrés à EasyGhost) et emoji de secours."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication

from .iconset import ICON_TABLE
from .model import FALLBACK_ICON, ICONS

ICON_DIR = Path(__file__).parent / "icons"
APP_ICON_PATH = ICON_DIR / "AppIcon.icns"   # icône de l'application (Dock, fenêtre, bundle macOS)
_NODE_FILES = {key: svg for key, svg, *_ in ICON_TABLE}



# --------------------------------------------------------------------- SVG
@lru_cache(maxsize=None)
def _svg_text(kind: str, name: str) -> str | None:
    path = ICON_DIR / kind / f"{name}.svg"
    return path.read_text(encoding="utf-8") if path.is_file() else None


_renderers: dict[tuple[str, str, str], QSvgRenderer | None] = {}


def svg_renderer(kind: str, name: str, color: str) -> QSvgRenderer | None:
    """Rendu vectoriel d'une icône Lucide, teintée avec `color` (« #RRGGBB »)."""
    cache_key = (kind, name, color)
    if cache_key not in _renderers:
        text = _svg_text(kind, name)
        renderer = None
        if text is not None:
            renderer = QSvgRenderer(QByteArray(text.replace("currentColor", color).encode("utf-8")))
            if not renderer.isValid():
                renderer = None
        _renderers[cache_key] = renderer
    return _renderers[cache_key]


def app_icon() -> QIcon:
    """Icône de l'application (toutes les tailles du fichier .icns) ; vide si le fichier manque."""
    return QIcon(str(APP_ICON_PATH)) if APP_ICON_PATH.is_file() else QIcon()


def ui_icon(name: str, color: QColor | None = None, size: int = 20) -> QIcon:
    """Icône d'interface (barres d'outils) ; la version grisée est générée par Qt."""
    app = QApplication.instance()
    if color is None:
        color = app.palette().color(QPalette.ColorRole.WindowText) if app else QColor("#333333")
    renderer = svg_renderer("ui", name, color.name())
    if renderer is None:
        return QIcon()
    ratio = 2  # écrans haute densité
    pix = QPixmap(QSize(size * ratio, size * ratio))
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    renderer.render(painter, QRectF(0, 0, size * ratio, size * ratio))
    painter.end()
    pix.setDevicePixelRatio(ratio)
    return QIcon(pix)


# -------------------------------------------------------------- icône d'un nœud
def paint_node_icon(p: QPainter, key: str, rect: QRectF, color: QColor) -> None:
    """Dessine l'icône `key` dans `rect` ; `color` teinte les icônes vectorielles.

    Une clé inconnue (ex. identifiant venu d'un fichier importé) s'affiche comme une étiquette générique."""
    if key in _NODE_FILES:
        renderer = svg_renderer("node", _NODE_FILES[key], color.name())
        if renderer is not None:
            renderer.render(p, rect)
            return
    font = QFont()
    font.setPixelSize(max(8, int(rect.height() * 0.85)))
    p.save()
    p.setFont(font)
    p.drawText(rect, Qt.AlignmentFlag.AlignCenter, ICONS[key][0] if key in ICONS else FALLBACK_ICON)
    p.restore()


def node_icon_pixmap(key: str, size: int, color: QColor) -> QPixmap:
    """Pastille pour les listes de sélection."""
    ratio = 2
    pix = QPixmap(QSize(size * ratio, size * ratio))
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    paint_node_icon(painter, key, QRectF(0, 0, size * ratio, size * ratio), color)
    painter.end()
    pix.setDevicePixelRatio(ratio)
    return pix
