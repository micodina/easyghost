"""Sauvegarde/chargement JSON versionné."""

from __future__ import annotations

import json
from pathlib import Path

from .model import MindMap, Node, NodeStyle, normalize_icon, normalize_link, normalize_note

FORMAT_VERSION = 1


def _node_to_dict(node: Node) -> dict:
    data: dict = {"id": node.id, "text": node.text}
    if node.collapsed:
        data["collapsed"] = True
    if node.side in ("left", "right"):
        data["side"] = node.side
    if node.note:
        data["note"] = node.note
    if node.link:
        data["link"] = node.link
    if node.icon:
        data["icon"] = node.icon
    if not node.style.is_default():
        data["style"] = node.style.to_dict()
    if node.children:
        data["children"] = [_node_to_dict(c) for c in node.children]
    return data


def to_dict(mindmap: MindMap) -> dict:
    return {"version": FORMAT_VERSION, "root": _node_to_dict(mindmap.root)}


def from_dict(data: dict) -> MindMap:
    if data.get("version") != FORMAT_VERSION:
        raise ValueError(f"version de fichier non prise en charge : {data.get('version')!r}")

    max_id = 0

    def build(d: dict) -> Node:
        nonlocal max_id
        node = Node(int(d["id"]), str(d.get("text", "")))
        node.collapsed = bool(d.get("collapsed", False))
        node.side = d.get("side") if d.get("side") in ("left", "right") else None
        node.note = normalize_note(d.get("note"))
        node.link = normalize_link(d.get("link"))
        node.icon = normalize_icon(d.get("icon"))
        if isinstance(d.get("style"), dict):
            node.style = NodeStyle.from_dict(d["style"])
        max_id = max(max_id, node.id)
        for child_data in d.get("children", []):
            child = build(child_data)
            child.parent = node
            node.children.append(child)
        return node

    mindmap = MindMap()
    mindmap.root = build(data["root"])
    mindmap._next_id = max_id + 1
    return mindmap


def save(path: str | Path, mindmap: MindMap) -> None:
    Path(path).write_text(
        json.dumps(to_dict(mindmap), ensure_ascii=False, indent=2), encoding="utf-8"
    )


def load(path: str | Path) -> MindMap:
    return from_dict(json.loads(Path(path).read_text(encoding="utf-8")))
