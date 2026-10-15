"""Scène graphique : nœuds, liens, édition en place, glisser-déposer."""

from __future__ import annotations

import math
from dataclasses import dataclass

from PySide6.QtCore import (
    QEasingCurve,
    QEvent,
    QParallelAnimationGroup,
    QPointF,
    QPropertyAnimation,
    QRectF,
    Qt,
    Signal,
)
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QFontMetricsF,
    QPainter,
    QPainterPath,
    QPen,
    QTextOption,
    QUndoStack,
)
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsItem,
    QGraphicsObject,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsTextItem,
)

from . import clipboard, commands
from .icons import paint_node_icon, svg_renderer
from .layout import compute_layout, root_split, visible_children
from .model import BRANCH_PALETTE, ICONS, MindMap, Node, normalize_text

PALETTE = BRANCH_PALETTE
ROOT_COLOR = QColor("#2F3E56")
SELECT_COLOR = QColor("#1A73E8")
DROP_COLOR = QColor("#FF8A00")
PAD_X, PAD_Y = 14.0, 8.0
MIN_W = 56.0
PLACEHOLDER = "Nouveau nœud"
ICON_PX = 18.0     # taille de l'icône du nœud
BADGE_PX = 14.0    # taille des pastilles note / lien
GLYPH_GAP = 6.0
DEFAULT_FONT_SIZES = {0: 17, 1: 14}   # en pixels, par profondeur ; 13 au-delà
DEFAULT_BORDER_WIDTH = 2.0
PEN_STYLES = {
    "solid": Qt.PenStyle.SolidLine,
    "dashed": Qt.PenStyle.DashLine,
    "dotted": Qt.PenStyle.DotLine,
}
ALIGN_FLAGS = {
    "left": Qt.AlignmentFlag.AlignLeft,
    "center": Qt.AlignmentFlag.AlignHCenter,
    "right": Qt.AlignmentFlag.AlignRight,
}


def depth_of(node: Node) -> int:
    d = 0
    while node.parent is not None:
        node = node.parent
        d += 1
    return d


def branch_color(node: Node) -> QColor:
    """Couleur de branche : personnalisée (héritée des ancêtres hors racine) ou palette."""
    n = node
    while n.parent is not None:
        if n.style.color:
            return QColor(n.style.color)
        n = n.parent
    if node.parent is None:
        return QColor(node.style.color) if node.style.color else ROOT_COLOR
    top = node
    while top.parent.parent is not None:
        top = top.parent
    return QColor(PALETTE[top.index % len(PALETTE)])


def text_color_on(fill: QColor) -> QColor:
    """Noir ou blanc selon la luminosité du fond."""
    luma = fill.red() * 0.299 + fill.green() * 0.587 + fill.blue() * 0.114
    return QColor("#222222") if luma > 186 else QColor("white")


@dataclass
class ResolvedStyle:
    """Style effectif d'un nœud : valeurs personnalisées, sinon valeurs par défaut."""

    fill: QColor | None
    border: QColor
    text: QColor
    link: QColor
    shape: str
    border_pen: Qt.PenStyle
    border_width: float
    link_pen: Qt.PenStyle
    link_width: float
    font: QFont
    align: str
    wrap: int  # 0 = pas de retour à la ligne automatique


def default_font_size(node: Node) -> int:
    return DEFAULT_FONT_SIZES.get(depth_of(node), 13)


def resolve_style(node: Node) -> ResolvedStyle:
    st = node.style
    depth = depth_of(node)
    branch = branch_color(node)
    shape = st.shape or "rounded"
    if st.fill == "none":
        fill = None
    elif st.fill:
        fill = QColor(st.fill)
    elif depth <= 1 and shape != "none":
        fill = branch
    elif depth <= 1:
        fill = None
    else:
        fill = QColor("#FFFFFF") if shape != "none" else None
    if st.text_color:
        text = QColor(st.text_color)
    elif fill is not None:
        text = text_color_on(fill)
    else:
        text = QColor("#222222")
    font = QFont()
    if st.font_family:
        font.setFamily(st.font_family)
    font.setPixelSize(st.font_size or default_font_size(node))
    font.setBold(depth <= 1 if st.bold is None else st.bold)
    font.setItalic(bool(st.italic))
    font.setUnderline(bool(st.underline))
    font.setStrikeOut(bool(st.strike))
    return ResolvedStyle(
        fill=fill,
        border=QColor(st.border_color) if st.border_color else branch,
        text=text,
        link=branch,
        shape=shape,
        border_pen=PEN_STYLES[st.border_style or "solid"],
        border_width=st.border_width or DEFAULT_BORDER_WIDTH,
        link_pen=PEN_STYLES[st.link_style or "solid"],
        link_width=st.link_width or (3.0 if depth == 1 else 2.0),
        font=font,
        align=st.align or "center",
        wrap=st.wrap_width or 0,
    )


def measure_text(text: str, font: QFont, align: str, wrap: int) -> tuple[float, float]:
    """Taille du bloc de texte (multiligne, avec retour à la ligne si `wrap`)."""
    fm = QFontMetricsF(font)
    flags = int(ALIGN_FLAGS[align] | Qt.AlignmentFlag.AlignVCenter)
    if wrap:
        flags |= int(Qt.TextFlag.TextWordWrap)
        box = QRectF(0, 0, wrap, 100000)
    else:
        box = QRectF(0, 0, 100000, 100000)
    rect = fm.boundingRect(box, flags, text)
    return math.ceil(rect.width()), math.ceil(max(rect.height(), fm.height()))


class _Editor(QGraphicsTextItem):
    finished = Signal(bool)

    def __init__(self, parent: QGraphicsItem) -> None:
        super().__init__(parent)
        self.document().setDocumentMargin(0)
        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self._done = False

    def begin(self) -> None:
        self._done = False

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            if event.modifiers() & (Qt.KeyboardModifier.ShiftModifier | Qt.KeyboardModifier.AltModifier):
                self.textCursor().insertBlock()   # Maj+Entrée : retour à la ligne dans le nœud
            else:
                self._finish(True)
        elif event.key() == Qt.Key.Key_Escape:
            self._finish(False)
        else:
            super().keyPressEvent(event)

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self._finish(True)

    def _finish(self, accepted: bool) -> None:
        if self._done:
            return
        self._done = True
        self.finished.emit(accepted)


class NodeItem(QGraphicsObject):
    def __init__(self, scene: "MapScene", node: Node) -> None:
        super().__init__()
        self.map_scene = scene
        self.node = node
        self.side = 0
        self.drop_target = False
        self._w, self._h = MIN_W, 30.0
        self._hit: dict[str, QRectF] = {}
        self._icon_rect: QRectF | None = None
        self._text_rect = QRectF()
        self._badges: list[tuple[str, QRectF]] = []
        self._press: QPointF | None = None
        self._dragging = False
        self._drag_group: list[tuple[NodeItem, QPointF]] = []
        self.setFlags(
            QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
            | QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges
        )
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.editor = _Editor(self)
        self.editor.setVisible(False)
        self.editor.finished.connect(lambda ok: self.map_scene.edit_finished(self, ok))
        self.editor.document().contentsChanged.connect(self._on_editor_changed)
        self.refresh()

    # --- Apparence -----------------------------------------------------
    @property
    def editing(self) -> bool:
        return self.editor.isVisible()

    def display_text(self) -> str:
        return self.editor.toPlainText() if self.editing else self.node.text

    def size(self) -> tuple[float, float]:
        return self._w, self._h

    def shape_name(self) -> str:
        return self.node.style.shape or "rounded"

    def _tooltip(self) -> str:
        parts = []
        if self.node.icon:
            parts.append(ICONS[self.node.icon][1] if self.node.icon in ICONS else f"Icône : {self.node.icon}")
        if self.node.note:
            note = self.node.note
            parts.append(note if len(note) <= 600 else note[:600] + "…")
        if self.node.link:
            parts.append(f"Lien : {self.node.link}")
        return "\n".join(parts)

    def refresh(self) -> None:
        rs = resolve_style(self.node)
        text = self.display_text() or PLACEHOLDER
        tw, th = measure_text(text, rs.font, rs.align, rs.wrap)
        icon_w = ICON_PX + GLYPH_GAP if self.node.icon else 0.0
        kinds = [k for k, present in (("note", self.node.note), ("link", self.node.link)) if present]
        badges_w = len(kinds) * (BADGE_PX + GLYPH_GAP)
        content_w = icon_w + tw + badges_w
        w = max(MIN_W, content_w + 2 * PAD_X + 2)
        h = max(th, ICON_PX if self.node.icon else 0.0, BADGE_PX if kinds else 0.0) + 2 * PAD_Y
        if rs.shape == "diamond":
            w, h = w * 1.7, h * 1.7
        if (w, h) != (self._w, self._h):
            self.prepareGeometryChange()
            self._w, self._h = w, h
        x = (w - content_w) / 2
        self._icon_rect = QRectF(x, (h - ICON_PX) / 2, ICON_PX, ICON_PX) if self.node.icon else None
        x += icon_w
        self._text_rect = QRectF(x, (h - th) / 2, tw + 2, th)  # +2 : évite un retour à la ligne parasite
        x += tw + GLYPH_GAP
        self._badges, self._hit = [], {}
        for kind in kinds:
            self._badges.append((kind, QRectF(x, (h - BADGE_PX) / 2, BADGE_PX, BADGE_PX)))
            self._hit[kind] = QRectF(x - GLYPH_GAP / 2, 0, BADGE_PX + GLYPH_GAP, h)
            x += BADGE_PX + GLYPH_GAP
        self.editor.setFont(rs.font)
        self.editor.setTextWidth(rs.wrap if rs.wrap else -1)
        option = QTextOption()
        option.setAlignment(ALIGN_FLAGS[rs.align])
        self.editor.document().setDefaultTextOption(option)
        self.editor.setPos(self._text_rect.x(), self._text_rect.y())
        self.setToolTip(self._tooltip())
        self.update()

    def boundingRect(self) -> QRectF:
        badge = 24.0  # place pour la pastille de repli, côté extérieur
        left = -4 - (badge if self.side < 0 else 0)
        right = self._w + 4 + (badge if self.side >= 0 else 0)
        return QRectF(left, -4, right - left, self._h + 8)

    def body_path(self) -> QPainterPath:
        rect = QRectF(0, 0, self._w, self._h)
        path = QPainterPath()
        shape = self.shape_name()
        if shape == "diamond":
            path.moveTo(rect.center().x(), 0)
            path.lineTo(self._w, self._h / 2)
            path.lineTo(rect.center().x(), self._h)
            path.lineTo(0, self._h / 2)
            path.closeSubpath()
        elif shape == "rect":
            path.addRoundedRect(rect, 3, 3)
        else:  # "rounded" et "none"
            radius = min(self._h / 2, 14.0)
            path.addRoundedRect(rect, radius, radius)
        return path

    def shape(self) -> QPainterPath:
        return self.body_path()

    def paint(self, p: QPainter, option, widget=None) -> None:
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        rs = resolve_style(self.node)
        path = self.body_path()
        borderless = rs.shape == "none"
        if self.drop_target:
            pen = QPen(DROP_COLOR, 3.5)
        elif self.isSelected():
            pen = QPen(SELECT_COLOR, 3.0, Qt.PenStyle.DashLine if borderless else Qt.PenStyle.SolidLine)
        elif borderless:
            pen = QPen(Qt.PenStyle.NoPen)
        else:
            pen = QPen(rs.border, rs.border_width, rs.border_pen)
        p.setPen(Qt.PenStyle.NoPen)
        if rs.fill is not None:
            p.setBrush(QBrush(rs.fill))
            p.drawPath(path)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(pen)
        p.drawPath(path)

        if self.editor.isVisible():
            self.editor.setDefaultTextColor(rs.text)
        else:
            font, text = rs.font, self.node.text
            if not text:
                text, font = PLACEHOLDER, QFont(font)
                font.setItalic(True)
                p.setPen(QColor(rs.text.red(), rs.text.green(), rs.text.blue(), 130))
            else:
                p.setPen(rs.text)
            p.setFont(font)
            flags = int(ALIGN_FLAGS[rs.align] | Qt.AlignmentFlag.AlignVCenter)
            if rs.wrap:
                flags |= int(Qt.TextFlag.TextWordWrap)
            p.drawText(self._text_rect, flags, text)

        # icône à gauche, pastilles note / lien après le texte
        if self._icon_rect is not None and self.node.icon:
            paint_node_icon(p, self.node.icon, self._icon_rect, rs.text)
        for kind, rect in self._badges:
            renderer = svg_renderer("ui", "sticky-note", rs.text.name()) if kind == "note" else svg_renderer("node", "link", rs.text.name())
            if renderer is not None:
                renderer.render(p, rect)

        if self.node.collapsed and self.node.children:
            r = 9.0
            cx = self._w + r + 3 if self.side >= 0 else -r - 3
            p.setPen(QPen(rs.border, 1.5))
            p.setBrush(QColor("white"))
            p.drawEllipse(QPointF(cx, self._h / 2), r, r)
            small = QFont()
            small.setPixelSize(10)
            small.setBold(True)
            p.setFont(small)
            p.setPen(rs.border.darker(120))
            badge = QRectF(cx - r, self._h / 2 - r, 2 * r, 2 * r)
            p.drawText(badge, Qt.AlignmentFlag.AlignCenter, str(len(self.node.children)))

    # --- Édition -------------------------------------------------------
    def begin_edit(self) -> None:
        self.editor.begin()
        self.editor.setPlainText(self.node.text)
        self.editor.setDefaultTextColor(resolve_style(self.node).text)
        self.editor.setVisible(True)
        self.refresh()
        self.editor.setFocus()
        cursor = self.editor.textCursor()
        cursor.select(cursor.SelectionType.Document)
        self.editor.setTextCursor(cursor)

    def end_edit(self) -> None:
        self.editor.setVisible(False)
        self.editor.clearFocus()
        self.refresh()

    def _on_editor_changed(self) -> None:
        if self.editing:
            self.refresh()
            self.map_scene.relayout(animate=False)

    def mouseDoubleClickEvent(self, event) -> None:
        self.map_scene.start_edit(self.node)

    def contextMenuEvent(self, event) -> None:
        self.map_scene.node_context_menu(self, event.screenPos())
        event.accept()

    # --- Glisser-déposer pour re-parenter -----------------------------
    def mousePressEvent(self, event) -> None:
        super().mousePressEvent(event)
        if event.button() == Qt.MouseButton.LeftButton and not self.editing:
            for kind, rect in self._hit.items():
                if rect.contains(event.pos()):
                    self._press = None
                    signal = self.map_scene.link_activated if kind == "link" else self.map_scene.note_requested
                    signal.emit(self.node)
                    return
        self._press = event.scenePos()
        self._dragging = False

    def mouseMoveEvent(self, event) -> None:
        if self._press is None or self.node.parent is None or self.editing:
            return
        delta = event.scenePos() - self._press
        if not self._dragging:
            if delta.manhattanLength() < 8:
                return
            self._dragging = True
            self._drag_group = self.map_scene.subtree_items(self)
            for it, _ in self._drag_group:
                it.setZValue(10)
        for it, start in self._drag_group:
            it.setPos(start + delta)
        self.map_scene.drag_moved(self, event.scenePos())

    def mouseReleaseEvent(self, event) -> None:
        super().mouseReleaseEvent(event)
        if self._dragging:
            for it, _ in self._drag_group:
                it.setZValue(0)
            self._dragging = False
            self._drag_group = []
            self.map_scene.drag_finished(self)
        self._press = None

    def itemChange(self, change, value):
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self.map_scene.update_edges_of(self)
        return super().itemChange(change, value)


class EdgeItem(QGraphicsPathItem):
    def __init__(self, parent_item: NodeItem, child_item: NodeItem) -> None:
        super().__init__()
        self.parent_item = parent_item
        self.child_item = child_item
        self.setZValue(-1)
        self.update_path()

    def update_path(self) -> None:
        a, b = self.parent_item, self.child_item
        aw, ah = a.size()
        bw, bh = b.size()
        goes_right = b.pos().x() + bw / 2 >= a.pos().x() + aw / 2
        if goes_right:
            start = QPointF(a.pos().x() + aw, a.pos().y() + ah / 2)
            end = QPointF(b.pos().x(), b.pos().y() + bh / 2)
        else:
            start = QPointF(a.pos().x(), a.pos().y() + ah / 2)
            end = QPointF(b.pos().x() + bw, b.pos().y() + bh / 2)
        mid = (start.x() + end.x()) / 2
        path = QPainterPath(start)
        path.cubicTo(QPointF(mid, start.y()), QPointF(mid, end.y()), end)
        self.setPath(path)
        rs = resolve_style(b.node)
        pen = QPen(rs.link, rs.link_width, rs.link_pen)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        self.setPen(pen)


class MapScene(QGraphicsScene):
    editing_changed = Signal(bool)
    structure_changed = Signal()      # après chaque synchronisation (plan, panneaux…)
    note_requested = Signal(object)   # clic sur la pastille « note »
    link_activated = Signal(object)   # clic sur la pastille « lien »
    context_menu_requested = Signal(object, object)   # (nœud, position globale) : clic droit

    def __init__(self, undo_stack: QUndoStack, parent=None) -> None:
        super().__init__(parent)
        self.undo_stack = undo_stack
        self.animated = True
        self.mindmap = MindMap()
        self._items: dict[int, NodeItem] = {}
        self._edges: dict[int, EdgeItem] = {}
        self._anim: QParallelAnimationGroup | None = None
        self._editing: NodeItem | None = None
        self._macro_open = False
        self._drop_target: NodeItem | None = None
        self.setSceneRect(-20000, -20000, 40000, 40000)
        self.sync(select=self.mindmap.root.id, animate=False)

    # --- Chargement ----------------------------------------------------
    def set_mindmap(self, mindmap: MindMap) -> None:
        if self._anim is not None:
            self._anim.stop()
        for item in list(self._items.values()):
            self.removeItem(item)
        for edge in list(self._edges.values()):
            self.removeItem(edge)
        self._items.clear()
        self._edges.clear()
        self._editing = None
        self._macro_open = False
        self.mindmap = mindmap
        self.sync(select=mindmap.root.id, animate=False)

    # --- Synchronisation modèle -> éléments graphiques -----------------
    def _visible_nodes(self):
        stack = [self.mindmap.root]
        while stack:
            n = stack.pop()
            yield n
            stack.extend(reversed(visible_children(n)))

    def item_for(self, node: Node) -> NodeItem | None:
        return self._items.get(node.id)

    def sync(self, select: int | None = None, animate: bool = True) -> None:
        visible = list(self._visible_nodes())
        ids = {n.id for n in visible}
        for nid in [i for i in self._items if i not in ids]:
            if self._items[nid] is self._editing:
                self._editing = None
            self.removeItem(self._items.pop(nid))
        for nid in [i for i in self._edges if i not in ids]:
            self.removeItem(self._edges.pop(nid))

        new_ids: set[int] = set()
        for n in visible:
            item = self._items.get(n.id)
            if item is None:
                item = NodeItem(self, n)
                self._items[n.id] = item
                self.addItem(item)
                new_ids.add(n.id)
            item.node = n
            item.refresh()
        for n in visible:
            if n.parent is None:
                continue
            edge = self._edges.get(n.id)
            if edge is None:
                edge = EdgeItem(self._items[n.parent.id], self._items[n.id])
                self._edges[n.id] = edge
                self.addItem(edge)
            else:
                edge.parent_item = self._items[n.parent.id]
                edge.child_item = self._items[n.id]

        self.relayout(animate=animate, new_ids=new_ids)

        if select is not None and select in self._items:
            self.clearSelection()
            target = self._items[select]
            target.setSelected(True)
            self._ensure_visible(target)
        self.structure_changed.emit()

    def relayout(self, animate: bool = True, new_ids: set[int] | None = None) -> None:
        positions = compute_layout(self.mindmap, lambda n: self._items[n.id].size())
        # côté (gauche/droite) de chaque branche
        root = self.mindmap.root
        self._items[root.id].side = 0
        right, left = root_split(root)
        for side, branch_roots in ((1, right), (-1, left)):
            stack = list(branch_roots)
            while stack:
                n = stack.pop()
                item = self._items[n.id]
                if item.side != side:
                    item.prepareGeometryChange()
                    item.side = side
                stack.extend(visible_children(n))

        if self._anim is not None:
            self._anim.stop()
            self._anim = None
        use_anim = animate and self.animated
        group = QParallelAnimationGroup(self) if use_anim else None
        for nid, (x, y) in positions.items():
            item = self._items[nid]
            target = QPointF(x, y)
            if new_ids and nid in new_ids and use_anim:
                parent = item.node.parent
                start = self._items[parent.id].pos() if parent else target
                item.setPos(start)
            if use_anim and item.pos() != target:
                anim = QPropertyAnimation(item, b"pos", group)
                anim.setDuration(180)
                anim.setStartValue(item.pos())
                anim.setEndValue(target)
                anim.setEasingCurve(QEasingCurve.Type.OutCubic)
                group.addAnimation(anim)
            else:
                item.setPos(target)
        for edge in self._edges.values():
            edge.update_path()
        if group is not None and group.animationCount():
            self._anim = group
            group.start()
        self._targets = positions

    def _ensure_visible(self, item: NodeItem) -> None:
        x, y = self._targets.get(item.node.id, (item.pos().x(), item.pos().y()))
        w, h = item.size()
        rect = QRectF(x, y, w, h)
        for view in self.views():
            view.ensureVisible(rect, 80, 60)

    def update_edges_of(self, item: NodeItem) -> None:
        edge = self._edges.get(item.node.id)
        if edge is not None:
            edge.update_path()
        for child in visible_children(item.node):
            edge = self._edges.get(child.id)
            if edge is not None:
                edge.update_path()

    def subtree_items(self, item: NodeItem) -> list[tuple[NodeItem, QPointF]]:
        out = []
        stack = [item.node]
        while stack:
            n = stack.pop()
            it = self._items.get(n.id)
            if it is not None:
                out.append((it, it.pos()))
            stack.extend(visible_children(n))
        return out

    # --- Sélection -----------------------------------------------------
    def selected_item(self) -> NodeItem | None:
        for it in self.selectedItems():
            if isinstance(it, NodeItem):
                return it
        return None

    def selected_nodes(self) -> list[Node]:
        return [it.node for it in self.selectedItems() if isinstance(it, NodeItem)]

    def apply_style(self, changes: dict) -> None:
        """Applique un changement de style aux nœuds sélectionnés (annulable)."""
        nodes = self.selected_nodes()
        if not nodes or self.is_editing():
            return
        self.undo_stack.push(commands.SetStyle(self, nodes, changes))

    def set_data(self, nodes, **changes) -> None:
        """Modifie note / lien / icône d'un nœud ou d'une liste de nœuds (annulable) ;
        sans effet si rien ne change."""
        nodes = [nodes] if isinstance(nodes, Node) else list(nodes)
        nodes = [n for n in nodes if any(getattr(n, k) != v for k, v in changes.items())]
        if nodes and not self.is_editing():
            self.undo_stack.push(commands.SetData(self, nodes, **changes))

    def selected_node(self) -> Node | None:
        item = self.selected_item()
        return item.node if item else None

    def reveal_and_select(self, node: Node) -> bool:
        """Sélectionne `node`, en dépliant (annulable) les branches repliées qui le cachent."""
        hidden = []
        a = node.parent
        while a is not None:
            if a.collapsed:
                hidden.append(a)
            a = a.parent
        if hidden and not self.is_editing():
            self.undo_stack.beginMacro("Déplier jusqu'au nœud")
            for a in reversed(hidden):
                self.undo_stack.push(commands.ToggleCollapse(self, a))
            self.undo_stack.endMacro()
        if node.id in self._items:
            self.select_node(node)
            return True
        return False

    def select_nodes(self, nodes: list[Node]) -> None:
        """Sélectionne plusieurs nœuds (ceux qui sont visibles)."""
        self.clearSelection()
        items = [self._items[n.id] for n in nodes if n.id in self._items]
        for item in items:
            item.setSelected(True)
        if items:
            self._ensure_visible(items[0])

    def select_node(self, node: Node) -> None:
        item = self._items.get(node.id)
        if item is not None:
            self.clearSelection()
            item.setSelected(True)
            self._ensure_visible(item)

    # --- Actions utilisateur --------------------------------------------
    def is_editing(self) -> bool:
        return self._editing is not None

    def _target_node(self) -> Node:
        return self.selected_node() or self.mindmap.root

    def _begin_new(self, cmd: commands.AddNode) -> None:
        self.undo_stack.beginMacro("Ajouter un nœud")
        self._macro_open = True
        self.undo_stack.push(cmd)
        self.start_edit(cmd.node)

    def _side_for_new_root_child(self, like: Node | None = None) -> str:
        """Côté d'une nouvelle branche principale : celui de `like`, sinon le moins chargé."""
        item = self._items.get(like.id) if like is not None else None
        if item is not None and item.side:
            return "right" if item.side > 0 else "left"
        right, left = root_split(self.mindmap.root)
        return "right" if len(right) <= len(left) else "left"

    def add_child(self) -> None:
        if self.is_editing():
            return
        node = self._target_node()
        side = self._side_for_new_root_child() if node.parent is None else None
        self._begin_new(commands.AddNode(self, node, side=side))

    def add_sibling(self) -> None:
        if self.is_editing():
            return
        node = self._target_node()
        if node.parent is None:
            self._begin_new(commands.AddNode(self, node, side=self._side_for_new_root_child()))
        else:
            side = self._side_for_new_root_child(node) if node.parent.parent is None else None
            self._begin_new(commands.AddNode(self, node.parent, node.index + 1, side=side))

    # --- Menu contextuel -------------------------------------------------
    def node_context_menu(self, item: NodeItem, global_pos) -> None:
        """Clic droit sur un nœud : il est sélectionné (sauf s'il fait déjà partie de la sélection)."""
        if self.is_editing():
            return
        if not item.isSelected():
            self.clearSelection()
            item.setSelected(True)
        self.context_menu_requested.emit(item.node, global_pos)

    # --- Presse-papiers --------------------------------------------------
    def copy_selection(self) -> bool:
        nodes = clipboard.top_level(self.selected_nodes())
        if not nodes or self.is_editing():
            return False
        try:
            mime = clipboard.make_mime(nodes)
        except RecursionError:      # sous-arbre démesurément profond : on ne touche pas au presse-papiers
            return False
        QApplication.clipboard().setMimeData(mime)
        return True

    def cut_selection(self) -> bool:
        """Copie puis supprime la sélection (la racine ne peut pas être coupée)."""
        nodes = self.selected_nodes()
        if not nodes or any(n.parent is None for n in nodes) or self.is_editing():
            return False
        if not self.copy_selection():
            return False
        self.delete_selected()
        return True

    def can_paste(self) -> bool:
        return clipboard.has_content(QApplication.clipboard().mimeData())

    def paste(self, target: Node | None = None) -> bool:
        """Colle le contenu du presse-papiers comme enfants de `target` (par défaut : la sélection)."""
        payload = clipboard.read(QApplication.clipboard().mimeData())
        if payload is None or self.is_editing():
            return False
        target = target or self._target_node()
        roots = clipboard.instantiate(self.mindmap, payload)
        if not roots:
            return False
        sides = None
        if target.parent is None:   # nouvelles branches principales : on alterne les côtés
            right, left = root_split(self.mindmap.root)
            counts = {"right": len(right), "left": len(left)}
            sides = []
            for _ in roots:
                side = "right" if counts["right"] <= counts["left"] else "left"
                counts[side] += 1
                sides.append(side)
        self.undo_stack.push(commands.PasteNodes(self, target, roots, sides))
        return True

    def delete_selected(self) -> None:
        """Supprime les nœuds sélectionnés (sauf la racine) ; un sous-arbre déjà inclus n'est pas compté deux fois."""
        nodes = [n for n in self.selected_nodes() if n.parent is not None]
        if not nodes or self.is_editing():
            return
        chosen = {id(n) for n in nodes}

        def has_chosen_ancestor(n: Node) -> bool:
            a = n.parent
            while a is not None:
                if id(a) in chosen:
                    return True
                a = a.parent
            return False

        tops = [n for n in nodes if not has_chosen_ancestor(n)]
        if len(tops) == 1:
            self.undo_stack.push(commands.DeleteNode(self, tops[0]))
            return
        self.undo_stack.beginMacro(f"Supprimer {len(tops)} nœuds")
        for n in tops:
            self.undo_stack.push(commands.DeleteNode(self, n))
        self.undo_stack.endMacro()

    def add_parent(self) -> None:
        """Insère un nœud entre le nœud sélectionné et son parent."""
        node = self.selected_node()
        if node is None or node.parent is None or self.is_editing():
            return
        self._begin_new(commands.InsertParent(self, node))

    def toggle_collapse(self) -> None:
        """Replie les enfants des nœuds sélectionnés ; s'ils sont tous déjà repliés, les déplie."""
        nodes = [n for n in self.selected_nodes() if n.children]
        if not nodes or self.is_editing():
            return
        collapse = not all(n.collapsed for n in nodes)
        todo = [n for n in nodes if n.collapsed != collapse]
        if len(todo) == 1:
            self.undo_stack.push(commands.ToggleCollapse(self, todo[0]))
        elif todo:
            self.undo_stack.beginMacro("Replier" if collapse else "Déplier")
            for n in todo:
                self.undo_stack.push(commands.ToggleCollapse(self, n))
            self.undo_stack.endMacro()

    def start_edit(self, node: Node) -> None:
        item = self._items.get(node.id)
        if item is None or self._editing is not None:
            return
        self._editing = item
        self.editing_changed.emit(True)
        item.begin_edit()

    def edit_finished(self, item: NodeItem, accepted: bool) -> None:
        if self._editing is not item:
            return
        node = item.node
        new_text = normalize_text(item.editor.toPlainText()) if accepted else node.text
        item.end_edit()
        self._editing = None
        if new_text != node.text:
            self.undo_stack.push(commands.EditText(self, node, new_text))
        else:
            self.sync(select=node.id)
        if self._macro_open:
            self.undo_stack.endMacro()
            self._macro_open = False
        self.editing_changed.emit(False)

    def navigate(self, key: int) -> None:
        item = self.selected_item() or self._items[self.mindmap.root.id]
        node = item.node
        if key in (Qt.Key.Key_Up, Qt.Key.Key_Down):
            if node.parent is None:
                return
            depth = depth_of(node)
            cands = [
                it for it in self._items.values()
                if it is not item and it.side == item.side and depth_of(it.node) == depth
            ]
            sign = 1 if key == Qt.Key.Key_Down else -1
            cands = [it for it in cands if (it.pos().y() - item.pos().y()) * sign > 0]
            if cands:
                best = min(cands, key=lambda it: abs(it.pos().y() - item.pos().y()))
                self.select_node(best.node)
            return
        direction = 1 if key == Qt.Key.Key_Right else -1
        kids = visible_children(node)
        if node.parent is None:
            pool = root_split(node)[0 if direction > 0 else 1]
            if pool:
                self.select_node(pool[0])
        elif item.side == direction:
            if kids:
                self.select_node(kids[0])
        elif node.parent is not None:
            self.select_node(node.parent)

    def event(self, event) -> bool:
        # QGraphicsScene::event consomme Tab pour la navigation du focus,
        # avant keyPressEvent : on le récupère ici.
        if (
            event.type() == QEvent.Type.KeyPress
            and event.key() == Qt.Key.Key_Tab
            and not self.is_editing()
        ):
            self.keyPressEvent(event)
            return True
        return super().event(event)

    def keyPressEvent(self, event) -> None:
        if self.is_editing():
            return super().keyPressEvent(event)
        key = event.key()
        if self.selected_item() is None and key in (
            Qt.Key.Key_Tab, Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_F2,
            Qt.Key.Key_Space, Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down,
        ):
            self.select_node(self.mindmap.root)
        handled = True
        if key == Qt.Key.Key_Tab:
            self.add_child()
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.add_sibling()
        elif key == Qt.Key.Key_F2:
            self.start_edit(self._target_node())
        elif key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            self.delete_selected()
        elif key == Qt.Key.Key_Space:
            self.toggle_collapse()
        elif key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down):
            self.navigate(key)
        else:
            handled = False
        if handled:
            event.accept()
        else:
            super().keyPressEvent(event)

    # --- Glisser-déposer -------------------------------------------------
    def drag_moved(self, dragged: NodeItem, scene_pos: QPointF) -> None:
        target = None
        for it in self.items(scene_pos):
            if (
                isinstance(it, NodeItem)
                and it is not dragged
                and not it.node.is_descendant_of(dragged.node)
            ):
                target = it
                break
        if target is not self._drop_target:
            if self._drop_target is not None:
                self._drop_target.drop_target = False
                self._drop_target.update()
            self._drop_target = target
            if target is not None:
                target.drop_target = True
                target.update()

    def drag_finished(self, dragged: NodeItem) -> None:
        target = self._drop_target
        if target is not None:
            target.drop_target = False
            target.update()
        self._drop_target = None
        if target is not None and target.node is not dragged.node.parent:
            self.undo_stack.push(commands.Reparent(self, dragged.node, target.node))
        else:
            self.sync(select=dragged.node.id)
