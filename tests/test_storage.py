import json

import pytest

from easyghost import storage
from easyghost.model import MindMap


def build():
    m = MindMap("Racine é")
    a = m.add_child(m.root, "a")
    m.add_child(a, "a1")
    b = m.add_child(m.root, "b")
    b.collapsed = True
    return m


def test_round_trip(tmp_path):
    m = build()
    path = tmp_path / "x.json"
    storage.save(path, m)
    loaded = storage.load(path)
    assert storage.to_dict(loaded) == storage.to_dict(m)
    assert loaded.find(3).collapsed or loaded.find(4).collapsed


def test_new_ids_do_not_collide_after_load(tmp_path):
    path = tmp_path / "x.json"
    storage.save(path, build())
    loaded = storage.load(path)
    new = loaded.add_child(loaded.root, "n")
    assert sum(1 for n in loaded.nodes() if n.id == new.id) == 1


def test_unknown_version_is_rejected(tmp_path):
    path = tmp_path / "x.json"
    path.write_text(json.dumps({"version": 99, "root": {"id": 1}}))
    with pytest.raises(ValueError):
        storage.load(path)
