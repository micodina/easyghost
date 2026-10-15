"""Notes, liens, icônes : modèle, stockage, formats, exports d'images."""

import json
import zipfile
from xml.etree import ElementTree as ET

import pytest

from easyghost import storage
from easyghost.formats import freemind, markdown, opml, smmx, xmind
from easyghost.model import MindMap, complete_link, is_openable_link, normalize_icon, normalize_link, normalize_note


def rich_map():
    m = MindMap("Racine")
    m.root.note = "note racine"
    a = m.add_child(m.root, "Doc [1] *x*")
    a.note = "ligne 1\n\nligne 3"
    a.link = "https://exemple.org/a?b=1&c=2"
    a.icon = "idea"
    b = m.add_child(m.root, "Autre")
    b.icon = "cle_inconnue"           # clé d'icône inconnue d'EasyGhost : conservée dans un fichier natif
    b.link = "mailto:moi@exemple.org"
    m.add_child(a, "Enfant").note = "é à ü — \"guillemets\" & <balises>"
    return m


def snapshot(m):
    return [(n.text, n.note, n.link, n.icon) for n in m.nodes()]


# ------------------------------------------------------------- validation
def test_normalizers():
    assert normalize_note("  a\r\nb\rc \n") == "a\nb\nc"
    assert normalize_note(None) == "" and normalize_note(3) == ""
    assert normalize_link(" http://x.y/\u0000a\n ") == "http://x.y/a"
    assert normalize_link("   ") is None and normalize_link(None) is None
    assert normalize_icon("star") == "star" and normalize_icon("a b") is None and normalize_icon("../x") is None


@pytest.mark.parametrize("url,ok", [
    ("https://a.b", True), ("HTTP://a.b", True), ("mailto:x@y.z", True),
    ("javascript:alert(1)", False), ("file:///etc/passwd", False), ("ftp://a.b", False),
    ("exemple.com", False), ("", False), (None, False),
])
def test_only_safe_links_are_openable(url, ok):
    assert is_openable_link(url) is ok


# ---------------------------------------------------------------- stockage
def test_storage_round_trip(tmp_path):
    m = rich_map()
    storage.save(tmp_path / "x.easyghost", m)
    assert snapshot(storage.load(tmp_path / "x.easyghost")) == snapshot(m)


def test_storage_sanitizes_hostile_values():
    data = {"version": 1, "root": {"id": 1, "text": "r", "note": 5, "link": "  http://ok.org \n", "icon": "../../x"}}
    root = storage.from_dict(data).root
    assert (root.note, root.link, root.icon) == ("", "http://ok.org", None)


# ------------------------------------------------------------------ SimpleMind
def test_smmx_round_trip_keeps_note_and_link_but_not_icons(tmp_path):
    m = rich_map()
    smmx.export_file(tmp_path / "x.smmx", m)
    back = smmx.import_file(tmp_path / "x.smmx").mindmap
    assert [(n.text, n.note, n.link) for n in back.nodes()] == [(n.text, n.note, n.link) for n in m.nodes()]
    assert all(n.icon is None for n in back.nodes())            # les icônes ne passent pas par SimpleMind
    assert b"icon=" not in zipfile.ZipFile(tmp_path / "x.smmx").read("document/mindmap.xml")


def test_smmx_export_warns_that_icons_are_not_exported(tmp_path):
    warnings = smmx.export_file(tmp_path / "x.smmx", rich_map())
    assert any("2 icône(s) non exportée(s)" in w for w in warnings)         # idea + identifiant inconnu
    assert not any("icône" in w for w in smmx.export_file(tmp_path / "y.smmx", MindMap("sans icône")))


def test_smmx_import_reads_real_attributes():
    xml = b"""<simplemind-mindmaps><mindmap><meta/><topics>
      <topic id="0" parent="-1" x="0" y="0" text="R" icon="ic8_96_x">
        <link urllink="https://simplemind.eu/"></link><note textfmt="plain">Une
note</note></topic>
      <topic id="1" parent="0" x="1" y="1" text="C"><link phone-contact="000" thumbnail="#x"></link></topic>
    </topics></mindmap></simplemind-mindmaps>"""
    res = smmx.parse_xml(xml)
    r = res.mindmap.root
    assert (r.link, r.note) == ("https://simplemind.eu/", "Une\nnote")
    assert r.icon is None                                      # icône SimpleMind « ic8_96_x » ignorée
    assert res.mindmap.root.children[0].link is None
    assert any("contact" in w for w in res.warnings)
    assert any("1 icônes SimpleMind" in w for w in res.warnings)


# ------------------------------------------------------------------- FreeMind
def test_freemind_round_trip(tmp_path):
    m = rich_map()
    m.root.children[1].icon = None
    freemind.export_file(tmp_path / "x.mm", m)
    back = freemind.import_file(tmp_path / "x.mm").mindmap
    assert snapshot(back) == snapshot(m)


def test_freemind_old_note_hook_and_unknown_icons():
    xml = b"""<map><node TEXT="R" LINK="http://a.b">
      <hook NAME="accessories/plugins/NodeNote.properties"><text>vieille note</text></hook>
      <icon BUILTIN="unknown_icon"/><icon BUILTIN="help"/></node></map>"""
    res = freemind.parse_xml(xml)
    r = res.mindmap.root
    assert (r.note, r.link, r.icon) == ("vieille note", "http://a.b", "question")
    assert res.warnings == ["Non pris en charge (ignorés) : 1 icônes sans équivalent"]  # « unknown_icon »


def test_freemind_export_warns_when_icon_has_no_equivalent(tmp_path):
    m = MindMap()
    m.root.icon = "heart"
    assert any("icône" in w for w in freemind.export_file(tmp_path / "x.mm", m))


# ------------------------------------------------------------------------ OPML
def test_opml_export(tmp_path):
    m = rich_map()
    opml.export_file(tmp_path / "x.opml", m)
    doc = ET.parse(tmp_path / "x.opml").getroot()
    assert doc.tag == "opml" and doc.get("version") == "2.0"
    top = doc.find("body/outline")
    assert top.get("text") == "Racine" and top.get("_note") == "note racine"
    first = top.find("outline")
    assert first.get("text") == "Doc [1] *x*" and first.get("url") == "https://exemple.org/a?b=1&c=2"
    assert first.get("_note") == "ligne 1\n\nligne 3"
    assert first.find("outline").get("_note") == "é à ü — \"guillemets\" & <balises>"


# -------------------------------------------------------------------- Markdown
def test_markdown_export(tmp_path):
    m = rich_map()
    m.root.children[0].link = "https://x.org/a b(c)"
    markdown.export_file(tmp_path / "x.md", m)
    text = (tmp_path / "x.md").read_text(encoding="utf-8")
    lines = text.splitlines()
    assert lines[0] == "# Racine"
    assert "> note racine" in lines
    assert "- 💡 [Doc \\[1\\] \\*x\\*](https://x.org/a%20b%28c%29)" in lines
    assert "  > ligne 1" in lines and "  >" in lines and "  > ligne 3" in lines   # note multiligne
    assert "  - Enfant" in lines
    assert "- [Autre](mailto:moi@exemple.org)" in lines
    assert text.endswith("\n")


def test_markdown_escapes_block_syntax():
    m = MindMap("# titre")
    m.add_child(m.root, "> citation")
    m.add_child(m.root, "")
    text = markdown.build_markdown(m)
    assert text.startswith("# \\# titre")
    assert "- \\> citation" in text and "- (sans titre)" in text


# ----------------------------------------------------------------------- XMind
def test_xmind_export(tmp_path):
    m = rich_map()
    m.root.children[0].icon = "check"
    m.root.children[0].collapsed = True
    m.root.children[0].style.bold = True
    m.root.children[0].style.fill = "#FFEEAA"
    warnings = xmind.export_file(tmp_path / "x.xmind", m)
    with zipfile.ZipFile(tmp_path / "x.xmind") as zf:
        assert sorted(zf.namelist()) == ["content.json", "manifest.json", "metadata.json"]
        content = json.loads(zf.read("content.json"))
        json.loads(zf.read("metadata.json")); json.loads(zf.read("manifest.json"))
    (sheet,) = content
    root = sheet["rootTopic"]
    assert sheet["class"] == "sheet" and root["title"] == "Racine"
    assert root["notes"]["plain"]["content"] == "note racine"
    doc, other = root["children"]["attached"]
    assert doc["title"] == "Doc [1] *x*" and doc["href"] == "https://exemple.org/a?b=1&c=2"
    assert doc["markers"] == [{"markerId": "task-done"}] and doc["branch"] == "folded"
    assert doc["style"]["properties"]["fo:font-weight"] == "bold"
    assert doc["style"]["properties"]["svg:fill"] == "#FFEEAA"
    assert doc["children"]["attached"][0]["notes"]["plain"]["content"].startswith("é à ü")
    assert "markers" not in other                      # icône inconnue : pas de marqueur
    ids = []
    def collect(t):
        ids.append(t["id"])
        for c in t.get("children", {}).get("attached", []):
            collect(c)
    collect(root)
    assert len(ids) == len(set(ids)) == 4
    assert any("icône" in w for w in warnings)


# ------------------------------------------------------------ images (offscreen)
@pytest.fixture(scope="module")
def qapp():
    import os
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    from PySide6.QtWidgets import QApplication
    return QApplication.instance() or QApplication([])


@pytest.fixture
def scene(qapp):
    from PySide6.QtGui import QUndoStack
    from easyghost.scene import MapScene

    stack = QUndoStack()
    sc = MapScene(stack)
    sc.animated = False
    sc.set_mindmap(rich_map())
    sc.select_node(sc.mindmap.root)
    yield sc
    sc.clear()


def test_export_png(scene, tmp_path):
    from PySide6.QtGui import QImage

    from easyghost import export_image

    export_image.export_png(scene, tmp_path / "x.png", scale=1.0)
    img = QImage(str(tmp_path / "x.png"))
    assert not img.isNull() and img.width() > 150 and img.height() > 60
    assert img.pixelColor(2, 2).name() == "#ffffff"           # marge blanche
    colors = {img.pixelColor(x, y).name() for x in range(0, img.width(), 3) for y in range(0, img.height(), 3)}
    assert len(colors) > 4                                    # il y a bien du contenu dessiné
    assert scene.selected_node() is scene.mindmap.root         # la sélection est restaurée


def test_export_png_scale(scene, tmp_path):
    from PySide6.QtGui import QImage

    from easyghost import export_image

    export_image.export_png(scene, tmp_path / "1.png", scale=1.0)
    export_image.export_png(scene, tmp_path / "2.png", scale=2.0)
    a, b = QImage(str(tmp_path / "1.png")), QImage(str(tmp_path / "2.png"))
    assert abs(b.width() - 2 * a.width()) <= 2


def test_export_svg(scene, tmp_path):
    from easyghost import export_image

    export_image.export_svg(scene, tmp_path / "x.svg", "Racine")
    root = ET.parse(tmp_path / "x.svg").getroot()
    assert root.tag.endswith("svg") and root.get("viewBox")
    assert "Racine" in (tmp_path / "x.svg").read_text(encoding="utf-8")


def test_export_pdf(scene, tmp_path):
    from easyghost import export_image

    export_image.export_pdf(scene, tmp_path / "x.pdf", "Racine")
    data = (tmp_path / "x.pdf").read_bytes()
    assert data.startswith(b"%PDF") and b"%%EOF" in data[-64:] and len(data) > 1000


@pytest.mark.parametrize("raw,expected", [
    ("exemple.com", "https://exemple.com"),
    ("localhost:8080/x", "https://localhost:8080/x"),
    ("exemple.com:443", "https://exemple.com:443"),
    ("http://a.b", "http://a.b"),
    ("mailto:x@y.z", "mailto:x@y.z"),
    ("javascript:alert(1)", "javascript:alert(1)"),   # laissé tel quel, puis refusé
    ("file:///etc/passwd", "file:///etc/passwd"),
])
def test_complete_link(raw, expected):
    assert complete_link(raw) == expected
    if expected == raw and raw.split(":")[0] in ("javascript", "file"):
        assert not is_openable_link(complete_link(raw))


def test_smmx_import_ignores_every_simplemind_icon_and_says_so():
    xml = b"""<simplemind-mindmaps><mindmap><meta/><topics>
      <topic id="0" parent="-1" x="0" y="0" text="R" icon="ic8_96_clinic"></topic>
      <topic id="1" parent="0" x="1" y="1" text="A" icon="ic8_96_airplane"></topic>
      <topic id="2" parent="0" x="1" y="2" text="B"></topic>
    </topics></mindmap></simplemind-mindmaps>"""
    res = smmx.parse_xml(xml)
    assert [n.icon for n in res.mindmap.nodes()] == [None, None, None]
    assert [w for w in res.warnings if "icônes SimpleMind" in w] == [
        "Non pris en charge (ignorés) : 2 icônes SimpleMind (EasyGhost a les siennes)"]


def test_smmx_import_without_icons_gives_no_icon_warning():
    xml = b"""<simplemind-mindmaps><mindmap><meta/><topics>
      <topic id="0" parent="-1" x="0" y="0" text="R"></topic></topics></mindmap></simplemind-mindmaps>"""
    assert smmx.parse_xml(xml).warnings == []


# ------------------------------------------------------------- icône de l'application
def test_app_icon_is_bundled_and_complete():
    import easyghost
    from pathlib import Path

    path = Path(easyghost.__file__).parent / "icons" / "AppIcon.icns"
    assert path.is_file() and path.read_bytes()[:4] == b"icns"
    assert not (Path(easyghost.__file__).parents[1] / "AppIcon.icns").exists()      # plus à la racine du projet


def test_app_icon_loads_with_all_sizes(qapp):
    from easyghost.icons import app_icon

    icon = app_icon()
    assert not icon.isNull()
    sizes = {s.width() for s in icon.availableSizes()}
    assert {32, 128, 512, 1024} <= sizes
    assert not icon.pixmap(64, 64).isNull()


def test_application_and_window_use_the_icon(qapp):
    from PySide6.QtWidgets import QApplication

    from easyghost.__main__ import configure
    from easyghost.main_window import MainWindow

    configure(QApplication.instance())
    assert QApplication.instance().applicationName() == "EasyGhost"
    assert not QApplication.windowIcon().isNull()
    win = MainWindow()
    try:
        assert not win.windowIcon().isNull()
    finally:
        win.stack.setClean()
        win.close()


# ------------------------------------------------------- ouverture système, auto-vérification
def test_file_open_event_opens_the_document(qapp, tmp_path):
    from PySide6.QtCore import QCoreApplication
    from PySide6.QtGui import QFileOpenEvent
    from PySide6.QtWidgets import QApplication

    from easyghost import storage
    from easyghost.__main__ import FileOpenHandler
    from easyghost.main_window import MainWindow

    m = MindMap("Ouvert par le Finder")
    m.add_child(m.root, "x")
    path = tmp_path / "doc.easyghost"
    storage.save(path, m)
    win = MainWindow()
    handler = FileOpenHandler(qapp)
    handler.opened.connect(win.open_requested)
    qapp.installEventFilter(handler)
    try:
        QCoreApplication.sendEvent(qapp, QFileOpenEvent(str(path)))
        assert [n.text for n in win.scene.mindmap.nodes()] == ["Ouvert par le Finder", "x"]
        assert win.path == path
    finally:
        qapp.removeEventFilter(handler)
        win.stack.setClean()
        win.close()


def test_file_open_event_asks_before_discarding_changes(qapp, tmp_path, monkeypatch):
    from PySide6.QtWidgets import QMessageBox

    from easyghost import storage
    from easyghost.main_window import MainWindow

    path = tmp_path / "doc.easyghost"
    storage.save(path, MindMap("Autre"))
    win = MainWindow()
    win.scene.mindmap.add_child(win.scene.mindmap.root, "modif")
    win.scene.undo_stack.push(__import__("easyghost.commands", fromlist=["x"]).EditText(win.scene, win.scene.mindmap.root, "changé"))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Cancel)
    try:
        win.open_requested(str(path))
        assert win.scene.mindmap.root.text == "changé"            # annulé : le document courant est conservé
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Discard)
        win.open_requested(str(path))
        assert win.scene.mindmap.root.text == "Autre"
    finally:
        win.stack.setClean()
        win.close()


def test_self_check_passes(qapp, capsys):
    from easyghost.selfcheck import CHECKS, run

    assert run() == 0
    out = capsys.readouterr().out
    assert out.count("OK  ") == len(CHECKS) == 5 and "ÉCHEC" not in out and "réussie" in out


def test_self_check_reports_a_failure(qapp, capsys, monkeypatch):
    from easyghost import selfcheck

    monkeypatch.setattr(selfcheck, "CHECKS", [("cassé", lambda: 1 / 0), ("bon", lambda: True)])
    assert selfcheck.run() == 1
    out = capsys.readouterr().out
    assert "ÉCHEC cassé (ZeroDivisionError" in out and "OK   bon" in out and "1 contrôle(s) en échec" in out


def test_packaged_document_types_match_the_formats_the_app_opens():
    """Les types de fichiers déclarés dans le paquet macOS doivent correspondre au code."""
    from pathlib import Path

    import easyghost
    from easyghost import formats

    root = Path(easyghost.__file__).parent.parent
    spec = (root / "packaging" / "easyghost.spec").read_text(encoding="utf-8")
    from easyghost.main_window import NATIVE_EXT

    declared = {NATIVE_EXT.lstrip(".")} | {f.extension.lstrip(".") for f in formats.importable_formats()}
    for ext in declared:
        assert f'"{ext}"' in spec, ext                       # chaque format ouvrable est déclaré
    assert 'CFBundleTypeExtensions": ["mindmap"]' not in spec
    assert (root / "packaging" / "launcher.py").is_file() and (root / "tools" / "build_macos.sh").is_file()
    import os
    assert os.access(root / "tools" / "build_macos.sh", os.X_OK)
