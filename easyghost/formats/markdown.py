"""Markdown (export) : titre = racine, puis liste imbriquée.

Les notes deviennent des citations sous leur élément, les liens des liens Markdown,
les icônes un symbole devant le texte.
"""

from __future__ import annotations

import re
from pathlib import Path

from ..model import ICONS, MindMap, Node
from . import Format

_ESCAPE_RE = re.compile(r"([\\`*_\[\]<>#|~])")


def _escape(text: str) -> str:
    return _ESCAPE_RE.sub(r"\\\1", " ".join(text.split()))


def _inline(node: Node) -> str:
    text = _escape(node.text) or "(sans titre)"
    if node.link:
        url = node.link.replace(" ", "%20").replace("(", "%28").replace(")", "%29")
        text = f"[{text}]({url})"
    if node.icon in ICONS:
        text = f"{ICONS[node.icon][0]} {text}"
    return text


def _note_lines(node: Node, indent: str) -> list[str]:
    return [f"{indent}> {line}".rstrip() for line in node.note.split("\n")] if node.note else []


def build_markdown(mindmap: MindMap) -> str:
    root = mindmap.root
    lines = [f"# {_inline(root)}", ""]
    if root.note:
        lines += [*_note_lines(root, ""), ""]
    stack = [(c, 0) for c in reversed(root.children)]
    while stack:
        node, depth = stack.pop()
        indent = "  " * depth
        lines.append(f"{indent}- {_inline(node)}")
        lines += _note_lines(node, indent + "  ")
        stack.extend((c, depth + 1) for c in reversed(node.children))
    return "\n".join(lines).rstrip("\n") + "\n"


def export_file(path: Path, mindmap: MindMap) -> list[str]:
    Path(path).write_text(build_markdown(mindmap), encoding="utf-8")
    if any(not n.style.is_default() for n in mindmap.nodes()):
        return ["Les styles (couleurs, formes…) ne sont pas exportés en Markdown."]
    return []


FORMAT = Format("markdown", "Markdown", ".md", None, export_file)
