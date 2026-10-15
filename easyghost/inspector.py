"""Inspecteur (panneau de droite) : Contour, Note, Couleur, Icônes, Style."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, QTimer, Signal
from shiboken6 import isValid
from PySide6.QtGui import QColor, QFont, QIcon, QPainter, QPalette, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup,
    QColorDialog,
    QComboBox,
    QDockWidget,
    QDoubleSpinBox,
    QFontComboBox,
    QFormLayout,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QPlainTextEdit,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpinBox,
    QStackedWidget,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from . import icons
from .iconset import CATEGORIES, ICON_TABLE
from .model import (
    BRANCH_PALETTE,
    FONT_SIZE_RANGE,
    LINE_STYLE_LABELS,
    LINE_WIDTH_RANGE,
    SHAPE_LABELS,
    WRAP_WIDTH_RANGE,
    Node,
    normalize_note,
)
from .scene import MapScene, default_font_size, resolve_style

PAGES = [("outline", "Contour"), ("note", "Note"), ("color", "Couleur"), ("icons", "Icônes"), ("style", "Style")]
RESET_ALL = {
    k: None
    for k in (
        "color", "fill", "text_color", "border_color", "shape", "border_style", "border_width",
        "link_style", "link_width", "bold", "italic", "underline", "strike", "font_family",
        "font_size", "align", "wrap_width",
    )
}


def _mix(color: str, other: str, t: float) -> str:
    """Mélange `color` avec `other` (t = part de `other`)."""
    a, b = QColor(color), QColor(other)
    return QColor(
        round(a.red() * (1 - t) + b.red() * t),
        round(a.green() * (1 - t) + b.green() * t),
        round(a.blue() * (1 - t) + b.blue() * t),
    ).name().upper()


PALETTE_ROWS = [
    ["#FFFFFF", "#F2F2F2", "#D9D9D9", "#A6A6A6", "#737373", "#404040", "#1A1A1A", "#000000"],
    list(BRANCH_PALETTE),
    [_mix(c, "#FFFFFF", 0.65) for c in BRANCH_PALETTE],
    [_mix(c, "#FFFFFF", 0.85) for c in BRANCH_PALETTE],
    [_mix(c, "#000000", 0.35) for c in BRANCH_PALETTE],
]


def swatch_icon(color: str | None, size: int = 16) -> QIcon:
    pix = QPixmap(size, size)
    pix.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pix)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    if color in (None, "none"):  # automatique / transparent : damier barré
        painter.setPen(QColor("#999999"))
        painter.setBrush(QColor("white"))
        painter.drawRoundedRect(1, 1, size - 2, size - 2, 3, 3)
        painter.drawLine(3, size - 3, size - 3, 3)
    else:
        painter.setPen(QColor(0, 0, 0, 60))
        painter.setBrush(QColor(color))
        painter.drawRoundedRect(1, 1, size - 2, size - 2, 3, 3)
    painter.end()
    return QIcon(pix)


def _node_label(node: Node) -> str:
    text = node.text.split("\n")[0] + (" …" if "\n" in node.text else "")
    return text or "(sans titre)"


# =============================================================== pages
class _Page(QWidget):
    def __init__(self, scene: MapScene) -> None:
        super().__init__()
        self.scene = scene

    def refresh(self) -> None:  # appelé quand la page est visible et que la sélection/structure change
        pass


# ------------------------------------------------------------------ Contour
class OutlinePage(_Page):
    def __init__(self, scene: MapScene) -> None:
        super().__init__(scene)
        self._syncing = False
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.setIconSize(QSize(16, 16))
        self.tree.setIndentation(16)
        self.tree.setSelectionMode(QTreeWidget.SelectionMode.SingleSelection)
        self.tree.setAnimated(False)
        self.tree.itemSelectionChanged.connect(self._tree_selection_changed)
        self.tree.itemDoubleClicked.connect(lambda item, _c: self._edit(item))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.tree)
        self._items: dict[int, QTreeWidgetItem] = {}
        self._expanded: set[int] = set()
        self._known: set[int] = set()

    def _edit(self, item: QTreeWidgetItem) -> None:
        node = self.scene.mindmap.find(item.data(0, Qt.ItemDataRole.UserRole))
        if node is not None and self.scene.reveal_and_select(node):
            self.scene.start_edit(node)

    def refresh(self) -> None:
        self._remember_expansion()
        self._syncing = True
        try:
            self.tree.clear()
            self._items = {}
            color = self.palette().color(QPalette.ColorRole.WindowText)
            stack = [(self.scene.mindmap.root, self.tree.invisibleRootItem())]
            while stack:
                node, parent_item = stack.pop()
                item = QTreeWidgetItem(parent_item, [_node_label(node)])
                item.setData(0, Qt.ItemDataRole.UserRole, node.id)
                if node.icon:
                    item.setIcon(0, QIcon(icons.node_icon_pixmap(node.icon, 16, color)))
                if node.collapsed and node.children:
                    item.setToolTip(0, "Branche repliée dans la carte")
                self._items[node.id] = item
                stack.extend((c, item) for c in reversed(node.children))
            for nid, item in self._items.items():
                if nid not in self._known or nid in self._expanded:   # nouveaux nœuds : dépliés
                    item.setExpanded(True)
            self._known = set(self._items)
            self._select_current()
        finally:
            self._syncing = False

    def _remember_expansion(self) -> None:
        self._expanded = {nid for nid, item in self._items.items() if item.isExpanded()}

    def _select_current(self) -> None:
        nodes = self.scene.selected_nodes()
        self.tree.clearSelection()
        if len(nodes) == 1 and nodes[0].id in self._items:
            item = self._items[nodes[0].id]
            item.setSelected(True)
            self.tree.scrollToItem(item)

    def selection_changed_in_scene(self) -> None:
        if not self._syncing:
            self._syncing = True
            try:
                self._select_current()
            finally:
                self._syncing = False

    def _tree_selection_changed(self) -> None:
        if self._syncing:
            return
        items = self.tree.selectedItems()
        if not items:
            return
        node = self.scene.mindmap.find(items[0].data(0, Qt.ItemDataRole.UserRole))
        if node is not None:
            self._syncing = True
            try:
                self.scene.reveal_and_select(node)
            finally:
                self._syncing = False


# --------------------------------------------------------------------- Note
class _NoteEdit(QPlainTextEdit):
    committed = Signal()

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self.committed.emit()


class NotePage(_Page):
    def __init__(self, scene: MapScene) -> None:
        super().__init__(scene)
        self._node: Node | None = None
        self._dirty = False  # vrai seulement si l'utilisateur a tapé dans le champ
        self.title = QLabel()
        self.title.setStyleSheet("font-weight: 600;")
        self.title.setWordWrap(True)
        self.edit = _NoteEdit()
        self.edit.setPlaceholderText("Sélectionnez un nœud pour voir ou écrire sa note.")
        self.edit.setEnabled(False)
        self.edit.committed.connect(self.commit)
        self.edit.textChanged.connect(lambda: setattr(self, "_dirty", True))
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(self.title)
        layout.addWidget(self.edit)

    def _single(self) -> Node | None:
        nodes = self.scene.selected_nodes()
        return nodes[0] if len(nodes) == 1 else None

    def _bind(self, node: Node | None) -> None:
        self._node = node
        blocker = self.edit.blockSignals(True)
        self.edit.setPlainText(node.note if node else "")
        self.edit.blockSignals(blocker)
        self._dirty = False
        self.edit.setEnabled(node is not None)
        self.title.setText(_node_label(node) if node else "Aucun nœud sélectionné")

    def commit(self) -> None:
        node = self._node
        if node is None or not self._dirty:
            return
        self._dirty = False
        text = normalize_note(self.edit.toPlainText())
        if text != node.note:
            self.scene.set_data(node, note=text)

    def on_selection(self) -> None:
        self.commit()                  # la saisie en cours va au nœud précédent
        self._bind(self._single())

    def rebind(self) -> None:
        self._bind(self._single())     # après annuler/rétablir : pas de commit

    def refresh(self) -> None:
        pass


# ------------------------------------------------------------------ Couleur
class ColorPage(_Page):
    TARGETS = [("fill", "Fond"), ("text_color", "Texte"), ("border_color", "Contour"), ("color", "Branche")]

    def __init__(self, scene: MapScene) -> None:
        super().__init__(scene)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.addWidget(QLabel("Appliquer la couleur à :"))
        row = QHBoxLayout()
        self.group = QButtonGroup(self)
        self.target_buttons: dict[str, QPushButton] = {}
        for key, label in self.TARGETS:
            b = QPushButton(label)
            b.setCheckable(True)
            b.setProperty("target", key)
            self.group.addButton(b)
            self.target_buttons[key] = b
            row.addWidget(b)
        self.group.setExclusive(True)
        self.target_buttons["fill"].setChecked(True)
        self.group.buttonToggled.connect(lambda *_: self.refresh())
        layout.addLayout(row)
        hint = QLabel("« Branche » colore le lien et le contour du nœud ; ses descendants en héritent.")
        hint.setWordWrap(True)
        hint.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(hint)

        grid = QGridLayout()
        grid.setSpacing(4)
        self.swatches: list[QToolButton] = []
        for r, colors in enumerate(PALETTE_ROWS):
            for c, color in enumerate(colors):
                b = QToolButton()
                b.setAutoRaise(False)
                b.setFixedSize(26, 26)
                b.setIcon(swatch_icon(color, 20))
                b.setIconSize(QSize(20, 20))
                b.setToolTip(color)
                b.clicked.connect(lambda _=False, col=color: self.apply(col))
                grid.addWidget(b, r, c)
                self.swatches.append(b)
        layout.addLayout(grid)

        actions = QHBoxLayout()
        self.auto_btn = QPushButton("Automatique")
        self.auto_btn.setToolTip("Revenir à la couleur par défaut")
        self.auto_btn.clicked.connect(lambda: self.apply(None))
        self.transparent_btn = QPushButton("Transparent")
        self.transparent_btn.clicked.connect(lambda: self.apply("none"))
        self.other_btn = QPushButton("Autre…")
        self.other_btn.clicked.connect(self.pick_other)
        for b in (self.auto_btn, self.transparent_btn, self.other_btn):
            actions.addWidget(b)
        layout.addLayout(actions)
        current = QHBoxLayout()
        current.addWidget(QLabel("Actuelle :"))
        self.current = QLabel()
        self.current.setFixedSize(22, 22)
        current.addWidget(self.current)
        self.current_name = QLabel()
        current.addWidget(self.current_name, 1)
        layout.addLayout(current)
        layout.addStretch(1)

    @property
    def target(self) -> str:
        return self.group.checkedButton().property("target")

    def set_target(self, key: str) -> None:
        self.target_buttons[key].setChecked(True)

    def apply(self, value: str | None) -> None:
        self.scene.apply_style({self.target: value})

    def pick_other(self) -> None:
        nodes = self.scene.selected_nodes()
        initial = self._current_color(nodes[0]) if nodes else QColor("white")
        color = QColorDialog.getColor(initial or QColor("white"), self, "Choisir une couleur")
        if color.isValid():
            self.apply(color.name().upper())

    def _current_color(self, node: Node) -> QColor | None:
        rs = resolve_style(node)
        return {"fill": rs.fill, "text_color": rs.text, "border_color": rs.border, "color": rs.link}[self.target]

    def refresh(self) -> None:
        nodes = self.scene.selected_nodes()
        enabled = bool(nodes)
        for b in [*self.swatches, self.auto_btn, self.other_btn]:
            b.setEnabled(enabled)
        self.transparent_btn.setEnabled(enabled and self.target == "fill")
        color = self._current_color(nodes[0]) if nodes else None
        if color is None:
            self.current.setStyleSheet("border: 1px solid #999; background: transparent;")
            self.current_name.setText("transparent" if nodes else "")
        else:
            self.current.setStyleSheet(f"border: 1px solid #999; border-radius: 3px; background: {color.name()};")
            self.current_name.setText(color.name().upper())


# ------------------------------------------------------------------ Icônes
class IconsPage(_Page):
    SIZE = 28
    ALL = "Toutes"

    def __init__(self, scene: MapScene) -> None:
        super().__init__(scene)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        top = QHBoxLayout()
        self.category = QComboBox()
        self.category.addItems([self.ALL, *CATEGORIES])
        self.category.currentIndexChanged.connect(self._fill)
        top.addWidget(self.category, 1)
        self.none_btn = QPushButton("Aucune")
        self.none_btn.clicked.connect(lambda: self._assign(None))
        top.addWidget(self.none_btn)
        layout.addLayout(top)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Rechercher une icône…")
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self._fill)
        layout.addWidget(self.search)
        self.list = QListWidget()
        self.list.setViewMode(QListView.ViewMode.IconMode)
        self.list.setIconSize(QSize(self.SIZE, self.SIZE))
        self.list.setGridSize(QSize(self.SIZE + 18, self.SIZE + 14))
        self.list.setResizeMode(QListView.ResizeMode.Adjust)
        self.list.setMovement(QListView.Movement.Static)
        self.list.setUniformItemSizes(True)
        self.list.setSpacing(2)
        self.list.itemClicked.connect(lambda item: self._assign(item.data(Qt.ItemDataRole.UserRole)))
        layout.addWidget(self.list, 1)
        self.info = QLabel()
        self.info.setWordWrap(True)
        self.info.setStyleSheet("color: gray; font-size: 11px;")
        layout.addWidget(self.info)
        self._filled = False

    def _entries(self) -> list[tuple[str, str]]:
        """[(clé, libellé)] pour la catégorie et la recherche en cours."""
        query = self.search.text().strip().lower()
        cat = self.category.currentText()
        rows = [(k, label) for k, _svg, label, c, _e in ICON_TABLE if cat in (self.ALL, c)]
        return [(k, lab) for k, lab in rows if not query or query in lab.lower() or query in k.lower()]

    def _fill(self, *_) -> None:
        self.list.clear()
        color = self.palette().color(QPalette.ColorRole.WindowText)
        for key, label in self._entries():
            item = QListWidgetItem(QIcon(icons.node_icon_pixmap(key, self.SIZE, color)), "")
            item.setToolTip(label)
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.list.addItem(item)
        self._filled = True
        self._mark_current()

    def _mark_current(self) -> None:
        nodes = self.scene.selected_nodes()
        current = nodes[0].icon if nodes else None
        self.list.clearSelection()
        for i in range(self.list.count()):
            item = self.list.item(i)
            if current and item.data(Qt.ItemDataRole.UserRole) == current:
                item.setSelected(True)
                self.list.scrollToItem(item)
                break
        enabled = bool(nodes)
        self.list.setEnabled(enabled)
        self.none_btn.setEnabled(enabled)
        self.info.setText(
            "" if enabled
            else "Sélectionnez un ou plusieurs nœuds pour leur choisir une icône."
        )

    def _assign(self, key: str | None) -> None:
        self.scene.set_data(self.scene.selected_nodes(), icon=key)

    def refresh(self) -> None:
        if not self._filled:
            self._fill()
        else:
            self._mark_current()


# -------------------------------------------------------------------- Style
class ColorButton(QToolButton):
    """Bouton-couleur avec menu : choisir, automatique, (transparent)."""

    changed = Signal(object)   # "#RRGGBB" | "none" | None

    def __init__(self, label: str, allow_transparent: bool = False) -> None:
        super().__init__()
        self.setText(label)
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.setIconSize(QSize(16, 16))
        self.setMinimumWidth(150)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        menu = QMenu(self)
        menu.addAction("Choisir une couleur…", self._choose)
        menu.addAction("Automatique", lambda: self.changed.emit(None))
        if allow_transparent:
            menu.addAction("Transparent", lambda: self.changed.emit("none"))
        self.setMenu(menu)
        self._value: str | None = None

    def set_color(self, color: str | None) -> None:
        self._value = color
        self.setIcon(swatch_icon(color))

    def _choose(self) -> None:
        initial = QColor(self._value) if self._value and self._value != "none" else QColor("white")
        color = QColorDialog.getColor(initial, self, "Choisir une couleur")
        if color.isValid():
            self.changed.emit(color.name().upper())


class StylePage(_Page):
    def __init__(self, scene: MapScene) -> None:
        super().__init__(scene)
        self._loading = False
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        outer.addWidget(scroll)
        body = QWidget()
        scroll.setWidget(body)
        layout = QVBoxLayout(body)
        layout.setContentsMargins(8, 8, 8, 8)

        # --- Police
        box = QGroupBox("Police")
        form = QFormLayout(box)
        self.font_family = QFontComboBox()
        self.font_family.setEditable(True)   # permet d'afficher « Police par défaut » quand rien n'est choisi
        self.font_family.lineEdit().setPlaceholderText("Police par défaut")
        self.font_family.currentFontChanged.connect(self._family_changed)
        form.addRow(self.font_family)
        row = QHBoxLayout()
        self.font_size = QSpinBox()
        self.font_size.setRange(*FONT_SIZE_RANGE)
        self.font_size.setSuffix(" px")
        self.font_size.setKeyboardTracking(False)
        self.font_size.valueChanged.connect(lambda v: self._apply(font_size=v))
        row.addWidget(self.font_size)
        self.flags: dict[str, QToolButton] = {}
        for key, label, font in (("bold", "G", QFont()), ("italic", "I", QFont()),
                                 ("underline", "S", QFont()), ("strike", "S", QFont())):
            b = QToolButton()
            b.setText(label)
            b.setCheckable(True)
            b.setFixedSize(28, 28)
            f = QFont(font)
            f.setBold(key == "bold")
            f.setItalic(key == "italic")
            f.setUnderline(key == "underline")
            f.setStrikeOut(key == "strike")
            b.setFont(f)
            b.setToolTip({"bold": "Gras", "italic": "Italique", "underline": "Souligné", "strike": "Barré"}[key])
            b.clicked.connect(lambda checked, k=key: self._apply(**{k: checked}))
            row.addWidget(b)
            self.flags[key] = b
        form.addRow("Taille", row)
        layout.addWidget(box)

        # --- Paragraphe
        box = QGroupBox("Paragraphe")
        form = QFormLayout(box)
        row = QHBoxLayout()
        self.align_group = QButtonGroup(self)
        self.align_buttons: dict[str, QToolButton] = {}
        for key, icon_name, tip in (("left", "align-left", "À gauche"), ("center", "align-center", "Centré"),
                                    ("right", "align-right", "À droite")):
            b = QToolButton()
            b.setIcon(icons.ui_icon(icon_name))
            b.setCheckable(True)
            b.setToolTip(tip)
            b.setFixedSize(30, 28)
            self.align_group.addButton(b)
            b.clicked.connect(lambda _=False, k=key: self._apply(align=k))
            row.addWidget(b)
            self.align_buttons[key] = b
        self.align_group.setExclusive(True)
        row.addStretch(1)
        form.addRow("Alignement", row)
        self.wrap = QSpinBox()
        self.wrap.setRange(0, WRAP_WIDTH_RANGE[1])
        self.wrap.setSingleStep(20)
        self.wrap.setSpecialValueText("Illimitée")
        self.wrap.setSuffix(" px")
        self.wrap.setKeyboardTracking(False)
        self.wrap.valueChanged.connect(self._wrap_changed)
        self.wrap.setToolTip("Largeur maximale du texte avant retour à la ligne automatique")
        form.addRow("Largeur max.", self.wrap)
        layout.addWidget(box)

        # --- Forme et traits
        box = QGroupBox("Forme et traits")
        form = QFormLayout(box)
        self.shape = QComboBox()
        for key, label in SHAPE_LABELS.items():
            self.shape.addItem("Rectangle arrondi" if key == "rounded" else label, key)
        self.shape.activated.connect(lambda i: self._apply(shape=self.shape.itemData(i)))
        form.addRow("Forme", self.shape)
        self.border_style, self.border_width = self._line_controls("border")
        form.addRow("Contour", self._row(self.border_style, self.border_width))
        self.link_style, self.link_width = self._line_controls("link")
        form.addRow("Lien", self._row(self.link_style, self.link_width))
        layout.addWidget(box)

        # --- Couleurs
        box = QGroupBox("Couleurs")
        col = QVBoxLayout(box)
        self.color_buttons = {
            "fill": ColorButton("Fond", allow_transparent=True),
            "border_color": ColorButton("Contour"),
            "color": ColorButton("Lien / branche"),
            "text_color": ColorButton("Texte"),
        }
        for key, b in self.color_buttons.items():
            b.changed.connect(lambda value, k=key: self._apply(**{k: value}))
            col.addWidget(b)
        layout.addWidget(box)

        reset = QPushButton("Réinitialiser le style")
        reset.clicked.connect(lambda: self.scene.apply_style(dict(RESET_ALL)))
        layout.addWidget(reset)
        layout.addStretch(1)
        self._controls = [self.font_family, self.font_size, self.wrap, self.shape, self.border_style,
                          self.border_width, self.link_style, self.link_width, reset,
                          *self.flags.values(), *self.align_buttons.values(), *self.color_buttons.values()]

    def _line_controls(self, prefix: str) -> tuple[QComboBox, QDoubleSpinBox]:
        style = QComboBox()
        for key, label in LINE_STYLE_LABELS.items():
            style.addItem(label, key)
        style.activated.connect(lambda i: self._apply(**{f"{prefix}_style": style.itemData(i)}))
        width = QDoubleSpinBox()
        width.setRange(*LINE_WIDTH_RANGE)
        width.setSingleStep(0.5)
        width.setDecimals(1)
        width.setSuffix(" px")
        width.setKeyboardTracking(False)
        width.valueChanged.connect(lambda v: self._apply(**{f"{prefix}_width": float(v)}))
        return style, width

    @staticmethod
    def _row(*widgets: QWidget) -> QWidget:
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        for x in widgets:
            lay.addWidget(x)
        return w

    # --- appliquer
    def _apply(self, **changes) -> None:
        if not self._loading:
            self.scene.apply_style(changes)

    def _family_changed(self, font: QFont) -> None:
        self._apply(font_family=font.family())

    def _wrap_changed(self, value: int) -> None:
        self._apply(wrap_width=None if value == 0 else max(value, WRAP_WIDTH_RANGE[0]))

    # --- afficher la valeur effective du premier nœud sélectionné
    def refresh(self) -> None:
        nodes = self.scene.selected_nodes()
        for c in self._controls:
            c.setEnabled(bool(nodes))
        if not nodes:
            return
        node = nodes[0]
        st, rs = node.style, resolve_style(node)
        self._loading = True
        try:
            if st.font_family:
                self.font_family.setCurrentFont(QFont(st.font_family))
            else:
                self.font_family.setCurrentIndex(-1)   # police par défaut
            self.font_size.setValue(st.font_size or default_font_size(node))
            for key, button in self.flags.items():
                button.setChecked(getattr(rs.font, {"bold": "bold", "italic": "italic",
                                                    "underline": "underline", "strike": "strikeOut"}[key])())
            self.align_buttons[rs.align].setChecked(True)
            self.wrap.setValue(st.wrap_width or 0)
            self.shape.setCurrentIndex(max(0, self.shape.findData(rs.shape)))
            self.border_style.setCurrentIndex(max(0, self.border_style.findData(st.border_style or "solid")))
            self.border_width.setValue(rs.border_width)
            self.link_style.setCurrentIndex(max(0, self.link_style.findData(st.link_style or "solid")))
            self.link_width.setValue(rs.link_width)
            self.color_buttons["fill"].set_color("none" if rs.fill is None else rs.fill.name().upper())
            self.color_buttons["border_color"].set_color(rs.border.name().upper())
            self.color_buttons["color"].set_color(rs.link.name().upper())
            self.color_buttons["text_color"].set_color(rs.text.name().upper())
        finally:
            self._loading = False


# ============================================================== Inspecteur
class Inspector(QDockWidget):
    page_changed = Signal(str)

    def __init__(self, scene: MapScene, stack, parent=None) -> None:
        super().__init__("Inspecteur", parent)
        self.scene = scene
        self.setObjectName("inspector")
        self.setFeatures(QDockWidget.DockWidgetFeature.DockWidgetClosable)
        self.setMinimumWidth(290)
        self.stack = QStackedWidget()
        self.setWidget(self.stack)
        self.outline_page = OutlinePage(scene)
        self.note_page = NotePage(scene)
        self.color_page = ColorPage(scene)
        self.icons_page = IconsPage(scene)
        self.style_page = StylePage(scene)
        self._pages: dict[str, _Page] = {
            "outline": self.outline_page, "note": self.note_page, "color": self.color_page,
            "icons": self.icons_page, "style": self.style_page,
        }
        for key, _label in PAGES:
            self.stack.addWidget(self._pages[key])
        self._refresh_timer = QTimer(self)
        self._refresh_timer.setSingleShot(True)
        self._refresh_timer.setInterval(0)
        self._refresh_timer.timeout.connect(self._refresh_current)
        scene.selectionChanged.connect(self._on_selection)
        scene.structure_changed.connect(self.schedule_refresh)
        stack.indexChanged.connect(lambda *_: self.note_page.rebind())
        self.show_page("outline", show=False)

    @property
    def current_key(self) -> str:
        return PAGES[self.stack.currentIndex()][0]

    def page(self, key: str) -> _Page:
        return self._pages[key]

    def show_page(self, key: str, show: bool = True) -> None:
        self.stack.setCurrentWidget(self._pages[key])
        label = dict(PAGES)[key]
        self.setWindowTitle(f"Inspecteur — {label}")
        self._refresh_current()
        if show:
            self.show()
        self.page_changed.emit(key)

    def commit_pending(self) -> None:
        """Valide une saisie en cours (note) avant d'enregistrer, d'exporter ou de fermer."""
        self.note_page.commit()

    def _on_selection(self) -> None:
        if not isValid(self.scene):      # fermeture : la scène est détruite avant l'Inspecteur
            return
        self.note_page.on_selection()
        self.outline_page.selection_changed_in_scene()
        self.schedule_refresh()

    def schedule_refresh(self) -> None:
        if isValid(self.scene):
            self._refresh_timer.start()

    def _refresh_current(self) -> None:
        if isValid(self.scene):
            self._pages[self.current_key].refresh()
