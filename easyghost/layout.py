"""Mise en page en arbre équilibré (racine au centre, branches à gauche et à droite)."""

from __future__ import annotations

from typing import Callable

from .model import MindMap, Node

H_GAP = 60.0
V_GAP = 14.0

Size = tuple[float, float]


def visible_children(node: Node) -> list[Node]:
    return [] if node.collapsed else node.children


def root_split(root: Node, expand_all: bool = False) -> tuple[list[Node], list[Node]]:
    """Répartit les enfants de la racine entre (droite, gauche), dans l'ordre.

    Sans aucun côté explicite : première moitié à droite (comportement historique).
    Sinon : les côtés explicites sont respectés, les autres vont du côté le moins chargé.
    """
    kids = root.children if expand_all else visible_children(root)
    if not any(k.side in ("left", "right") for k in kids):
        half = (len(kids) + 1) // 2
        return kids[:half], kids[half:]
    assigned: dict[int, str] = {}
    counts = {"right": 0, "left": 0}
    for k in kids:
        if k.side in counts:
            assigned[k.id] = k.side
            counts[k.side] += 1
    for k in kids:
        if k.id not in assigned:
            side = "right" if counts["right"] <= counts["left"] else "left"
            assigned[k.id] = side
            counts[side] += 1
    return (
        [k for k in kids if assigned[k.id] == "right"],
        [k for k in kids if assigned[k.id] == "left"],
    )


def compute_layout(
    mindmap: MindMap, size_of: Callable[[Node], Size], expand_all: bool = False
) -> dict[int, tuple[float, float]]:
    """Renvoie {id: (x, y)} : coin supérieur gauche de chaque nœud visible.

    La racine est centrée sur (0, 0). Avec `expand_all`, les branches repliées
    sont placées comme si elles étaient dépliées (utile pour l'export).
    """
    children_of = (lambda n: n.children) if expand_all else visible_children

    sizes: dict[int, Size] = {}
    heights: dict[int, float] = {}

    def size(n: Node) -> Size:
        if n.id not in sizes:
            sizes[n.id] = size_of(n)
        return sizes[n.id]

    def subtree_height(n: Node) -> float:
        if n.id not in heights:
            kids = children_of(n)
            block = sum(subtree_height(c) for c in kids) + V_GAP * max(len(kids) - 1, 0)
            heights[n.id] = max(size(n)[1], block)
        return heights[n.id]

    positions: dict[int, tuple[float, float]] = {}

    def place(n: Node, x: float, center_y: float, direction: int) -> None:
        """Place `n` (bord proche en x) et ses descendants du côté `direction` (+1/-1)."""
        w, h = size(n)
        left = x if direction > 0 else x - w
        positions[n.id] = (left, center_y - h / 2)
        place_children(children_of(n), left, w, center_y, direction)

    def place_children(
        kids: list[Node], left: float, w: float, center_y: float, direction: int
    ) -> None:
        if not kids:
            return
        total = sum(subtree_height(c) for c in kids) + V_GAP * (len(kids) - 1)
        y = center_y - total / 2
        child_x = left + w + H_GAP if direction > 0 else left - H_GAP
        for c in kids:
            slot = subtree_height(c)
            place(c, child_x, y + slot / 2, direction)
            y += slot + V_GAP

    root = mindmap.root
    rw, rh = size(root)
    positions[root.id] = (-rw / 2, -rh / 2)
    right, left = root_split(root, expand_all)
    place_children(right, -rw / 2, rw, 0.0, +1)
    place_children(left, -rw / 2, rw, 0.0, -1)
    return positions
