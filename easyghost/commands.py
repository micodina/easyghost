"""Commandes annulables. `ctx` est la scène : elle expose `mindmap` et `sync()`."""

from __future__ import annotations

from PySide6.QtGui import QUndoCommand

from .model import Node


class _Cmd(QUndoCommand):
    def __init__(self, ctx, text: str) -> None:
        super().__init__(text)
        self.ctx = ctx


class AddNode(_Cmd):
    def __init__(self, ctx, parent: Node, index: int | None = None, side: str | None = None) -> None:
        super().__init__(ctx, "Ajouter un nœud")
        self.parent = parent
        self.index = index
        self.side = side
        self.node: Node | None = None
        self._parent_was_collapsed = parent.collapsed

    def redo(self) -> None:
        mm = self.ctx.mindmap
        if self.node is None:
            self.node = mm.new_node("")
            self.node.side = self.side
        if self.index is None:
            self.index = len(self.parent.children)
        mm.insert(self.parent, self.node, self.index)
        self.parent.collapsed = False
        self.ctx.sync(select=self.node.id)

    def undo(self) -> None:
        self.ctx.mindmap.detach(self.node)
        self.parent.collapsed = self._parent_was_collapsed
        self.ctx.sync(select=self.parent.id)


class DeleteNode(_Cmd):
    def __init__(self, ctx, node: Node) -> None:
        super().__init__(ctx, "Supprimer le nœud")
        self.node = node
        self.parent: Node | None = None
        self.index = 0

    def redo(self) -> None:
        self.parent, self.index = self.ctx.mindmap.detach(self.node)
        self.ctx.sync(select=self.parent.id)

    def undo(self) -> None:
        self.ctx.mindmap.insert(self.parent, self.node, self.index)
        self.ctx.sync(select=self.node.id)


class EditText(_Cmd):
    def __init__(self, ctx, node: Node, new_text: str) -> None:
        super().__init__(ctx, "Modifier le texte")
        self.node = node
        self.old = node.text
        self.new = new_text

    def redo(self) -> None:
        self.node.text = self.new
        self.ctx.sync(select=self.node.id)

    def undo(self) -> None:
        self.node.text = self.old
        self.ctx.sync(select=self.node.id)


class Reparent(_Cmd):
    def __init__(self, ctx, node: Node, new_parent: Node) -> None:
        super().__init__(ctx, "Déplacer le nœud")
        self.node = node
        self.new_parent = new_parent
        self.old_parent = node.parent
        self.old_index = node.index
        self.old_side = node.side
        self._new_parent_was_collapsed = new_parent.collapsed

    def redo(self) -> None:
        self.node.side = None
        self.ctx.mindmap.move(self.node, self.new_parent)
        self.new_parent.collapsed = False
        self.ctx.sync(select=self.node.id)

    def undo(self) -> None:
        self.ctx.mindmap.move(self.node, self.old_parent, self.old_index)
        self.node.side = self.old_side
        self.new_parent.collapsed = self._new_parent_was_collapsed
        self.ctx.sync(select=self.node.id)


class ToggleCollapse(_Cmd):
    def __init__(self, ctx, node: Node) -> None:
        super().__init__(ctx, "Replier/déplier")
        self.node = node

    def redo(self) -> None:
        self.node.collapsed = not self.node.collapsed
        self.ctx.sync(select=self.node.id)

    undo = redo


class SetStyle(_Cmd):
    """Applique `changes` (attribut -> valeur, None = défaut) à plusieurs nœuds.

    Changer la couleur d'une branche la rend aussi à ses descendants : leurs
    couleurs personnalisées sont remises à « automatique » pour qu'ils héritent.
    """

    def __init__(self, ctx, nodes: list[Node], changes: dict) -> None:
        super().__init__(ctx, "Modifier le style")
        self.nodes = list(nodes)
        self.changes = dict(changes)
        self.cascade: list[Node] = []
        if "color" in self.changes:
            chosen = {id(n) for n in self.nodes}
            for n in self.nodes:
                self.cascade.extend(d for d in n.walk() if d is not n and id(d) not in chosen)
        self.before = {id(n): n.style.copy() for n in [*self.nodes, *self.cascade]}

    def redo(self) -> None:
        for n in self.nodes:
            n.style = self.before[id(n)].merged(self.changes)
        for n in self.cascade:
            n.style = self.before[id(n)].merged({"color": None})
        self.ctx.sync()

    def undo(self) -> None:
        for n in [*self.nodes, *self.cascade]:
            n.style = self.before[id(n)].copy()
        self.ctx.sync()


class SetData(_Cmd):
    """Modifie note, lien et/ou icône d'un ou plusieurs nœuds (champs : note/link/icon)."""

    KEYS = ("note", "link", "icon")

    def __init__(self, ctx, nodes, **changes) -> None:
        super().__init__(ctx, "Modifier la note, le lien ou l'icône")
        unknown = set(changes) - set(self.KEYS)
        if unknown:
            raise KeyError(f"champs inconnus : {sorted(unknown)}")
        self.nodes = [nodes] if isinstance(nodes, Node) else list(nodes)
        self.new = changes
        self.old = {id(n): {k: getattr(n, k) for k in changes} for n in self.nodes}

    def _select(self) -> None:
        self.ctx.sync(select=self.nodes[0].id if len(self.nodes) == 1 else None)

    def redo(self) -> None:
        for n in self.nodes:
            for k, v in self.new.items():
                setattr(n, k, v)
        self._select()

    def undo(self) -> None:
        for n in self.nodes:
            for k, v in self.old[id(n)].items():
                setattr(n, k, v)
        self._select()


class InsertParent(_Cmd):
    """Insère un nouveau nœud entre `child` et son parent (le nœud devient son enfant)."""

    def __init__(self, ctx, child: Node) -> None:
        super().__init__(ctx, "Ajouter un nœud parent")
        self.child = child
        self.node: Node | None = None          # le nouveau nœud (pour la saisie du texte)
        self.old_parent = child.parent
        self.old_index = child.index
        self.old_side = child.side

    def redo(self) -> None:
        mm = self.ctx.mindmap
        if self.node is None:
            self.node = mm.new_node("")
        under_root = self.old_parent.parent is None
        self.node.side = self.old_side if under_root else None  # le nouveau nœud garde le côté
        self.child.side = None
        mm.insert_parent(self.child, self.node)
        self.ctx.sync(select=self.node.id)

    def undo(self) -> None:
        mm = self.ctx.mindmap
        mm.detach(self.child)
        mm.detach(self.node)
        mm.insert(self.old_parent, self.child, self.old_index)
        self.child.side = self.old_side
        self.ctx.sync(select=self.child.id)


class PasteNodes(_Cmd):
    """Colle des sous-arbres (déjà instanciés) comme derniers enfants de `parent`."""

    def __init__(self, ctx, parent: Node, roots: list[Node], sides: list[str | None] | None = None) -> None:
        super().__init__(ctx, "Coller")
        self.parent = parent
        self.roots = list(roots)
        self.parent_was_collapsed = parent.collapsed
        for node, side in zip(self.roots, sides or []):
            node.side = side

    def redo(self) -> None:
        mm = self.ctx.mindmap
        for node in self.roots:
            mm.insert(self.parent, node)
        self.parent.collapsed = False
        self.ctx.sync()
        self.ctx.select_nodes(self.roots)

    def undo(self) -> None:
        mm = self.ctx.mindmap
        for node in reversed(self.roots):
            mm.detach(node)
        self.parent.collapsed = self.parent_was_collapsed
        self.ctx.sync(select=self.parent.id)
