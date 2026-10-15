"""XMind (export, .xmind) : archive zip content.json + metadata.json + manifest.json.

Structure : [ {class: "sheet", rootTopic: {title, children: {attached: [...]},
notes: {plain: {content}}, href, markers: [{markerId}], style: {properties}}} ].
Les propriétés de style et les identifiants de marqueurs sont écrits d'après les
conventions connues d'XMind Zen ; XMind ignore ceux qu'il ne reconnaît pas.
"""

from __future__ import annotations

import json
import uuid
import zipfile
from pathlib import Path

from ..layout import root_split
from ..model import MindMap, Node
from . import Format

ICON_TO_MARKER = {
    "important": "priority-1", "check": "task-done", "cross": "symbol-wrong",
    "question": "symbol-question", "warning": "symbol-exclam", "info": "symbol-info",
    "flag": "flag-red", "star": "star-red",
}
SHAPE_CLASS = {
    "rounded": "org.xmind.topicShape.roundedRect",
    "rect": "org.xmind.topicShape.rect",
    "diamond": "org.xmind.topicShape.diamond",
    "none": "org.xmind.topicShape.underline",
}


def _uid() -> str:
    return uuid.uuid4().hex[:26]


def _style_properties(node: Node) -> dict:
    st = node.style
    props: dict[str, str] = {}
    if st.bold:
        props["fo:font-weight"] = "bold"
    if st.italic:
        props["fo:font-style"] = "italic"
    if st.text_color:
        props["fo:color"] = st.text_color
    if st.fill and st.fill != "none":
        props["svg:fill"] = st.fill
    if st.color:
        props["line-color"] = st.color
        props["border-line-color"] = st.color
    if st.shape:
        props["shape-class"] = SHAPE_CLASS[st.shape]
    if st.font_family:
        props["fo:font-family"] = st.font_family
    if st.font_size:
        props["fo:font-size"] = f"{st.font_size}pt"
    decorations = [d for d, on in (("underline", st.underline), ("line-through", st.strike)) if on]
    if decorations:
        props["fo:text-decoration"] = " ".join(decorations)
    if st.align:
        props["fo:text-align"] = st.align
    return props


def _topic(node: Node) -> dict:
    topic: dict = {"id": _uid(), "class": "topic", "title": node.text}
    if node.note:
        topic["notes"] = {"plain": {"content": node.note}}
    if node.link:
        topic["href"] = node.link
    if node.icon in ICON_TO_MARKER:
        topic["markers"] = [{"markerId": ICON_TO_MARKER[node.icon]}]
    props = _style_properties(node)
    if props:
        topic["style"] = {"id": _uid(), "properties": props}
    if node.collapsed and node.children:
        topic["branch"] = "folded"
    return topic


def build_content(mindmap: MindMap) -> list[dict]:
    right, left = root_split(mindmap.root, expand_all=True)
    root_topic = _topic(mindmap.root)
    root_topic["structureClass"] = "org.xmind.ui.map.clockwise"
    stack = [(mindmap.root, root_topic, [*right, *left])]
    while stack:
        node, topic, children = stack.pop()
        if not children:
            continue
        attached = []
        for child in children:
            child_topic = _topic(child)
            attached.append(child_topic)
            stack.append((child, child_topic, child.children))
        topic["children"] = {"attached": attached}
    sheet = {
        "id": _uid(),
        "class": "sheet",
        "title": mindmap.root.text or "Carte mentale",
        "rootTopic": root_topic,
    }
    return [sheet]


def export_file(path: Path, mindmap: MindMap) -> list[str]:
    content = json.dumps(build_content(mindmap), ensure_ascii=False, indent=2)
    metadata = json.dumps({"creator": {"name": "easyghost", "version": "0.1"}})
    manifest = json.dumps({"file-entries": {"content.json": {}, "metadata.json": {}}})
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("content.json", content)
        zf.writestr("metadata.json", metadata)
        zf.writestr("manifest.json", manifest)
    lost = sum(1 for n in mindmap.nodes() if n.icon and n.icon not in ICON_TO_MARKER)
    warnings = []
    if lost:
        warnings.append(f"{lost} icône(s) sans marqueur XMind équivalent non exportée(s).")
    warnings.append("XMind répartit lui-même les branches à gauche et à droite.")
    return warnings


FORMAT = Format("xmind", "XMind", ".xmind", None, export_file)
