import pytest

from easyghost.model import MindMap


def test_add_children_and_siblings():
    m = MindMap("root")
    a = m.add_child(m.root, "a")
    c = m.add_child(m.root, "c")
    b = m.add_sibling(a, "b")
    assert [n.text for n in m.root.children] == ["a", "b", "c"]
    assert b.parent is m.root and c.index == 2


def test_remove_returns_position_and_reinsert_restores():
    m = MindMap("root")
    a = m.add_child(m.root, "a")
    b = m.add_child(m.root, "b")
    parent, index = m.remove(a)
    assert m.root.children == [b] and a.parent is None
    m.insert(parent, a, index)
    assert m.root.children == [a, b]


def test_root_cannot_be_removed():
    m = MindMap()
    with pytest.raises(ValueError):
        m.remove(m.root)


def test_move_reparents():
    m = MindMap()
    a = m.add_child(m.root, "a")
    b = m.add_child(m.root, "b")
    m.move(b, a)
    assert b.parent is a and m.root.children == [a]


def test_move_under_own_descendant_is_refused():
    m = MindMap()
    a = m.add_child(m.root, "a")
    b = m.add_child(a, "b")
    with pytest.raises(ValueError):
        m.move(a, b)
    with pytest.raises(ValueError):
        m.move(a, a)
    assert b.parent is a and a.parent is m.root


def test_ids_are_unique():
    m = MindMap()
    ids = [m.add_child(m.root, str(i)).id for i in range(5)]
    assert len(set(ids + [m.root.id])) == 6
