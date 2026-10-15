import zipfile
from pathlib import Path

import pytest

from easyghost import formats
from easyghost.formats import FormatError, freemind, smmx
from easyghost.model import MindMap, NodeStyle

SAMPLE = Path(__file__).resolve().parent.parent / "examples" / "sac de survie.smmx"

XML = """<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE simplemind-mindmaps>
<simplemind-mindmaps doc-version="3">
  <mindmap>
    <meta><main-centraltheme id="0"></main-centraltheme></meta>
    <topics>
      <topic id="0" parent="-1" x="400" y="400" text="Racine" textfmt="plain"></topic>
      <topic id="1" parent="0" x="500" y="300" palette="2" text="Droite haut">
        <style borderstyle="sbsDiamond"><font bold="true"></font></style>
        <fillcolor r="255" g="238" b="170"></fillcolor>
        <textcolor r="0" g="0" b="0"></textcolor>
        <note>une note</note>
      </topic>
      <topic id="2" parent="0" x="500" y="500" palette="3" text="Droite bas"></topic>
      <topic id="3" parent="0" x="300" y="400" text="Gauche"><strokecolor r="0" g="51" b="255"></strokecolor>
        <fillcolor none="true"></fillcolor></topic>
      <topic id="4" parent="1" x="600" y="300" text="Enfant\\Nmultiligne"></topic>
      <topic id="9" parent="42" x="0" y="0" text="Orphelin"></topic>
    </topics>
    <relations></relations>
  </mindmap>
</simplemind-mindmaps>"""


def tree(m):
    def walk(n):
        return (n.text, [walk(c) for c in n.children])
    return walk(m.root)


def test_parse_smmx_structure_styles_and_sides():
    res = smmx.parse_xml(XML.encode())
    m = res.mindmap
    assert m.root.text == "Racine"
    top = {c.text: c for c in m.root.children}
    assert set(top) == {"Droite haut", "Droite bas", "Gauche", "Orphelin"}
    assert top["Droite haut"].side == "right" and top["Gauche"].side == "left"
    st = top["Droite haut"].style
    assert (st.shape, st.bold, st.fill, st.text_color) == ("diamond", True, "#FFEEAA", "#000000")
    assert top["Droite haut"].style.color == "#4F8EF7"          # palette 2 -> 1re couleur
    assert top["Droite bas"].style.color == "#F2994A"           # palette 3 -> 2e couleur
    assert top["Gauche"].style.color == "#0033FF" and top["Gauche"].style.fill == "none"
    assert top["Droite haut"].children[0].text == "Enfant\nmultiligne"      # \N : vrai retour à la ligne
    joined = " ".join(res.warnings)
    assert "non rattachés" in joined and "multilignes" not in joined
    assert top["Droite haut"].note == "une note"            # les notes sont maintenant reprises
    assert "notes" not in joined


def test_parse_smmx_rejects_non_simplemind_and_entities():
    with pytest.raises(FormatError):
        smmx.parse_xml(b"<map version='1'/>")
    with pytest.raises(FormatError):
        smmx.parse_xml(b"<!DOCTYPE x [<!ENTITY a 'b'>]><simplemind-mindmaps/>")
    with pytest.raises(FormatError):
        smmx.parse_xml(b"<simplemind-mindmaps><mindmap><topics></topics></mindmap></simplemind-mindmaps>")


def test_import_rejects_bad_archives(tmp_path):
    bad = tmp_path / "bad.smmx"
    bad.write_bytes(b"not a zip")
    with pytest.raises(FormatError):
        smmx.import_file(bad)
    empty = tmp_path / "empty.smmx"
    with zipfile.ZipFile(empty, "w") as zf:
        zf.writestr("other.txt", "x")
    with pytest.raises(FormatError):
        smmx.import_file(empty)


def styled_map():
    m = MindMap("Racine")
    a = m.add_child(m.root, "A")
    a.side = "right"
    a.style = NodeStyle(color="#EB5757", fill="#FFEEAA", text_color="#112233", shape="none", bold=True)
    b = m.add_child(m.root, "B")
    b.side = "left"
    b.style = NodeStyle(shape="rounded")
    a1 = m.add_child(a, "A1")
    a1.style = NodeStyle(fill="none", italic=True)
    m.add_child(a1, "A1x")
    return m


def test_smmx_round_trip(tmp_path):
    m = styled_map()
    path = tmp_path / "x.smmx"
    smmx.export_file(path, m)
    assert zipfile.ZipFile(path).namelist() == ["document/mindmap.xml"]
    back = smmx.import_file(path).mindmap
    assert tree(back) == tree(m)
    a = back.root.children[0]
    assert a.side == "right" and back.root.children[1].side == "left"
    assert a.style.fill == "#FFEEAA" and a.style.text_color == "#112233"
    assert a.style.color == "#EB5757" and a.style.shape == "none" and a.style.bold
    assert a.children[0].style.fill == "none" and a.children[0].style.italic


def test_smmx_export_includes_hidden_branches(tmp_path):
    m = styled_map()
    m.root.children[0].collapsed = True
    path = tmp_path / "x.smmx"
    warnings = smmx.export_file(path, m)
    assert any("replié" in w for w in warnings)
    assert "A1x" in zipfile.ZipFile(path).read("document/mindmap.xml").decode("utf-8")


@pytest.mark.skipif(not SAMPLE.exists(), reason="fichier d'exemple absent")
def test_real_sample_file():
    res = smmx.import_file(SAMPLE)
    m = res.mindmap
    assert m.root.text == "sac de survie"
    assert len(list(m.nodes())) == 55
    assert len(m.root.children) == 10
    names = {c.text for c in m.root.children}
    assert {"Manger", "Boire", "Se soigner"} <= names
    soigner = next(c for c in m.root.children if c.text == "Se soigner")
    assert [c.text for c in soigner.children][0] == "Trousse d'hygiène"
    assert [c.text for c in soigner.children[0].children] == ["Savon", "Shampoing", "Rasoirs"]


FREEMIND = """<map version="1.0.1">
<node ID="ID_1" TEXT="Racine">
  <node ID="ID_2" TEXT="Gauche" POSITION="left" COLOR="#ff0000" BACKGROUND_COLOR="#ffff00" STYLE="fork" FOLDED="true">
    <font NAME="SansSerif" SIZE="12" BOLD="true" ITALIC="true"/>
    <edge COLOR="#00ff00"/>
    <icon BUILTIN="idea"/>
    <node ID="ID_3" TEXT="Enfant"/>
  </node>
  <node ID="ID_4" POSITION="right">
    <richcontent TYPE="NODE"><html><body><p>Texte <b>riche</b></p></body></html></richcontent>
    <richcontent TYPE="NOTE"><html><body>note</body></html></richcontent>
  </node>
</node>
</map>"""


def test_parse_freemind():
    res = freemind.parse_xml(FREEMIND.encode())
    m = res.mindmap
    g, r = m.root.children
    assert (g.text, g.side, g.collapsed) == ("Gauche", "left", True)
    assert g.style == NodeStyle(color="#00FF00", fill="#FFFF00", text_color="#FF0000", shape="none",
                                bold=True, italic=True)
    assert g.children[0].text == "Enfant"
    assert r.text == "Texte riche" and r.side == "right"
    assert r.note == "note"
    assert g.icon == "idea"                                  # <icon BUILTIN="idea"/>
    assert res.warnings == []


def test_freemind_rejects_wrong_files():
    with pytest.raises(FormatError):
        freemind.parse_xml(b"<simplemind-mindmaps/>")
    with pytest.raises(FormatError):
        freemind.parse_xml(b"<map version='1'/>")
    with pytest.raises(FormatError):
        freemind.parse_xml(b"<map><node")


def test_freemind_round_trip(tmp_path):
    m = styled_map()
    m.root.children[0].collapsed = True
    path = tmp_path / "x.mm"
    freemind.export_file(path, m)
    text = path.read_text(encoding="utf-8")
    assert 'POSITION="left"' in text and 'FOLDED="true"' in text
    back = freemind.import_file(path).mindmap
    assert tree(back) == tree(m)
    a, b = back.root.children
    assert a.side == "right" and b.side == "left" and a.collapsed
    assert (a.style.fill, a.style.text_color, a.style.color, a.style.shape, a.style.bold) == (
        "#FFEEAA", "#112233", "#EB5757", "none", True)
    assert b.style.shape == "rounded"
    assert a.children[0].style.italic


def test_freemind_text_special_characters(tmp_path):
    m = MindMap('a "b" <c> & d é')
    m.add_child(m.root, "x'y")
    path = tmp_path / "s.mm"
    freemind.export_file(path, m)
    back = freemind.import_file(path).mindmap
    assert tree(back) == tree(m)


def test_format_registry():
    assert formats.format_for_path("a/b.SMMX").key == "smmx"
    assert formats.format_for_path("c.mm").key == "freemind"
    assert formats.format_for_path("d.easyghost") is None
