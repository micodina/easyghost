"""Presse-papiers des nœuds : format interne, texte indenté, validation."""

import json

import pytest
from PySide6.QtCore import QMimeData

from easyghost import clipboard
from easyghost.model import MindMap, NodeStyle


def sample():
    m = MindMap("R")
    a = m.add_child(m.root, "A")
    a.note, a.link, a.icon, a.collapsed = "une note", "https://exemple.org", "star", True
    a.style = NodeStyle(bold=True, fill="#FFEEAA", font_size=18, link_style="dashed")
    a1 = m.add_child(a, "A1")
    m.add_child(a1, "A1x")
    b = m.add_child(m.root, "B")
    return m, a, b


def test_internal_round_trip_keeps_everything():
    m, a, b = sample()
    payload = clipboard.read(clipboard.make_mime([a]))
    (copy,) = clipboard.instantiate(m, payload)
    assert copy is not a and copy.id != a.id
    assert (copy.text, copy.note, copy.link, copy.icon, copy.collapsed) == ("A", "une note", "https://exemple.org", "star", True)
    assert copy.style == a.style
    assert [c.text for c in copy.children] == ["A1"] and copy.children[0].children[0].text == "A1x"
    ids = [n.id for n in (copy, *copy.children, *copy.children[0].children)]
    assert len(set(ids)) == 3 and not set(ids) & {n.id for n in m.nodes()}   # identifiants neufs
    assert copy.parent is None                                                 # détaché : prêt à être collé


def test_text_flavor_is_an_indented_outline():
    m, a, b = sample()
    assert clipboard.make_mime([a, b]).text() == "A\n\tA1\n\t\tA1x\nB"
    m.root.children[0].text = "ligne 1\nligne 2"
    assert clipboard.outline_text([a]).splitlines()[0] == "ligne 1 ligne 2"      # un nœud = une ligne


def test_top_level_drops_nodes_already_in_a_selected_subtree():
    m, a, b = sample()
    a1 = a.children[0]
    assert clipboard.top_level([a1, b, a]) == [a, b]                 # ordre de la carte, pas de la sélection
    assert clipboard.top_level([b, a1]) == [a1, b]
    assert clipboard.top_level([]) == []


@pytest.mark.parametrize("text,expected", [
    ("un\ndeux\ntrois", [("un", []), ("deux", []), ("trois", [])]),
    ("- un\n  - deux\n    - trois\n- quatre", [("un", [("deux", [("trois", [])])]), ("quatre", [])]),
    ("A\n\tA1\n\t\tA1a\n\tA2\nB", [("A", [("A1", [("A1a", [])]), ("A2", [])]), ("B", [])]),
    ("* x\n\n\n  * y", [("x", [("y", [])])]),
    ("• puce\n  – sous-puce", [("puce", [("sous-puce", [])])]),
    ("  décalé\nnormal", [("décalé", []), ("normal", [])]),
])
def test_text_paste_builds_the_hierarchy(text, expected):
    mime = QMimeData()
    mime.setText(text)
    m = MindMap()

    def shape(n):
        return (n.text, [shape(c) for c in n.children])

    assert [shape(n) for n in clipboard.instantiate(m, clipboard.read(mime))] == expected


@pytest.mark.parametrize("mime_setup", [
    lambda m: None,                                                   # vide
    lambda m: m.setText("   \n  \n"),                                 # que des blancs
    lambda m: m.setData(clipboard.MIME, b"pas du json"),
    lambda m: m.setData(clipboard.MIME, b'{"version": 99, "nodes": [{"text": "x"}]}'),
    lambda m: m.setData(clipboard.MIME, b'{"version": 1, "nodes": []}'),
    lambda m: m.setData(clipboard.MIME, b'{"version": 1, "nodes": ["x"]}'),
    lambda m: m.setData(clipboard.MIME, b"\xff\xfe"),
    lambda m: m.setData(clipboard.MIME, b"[" * 100000),               # imbrication démesurée
])
def test_invalid_clipboard_content_is_ignored(mime_setup):
    mime = QMimeData()
    mime_setup(mime)
    assert clipboard.read(mime) is None and not clipboard.has_content(mime)
    assert clipboard.read(None) is None


def test_pasted_values_are_revalidated():
    hostile = {"version": 1, "nodes": [{
        "text": "  a \r\n  b ", "note": 12, "link": "  javascript:x\n", "icon": "../../etc", "collapsed": "oui",
        "style": {"font_size": 9999, "color": "rouge", "shape": "star", "bold": "yes", "fill": "#abcdef"},
        "children": [{"text": "ok"}, "pas un dict", {"text": None}],
    }]}
    mime = QMimeData()
    mime.setData(clipboard.MIME, json.dumps(hostile).encode())
    (node,) = clipboard.instantiate(MindMap(), clipboard.read(mime))
    assert node.text == "a\nb" and node.note == "" and node.icon is None and node.collapsed is False
    assert node.style.font_size is None and node.style.color is None and node.style.shape is None
    assert node.style.bold is None and node.style.fill == "#ABCDEF"
    assert node.link == "javascript:x"          # conservé tel quel : il ne sera jamais ouvert (schéma refusé)
    assert [c.text for c in node.children] == ["ok", ""]


def test_size_and_depth_limits(monkeypatch):
    monkeypatch.setattr(clipboard, "MAX_NODES", 50)
    monkeypatch.setattr(clipboard, "MAX_DEPTH", 5)
    wide = {"text": "r", "children": [{"text": str(i)} for i in range(500)]}
    (root,) = clipboard.instantiate(MindMap(), [wide])
    assert len(root.children) == 49                                  # tronqué à 50 nœuds au total
    deep = cur = {"text": "0"}
    for i in range(1, 40):
        cur["children"] = [{"text": str(i)}]
        cur = cur["children"][0]
    (root,) = clipboard.instantiate(MindMap(), [deep])
    n, depth = root, 0
    while n.children:
        n, depth = n.children[0], depth + 1
    assert depth == 5                                                # profondeur bornée


def test_very_deep_subtree_can_be_copied_without_recursion():
    m = MindMap()
    node = m.root
    for i in range(3000):                                            # bien au-delà de la limite de récursion
        node = m.add_child(node, str(i))
    mime = clipboard.make_mime([m.root])
    assert mime.text().count("\n") == 3000


def test_text_paste_is_bounded():
    mime = QMimeData()
    mime.setText("\n".join(f"ligne {i}" for i in range(clipboard.MAX_TEXT_LINES + 1)))
    assert clipboard.read(mime) is None
