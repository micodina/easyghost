"""Fenêtre principale : menus, fichiers, annuler/rétablir."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QSize, Qt, QUrl
from PySide6.QtGui import QAction, QColor, QDesktopServices, QKeySequence, QUndoStack
from shiboken6 import isValid
from PySide6.QtWidgets import (
    QColorDialog,
    QFileDialog,
    QInputDialog,
    QApplication,
    QMainWindow,
    QMenu,
    QMenuBar,
    QMessageBox,
    QSizePolicy,
    QToolBar,
    QToolButton,
    QWidget,
)

from . import export_image, formats, storage
from .icons import app_icon, ui_icon
from .inspector import PAGES, RESET_ALL, Inspector
from .model import (
    OPENABLE_SCHEMES,
    SHAPE_LABELS,
    MindMap,
    complete_link,
    is_openable_link,
    normalize_link,
)
from .scene import MapScene, branch_color
from .view import MapView

NATIVE_EXT = ".easyghost"


def _open_filter() -> str:
    fmts = formats.importable_formats()
    native = f"*{NATIVE_EXT}"
    exts = " ".join([native, *(f"*{f.extension}" for f in fmts)])
    parts = [f"Cartes mentales ({exts})", f"EasyGhost ({native})"]
    parts += [f"{f.label} (*{f.extension})" for f in fmts]
    return ";;".join([*parts, "Tous les fichiers (*)"])


FILE_FILTER = f"Carte mentale (*{NATIVE_EXT});;Tous les fichiers (*)"
HINT = (
    "Tab : enfant   ·   Entrée : frère   ·   F2 / double-clic : éditer   ·   "
    "Suppr : supprimer   ·   Espace : replier   ·   glisser un nœud sur un autre : déplacer"
)


class MainWindow(QMainWindow):
    def __init__(self, path: str | None = None) -> None:
        super().__init__()
        self.path: Path | None = None
        self.doc_name: str | None = None  # nom du fichier importé (document non encore enregistré)
        self.stack = QUndoStack(self)
        self.scene = MapScene(self.stack, self)
        self.view = MapView(self.scene)
        self.setCentralWidget(self.view)
        self.setWindowIcon(app_icon())
        self.resize(1320, 780)
        self.statusBar().showMessage(HINT)
        self._canvas_has_focus = True   # la carte a le focus à l'ouverture

        self.inspector = Inspector(self.scene, self.stack, self)
        self.addDockWidget(Qt.DockWidgetArea.RightDockWidgetArea, self.inspector)
        self.inspector.show()    # affiché dès l'ouverture (page « Contour »)
        self._build_actions()
        self._build_toolbar()
        self.stack.cleanChanged.connect(self._update_title)
        self.stack.indexChanged.connect(self._update_style_actions)
        self.scene.editing_changed.connect(self._on_editing)
        self.scene.selectionChanged.connect(self._update_style_actions)
        self.scene.note_requested.connect(self.show_note_panel)
        self.scene.link_activated.connect(self.open_link)
        self.view.zoom_changed.connect(self._on_zoom_changed)
        self.scene.context_menu_requested.connect(self.show_node_menu)
        QApplication.instance().focusChanged.connect(self._on_focus_changed)
        QApplication.clipboard().dataChanged.connect(self._refresh_canvas_actions)
        self.inspector.page_changed.connect(self._sync_inspector_buttons)
        self.inspector.visibilityChanged.connect(self._sync_inspector_buttons)
        self._update_title()
        self._update_style_actions()
        self._sync_inspector_buttons()

        if path:
            self.open_path(Path(path))

    # --- Actions ---------------------------------------------------------
    def _action(self, text, slot, shortcut=None) -> QAction:
        act = QAction(text, self)
        if shortcut is not None:
            act.setShortcut(shortcut)
        act.triggered.connect(lambda _=False: slot())
        return act

    def _build_actions(self) -> None:
        S = QKeySequence
        file_menu = self.menuBar().addMenu("Fichier")
        for act in (
            self._action("Nouveau", self.new_file, S.StandardKey.New),
            self._action("Ouvrir…", self.open_file, S.StandardKey.Open),
            self._action("Enregistrer", self.save, S.StandardKey.Save),
            self._action("Enregistrer sous…", self.save_as, S.StandardKey.SaveAs),
        ):
            file_menu.addAction(act)
        file_menu.addSeparator()
        export_menu = file_menu.addMenu("Exporter vers")
        for key, (label, ext, _) in export_image.IMAGE_FORMATS.items():
            export_menu.addAction(self._action(f"Image {label} ({ext})…", lambda k=key: self.export_image_as(k)))
        export_menu.addSeparator()
        for fmt in formats.all_formats():
            export_menu.addAction(self._action(f"{fmt.label} ({fmt.extension})…", lambda f=fmt: self.export_as(f)))

        edit_menu = self.menuBar().addMenu("Édition")
        self.undo_action = self.stack.createUndoAction(self, "Annuler")
        self.undo_action.setShortcut(S.StandardKey.Undo)
        self.redo_action = self.stack.createRedoAction(self, "Rétablir")
        self.redo_action.setShortcut(S.StandardKey.Redo)
        edit_menu.addAction(self.undo_action)
        edit_menu.addAction(self.redo_action)
        edit_menu.addSeparator()
        # Vraies actions à raccourci (affichés par le menu, y compris le menu natif de macOS).
        # Elles ne sont actives que si la carte a le focus et qu'aucun texte n'est en cours
        # d'édition, pour ne jamais gêner la saisie (nœud, note, champs de l'Inspecteur).
        Key = Qt.Key
        self.cut_action = self._canvas_action("Couper", self.scene.cut_selection, [S.StandardKey.Cut])
        self.copy_action = self._canvas_action("Copier", self.scene.copy_selection, [S.StandardKey.Copy])
        self.paste_action = self._canvas_action("Coller", self.scene.paste, [S.StandardKey.Paste])
        for act in (self.cut_action, self.copy_action, self.paste_action):
            edit_menu.addAction(act)
        edit_menu.addSeparator()
        self.add_child_action = self._canvas_action("Nouvel enfant", self.scene.add_child, [Key.Key_Tab])
        self.add_sibling_action = self._canvas_action("Nouveau frère", self.scene.add_sibling,
                                                      [Key.Key_Return, Key.Key_Enter])
        self.add_parent_action = self._canvas_action("Nouveau parent", self.scene.add_parent, ["Ctrl+Return"])
        self.edit_text_action = self._canvas_action("Modifier le texte", self.edit_selected_text, [Key.Key_F2])
        self.fold_action = self._canvas_action("Replier / déplier les enfants", self.scene.toggle_collapse,
                                               [Key.Key_Space])
        self.delete_action = self._canvas_action("Supprimer", self.scene.delete_selected,
                                                 [Key.Key_Backspace, Key.Key_Delete])
        for act in (self.add_child_action, self.add_sibling_action, self.add_parent_action,
                    self.edit_text_action, self.fold_action):
            edit_menu.addAction(act)
        edit_menu.addSeparator()
        edit_menu.addAction(self.delete_action)

        self._build_style_actions()
        self._build_content_actions()

        view_menu = self.menuBar().addMenu("Affichage")
        view_menu.addAction(self._action("Zoom avant", lambda: self.view.zoom_by(1.2), S.StandardKey.ZoomIn))
        view_menu.addAction(self._action("Zoom arrière", lambda: self.view.zoom_by(1 / 1.2), S.StandardKey.ZoomOut))
        view_menu.addAction(self._action("Taille réelle", self.view.reset_zoom, "Ctrl+1"))
        view_menu.addAction(self._action("Ajuster à la fenêtre", self.view.fit_all, "Ctrl+0"))
        view_menu.addAction(self._action("Centrer sur le nœud principal", self.view.center_on_root, "Ctrl+Shift+0"))
        view_menu.addSeparator()
        inspector_menu = view_menu.addMenu("Inspecteur")
        for key, label in PAGES:
            inspector_menu.addAction(self._action(label, lambda k=key: self._inspector_button(k)))

    # --- Actions de la carte (raccourcis, menu contextuel) -------------------------
    @staticmethod
    def _sequence(shortcut) -> QKeySequence:
        if isinstance(shortcut, QKeySequence):
            return shortcut
        return QKeySequence(shortcut)

    def _canvas_action(self, text: str, slot, shortcuts: list) -> QAction:
        """Action à raccourci, limitée à la carte : le raccourci n'existe que si elle a le focus."""
        act = QAction(text, self)
        act.setShortcuts([self._sequence(sc) for sc in shortcuts])
        act.setShortcutContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        act.triggered.connect(lambda _=False: slot())
        self.view.addAction(act)
        return act

    def _on_focus_changed(self, _old, new) -> None:
        if isinstance(new, (QMenuBar, QMenu)):
            return   # ouvrir un menu ne change pas la destination du clavier
        self._canvas_has_focus = new is not None and (new is self.view or self.view.isAncestorOf(new))
        self._refresh_canvas_actions()

    def _refresh_canvas_actions(self, *_, force_focus: bool = False) -> None:
        if not isValid(self.scene):
            return
        scene = self.scene
        active = (force_focus or self._canvas_has_focus) and not scene.is_editing()
        nodes = scene.selected_nodes()
        with_children = [n for n in nodes if n.children]
        self.add_child_action.setEnabled(active)
        self.add_sibling_action.setEnabled(active)
        self.add_parent_action.setEnabled(active and len(nodes) == 1 and nodes[0].parent is not None)
        self.edit_text_action.setEnabled(active and len(nodes) == 1)
        self.fold_action.setEnabled(active and bool(with_children))
        self.delete_action.setEnabled(active and any(n.parent is not None for n in nodes))
        self.copy_action.setEnabled(active and bool(nodes))
        self.cut_action.setEnabled(active and bool(nodes) and all(n.parent is not None for n in nodes))
        self.paste_action.setEnabled(active and scene.can_paste())
        all_collapsed = bool(with_children) and all(n.collapsed for n in with_children)
        self.fold_action.setText(
            "Déplier les enfants" if all_collapsed
            else "Replier les enfants" if with_children
            else "Replier / déplier les enfants"
        )

    def edit_selected_text(self) -> None:
        node = self.scene.selected_node()
        if node is not None:
            self.scene.start_edit(node)

    def _menu_entry(self, menu: QMenu, main: QAction, slot) -> QAction:
        """Entrée de menu contextuel : même libellé, raccourci affiché et état que l'action du menu
        Édition, mais liée au nœud cliqué. Son raccourci est purement décoratif (contexte « widget »
        sans widget) : le vrai raccourci reste celui de l'action principale, il n'y a pas de conflit."""
        act = QAction(main.text(), menu)
        act.setShortcuts(main.shortcuts())
        act.setShortcutContext(Qt.ShortcutContext.WidgetShortcut)
        act.setEnabled(main.isEnabled())
        act.triggered.connect(lambda _=False: slot())
        menu.addAction(act)
        return act

    def show_node_menu(self, node, global_pos) -> None:
        """Clic droit sur un nœud : presse-papiers, repli des enfants, pages de l'Inspecteur."""
        self._refresh_canvas_actions(force_focus=True)   # le clic droit donne le focus à la carte
        scene = self.scene
        menu = QMenu(self)
        self._menu_entry(menu, self.cut_action, scene.cut_selection)
        self._menu_entry(menu, self.copy_action, scene.copy_selection)
        self._menu_entry(menu, self.paste_action, lambda: scene.paste(node))   # colle chez le nœud cliqué
        menu.addSeparator()
        self._menu_entry(menu, self.fold_action, scene.toggle_collapse)
        menu.addSeparator()
        pages = menu.addMenu("Afficher dans l'inspecteur")
        for key, label in PAGES:
            pages.addAction(label, lambda k=key: self.show_page_for(node, k))
        try:
            self._exec_menu(menu, global_pos)
        finally:
            self._refresh_canvas_actions()

    def _exec_menu(self, menu: QMenu, global_pos) -> None:
        """Affiche le menu et attend le choix (méthode à part : les tests la remplacent)."""
        menu.exec(global_pos)

    def show_page_for(self, node, key: str) -> None:
        """Affiche une page de l'Inspecteur pour le nœud cliqué.

        Les pages Couleur, Icônes et Style gardent une sélection multiple qui contient le nœud ;
        les pages Contour et Note se règlent sur ce seul nœud.
        """
        keep_selection = key in ("color", "icons", "style") and node in self.scene.selected_nodes()
        if not keep_selection:
            self.scene.reveal_and_select(node)
        if key == "note":
            self.show_note_panel(node)
        else:
            self.inspector.show_page(key)

    # --- Barre d'outils ------------------------------------------------------
    def _tool_action(self, text: str, icon: str, slot, tip: str | None = None, checkable: bool = False) -> QAction:
        act = QAction(ui_icon(icon), text, self)
        act.setToolTip(tip or text)
        act.setCheckable(checkable)
        act.triggered.connect(lambda _=False: slot())
        return act

    def _build_toolbar(self) -> None:
        bar = QToolBar("Outils", self)
        bar.setObjectName("mainToolbar")
        bar.setMovable(False)
        bar.setIconSize(QSize(22, 22))
        bar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, bar)
        self.toolbar = bar
        scene, view = self.scene, self.view

        # --- fichier
        self.tb_open = self._tool_action("Ouvrir", "folder-open", lambda: self.open_file(), "Ouvrir ou importer une carte")
        self.tb_save = self._tool_action("Enregistrer", "save", lambda: self.save(), "Enregistrer la carte")
        self.tb_save_as = self._tool_action("Enreg. sous", "file-down", lambda: self.save_as(), "Enregistrer sous un autre nom")
        self.tb_close = self._tool_action("Fermer", "x", lambda: self.close(), "Fermer la carte et quitter")
        for act in (self.tb_open, self.tb_save, self.tb_save_as, self.tb_close):
            bar.addAction(act)
        bar.addSeparator()

        # --- annuler / rétablir
        self.tb_undo = self._tool_action("Défaire", "undo-2", self.stack.undo)
        self.tb_redo = self._tool_action("Refaire", "redo-2", self.stack.redo)
        for act, can_signal, text_signal, label in (
            (self.tb_undo, self.stack.canUndoChanged, self.stack.undoTextChanged, "Défaire"),
            (self.tb_redo, self.stack.canRedoChanged, self.stack.redoTextChanged, "Refaire"),
        ):
            act.setEnabled(False)
            can_signal.connect(act.setEnabled)
            text_signal.connect(lambda t, a=act, l=label: a.setToolTip(f"{l} : {t}" if t else l))
        bar.addAction(self.tb_undo)
        bar.addAction(self.tb_redo)
        bar.addSeparator()

        # --- ajouter un nœud (enfant / parent / frère) et supprimer
        menu = QMenu(self)
        self.tb_add_child = menu.addAction("Nœud enfant", scene.add_child)
        self.tb_add_parent = menu.addAction("Nœud parent", scene.add_parent)
        self.tb_add_sibling = menu.addAction("Nœud frère", scene.add_sibling)
        self.tb_add = QToolButton()
        self.tb_add.setText("Nœud")
        self.tb_add.setIcon(ui_icon("plus"))
        self.tb_add.setToolTip("Ajouter un nœud enfant (flèche : parent ou frère)")
        self.tb_add.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.tb_add.setPopupMode(QToolButton.ToolButtonPopupMode.MenuButtonPopup)
        self.tb_add.setMenu(menu)
        self.tb_add.clicked.connect(lambda: scene.add_child())
        bar.addWidget(self.tb_add)
        self.tb_delete = self._tool_action("Supprimer", "trash-2", scene.delete_selected, "Supprimer la sélection")
        bar.addAction(self.tb_delete)
        bar.addSeparator()

        # --- zoom et centrage
        zoom_menu = QMenu(self)
        for percent in (25, 50, 75, 100, 150, 200, 300):
            zoom_menu.addAction(f"{percent} %", lambda p=percent: view.set_zoom(p / 100))
        zoom_menu.addSeparator()
        zoom_menu.addAction("Ajuster à la fenêtre", view.fit_all)
        self.tb_zoom = QToolButton()
        self.tb_zoom.setText("100 %")
        self.tb_zoom.setIcon(ui_icon("zoom-in"))
        self.tb_zoom.setToolTip("Niveau de zoom")
        self.tb_zoom.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
        self.tb_zoom.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.tb_zoom.setMenu(zoom_menu)
        self.tb_zoom.setMinimumWidth(58)
        bar.addWidget(self.tb_zoom)
        self.tb_center = self._tool_action("Centrer", "locate-fixed", view.center_on_root, "Centrer sur le nœud principal")
        bar.addAction(self.tb_center)

        # --- boutons de l'Inspecteur, alignés à droite
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        bar.addWidget(spacer)
        self.inspector_actions: dict[str, QAction] = {}
        for key, label, icon in (
            ("outline", "Contour", "list-tree"), ("note", "Note", "sticky-note"),
            ("color", "Couleur", "palette"), ("icons", "Icônes", "smile"), ("style", "Style", "paintbrush"),
        ):
            act = self._tool_action(label, icon, lambda k=key: self._inspector_button(k),
                                    f"Inspecteur : {label}", checkable=True)
            self.inspector_actions[key] = act
            bar.addAction(act)

    def _inspector_button(self, key: str) -> None:
        if not self.inspector.isHidden() and self.inspector.current_key == key:
            self.inspector.hide()          # un second clic sur le bouton actif referme l'Inspecteur
        else:
            self.inspector.show_page(key)
        self._sync_inspector_buttons()

    def _sync_inspector_buttons(self, *_) -> None:
        shown = not self.inspector.isHidden()
        for key, act in self.inspector_actions.items():
            act.setChecked(shown and self.inspector.current_key == key)

    def _on_zoom_changed(self, factor: float) -> None:
        self.tb_zoom.setText(f"{round(factor * 100)} %")

    # --- Styles ------------------------------------------------------------
    def _pick_color(self, title: str, key: str, initial: QColor | None = None) -> None:
        color = QColorDialog.getColor(initial or QColor("white"), self, title)
        if color.isValid():
            self.scene.apply_style({key: color.name().upper()})

    def _toggle_flag(self, key: str, checked: bool) -> None:
        self.scene.apply_style({key: checked})

    def _build_style_actions(self) -> None:
        style_menu = self.menuBar().addMenu("Style")
        scene = self.scene
        self.style_actions: list[QAction] = []

        def add(menu, act: QAction) -> QAction:
            menu.addAction(act)
            self.style_actions.append(act)
            return act

        branch = add(style_menu, self._action(
            "Couleur de la branche…",
            lambda: self._pick_color("Couleur de la branche", "color",
                                     branch_color(scene.selected_node()) if scene.selected_node() else None)))
        add(style_menu, self._action("Couleur de remplissage…",
                                     lambda: self._pick_color("Couleur de remplissage", "fill")))
        add(style_menu, self._action("Sans remplissage", lambda: scene.apply_style({"fill": "none"})))
        add(style_menu, self._action("Couleur du texte…",
                                     lambda: self._pick_color("Couleur du texte", "text_color")))
        style_menu.addSeparator()
        shape_menu = style_menu.addMenu("Forme")
        for key, label in SHAPE_LABELS.items():
            add(shape_menu, self._action(label, lambda k=key: scene.apply_style({"shape": k})))
        style_menu.addSeparator()
        self.bold_action = add(style_menu, QAction("Gras", self, checkable=True))
        self.bold_action.setShortcut(QKeySequence.StandardKey.Bold)
        self.bold_action.triggered.connect(lambda checked: self._toggle_flag("bold", checked))
        self.italic_action = add(style_menu, QAction("Italique", self, checkable=True))
        self.italic_action.setShortcut(QKeySequence.StandardKey.Italic)
        self.italic_action.triggered.connect(lambda checked: self._toggle_flag("italic", checked))
        style_menu.addSeparator()
        add(style_menu, self._action("Réinitialiser le style", lambda: scene.apply_style(dict(RESET_ALL))))
        add(style_menu, self._action("Afficher l'inspecteur de style", lambda: self.inspector.show_page("style")))

    @property
    def note_edit(self):
        """Champ de saisie de la note (page « Note » de l'Inspecteur)."""
        return self.inspector.note_page.edit

    # --- Notes, liens, icônes ------------------------------------------------
    def _build_content_actions(self) -> None:
        menu = self.menuBar().addMenu("Contenu")
        scene = self.scene

        def current() -> object:
            return scene.selected_node()

        def add(act: QAction) -> QAction:
            menu.addAction(act)
            self.style_actions.append(act)
            return act

        add(self._action("Note…", lambda: current() and self.show_note_panel(current()), "Ctrl+Shift+N"))
        add(self._action("Lien…", lambda: current() and self.edit_link(current()), "Ctrl+K"))
        self.open_link_action = self._action("Ouvrir le lien", lambda: current() and self.open_link(current()))
        menu.addAction(self.open_link_action)
        menu.addSeparator()
        add(self._action("Icône…", lambda: self.inspector.show_page("icons")))
        add(self._action("Aucune icône", lambda: scene.set_data(scene.selected_nodes(), icon=None)))
        menu.addSeparator()
        add(self._action("Supprimer la note", lambda: current() and scene.set_data(current(), note="")))
        add(self._action("Supprimer le lien", lambda: current() and scene.set_data(current(), link=None)))

    def show_note_panel(self, node=None) -> None:
        """Affiche la note du nœud dans l'Inspecteur et place le curseur dedans."""
        if node is not None and node not in self.scene.selected_nodes():
            self.scene.select_node(node)
        self.inspector.show_page("note")
        self.note_edit.setFocus()

    def edit_link(self, node) -> None:
        text, ok = QInputDialog.getText(
            self, "Lien", "Adresse (http://, https:// ou mailto:) — vide pour supprimer :", text=node.link or ""
        )
        self.view.setFocus()
        if not ok:
            return
        link = normalize_link(text)
        if link:
            link = complete_link(link)  # « exemple.com » -> « https://exemple.com »
        if link and not is_openable_link(link):
            QMessageBox.warning(self, "Lien refusé", f"Seuls ces types d'adresses sont acceptés : {', '.join(OPENABLE_SCHEMES)}.")
            return
        self.scene.set_data(node, link=link)

    def open_link(self, node) -> None:
        if not is_openable_link(node.link):
            if node.link:
                QMessageBox.information(
                    self, "Lien non ouvert",
                    f"Ce lien n'est pas ouvert automatiquement (types acceptés : {', '.join(OPENABLE_SCHEMES)}) :\n{node.link}",
                )
            return
        QDesktopServices.openUrl(QUrl(node.link))

    def _update_style_actions(self) -> None:
        nodes = self.scene.selected_nodes()
        enabled = bool(nodes) and not self.scene.is_editing()
        for act in self.style_actions:
            act.setEnabled(enabled)
        node = nodes[0] if nodes else None
        bold = node.style.bold if node and node.style.bold is not None else bool(node and (node.parent is None or node.parent.parent is None))
        editing = self.scene.is_editing()
        self.open_link_action.setEnabled(bool(node and node.link) and not editing)
        self.tb_add_parent.setEnabled(bool(node and node.parent) and not editing)
        self.tb_add.setEnabled(not editing)
        self.tb_delete.setEnabled(any(n.parent is not None for n in nodes) and not editing)
        self.bold_action.setChecked(bold)
        self.italic_action.setChecked(bool(node and node.style.italic))
        self._refresh_canvas_actions()

    def _on_editing(self, editing: bool) -> None:
        self._update_style_actions()
        if editing:
            self.undo_action.setEnabled(False)
            self.redo_action.setEnabled(False)
        else:
            self.undo_action.setEnabled(self.stack.canUndo())
            self.redo_action.setEnabled(self.stack.canRedo())
            self.view.setFocus()

    def _update_title(self, *_) -> None:
        name = self.path.name if self.path else (self.doc_name or "Sans titre")
        self.setWindowTitle(f"{name}[*] — EasyGhost")
        self.setWindowModified(not self.stack.isClean())

    # --- Fichiers --------------------------------------------------------
    def _maybe_save(self) -> bool:
        """Renvoie False si l'utilisateur annule."""
        self.inspector.commit_pending()
        if self.stack.isClean():
            return True
        box = QMessageBox.question(
            self,
            "Modifications non enregistrées",
            "Enregistrer les modifications avant de continuer ?",
            QMessageBox.StandardButton.Save
            | QMessageBox.StandardButton.Discard
            | QMessageBox.StandardButton.Cancel,
        )
        if box == QMessageBox.StandardButton.Save:
            return self.save()
        return box == QMessageBox.StandardButton.Discard

    def _load_map(self, mindmap: MindMap, path: Path | None, doc_name: str | None = None) -> None:
        self.scene.set_mindmap(mindmap)
        self.stack.clear()
        self.stack.setClean()
        self.path = path
        self.doc_name = doc_name
        self._update_title()
        self.view.resetTransform()
        self.view.zoom_changed.emit(1.0)
        self.view.centerOn(0, 0)
        self.view.setFocus()

    def new_file(self) -> None:
        if self._maybe_save():
            self._load_map(MindMap(), None)

    def open_file(self) -> None:
        if not self._maybe_save():
            return
        name, _ = QFileDialog.getOpenFileName(self, "Ouvrir ou importer", "", _open_filter())
        if name:
            self.open_path(Path(name))

    def open_requested(self, path: str) -> None:
        """Ouverture demandée par le système (Finder, Dock) : propose d'abord d'enregistrer."""
        if self._maybe_save():
            self.open_path(Path(path))

    def open_path(self, path: Path) -> None:
        fmt = formats.format_for_path(path, for_import=True)
        warnings: list[str] = []
        try:
            if fmt is None:
                mindmap = storage.load(path)
            else:
                result = fmt.import_file(path)
                mindmap, warnings = result.mindmap, result.warnings
        except (OSError, ValueError, KeyError) as exc:
            QMessageBox.critical(self, "Erreur", f"Impossible d'ouvrir {path.name} :\n{exc}")
            return
        if fmt is None:
            self._load_map(mindmap, path)
        else:
            # Document importé : il faut l'enregistrer au format natif pour le garder.
            self._load_map(mindmap, None, doc_name=path.stem)
            self.statusBar().showMessage(f"{path.name} importé ({fmt.label})", 6000)
        if warnings:
            QMessageBox.information(self, "Import", "\n".join(f"• {w}" for w in warnings))

    def export_image_as(self, key: str) -> None:
        self.inspector.commit_pending()
        label, ext, function = export_image.IMAGE_FORMATS[key]
        base = (self.path.stem if self.path else self.doc_name) or "carte"
        name, _ = QFileDialog.getSaveFileName(
            self, f"Exporter en image {label}", f"{base}{ext}", f"{label} (*{ext})"
        )
        if not name:
            return
        path = Path(name)
        if path.suffix.lower() != ext:
            path = path.with_name(path.name + ext)
        try:
            if key == "png":
                function(self.scene, path)
            else:
                function(self.scene, path, self.scene.mindmap.root.text)
        except (OSError, ValueError) as exc:
            QMessageBox.critical(self, "Erreur", f"Impossible d'exporter :\n{exc}")
            return
        self.statusBar().showMessage(f"Exporté vers {path.name}", 6000)

    def export_as(self, fmt: formats.Format) -> None:
        self.inspector.commit_pending()
        base = (self.path.stem if self.path else self.doc_name) or "carte"
        name, _ = QFileDialog.getSaveFileName(
            self, f"Exporter vers {fmt.label}", f"{base}{fmt.extension}", f"{fmt.label} (*{fmt.extension})"
        )
        if not name:
            return
        path = Path(name)
        if path.suffix.lower() != fmt.extension:
            path = path.with_name(path.name + fmt.extension)
        try:
            warnings = fmt.export_file(path, self.scene.mindmap)
        except OSError as exc:
            QMessageBox.critical(self, "Erreur", f"Impossible d'exporter :\n{exc}")
            return
        self.statusBar().showMessage(f"Exporté vers {path.name}", 6000)
        if warnings:
            QMessageBox.information(self, "Export", "\n".join(f"• {w}" for w in warnings))

    def save(self) -> bool:
        if self.path is None:
            return self.save_as()
        return self._write(self.path)

    def save_as(self) -> bool:
        suggestion = f"{self.doc_name}{NATIVE_EXT}" if self.doc_name and not self.path else ""
        name, _ = QFileDialog.getSaveFileName(self, "Enregistrer sous", suggestion, FILE_FILTER)
        if not name:
            return False
        path = Path(name)
        if not path.suffix:
            path = path.with_suffix(NATIVE_EXT)
        return self._write(path)

    def _write(self, path: Path) -> bool:
        self.inspector.commit_pending()
        try:
            storage.save(path, self.scene.mindmap)
        except OSError as exc:
            QMessageBox.critical(self, "Erreur", f"Impossible d'enregistrer :\n{exc}")
            return False
        self.path = path
        self.stack.setClean()
        self._update_title()
        return True

    def closeEvent(self, event) -> None:
        if self._maybe_save():
            event.accept()
        else:
            event.ignore()
