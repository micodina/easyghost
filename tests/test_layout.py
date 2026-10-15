from easyghost.layout import V_GAP, compute_layout
from easyghost.model import MindMap

SIZE = lambda n: (100.0, 30.0)


def rect(pos, n):
    x, y = pos[n.id]
    return x, y, x + 100, y + 30


def overlap(r1, r2):
    return r1[0] < r2[2] and r2[0] < r1[2] and r1[1] < r2[3] and r2[1] < r1[3]


def big_map():
    m = MindMap("r")
    for i in range(5):
        c = m.add_child(m.root, f"c{i}")
        for j in range(i):
            g = m.add_child(c, f"g{i}{j}")
            for k in range(2):
                m.add_child(g, f"h{i}{j}{k}")
    return m


def test_root_centered_on_origin():
    m = MindMap()
    pos = compute_layout(m, SIZE)
    assert pos[m.root.id] == (-50.0, -15.0)


def test_no_overlaps():
    m = big_map()
    pos = compute_layout(m, SIZE)
    nodes = list(m.nodes())
    rects = [rect(pos, n) for n in nodes]
    for i in range(len(rects)):
        for j in range(i + 1, len(rects)):
            assert not overlap(rects[i], rects[j]), (nodes[i], nodes[j])


def test_children_split_left_and_right():
    m = MindMap()
    kids = [m.add_child(m.root, str(i)) for i in range(4)]
    pos = compute_layout(m, SIZE)
    assert all(pos[k.id][0] > 0 for k in kids[:2])
    assert all(pos[k.id][0] < -100 for k in kids[2:])


def test_parent_centered_on_children_block():
    m = MindMap()
    p = m.add_child(m.root, "p")
    a, b = m.add_child(p, "a"), m.add_child(p, "b")
    pos = compute_layout(m, SIZE)
    mid = (pos[a.id][1] + pos[b.id][1] + 30) / 2
    assert abs(pos[p.id][1] + 15 - mid) < 1e-9
    assert pos[b.id][1] - pos[a.id][1] == 30 + V_GAP


def test_collapsed_children_are_not_laid_out():
    m = MindMap()
    p = m.add_child(m.root, "p")
    c = m.add_child(p, "c")
    p.collapsed = True
    pos = compute_layout(m, SIZE)
    assert p.id in pos and c.id not in pos
