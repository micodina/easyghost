import pytest

from easyghost import storage
from easyghost.layout import root_split
from easyghost.model import MindMap, NodeStyle, normalize_color


def test_normalize_color():
    assert normalize_color("#ff8800") == "#FF8800"
    assert normalize_color("red") is None
    assert normalize_color("#12345") is None
    assert normalize_color("none") is None
    assert normalize_color("none", allow_none=True) == "none"


def test_style_dict_round_trip_and_defaults():
    st = NodeStyle(color="#112233", bold=True, shape="diamond")
    assert st.to_dict() == {"color": "#112233", "shape": "diamond", "bold": True}
    assert NodeStyle.from_dict(st.to_dict()) == st
    assert NodeStyle().is_default() and not st.is_default()


def test_from_dict_ignores_invalid_values():
    st = NodeStyle.from_dict({"color": "nope", "shape": "star", "bold": "yes", "fill": "none"})
    assert st.color is None and st.shape is None and st.bold is None and st.fill == "none"


def test_merged_none_resets_and_unknown_key_fails():
    st = NodeStyle(color="#112233", bold=True)
    assert st.merged({"color": None}).color is None
    assert st.merged({"italic": True}).bold is True  # le reste est conservé
    with pytest.raises(KeyError):
        st.merged({"couleur": "#000000"})


def test_storage_keeps_style_and_side(tmp_path):
    m = MindMap()
    a = m.add_child(m.root, "a")
    a.side = "left"
    a.style = NodeStyle(fill="#FFEEAA", text_color="#000000", shape="rect", italic=True)
    path = tmp_path / "s.easyghost"
    storage.save(path, m)
    loaded = storage.load(path)
    b = loaded.root.children[0]
    assert b.side == "left" and b.style == a.style


def test_old_files_without_style_still_load():
    data = {"version": 1, "root": {"id": 1, "text": "r", "children": [{"id": 2, "text": "x"}]}}
    m = storage.from_dict(data)
    assert m.root.children[0].style.is_default() and m.root.children[0].side is None


def test_root_split_respects_explicit_sides_and_balances_others():
    m = MindMap()
    a, b, c, d = (m.add_child(m.root, t) for t in "abcd")
    a.side = b.side = "right"
    c.side = "left"
    right, left = root_split(m.root)
    assert right == [a, b] and left == [c, d]  # d (sans côté) va du côté le moins chargé


# ---------------------------------------------------- nouveaux attributs de style
def test_new_style_fields_round_trip_and_validation(tmp_path):
    st = NodeStyle(font_family="Arial", font_size=18, underline=True, strike=False, align="right",
                   wrap_width=200, border_style="dashed", border_width=3.5, link_style="dotted",
                   link_width=1.5, border_color="#112233")
    assert NodeStyle.from_dict(st.to_dict()) == st
    bad = NodeStyle.from_dict({"font_size": 3, "wrap_width": 5, "border_width": 0, "align": "justify",
                               "border_style": "wavy", "font_family": "a\nb", "link_width": "3"})
    assert bad.is_default()                       # tout est hors bornes ou invalide : ignoré
    assert NodeStyle.from_dict({"font_size": True}).font_size is None   # un booléen n'est pas un entier


def test_new_fields_survive_storage(tmp_path):
    from easyghost import storage

    m = MindMap()
    a = m.add_child(m.root, "a")
    a.style = NodeStyle(font_size=20, align="left", link_style="dashed", wrap_width=160)
    path = tmp_path / "s.easyghost"
    storage.save(path, m)
    assert storage.load(path).root.children[0].style == a.style


def test_normalize_text_keeps_lines():
    from easyghost.model import normalize_text

    assert normalize_text("  a   b \r\n\n  c  \n\n") == "a b\n\nc"
    assert normalize_text(None) == "" and normalize_text("\n\n") == ""


def test_insert_parent():
    m = MindMap()
    a = m.add_child(m.root, "a")
    b = m.add_child(m.root, "b")
    new = m.new_node("P")
    m.insert_parent(a, new)
    assert m.root.children == [new, b] and new.children == [a] and a.parent is new
    with pytest.raises(ValueError):
        m.insert_parent(m.root, m.new_node("X"))


# ------------------------------------------------------------ catalogue d'icônes
def test_icon_catalog_is_consistent():
    from pathlib import Path

    import easyghost
    from easyghost.iconset import ICON_TABLE, UI_ICONS
    from easyghost.model import ICONS

    keys = [r[0] for r in ICON_TABLE]
    assert len(keys) == len(set(keys)) == len(ICONS) >= 80
    base = Path(easyghost.__file__).parent / "icons"
    for _key, svg, label, category, emoji in ICON_TABLE:
        assert (base / "node" / f"{svg}.svg").is_file(), svg
        assert label and category and emoji
    for name in UI_ICONS:
        assert (base / "ui" / f"{name}.svg").is_file(), name
    assert (base / "LICENSE-lucide.txt").is_file()                   # licence ISC fournie avec les icônes
    for stable in ("idea", "star", "check", "cross", "question", "important", "warning", "info", "heart",
                   "flag", "clock", "calendar", "bookmark", "key", "mail", "phone"):
        assert stable in ICONS                                       # clés d'icônes stables d'une version à l'autre
