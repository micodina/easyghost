"""Vue : zoom, panoramique, ajustement."""

from __future__ import annotations

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QFrame, QGraphicsView

MIN_ZOOM, MAX_ZOOM = 0.15, 4.0


class MapView(QGraphicsView):
    zoom_changed = Signal(float)   # facteur de zoom (1.0 = 100 %)

    def __init__(self, scene) -> None:
        super().__init__(scene)
        self.setRenderHints(
            QPainter.RenderHint.Antialiasing
            | QPainter.RenderHint.TextAntialiasing
            | QPainter.RenderHint.SmoothPixmapTransform
        )
        self.setDragMode(QGraphicsView.DragMode.ScrollHandDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setBackgroundBrush(QColor("#F7F7F5"))
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.centerOn(0, 0)

    def focusNextPrevChild(self, next_: bool) -> bool:
        return False  # Tab est réservé à « nouvel enfant »

    @property
    def zoom(self) -> float:
        return self.transform().m11()

    def set_zoom(self, factor: float) -> None:
        """Zoom absolu (1.0 = 100 %), borné ; le point sous le curseur / le centre reste fixe."""
        target = min(max(factor, MIN_ZOOM), MAX_ZOOM)
        if abs(target - self.zoom) > 1e-9:
            ratio = target / self.zoom
            self.scale(ratio, ratio)
        self.zoom_changed.emit(self.zoom)

    def zoom_by(self, factor: float) -> None:
        self.set_zoom(self.zoom * factor)

    def reset_zoom(self) -> None:
        self.resetTransform()
        node = self.scene().selected_item()
        self.centerOn(node if node else self.scene().item_for(self.scene().mindmap.root))
        self.zoom_changed.emit(self.zoom)

    def center_on_root(self) -> None:
        """Recentre l'affichage sur le nœud principal (le zoom est conservé)."""
        root = self.scene().item_for(self.scene().mindmap.root)
        if root is not None:
            self.centerOn(root)

    def fit_all(self) -> None:
        rect = self.scene().itemsBoundingRect().adjusted(-50, -50, 50, 50)
        self.fitInView(rect, Qt.AspectRatioMode.KeepAspectRatio)
        if self.zoom > 1.5:
            self.set_zoom(1.5)
            self.centerOn(rect.center())
        self.zoom_changed.emit(self.zoom)

    def wheelEvent(self, event) -> None:
        if event.modifiers() & Qt.KeyboardModifier.ControlModifier:
            self.zoom_by(1.0015 ** event.angleDelta().y())
            event.accept()
        else:
            super().wheelEvent(event)

    def viewportEvent(self, event) -> bool:
        if (
            event.type() == QEvent.Type.NativeGesture
            and event.gestureType() == Qt.NativeGestureType.ZoomNativeGesture
        ):
            self.zoom_by(1.0 + event.value())
            return True
        return super().viewportEvent(event)
