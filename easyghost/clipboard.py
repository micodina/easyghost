"""Presse-papiers des nœuds : format interne (sous-arbres complets) + texte indenté.

Copier place deux représentations : le format interne EasyGhost (style, note, lien, icône,
repli, sous-arbre) et le plan en texte indenté, lisible dans n'importe quel autre programme.
Coller accepte le format interne, ou du texte : une ligne par nœud, l'indentation donne la
hiérarchie (les puces « - », « * », « • » sont retirées).
"""

from __future__ import annotations

import json

from PySide6.QtCore import QMimeData

from .model import (
    MindMap,
    Node,
    NodeStyle,
    normalize_icon,
    normalize_link,
    normalize_note,
    normalize_text,
)

MIME = "application/x-easyghost-nodes"
FORMAT_VERSION = 1
MAX_NODES = 20000      # garde-fous contre un contenu énorme ou piégé
MAX_DEPTH = 200
MAX_TEXT_LINES = 5000


def top_level(nodes: list[Node]) -> list[Node]:
    """Nœuds qui ne sont pas déjà dans le sous-arbre d'un autre nœud de la liste, dans l'ordre
    de la carte (l'ordre d'une sélection Qt n'est pas garanti)."""
    chosen = {id(n) for n in nodes}

    def covered(n: Node) -> bool:
        a = n.parent
        while a is not None:
            if id(a) in chosen:
                return True
            a = a.parent
        return False

    kept = [n for n in nodes if not covered(n)]
    if len(kept) < 2:
        return kept
    root = kept[0]
    while root.parent is not None:
        root = root.parent
    position = {id(n): i for i, n in enumerate(root.walk())}
    return sorted(kept, key=lambda n: position[id(n)])


def _node_payload(node: Node) -> dict:
    """Description d'un nœud (sans récursion : un sous-arbre très profond reste copiable)."""
    root: dict = {}
    stack = [(node, root)]
    while stack:
        n, d = stack.pop()
        d["text"] = n.text
        if n.note:
            d["note"] = n.note
        if n.link:
            d["link"] = n.link
        if n.icon:
            d["icon"] = n.icon
        if n.collapsed:
            d["collapsed"] = True
        if not n.style.is_default():
            d["style"] = n.style.to_dict()
        if n.children:
            d["children"] = [{} for _ in n.children]
            stack.extend(zip(n.children, d["children"]))
    return root


def outline_text(nodes: list[Node]) -> str:
    """Plan en texte : une ligne par nœud, une tabulation par niveau."""
    lines: list[str] = []
    stack = [(n, 0) for n in reversed(nodes)]
    while stack:
        n, depth = stack.pop()
        lines.append("\t" * depth + " ".join(n.text.split()))
        stack.extend((c, depth + 1) for c in reversed(n.children))
    return "\n".join(lines)


def make_mime(nodes: list[Node]) -> QMimeData:
    mime = QMimeData()
    payload = {"version": FORMAT_VERSION, "nodes": [_node_payload(n) for n in nodes]}
    mime.setData(MIME, json.dumps(payload, ensure_ascii=False).encode("utf-8"))
    mime.setText(outline_text(nodes))
    return mime


# --------------------------------------------------------------------- lecture
def _parse_internal(mime: QMimeData) -> list[dict] | None:
    try:
        data = json.loads(bytes(mime.data(MIME)).decode("utf-8"))
    except (ValueError, RecursionError, UnicodeDecodeError):
        return None
    nodes = data.get("nodes") if isinstance(data, dict) and data.get("version") == FORMAT_VERSION else None
    return nodes if isinstance(nodes, list) and nodes and all(isinstance(n, dict) for n in nodes) else None


def _parse_text(text: str) -> list[dict] | None:
    """Texte indenté -> arbre de dictionnaires {text, children}."""
    lines = [ln for ln in text.replace("\r\n", "\n").replace("\r", "\n").split("\n") if ln.strip()]
    if not lines or len(lines) > MAX_TEXT_LINES:
        return None
    roots: list[dict] = []
    stack: list[tuple[int, dict]] = []   # (indentation, nœud)
    for raw in lines:
        expanded = raw.expandtabs(4)
        indent = len(expanded) - len(expanded.lstrip(" "))
        label = expanded.strip()
        for bullet in ("- ", "* ", "• ", "– "):
            if label.startswith(bullet):
                label = label[len(bullet):].strip()
                break
        node = {"text": label, "children": []}
        while stack and stack[-1][0] >= indent:
            stack.pop()
        (stack[-1][1]["children"] if stack else roots).append(node)
        stack.append((indent, node))
    return roots or None


def read(mime: QMimeData | None) -> list[dict] | None:
    """Contenu collable (format interne, sinon texte), ou None."""
    if mime is None:
        return None
    if mime.hasFormat(MIME):
        return _parse_internal(mime)
    if mime.hasText():
        return _parse_text(mime.text())
    return None


def has_content(mime: QMimeData | None) -> bool:
    return read(mime) is not None


# --------------------------------------------------------------- instanciation
def instantiate(mindmap: MindMap, payload: list[dict]) -> list[Node]:
    """Crée de nouveaux nœuds (identifiants neufs, détachés) à partir du contenu collé.

    Les valeurs sont revalidées comme à l'ouverture d'un fichier ; au-delà des limites de
    taille ou de profondeur le contenu est tronqué.
    """
    roots: list[Node] = []
    count = 0
    stack: list[tuple[dict, Node | None, int]] = [(d, None, 0) for d in reversed(payload)]
    while stack:
        d, parent, depth = stack.pop()
        if not isinstance(d, dict) or count >= MAX_NODES or depth > MAX_DEPTH:
            continue
        node = mindmap.new_node(normalize_text(d.get("text")))
        count += 1
        node.note = normalize_note(d.get("note"))
        node.link = normalize_link(d.get("link"))
        node.icon = normalize_icon(d.get("icon"))
        node.collapsed = d.get("collapsed") is True
        if isinstance(d.get("style"), dict):
            node.style = NodeStyle.from_dict(d["style"])
        if parent is None:
            roots.append(node)
        else:
            node.parent = parent
            parent.children.append(node)
        children = d.get("children")
        if isinstance(children, list):
            stack.extend((c, node, depth + 1) for c in reversed(children))
    return roots
