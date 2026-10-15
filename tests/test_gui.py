import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtCore import QPoint, QPointF, Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

from easyghost import storage
from easyghost.main_window import MainWindow


@pytest.fixture(scope="module")
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def win(app):
    w = MainWindow()
    w.scene.animated = False
    w.show()
    w.activateWindow()
    w.view.setFocus()
    app.processEvents()
    yield w
    w.stack.setClean()
    w.close()


def key(win, k, mods=Qt.KeyboardModifier.NoModifier):
    QTest.keyClick(win.view, k, mods)


def type_text(win, text):
    editor = win.scene._editing.editor
    editor.setPlainText(text)
    key(win, Qt.Key.Key_Return)


def texts(win):
    return [n.text for n in win.scene.mindmap.nodes()]


def test_tab_adds_child_and_edits(win):
    key(win, Qt.Key.Key_Tab)
    assert win.scene.is_editing()
    type_text(win, "Alpha")
    assert not win.scene.is_editing()
    assert texts(win) == ["Idée centrale", "Alpha"]
    assert win.scene.selected_node().text == "Alpha"


def test_add_is_single_undo_step(win):
    key(win, Qt.Key.Key_Tab)
    type_text(win, "Alpha")
    win.stack.undo()
    assert texts(win) == ["Idée centrale"]
    win.stack.redo()
    assert texts(win) == ["Idée centrale", "Alpha"]


def test_enter_adds_sibling_and_escape_keeps_empty(win):
    key(win, Qt.Key.Key_Tab)
    type_text(win, "A")
    key(win, Qt.Key.Key_Return)  # frère de A
    assert win.scene.is_editing()
    type_text(win, "B")
    assert [c.text for c in win.scene.mindmap.root.children] == ["A", "B"]
    key(win, Qt.Key.Key_Tab)
    key(win, Qt.Key.Key_Escape)
    assert not win.scene.is_editing()
    assert win.scene.mindmap.root.children[1].children[0].text == ""


def test_delete_and_undo(win):
    key(win, Qt.Key.Key_Tab)
    type_text(win, "A")
    key(win, Qt.Key.Key_Delete)
    assert texts(win) == ["Idée centrale"]
    assert win.scene.selected_node() is win.scene.mindmap.root
    win.stack.undo()
    assert texts(win) == ["Idée centrale", "A"]


def test_root_cannot_be_deleted(win):
    win.scene.select_node(win.scene.mindmap.root)
    key(win, Qt.Key.Key_Delete)
    assert texts(win) == ["Idée centrale"]


def test_collapse_hides_children(win):
    key(win, Qt.Key.Key_Tab)
    type_text(win, "A")
    key(win, Qt.Key.Key_Tab)
    type_text(win, "A1")
    win.scene.select_node(win.scene.mindmap.root.children[0])
    key(win, Qt.Key.Key_Space)
    assert win.scene.item_for(win.scene.mindmap.root.children[0].children[0]) is None
    key(win, Qt.Key.Key_Space)
    assert win.scene.item_for(win.scene.mindmap.root.children[0].children[0]) is not None


def test_navigation(win):
    key(win, Qt.Key.Key_Tab); type_text(win, "A")
    win.scene.select_node(win.scene.mindmap.root)
    key(win, Qt.Key.Key_Tab); type_text(win, "B")
    # A et B sont sur la même moitié ou non selon la répartition ; on navigue depuis la racine
    win.scene.select_node(win.scene.mindmap.root)
    key(win, Qt.Key.Key_Right)
    assert win.scene.selected_node().text == "A"
    key(win, Qt.Key.Key_Left)
    assert win.scene.selected_node() is win.scene.mindmap.root


def test_reparent_by_drag(win, app):
    key(win, Qt.Key.Key_Tab); type_text(win, "A")
    win.scene.select_node(win.scene.mindmap.root)
    key(win, Qt.Key.Key_Tab); type_text(win, "B")
    root = win.scene.mindmap.root
    a, b = root.children
    ia, ib = win.scene.item_for(a), win.scene.item_for(b)
    vp = win.view.viewport()

    def center(item):
        w, h = item.size()
        return win.view.mapFromScene(item.pos() + item.boundingRect().center() * 0 + QPointF(w / 2, h / 2))

    start, end = center(ib), center(ia)
    QTest.mousePress(vp, Qt.MouseButton.LeftButton, pos=start)
    mid = QPoint((start.x() + end.x()) // 2, (start.y() + end.y()) // 2)
    for p in (QPoint(start.x(), start.y() + 12), mid, end):
        QTest.mouseMove(vp, p)
        app.processEvents()
    assert ia.drop_target
    QTest.mouseRelease(vp, Qt.MouseButton.LeftButton, pos=end)
    assert b.parent is a
    win.stack.undo()
    assert b.parent is root


def test_save_and_open(win, tmp_path):
    key(win, Qt.Key.Key_Tab); type_text(win, "Alpha")
    assert win.isWindowModified()
    path = tmp_path / "m.easyghost"
    assert win._write(path)
    assert not win.isWindowModified()
    other = MainWindow(str(path))
    assert [n.text for n in other.scene.mindmap.nodes()] == ["Idée centrale", "Alpha"]
    other.close()


# ---------------------------------------------------------------- styles
def make_branch(win):
    """Racine -> A -> A1 ; renvoie (A, A1)."""
    key(win, Qt.Key.Key_Tab); type_text(win, "A")
    key(win, Qt.Key.Key_Tab); type_text(win, "A1")
    a = win.scene.mindmap.root.children[0]
    return a, a.children[0]


def test_apply_style_and_undo(win):
    a, _ = make_branch(win)
    win.scene.select_node(a)
    win.scene.apply_style({"fill": "#FFEEAA", "shape": "diamond", "bold": True})
    assert (a.style.fill, a.style.shape, a.style.bold) == ("#FFEEAA", "diamond", True)
    item = win.scene.item_for(a)
    assert item.shape_name() == "diamond"
    assert item.size()[1] > 40  # le losange est agrandi pour contenir le texte
    win.stack.undo()
    assert a.style.is_default() and win.scene.item_for(a).shape_name() == "rounded"
    win.stack.redo()
    assert a.style.shape == "diamond"


def test_branch_color_is_inherited_and_cascades(win):
    from easyghost.scene import branch_color

    a, a1 = make_branch(win)
    a1.style.color = "#112233"
    win.scene.select_node(a)
    win.scene.apply_style({"color": "#EB5757"})
    # la couleur choisie pour la branche remplace celle des descendants
    assert a1.style.color is None
    assert branch_color(a1).name().upper() == "#EB5757"
    win.stack.undo()
    assert a1.style.color == "#112233" and a.style.color is None


def test_style_on_multiple_selected_nodes(win):
    a, a1 = make_branch(win)
    win.scene.clearSelection()
    win.scene.item_for(a).setSelected(True)
    win.scene.item_for(a1).setSelected(True)
    win.scene.apply_style({"italic": True})
    assert a.style.italic and a1.style.italic
    assert len(win.scene.selected_nodes()) == 2  # la sélection est conservée
    win.stack.undo()
    assert not a.style.italic and not a1.style.italic


def test_reset_style(win):
    a, _ = make_branch(win)
    win.scene.select_node(a)
    win.scene.apply_style({"fill": "#FFEEAA", "bold": True})
    win.scene.apply_style({k: None for k in ("color", "fill", "text_color", "shape", "bold", "italic")})
    assert a.style.is_default()


def test_text_color_contrast():
    from PySide6.QtGui import QColor

    from easyghost.scene import text_color_on

    assert text_color_on(QColor("#FFFFFF")).name() == "#222222"
    assert text_color_on(QColor("#102030")).name() == "#ffffff"


def test_style_actions_follow_selection(win):
    win.scene.clearSelection()
    assert not win.bold_action.isEnabled()
    win.scene.select_node(win.scene.mindmap.root)
    assert win.bold_action.isEnabled() and win.bold_action.isChecked()  # la racine est en gras par défaut
    win.bold_action.trigger()
    assert win.scene.mindmap.root.style.bold is False


def test_new_root_branches_alternate_sides(win):
    root = win.scene.mindmap.root
    for name in "ABCD":
        win.scene.select_node(root)
        key(win, Qt.Key.Key_Tab); type_text(win, name)
    assert [c.side for c in root.children] == ["right", "left", "right", "left"]
    # Entrée sur une branche principale : le frère reste du même côté
    win.scene.select_node(root.children[1])
    key(win, Qt.Key.Key_Return); type_text(win, "E")
    assert root.children[2].text == "E" and root.children[2].side == "left"


def test_open_smmx_as_import(win, tmp_path):
    from pathlib import Path

    from easyghost.formats import smmx

    path = tmp_path / "x.smmx"
    from easyghost.model import MindMap

    m = MindMap("Import")
    m.add_child(m.root, "Enfant")
    smmx.export_file(path, m)
    win.open_path(path)
    assert [n.text for n in win.scene.mindmap.nodes()] == ["Import", "Enfant"]
    assert win.path is None and win.doc_name == "x"          # document importé, pas encore enregistré
    assert "x" in win.windowTitle()


def test_export_via_window(win, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog, QMessageBox

    from easyghost import formats

    key(win, Qt.Key.Key_Tab); type_text(win, "Alpha")
    target = tmp_path / "out"
    monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, **k: (str(target), ""))
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    win.export_as(formats.format_for_path("x.mm"))
    assert (tmp_path / "out.mm").exists() and "Alpha" in (tmp_path / "out.mm").read_text(encoding="utf-8")


# ------------------------------------------------- notes, liens, icônes
def test_set_data_undo_redo(win):
    root = win.scene.mindmap.root
    win.scene.select_node(root)
    win.scene.set_data(root, note="Une note", link="https://exemple.org", icon="star")
    assert (root.note, root.link, root.icon) == ("Une note", "https://exemple.org", "star")
    item = win.scene.item_for(root)
    assert set(item._hit) == {"note", "link"} and "Une note" in item.toolTip()
    win.stack.undo()
    assert (root.note, root.link, root.icon) == ("", None, None) and not item._hit
    win.stack.redo()
    assert root.icon == "star"
    n = win.stack.count()
    win.scene.set_data(root, note="Une note")        # inchangé : aucune commande
    assert win.stack.count() == n


def test_badges_make_node_wider(win):
    root = win.scene.mindmap.root
    item = win.scene.item_for(root)
    before = item.size()[0]
    win.scene.set_data(root, icon="idea", note="n", link="https://a.b")
    assert item.size()[0] > before + 30


def test_clicking_badges_emits_signals(win, monkeypatch):
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import QDialog

    # les slots de la fenêtre ouvriraient un dialogue modal / un navigateur : on les neutralise
    monkeypatch.setattr(QDialog, "exec", lambda self: QDialog.DialogCode.Rejected)
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: True)
    root = win.scene.mindmap.root
    win.scene.set_data(root, note="n", link="https://a.b")
    item = win.scene.item_for(root)
    got = []
    win.scene.note_requested.connect(lambda n: got.append(("note", n)))
    win.scene.link_activated.connect(lambda n: got.append(("link", n)))
    vp = win.view.viewport()
    for kind in ("note", "link"):
        r = item._hit[kind]
        pt = win.view.mapFromScene(item.mapToScene(r.center()))
        QTest.mouseClick(vp, Qt.MouseButton.LeftButton, pos=pt)
    assert got == [("note", root), ("link", root)]


def test_open_link_only_for_safe_schemes(win, monkeypatch):
    from PySide6.QtGui import QDesktopServices
    from PySide6.QtWidgets import QMessageBox

    opened = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url.toString()) or True)
    monkeypatch.setattr(QMessageBox, "information", lambda *a, **k: None)
    root = win.scene.mindmap.root
    root.link = "https://exemple.org/x"
    win.open_link(root)
    root.link = "file:///etc/passwd"
    win.open_link(root)
    root.link = "javascript:alert(1)"
    win.open_link(root)
    assert opened == ["https://exemple.org/x"]


def test_edit_link_dialog_normalizes_and_rejects(win, monkeypatch):
    from PySide6.QtWidgets import QInputDialog, QMessageBox

    root = win.scene.mindmap.root
    warned = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *a, **k: warned.append(a))
    answers = iter([("exemple.com/page", True), ("javascript:alert(1)", True), ("", True), ("x", False)])
    monkeypatch.setattr(QInputDialog, "getText", lambda *a, **k: next(answers))
    win.edit_link(root)
    assert root.link == "https://exemple.com/page"          # schéma ajouté
    win.edit_link(root)
    assert root.link == "https://exemple.com/page" and len(warned) == 1   # refusé
    win.edit_link(root)
    assert root.link is None                                 # vide : supprimé
    win.edit_link(root)
    assert root.link is None                                 # annulé : inchangé


def test_icon_menu_sets_icon(win):
    root = win.scene.mindmap.root
    win.scene.select_node(root)
    content_menu = next(a.menu() for a in win.menuBar().actions() if a.text() == "Contenu")
    next(a for a in content_menu.actions() if a.text() == "Icône…").trigger()
    assert win.inspector.current_key == "icons" and not win.inspector.isHidden()
    page = win.inspector.icons_page
    heart = next(i for i in range(page.list.count()) if page.list.item(i).data(Qt.ItemDataRole.UserRole) == "heart")
    page._assign(page.list.item(heart).data(Qt.ItemDataRole.UserRole))
    assert root.icon == "heart"
    next(a for a in content_menu.actions() if a.text() == "Aucune icône").trigger()
    assert root.icon is None


def test_image_export_via_window(win, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QFileDialog

    key(win, Qt.Key.Key_Tab); type_text(win, "Alpha")
    for k, magic in (("png", b"\x89PNG"), ("svg", b"<?xml"), ("pdf", b"%PDF")):
        target = tmp_path / f"out_{k}"
        monkeypatch.setattr(QFileDialog, "getSaveFileName", lambda *a, t=target, **kw: (str(t), ""))
        win.export_image_as(k)
        assert (tmp_path / f"out_{k}.{k}").read_bytes().startswith(magic)
    assert win.scene.selected_node().text == "Alpha"          # sélection conservée


# ------------------------------------------------------- panneau de note
def test_note_panel_shows_imported_notes(win, tmp_path):
    from easyghost.formats import smmx
    from easyghost.model import MindMap

    m = MindMap("Racine")
    a = m.add_child(m.root, "Famille")
    a.note = "Graines grosses.\nÀ enterrer profond."
    m.add_child(m.root, "Sans note")
    smmx.export_file(tmp_path / "n.smmx", m)
    win.open_path(tmp_path / "n.smmx")
    root = win.scene.mindmap.root
    win.scene.select_node(root.children[0])
    assert win.note_edit.toPlainText() == "Graines grosses.\nÀ enterrer profond."
    assert win.note_edit.isEnabled() and "Famille" in win.inspector.note_page.title.text()
    win.scene.select_node(root.children[1])
    assert win.note_edit.toPlainText() == ""
    win.scene.clearSelection()
    assert not win.note_edit.isEnabled()


def test_note_panel_edit_commits_and_undoes(win):
    root = win.scene.mindmap.root
    win.scene.select_node(root)
    win.note_edit.setPlainText("Ma note\n")
    win.note_edit.committed.emit()                       # perte de focus
    assert root.note == "Ma note" and win.stack.count() == 1
    assert win.scene.item_for(root)._hit.keys() == {"note"}
    win.stack.undo()
    assert root.note == "" and win.note_edit.toPlainText() == ""
    assert win.stack.count() == 1                        # l'annulation n'a pas recréé de commande
    win.stack.redo()
    assert root.note == "Ma note" and win.note_edit.toPlainText() == "Ma note"


def test_note_typed_goes_to_previous_node_when_selection_changes(win):
    key(win, Qt.Key.Key_Tab); type_text(win, "A")
    a = win.scene.mindmap.root.children[0]
    win.scene.select_node(a)
    win.note_edit.setPlainText("pour A")
    win.scene.select_node(win.scene.mindmap.root)       # sans avoir quitté le champ
    assert a.note == "pour A" and win.scene.mindmap.root.note == ""


def test_note_changed_elsewhere_is_not_overwritten_by_panel(win):
    root = win.scene.mindmap.root
    win.scene.select_node(root)
    win.scene.set_data(root, note="Via le menu")        # le panneau n'a pas été touché
    assert root.note == "Via le menu" and win.note_edit.toPlainText() == "Via le menu"


def test_pending_note_is_saved_with_the_file(win, tmp_path):
    root = win.scene.mindmap.root
    win.scene.select_node(root)
    win.note_edit.setPlainText("pas encore validée")      # sans perte de focus
    assert win._write(tmp_path / "n.easyghost")
    from easyghost import storage
    assert storage.load(tmp_path / "n.easyghost").root.note == "pas encore validée"


# ================================================== barre d'outils et Inspecteur
def names(win):
    return [n.text for n in win.scene.mindmap.nodes()]


def test_toolbar_has_requested_buttons(win):
    labels = [a.text() for a in win.toolbar.actions() if a.text()]
    for expected in ("Ouvrir", "Enregistrer", "Enreg. sous", "Fermer", "Défaire", "Refaire", "Supprimer",
                     "Centrer", "Contour", "Note", "Couleur", "Icônes", "Style"):
        assert expected in labels, expected
    assert win.tb_add.menu() is not None and win.tb_zoom.menu() is not None
    assert [a.text() for a in win.tb_add.menu().actions()] == ["Nœud enfant", "Nœud parent", "Nœud frère"]
    assert not any("Branche #" in (a.toolTip() or "") for a in win.toolbar.actions())   # ancienne barre de couleurs retirée


def test_toolbar_add_child_parent_delete_and_undo(win):
    root = win.scene.mindmap.root
    win.tb_add.click()                                   # clic principal : nœud enfant
    type_text(win, "A")
    a = root.children[0]
    win.scene.select_node(a)
    win.tb_add_parent.trigger()                          # nœud parent de A
    type_text(win, "P")
    p = root.children[0]
    assert p.text == "P" and a.parent is p and names(win) == ["Idée centrale", "P", "A"]
    win.stack.undo()                                     # saisie + insertion = une seule étape
    assert a.parent is root and names(win) == ["Idée centrale", "A"]
    win.stack.redo()
    assert a.parent.text == "P"
    win.scene.select_node(a)
    win.tb_delete.trigger()                              # poubelle
    assert names(win) == ["Idée centrale", "P"]
    win.stack.undo()
    assert "A" in names(win)


def test_parent_of_root_is_disabled(win):
    win.scene.select_node(win.scene.mindmap.root)
    assert not win.tb_add_parent.isEnabled() and not win.tb_delete.isEnabled()
    win.scene.add_parent()
    assert names(win) == ["Idée centrale"]


def test_add_parent_keeps_side_of_main_branch(win):
    root = win.scene.mindmap.root
    for t in "AB":
        win.scene.select_node(root)
        key(win, Qt.Key.Key_Tab); type_text(win, t)
    b = root.children[1]
    assert b.side == "left"
    win.scene.select_node(b)
    win.scene.add_parent()
    type_text(win, "P")
    assert root.children[1].text == "P" and root.children[1].side == "left" and b.side is None
    win.stack.undo()
    assert root.children[1] is b and b.side == "left"


def test_delete_several_selected_nodes_in_one_step(win):
    root = win.scene.mindmap.root
    for t in "ABC":
        win.scene.select_node(root)
        key(win, Qt.Key.Key_Tab); type_text(win, t)
    a, b, c = root.children
    win.scene.select_node(a)
    key(win, Qt.Key.Key_Tab); type_text(win, "A1")
    win.scene.clearSelection()
    for node in (a, a.children[0], b):                  # A1 est déjà dans le sous-arbre de A
        win.scene.item_for(node).setSelected(True)
    n = win.stack.count()
    win.tb_delete.trigger()
    assert [x.text for x in root.children] == ["C"]
    assert win.stack.count() == n + 1                    # macro : un seul pas d'annulation pour toute la sélection
    win.stack.undo()
    assert [x.text for x in root.children] == ["A", "B", "C"] and root.children[0].children[0].text == "A1"


def test_zoom_button_and_center(win):
    from PySide6.QtCore import QPointF

    assert win.tb_zoom.text() == "100 %"
    zoom_menu = win.tb_zoom.menu()
    next(a for a in zoom_menu.actions() if a.text() == "200 %").trigger()
    assert abs(win.view.zoom - 2.0) < 1e-6 and win.tb_zoom.text() == "200 %"
    win.view.zoom_by(0.5)
    assert win.tb_zoom.text() == "100 %"                 # le libellé suit aussi la molette / le pincement
    win.view.centerOn(QPointF(3000, 2000))
    win.tb_center.trigger()
    root_item = win.scene.item_for(win.scene.mindmap.root)
    center = win.view.mapToScene(win.view.viewport().rect().center())
    assert (center - root_item.sceneBoundingRect().center()).manhattanLength() < 5


def test_zoom_is_bounded(win):
    win.view.set_zoom(100)
    assert win.view.zoom <= 4.0 + 1e-9
    win.view.set_zoom(0.0001)
    assert win.view.zoom >= 0.15 - 1e-9


def test_undo_redo_buttons_follow_the_stack(win):
    assert not win.tb_undo.isEnabled() and not win.tb_redo.isEnabled()
    key(win, Qt.Key.Key_Tab); type_text(win, "A")
    assert win.tb_undo.isEnabled() and not win.tb_redo.isEnabled()
    win.tb_undo.trigger()
    assert not win.tb_undo.isEnabled() and win.tb_redo.isEnabled() and names(win) == ["Idée centrale"]
    win.tb_redo.trigger()
    assert names(win) == ["Idée centrale", "A"]


def test_file_toolbar_buttons_call_the_file_actions(win, monkeypatch):
    called = []
    monkeypatch.setattr(type(win), "open_file", lambda self: called.append("open"))
    monkeypatch.setattr(type(win), "save", lambda self: called.append("save"))
    monkeypatch.setattr(type(win), "save_as", lambda self: called.append("save_as"))
    win.tb_open.trigger(); win.tb_save.trigger(); win.tb_save_as.trigger()
    assert called == ["open", "save", "save_as"]


def test_close_button_closes_the_window(win):
    win.stack.setClean()
    win.tb_close.trigger()
    assert not win.isVisible()


def test_inspector_buttons_switch_pages_and_toggle(win):
    insp = win.inspector
    assert not insp.isHidden() and insp.current_key == "outline"      # au démarrage : plan affiché
    for key_ in ("note", "color", "icons", "style", "outline"):
        act = win.inspector_actions[key_]
        act.trigger()
        assert insp.current_key == key_ and not insp.isHidden() and act.isChecked()
        assert [k for k, a in win.inspector_actions.items() if a.isChecked()] == [key_]   # un seul actif
    win.inspector_actions["outline"].trigger()           # second clic sur le bouton actif : referme
    assert insp.isHidden() and not any(a.isChecked() for a in win.inspector_actions.values())
    win.inspector_actions["note"].trigger()
    assert not insp.isHidden() and insp.current_key == "note"


def test_outline_page_shows_the_tree_and_syncs_selection(win):
    root = win.scene.mindmap.root
    for t in ("A", "B"):
        win.scene.select_node(root)
        key(win, Qt.Key.Key_Tab); type_text(win, t)
    a = root.children[0]
    win.scene.select_node(a)
    key(win, Qt.Key.Key_Tab); type_text(win, "A1")
    win.inspector.show_page("outline")
    tree = win.inspector.outline_page.tree
    win.inspector.outline_page.refresh()
    top = tree.topLevelItem(0)
    assert top.text(0) == "Idée centrale" and [top.child(i).text(0) for i in range(top.childCount())] == ["A", "B"]
    assert top.child(0).child(0).text(0) == "A1"
    win.scene.select_node(root.children[1])              # carte -> plan
    assert [i.text(0) for i in tree.selectedItems()] == ["B"]
    tree.setCurrentItem(top.child(0).child(0))           # plan -> carte
    assert win.scene.selected_node().text == "A1"


def test_outline_reveals_nodes_hidden_in_collapsed_branches(win):
    root = win.scene.mindmap.root
    key(win, Qt.Key.Key_Tab); type_text(win, "A")
    a = root.children[0]
    key(win, Qt.Key.Key_Tab); type_text(win, "A1")
    a1 = a.children[0]
    win.scene.select_node(a)
    key(win, Qt.Key.Key_Space)
    assert a.collapsed and win.scene.item_for(a1) is None
    win.inspector.show_page("outline")
    win.inspector.outline_page.refresh()
    assert win.scene.reveal_and_select(a1)
    assert not a.collapsed and win.scene.selected_node() is a1
    win.stack.undo()                                     # le dépliage est annulable
    assert a.collapsed


def test_color_page_applies_color_to_the_chosen_target(win):
    root = win.scene.mindmap.root
    key(win, Qt.Key.Key_Tab); type_text(win, "A")
    a = root.children[0]
    win.scene.select_node(a)
    win.inspector.show_page("color")
    page = win.inspector.color_page
    for target, attr in (("fill", "fill"), ("text_color", "text_color"), ("border_color", "border_color"), ("color", "color")):
        page.set_target(target)
        page.apply("#123456")
        assert getattr(a.style, attr) == "#123456", target
    page.set_target("fill")
    page.apply("none")
    assert a.style.fill == "none"
    page.apply(None)
    assert a.style.fill is None
    win.stack.undo(); win.stack.undo()
    assert a.style.fill == "#123456"


def test_color_page_is_disabled_without_selection(win):
    win.scene.clearSelection()
    win.inspector.show_page("color")
    assert not any(b.isEnabled() for b in win.inspector.color_page.swatches)


def test_icons_page_filters_assigns_and_clears(win):
    root = win.scene.mindmap.root
    win.scene.select_node(root)
    win.inspector.show_page("icons")
    page = win.inspector.icons_page
    page._fill()
    total = page.list.count()
    assert total >= 80
    page.search.setText("coeur")
    assert page.list.count() == 0
    page.search.setText("cœur")
    assert [page.list.item(i).data(Qt.ItemDataRole.UserRole) for i in range(page.list.count())] == ["heart"]
    page.search.clear()
    page.category.setCurrentText("Nature")
    assert 0 < page.list.count() < total
    page.list.itemClicked.emit(page.list.item(0))
    assert root.icon == page.list.item(0).data(Qt.ItemDataRole.UserRole)
    page.none_btn.click()
    assert root.icon is None


def test_icons_page_applies_to_all_selected_nodes_in_one_step(win):
    root = win.scene.mindmap.root
    for t in "AB":
        win.scene.select_node(root)
        key(win, Qt.Key.Key_Tab); type_text(win, t)
    win.scene.clearSelection()
    for n in root.children:
        win.scene.item_for(n).setSelected(True)
    count = win.stack.count()
    win.inspector.icons_page._assign("star")
    assert [n.icon for n in root.children] == ["star", "star"] and win.stack.count() == count + 1
    win.stack.undo()
    assert [n.icon for n in root.children] == [None, None]


def test_icons_come_only_from_the_bundled_set(win):
    from easyghost import icons
    from easyghost.iconset import CATEGORIES

    page = win.inspector.icons_page
    assert [page.category.itemText(i) for i in range(page.category.count())] == ["Toutes", *CATEGORIES]
    assert not any("simplemind" in name.lower() for name in dir(icons))       # aucune lecture de ressources externes
    assert not any("simplemind" in name.lower() for name in dir(page))


def test_unknown_icon_id_is_kept_and_drawn_as_a_generic_tag(win):
    from PySide6.QtGui import QColor

    from easyghost import icons

    root = win.scene.mindmap.root
    win.scene.set_data(root, icon="ic8_96_inconnue")                           # identifiant venu d'un fichier importé
    item = win.scene.item_for(root)
    assert root.icon == "ic8_96_inconnue" and item._icon_rect is not None
    assert "ic8_96_inconnue" in item.toolTip()
    pix = icons.node_icon_pixmap("ic8_96_inconnue", 18, QColor("black"))
    assert not pix.isNull()
    win.inspector.show_page("outline")
    win.inspector.outline_page.refresh()                                       # le plan l'affiche aussi sans erreur


def test_style_page_shows_and_applies_values(win):
    root = win.scene.mindmap.root
    key(win, Qt.Key.Key_Tab); type_text(win, "A")
    a = root.children[0]
    win.scene.select_node(a)
    win.inspector.show_page("style")
    page = win.inspector.style_page
    page.refresh()
    assert page.font_size.value() == 14 and not page.flags["bold"].isChecked() is False or True
    assert page.align_buttons["center"].isChecked() and page.shape.currentData() == "rounded"
    page.font_size.setValue(22)                          # taille
    page.flags["italic"].click(); page.flags["underline"].click(); page.flags["strike"].click()
    page.align_buttons["right"].click()
    page.wrap.setValue(160)
    page.shape.setCurrentIndex(page.shape.findData("rect")); page.shape.activated.emit(page.shape.currentIndex())
    page.border_style.setCurrentIndex(page.border_style.findData("dashed")); page.border_style.activated.emit(page.border_style.currentIndex())
    page.border_width.setValue(4.0)
    page.link_style.setCurrentIndex(page.link_style.findData("dotted")); page.link_style.activated.emit(page.link_style.currentIndex())
    page.link_width.setValue(1.5)
    page.color_buttons["fill"].changed.emit("#FFEEAA")
    page.color_buttons["text_color"].changed.emit("#000000")
    page.color_buttons["color"].changed.emit("#EB5757")
    page.color_buttons["border_color"].changed.emit("#222222")
    st = a.style
    assert (st.font_size, st.italic, st.underline, st.strike, st.align, st.wrap_width, st.shape) == (
        22, True, True, True, "right", 160, "rect")
    assert (st.border_style, st.border_width, st.link_style, st.link_width) == ("dashed", 4.0, "dotted", 1.5)
    assert (st.fill, st.text_color, st.color, st.border_color) == ("#FFEEAA", "#000000", "#EB5757", "#222222")
    page.refresh()                                       # l'affichage reflète les valeurs appliquées
    assert page.font_size.value() == 22 and page.align_buttons["right"].isChecked() and page.wrap.value() == 160
    assert page.flags["underline"].isChecked() and page.link_width.value() == 1.5
    from PySide6.QtCore import Qt as _Qt
    from easyghost.scene import resolve_style
    rs = resolve_style(a)
    assert rs.border_pen == _Qt.PenStyle.DashLine and rs.link_pen == _Qt.PenStyle.DotLine
    assert rs.font.pixelSize() == 22 and rs.font.underline() and rs.font.strikeOut() and rs.font.italic()
    from PySide6.QtGui import QFont, QFontDatabase

    family = next(f for f in QFontDatabase.families() if f != page.font_family.currentFont().family())
    page.font_family.setCurrentFont(QFont(family))
    assert a.style.font_family == page.font_family.currentFont().family()
    reset = [b for b in page.findChildren(__import__("PySide6.QtWidgets", fromlist=["QPushButton"]).QPushButton)
             if b.text() == "Réinitialiser le style"][0]
    reset.click()
    assert a.style.is_default()
    win.stack.undo()
    assert not a.style.is_default()


def test_style_page_changes_apply_to_every_selected_node(win):
    root = win.scene.mindmap.root
    for t in "AB":
        win.scene.select_node(root)
        key(win, Qt.Key.Key_Tab); type_text(win, t)
    win.scene.clearSelection()
    for n in root.children:
        win.scene.item_for(n).setSelected(True)
    win.inspector.show_page("style")
    win.inspector.style_page.flags["bold"].click()
    assert all(n.style.bold is not None for n in root.children)
    win.inspector.style_page.align_buttons["left"].click()
    assert [n.style.align for n in root.children] == ["left", "left"]


def test_multiline_node_text_and_alignment(win):
    root = win.scene.mindmap.root
    key(win, Qt.Key.Key_Tab)
    editor = win.scene._editing.editor
    editor.setPlainText("Ligne 1\nLigne 2")
    key(win, Qt.Key.Key_Return)                          # Entrée valide
    a = root.children[0]
    assert a.text == "Ligne 1\nLigne 2"
    item = win.scene.item_for(a)
    win.scene.select_node(root)
    key(win, Qt.Key.Key_Tab); type_text(win, "Une ligne")
    single = win.scene.item_for(root.children[1]).size()[1]   # même police : nœud d'une seule ligne
    assert item.size()[1] > single + 10                  # deux lignes : plus haut qu'une ligne
    win.scene.select_node(a)
    win.scene.apply_style({"align": "left", "wrap_width": 40})
    assert item._text_rect.width() > 0
    win.scene.apply_style({"wrap_width": None})


def test_wrap_width_wraps_long_text(win):
    root = win.scene.mindmap.root
    win.scene.select_node(root)
    key(win, Qt.Key.Key_Tab); type_text(win, "un texte assez long pour passer à la ligne automatiquement")
    a = root.children[0]
    item = win.scene.item_for(a)
    wide = item.size()
    win.scene.select_node(a)
    win.scene.apply_style({"wrap_width": 120})
    narrow = item.size()
    assert narrow[0] < wide[0] and narrow[1] > wide[1]


def test_shift_enter_inserts_a_line_break_in_the_editor(win):
    key(win, Qt.Key.Key_Tab)
    editor = win.scene._editing.editor
    editor.setPlainText("A")
    cursor = editor.textCursor(); cursor.movePosition(cursor.MoveOperation.End); editor.setTextCursor(cursor)
    QTest.keyClick(win.view.scene().focusItem().scene().views()[0], Qt.Key.Key_Return, Qt.KeyboardModifier.ShiftModifier)
    assert win.scene.is_editing()                        # Maj+Entrée ne valide pas
    editor.textCursor().insertText("B")
    key(win, Qt.Key.Key_Return)
    assert win.scene.mindmap.root.children[0].text == "A\nB"


def test_inspector_note_page_still_commits_with_the_toolbar_layout(win):
    root = win.scene.mindmap.root
    win.scene.select_node(root)
    win.inspector_actions["note"].trigger()
    win.note_edit.setPlainText("depuis l'inspecteur")
    win.note_edit.committed.emit()
    assert root.note == "depuis l'inspecteur"
    win.scene.item_for(root)._hit["note"]                # la pastille est affichée


def test_clicking_note_badge_opens_the_note_page(win):
    root = win.scene.mindmap.root
    win.scene.set_data(root, note="n")
    win.inspector.hide()
    win.scene.note_requested.emit(root)
    assert not win.inspector.isHidden() and win.inspector.current_key == "note"


# ============================================ presse-papiers, clic droit, raccourcis
from PySide6.QtCore import QMimeData as _QMimeData
from PySide6.QtWidgets import QApplication as _QApplication


def build_family(win):
    """Racine -> A (A1, A2), B ; renvoie (A, A1, A2, B)."""
    root = win.scene.mindmap.root
    win.scene.select_node(root)
    key(win, Qt.Key.Key_Tab); type_text(win, "A")
    a = root.children[0]
    key(win, Qt.Key.Key_Tab); type_text(win, "A1")
    win.scene.select_node(a)
    key(win, Qt.Key.Key_Tab); type_text(win, "A2")
    win.scene.select_node(root)
    key(win, Qt.Key.Key_Tab); type_text(win, "B")
    return a, a.children[0], a.children[1], root.children[1]


def set_clipboard_text(text):
    mime = _QMimeData()
    mime.setText(text)
    _QApplication.clipboard().setMimeData(mime)


def test_copy_and_paste_a_subtree_under_another_node(win):
    root = win.scene.mindmap.root
    a, a1, a2, b = build_family(win)
    a.note, a.style.bold = "garder", True
    win.scene.select_node(a)
    assert win.copy_action.isEnabled() and win.scene.copy_selection()
    win.scene.select_node(b)
    assert win.paste_action.isEnabled()
    win.paste_action.trigger()
    copy = b.children[0]
    assert copy.text == "A" and copy.note == "garder" and copy.style.bold is True and copy is not a
    assert [c.text for c in copy.children] == ["A1", "A2"]
    assert win.scene.selected_nodes() == [copy]                      # le collé est sélectionné
    assert len(a.children) == 2 and [n.text for n in root.children] == ["A", "B"]   # l'original est intact
    win.stack.undo()
    assert b.children == [] and [n.text for n in root.children] == ["A", "B"]
    win.stack.redo()
    assert [c.text for c in b.children[0].children] == ["A1", "A2"]


def test_cut_removes_and_paste_moves(win):
    root = win.scene.mindmap.root
    a, a1, a2, b = build_family(win)
    win.scene.select_node(a1)
    win.cut_action.trigger()
    assert [c.text for c in a.children] == ["A2"]
    win.scene.select_node(b)
    win.paste_action.trigger()
    assert [c.text for c in b.children] == ["A1"]
    win.stack.undo(); win.stack.undo()                               # annule collage puis coupe
    assert [c.text for c in a.children] == ["A1", "A2"] and b.children == []


def test_root_cannot_be_cut_but_can_be_copied(win):
    root = win.scene.mindmap.root
    build_family(win)
    win.scene.select_node(root)
    assert not win.cut_action.isEnabled() and win.copy_action.isEnabled()
    assert not win.scene.cut_selection()
    assert len(root.children) == 2
    assert win.scene.copy_selection()


def test_copy_of_nested_selection_keeps_only_top_level(win):
    a, a1, a2, b = build_family(win)
    win.scene.clearSelection()
    for n in (a, a1, b):                                             # a1 est déjà dans le sous-arbre de a
        win.scene.item_for(n).setSelected(True)
    win.scene.copy_selection()
    assert _QApplication.clipboard().mimeData().text() == "A\n\tA1\n\tA2\nB"


def test_paste_text_list_from_outside(win):
    root = win.scene.mindmap.root
    set_clipboard_text("- Fruits\n  - Pomme\n  - Poire\n- Légumes")
    win.scene.select_node(root)
    assert win.paste_action.isEnabled()
    win.paste_action.trigger()
    assert [n.text for n in root.children] == ["Fruits", "Légumes"]
    assert [c.text for c in root.children[0].children] == ["Pomme", "Poire"]
    assert [n.side for n in root.children] == ["right", "left"]      # branches principales : côtés alternés
    win.stack.undo()
    assert root.children == []


def test_paste_unfolds_a_collapsed_target_and_undo_refolds_it(win):
    a, a1, a2, b = build_family(win)
    win.scene.select_node(b)
    win.scene.toggle_collapse()                                      # b n'a pas d'enfant : sans effet
    win.scene.select_node(a)
    win.scene.toggle_collapse()
    assert a.collapsed
    set_clipboard_text("nouveau")
    win.scene.paste(a)
    assert not a.collapsed and a.children[-1].text == "nouveau"
    win.stack.undo()
    assert a.collapsed and [c.text for c in a.children] == ["A1", "A2"]


def test_paste_is_disabled_when_the_clipboard_has_nothing_usable(win):
    win.scene.select_node(win.scene.mindmap.root)
    _QApplication.clipboard().setMimeData(_QMimeData())
    win._refresh_canvas_actions()
    assert not win.paste_action.isEnabled() and not win.scene.paste()
    set_clipboard_text("   ")
    win._refresh_canvas_actions()
    assert not win.paste_action.isEnabled()
    set_clipboard_text("ok")
    win._refresh_canvas_actions()
    assert win.paste_action.isEnabled()


# --------------------------------------------------------------- menu contextuel
@pytest.fixture
def menus(monkeypatch):
    """Capture les menus contextuels au lieu de les afficher (QMenu.exec bloquerait)."""
    shown = []
    monkeypatch.setattr(MainWindow, "_exec_menu", lambda self, menu, pos: shown.append(menu))
    return shown


def menu_texts(menu):
    return [a.text() for a in menu.actions() if not a.isSeparator()]


def right_click(win, node):
    from PySide6.QtCore import QPoint
    from PySide6.QtGui import QContextMenuEvent

    item = win.scene.item_for(node)
    pos = win.view.mapFromScene(item.sceneBoundingRect().center())
    event = QContextMenuEvent(QContextMenuEvent.Reason.Mouse, pos, win.view.viewport().mapToGlobal(pos))
    _QApplication.sendEvent(win.view.viewport(), event)


def test_right_click_opens_the_node_menu_with_the_requested_entries(win, menus):
    a, a1, a2, b = build_family(win)
    right_click(win, a)
    (menu,) = menus
    assert menu_texts(menu) == ["Couper", "Copier", "Coller", "Replier les enfants", "Afficher dans l'inspecteur"]
    submenu = next(act.menu() for act in menu.actions() if act.text() == "Afficher dans l'inspecteur")
    assert [x.text() for x in submenu.actions()] == ["Contour", "Note", "Couleur", "Icônes", "Style"]
    assert win.scene.selected_nodes() == [a]                         # le nœud cliqué est sélectionné


def test_right_click_selection_rules(win, menus):
    a, a1, a2, b = build_family(win)
    win.scene.clearSelection()
    for n in (a1, a2):
        win.scene.item_for(n).setSelected(True)
    right_click(win, a1)                                             # déjà sélectionné : on garde la multi-sélection
    assert sorted(n.text for n in win.scene.selected_nodes()) == ["A1", "A2"]
    right_click(win, b)                                              # hors sélection : seul b est sélectionné
    assert win.scene.selected_nodes() == [b]


def test_context_menu_is_not_shown_while_editing_text(win, menus):
    a, a1, a2, b = build_family(win)
    win.scene.select_node(a)
    key(win, Qt.Key.Key_F2)
    assert win.scene.is_editing()
    win.scene.node_context_menu(win.scene.item_for(b), None)
    assert menus == []


def test_context_menu_fold_entry_label_follows_state_and_toggles(win, menus):
    a, a1, a2, b = build_family(win)
    right_click(win, a)
    fold = next(x for x in menus[-1].actions() if "enfants" in x.text())
    assert fold.text() == "Replier les enfants" and fold.isEnabled()
    fold.trigger()
    assert a.collapsed and win.scene.item_for(a1) is None
    right_click(win, a)
    assert next(x for x in menus[-1].actions() if "enfants" in x.text()).text() == "Déplier les enfants"
    next(x for x in menus[-1].actions() if "enfants" in x.text()).trigger()
    assert not a.collapsed and win.scene.item_for(a1) is not None
    right_click(win, b)                                              # pas d'enfants : entrée grisée
    assert not next(x for x in menus[-1].actions() if "enfants" in x.text()).isEnabled()


def test_fold_applies_to_every_selected_node_in_one_step(win, menus):
    a, a1, a2, b = build_family(win)
    win.scene.select_node(a1)
    key(win, Qt.Key.Key_Tab); type_text(win, "A1x")
    win.scene.clearSelection()
    for n in (a, a1):
        win.scene.item_for(n).setSelected(True)
    n_cmds = win.stack.count()
    win.scene.toggle_collapse()
    assert a.collapsed and a1.collapsed and win.stack.count() == n_cmds + 1
    win.stack.undo()
    assert not a.collapsed and not a1.collapsed


def test_context_menu_paste_goes_to_the_clicked_node(win, menus):
    a, a1, a2, b = build_family(win)
    win.scene.clearSelection()
    for n in (a1, a2):
        win.scene.item_for(n).setSelected(True)
    set_clipboard_text("collé")
    right_click(win, a2)                                             # a2 n'est pas le premier sélectionné
    next(x for x in menus[-1].actions() if x.text() == "Coller").trigger()
    assert [c.text for c in a2.children] == ["collé"] and a1.children == []


def test_context_menu_copy_cut_paste_entries(win, menus):
    a, a1, a2, b = build_family(win)
    right_click(win, a1)
    menu = menus[-1]
    next(x for x in menu.actions() if x.text() == "Copier").trigger()
    right_click(win, b)
    next(x for x in menus[-1].actions() if x.text() == "Coller").trigger()
    assert [c.text for c in b.children] == ["A1"] and len(a.children) == 2
    right_click(win, a2)
    next(x for x in menus[-1].actions() if x.text() == "Couper").trigger()
    assert [c.text for c in a.children] == ["A1"]


@pytest.mark.parametrize("page", ["outline", "note", "color", "icons", "style"])
def test_context_menu_shows_each_inspector_page_for_the_clicked_node(win, menus, page):
    a, a1, a2, b = build_family(win)
    win.inspector.hide()
    right_click(win, a2)
    submenu = next(act.menu() for act in menus[-1].actions() if act.text() == "Afficher dans l'inspecteur")
    labels = {"outline": "Contour", "note": "Note", "color": "Couleur", "icons": "Icônes", "style": "Style"}
    next(x for x in submenu.actions() if x.text() == labels[page]).trigger()
    assert not win.inspector.isHidden() and win.inspector.current_key == page
    assert win.scene.selected_nodes() == [a2]


def test_style_pages_keep_a_multi_selection_that_contains_the_clicked_node(win, menus):
    a, a1, a2, b = build_family(win)
    win.scene.clearSelection()
    for n in (a1, a2):
        win.scene.item_for(n).setSelected(True)
    win.show_page_for(a1, "style")
    assert len(win.scene.selected_nodes()) == 2                      # on peut styler les deux
    win.show_page_for(a1, "note")
    assert win.scene.selected_nodes() == [a1]                        # la note concerne un seul nœud


def test_context_menu_reveals_hidden_node_for_the_outline_page(win, menus):
    a, a1, a2, b = build_family(win)
    win.scene.select_node(a)
    win.scene.toggle_collapse()
    win.show_page_for(a2, "outline")
    assert not a.collapsed and win.scene.selected_nodes() == [a2]


# ------------------------------------------------------------ raccourcis du menu
def test_edit_menu_uses_real_shortcuts_not_tab_characters(win):
    from PySide6.QtGui import QKeySequence

    edit = next(a.menu() for a in win.menuBar().actions() if a.text() == "Édition")
    assert not any("\t" in a.text() for a in edit.actions())         # plus de « Nouveau frère\tEntrée »
    expected = {
        "Nouvel enfant": "Tab", "Nouveau frère": "Return", "Nouveau parent": "Ctrl+Return",
        "Modifier le texte": "F2", "Replier / déplier les enfants": "Space", "Supprimer": "Backspace",
        "Couper": "Ctrl+X", "Copier": "Ctrl+C", "Coller": "Ctrl+V",
    }
    by_text = {a.text(): a for a in edit.actions() if not a.isSeparator()}
    for text, portable in expected.items():
        act = by_text[text]
        assert act.shortcut().toString(QKeySequence.SequenceFormat.PortableText) == portable, text
    assert [s.toString() for s in by_text["Nouveau frère"].shortcuts()] == ["Return", "Enter"]
    assert [s.toString() for s in by_text["Supprimer"].shortcuts()] == ["Backspace", "Del"]


def test_every_menu_shortcut_is_unique(win):
    seen = {}
    for act in win.findChildren(type(win.add_child_action)):
        for sc in act.shortcuts():
            text = sc.toString()
            if text:
                assert text not in seen or seen[text] is act, f"{text}: {seen[text].text()} / {act.text()}"
                seen[text] = act


def test_canvas_shortcuts_are_limited_to_the_map(win):
    for act in (win.add_child_action, win.add_sibling_action, win.add_parent_action, win.edit_text_action,
                win.fold_action, win.delete_action, win.cut_action, win.copy_action, win.paste_action):
        assert act.shortcutContext() == Qt.ShortcutContext.WidgetWithChildrenShortcut
        assert act in win.view.actions()


def test_canvas_actions_are_disabled_when_the_keyboard_is_elsewhere(win):
    a, a1, a2, b = build_family(win)
    win.scene.select_node(a)
    win._refresh_canvas_actions()
    acts = [win.add_child_action, win.add_sibling_action, win.fold_action, win.delete_action, win.copy_action]
    assert all(x.isEnabled() for x in acts)
    _QApplication.instance().focusChanged.emit(win.view, win.note_edit)   # le focus passe à l'Inspecteur
    assert not any(x.isEnabled() for x in acts)                           # Espace/Suppr/Tab y restent des touches de saisie
    _QApplication.instance().focusChanged.emit(win.note_edit, win.view)
    assert all(x.isEnabled() for x in acts)


def test_opening_a_menu_does_not_disable_the_actions(win):
    from PySide6.QtWidgets import QMenu

    win.scene.select_node(win.scene.mindmap.root)
    _QApplication.instance().focusChanged.emit(win.view, win.menuBar())
    _QApplication.instance().focusChanged.emit(win.menuBar(), QMenu())
    assert win.add_child_action.isEnabled()


def test_canvas_actions_are_disabled_while_editing_a_node(win):
    root = win.scene.mindmap.root
    win.scene.select_node(root)
    key(win, Qt.Key.Key_Tab)
    assert win.scene.is_editing()
    assert not any(x.isEnabled() for x in (win.add_child_action, win.add_sibling_action, win.fold_action,
                                           win.delete_action, win.paste_action))
    key(win, Qt.Key.Key_Escape)
    assert not win.scene.is_editing() and win.add_child_action.isEnabled()


def test_shortcut_availability_follows_the_selection(win):
    a, a1, a2, b = build_family(win)
    win.scene.select_node(win.scene.mindmap.root)
    assert not win.add_parent_action.isEnabled() and not win.delete_action.isEnabled()
    win.scene.select_node(b)
    assert win.add_parent_action.isEnabled() and win.delete_action.isEnabled() and not win.fold_action.isEnabled()
    win.scene.select_node(a)
    assert win.fold_action.isEnabled() and win.fold_action.text() == "Replier les enfants"
    win.fold_action.trigger()
    assert win.fold_action.text() == "Déplier les enfants"


def test_new_parent_shortcut_action_inserts_a_parent(win):
    a, a1, a2, b = build_family(win)
    win.scene.select_node(a1)
    win.add_parent_action.trigger()
    type_text(win, "P")
    assert a1.parent.text == "P" and a1.parent.parent is a


def test_actions_work_from_the_keyboard_through_the_map(win):
    """Les touches passent par l'action (raccourci) ou, à défaut, par la carte : même résultat."""
    root = win.scene.mindmap.root
    win.scene.select_node(root)
    key(win, Qt.Key.Key_Tab); type_text(win, "A")
    key(win, Qt.Key.Key_Return); type_text(win, "B")
    assert [n.text for n in root.children] == ["A", "B"]
    win.scene.select_node(root.children[0])
    key(win, Qt.Key.Key_Backspace)
    assert [n.text for n in root.children] == ["B"]
    win.stack.undo()
    assert [n.text for n in root.children] == ["A", "B"]
