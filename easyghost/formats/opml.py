"""OPML 2.0 (export) : plan hiérarchique lisible par les outliners.

<outline text _note url> : `_note` et `url` sont les conventions OPML 2.0 courantes.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from ..model import MindMap, Node
from . import Format


def build_xml(mindmap: MindMap) -> str:
    opml = ET.Element("opml", version="2.0")
    head = ET.SubElement(opml, "head")
    ET.SubElement(head, "title").text = mindmap.root.text or "Carte mentale"
    body = ET.SubElement(opml, "body")

    def outline(parent: ET.Element, node: Node) -> ET.Element:
        attrs = {"text": node.text}
        if node.note:
            attrs["_note"] = node.note
        if node.link:
            attrs["url"] = node.link
        return ET.SubElement(parent, "outline", attrs)

    top = outline(body, mindmap.root)
    stack = [(mindmap.root, top)]
    while stack:
        node, el = stack.pop()
        for child in node.children:
            stack.append((child, outline(el, child)))
    ET.indent(opml, space="  ")
    return '<?xml version="1.0" encoding="UTF-8"?>\n' + ET.tostring(opml, encoding="unicode")


def export_file(path: Path, mindmap: MindMap) -> list[str]:
    Path(path).write_text(build_xml(mindmap), encoding="utf-8")
    warnings = []
    if any(n.icon for n in mindmap.nodes()):
        warnings.append("Les icônes ne sont pas exportées en OPML.")
    if any(not n.style.is_default() for n in mindmap.nodes()):
        warnings.append("Les styles (couleurs, formes…) ne sont pas exportés en OPML.")
    return warnings


FORMAT = Format("opml", "OPML", ".opml", None, export_file)
