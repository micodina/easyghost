"""Modèle de données d'une carte mentale (sans dépendance à Qt)."""

from __future__ import annotations

import re
from urllib.parse import urlparse
from dataclasses import dataclass, fields, replace
from typing import Iterator

from .iconset import ICON_TABLE

SHAPES = ("rounded", "rect", "diamond", "none")
SHAPE_LABELS = {
    "rounded": "Arrondi",
    "rect": "Rectangle",
    "diamond": "Losange",
    "none": "Sans bordure",
}
LINE_STYLES = ("solid", "dashed", "dotted")
LINE_STYLE_LABELS = {"solid": "Continu", "dashed": "Tirets", "dotted": "Pointillés"}
ALIGNMENTS = ("left", "center", "right")
FONT_SIZE_RANGE = (6, 96)
LINE_WIDTH_RANGE = (0.5, 12.0)
WRAP_WIDTH_RANGE = (40, 1200)
BRANCH_PALETTE = [
    "#4F8EF7", "#F2994A", "#27AE60", "#BB6BD9",
    "#EB5757", "#2D9CDB", "#E0A800", "#16A085",
]

# Icônes intégrées : clé -> (emoji de secours, libellé) ; le catalogue complet est dans iconset.
# Une clé inconnue (ex. fichier d'une autre version) est conservée telle quelle.
ICONS = {key: (emoji, label) for key, _svg, label, _cat, emoji in ICON_TABLE}
FALLBACK_ICON = "🏷️"

OPENABLE_SCHEMES = ("http", "https", "mailto")
_ICON_ID_RE = re.compile(r"^[A-Za-z0-9_.\-]{1,64}$")
_CONTROL_RE = re.compile(r"[\x00-\x1f\x7f]")


def normalize_link(value) -> str | None:
    """Adresse nettoyée (sans espaces ni caractères de contrôle) ou None."""
    if not isinstance(value, str):
        return None
    value = _CONTROL_RE.sub("", value).strip()
    return value[:2048] or None


_SCHEME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9+.\-]*:(?!\d)")


def complete_link(link: str) -> str:
    """Ajoute https:// à une adresse sans schéma (« exemple.com », « localhost:8080 »).

    Une adresse qui a déjà un schéma (« javascript:… », « tel:… ») est laissée telle
    quelle pour être refusée ensuite par `is_openable_link`.
    """
    return link if _SCHEME_RE.match(link) else "https://" + link


def is_openable_link(url: str | None) -> bool:
    """Seuls http, https et mailto sont ouverts (jamais file:, javascript:…)."""
    if not url:
        return False
    try:
        return urlparse(url).scheme.lower() in OPENABLE_SCHEMES
    except ValueError:
        return False


def normalize_text(value) -> str:
    """Texte de nœud : lignes nettoyées (espaces réduits), sans lignes vides en début/fin."""
    if not isinstance(value, str):
        return ""
    lines = [" ".join(line.split()) for line in value.replace("\r\n", "\n").replace("\r", "\n").split("\n")]
    return "\n".join(lines).strip("\n")


def normalize_icon(value) -> str | None:
    return value if isinstance(value, str) and _ICON_ID_RE.match(value) else None


def normalize_note(value) -> str:
    return value.replace("\r\n", "\n").replace("\r", "\n").strip() if isinstance(value, str) else ""


_COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")


def normalize_color(value, allow_none: bool = False) -> str | None:
    """Renvoie « #RRGGBB » (majuscules), « none » si autorisé, sinon None."""
    if allow_none and value == "none":
        return "none"
    if isinstance(value, str) and _COLOR_RE.match(value):
        return value.upper()
    return None


def rgb_to_hex(r: int, g: int, b: int) -> str:
    return "#{:02X}{:02X}{:02X}".format(*(max(0, min(255, int(c))) for c in (r, g, b)))


def hex_to_rgb(color: str) -> tuple[int, int, int]:
    return int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)


_FAMILY_RE = re.compile(r"^[^\x00-\x1f\x7f]{1,100}$")


def _bounded_int(value, low: int, high: int) -> int | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return int(value) if low <= value <= high else None


def _bounded_float(value, low: float, high: float) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value) if low <= value <= high else None


@dataclass
class NodeStyle:
    """Style d'un nœud ; None = automatique (valeur calculée selon la position)."""

    # couleurs
    color: str | None = None         # couleur de la branche : lien + contour par défaut, héritée
    fill: str | None = None          # fond ; "none" = transparent
    text_color: str | None = None
    border_color: str | None = None  # contour, si différent de la branche
    # forme et traits
    shape: str | None = None         # voir SHAPES
    border_style: str | None = None  # voir LINE_STYLES
    border_width: float | None = None
    link_style: str | None = None    # trait du lien vers le parent
    link_width: float | None = None
    # texte
    bold: bool | None = None
    italic: bool | None = None
    underline: bool | None = None
    strike: bool | None = None
    font_family: str | None = None
    font_size: int | None = None     # en pixels
    align: str | None = None         # alignement du paragraphe : voir ALIGNMENTS
    wrap_width: int | None = None    # largeur max du texte avant retour à la ligne

    def to_dict(self) -> dict:
        return {f.name: getattr(self, f.name) for f in fields(self) if getattr(self, f.name) is not None}

    @classmethod
    def from_dict(cls, data: dict) -> NodeStyle:
        """Lecture tolérante : les valeurs invalides sont ignorées."""
        st = cls()
        st.color = normalize_color(data.get("color"))
        st.fill = normalize_color(data.get("fill"), allow_none=True)
        st.text_color = normalize_color(data.get("text_color"))
        st.border_color = normalize_color(data.get("border_color"))
        st.shape = data.get("shape") if data.get("shape") in SHAPES else None
        for name in ("border_style", "link_style"):
            setattr(st, name, data.get(name) if data.get(name) in LINE_STYLES else None)
        st.border_width = _bounded_float(data.get("border_width"), *LINE_WIDTH_RANGE)
        st.link_width = _bounded_float(data.get("link_width"), *LINE_WIDTH_RANGE)
        for name in ("bold", "italic", "underline", "strike"):
            value = data.get(name)
            setattr(st, name, value if isinstance(value, bool) else None)
        family = data.get("font_family")
        st.font_family = family if isinstance(family, str) and _FAMILY_RE.match(family) else None
        st.font_size = _bounded_int(data.get("font_size"), *FONT_SIZE_RANGE)
        st.align = data.get("align") if data.get("align") in ALIGNMENTS else None
        st.wrap_width = _bounded_int(data.get("wrap_width"), *WRAP_WIDTH_RANGE)
        return st

    def is_default(self) -> bool:
        return all(getattr(self, f.name) is None for f in fields(self))

    def copy(self) -> NodeStyle:
        return replace(self)

    def merged(self, changes: dict) -> NodeStyle:
        """Copie avec `changes` appliqués ; une valeur None remet l'attribut par défaut."""
        names = {f.name for f in fields(self)}
        unknown = set(changes) - names
        if unknown:
            raise KeyError(f"attributs de style inconnus : {sorted(unknown)}")
        return replace(self, **changes)


class Node:
    def __init__(self, node_id: int, text: str = "") -> None:
        self.id = node_id
        self.text = text
        self.children: list[Node] = []
        self.parent: Node | None = None
        self.collapsed = False
        self.style = NodeStyle()
        self.note = ""                  # texte libre (plusieurs lignes)
        self.link: str | None = None    # adresse web / e-mail
        self.icon: str | None = None    # clé de ICONS (ou identifiant importé)
        self.side: str | None = None  # "left"/"right" ; utilisé seulement pour les enfants de la racine

    def __repr__(self) -> str:
        return f"Node({self.id}, {self.text!r})"

    def walk(self) -> Iterator[Node]:
        """Parcours en profondeur, parent avant enfants."""
        yield self
        for child in self.children:
            yield from child.walk()

    def is_descendant_of(self, other: Node) -> bool:
        node = self.parent
        while node is not None:
            if node is other:
                return True
            node = node.parent
        return False

    @property
    def index(self) -> int:
        return self.parent.children.index(self) if self.parent else 0


class MindMap:
    def __init__(self, root_text: str = "Idée centrale") -> None:
        self._next_id = 1
        self.root = self.new_node(root_text)

    def new_node(self, text: str = "") -> Node:
        node = Node(self._next_id, text)
        self._next_id += 1
        return node

    def nodes(self) -> Iterator[Node]:
        return self.root.walk()

    def find(self, node_id: int) -> Node | None:
        return next((n for n in self.nodes() if n.id == node_id), None)

    # --- Opérations structurelles -------------------------------------
    def insert(self, parent: Node, node: Node, index: int | None = None) -> None:
        """Rattache `node` (détaché) à `parent`."""
        if node.parent is not None:
            raise ValueError("le nœud est déjà rattaché")
        if parent is node or parent.is_descendant_of(node):
            raise ValueError("cycle interdit")
        if index is None:
            index = len(parent.children)
        parent.children.insert(index, node)
        node.parent = parent

    def detach(self, node: Node) -> tuple[Node, int]:
        """Détache `node` de son parent ; renvoie (ancien parent, ancien index)."""
        if node is self.root or node.parent is None:
            raise ValueError("la racine ne peut pas être détachée")
        parent, index = node.parent, node.index
        parent.children.pop(index)
        node.parent = None
        return parent, index

    def add_child(self, parent: Node, text: str = "", index: int | None = None) -> Node:
        node = self.new_node(text)
        self.insert(parent, node, index)
        return node

    def add_sibling(self, node: Node, text: str = "") -> Node:
        if node.parent is None:
            return self.add_child(node, text)
        return self.add_child(node.parent, text, node.index + 1)

    def remove(self, node: Node) -> tuple[Node, int]:
        return self.detach(node)

    def move(self, node: Node, new_parent: Node, index: int | None = None) -> None:
        if new_parent is node or new_parent.is_descendant_of(node):
            raise ValueError("impossible de déplacer un nœud sous lui-même")
        self.detach(node)
        self.insert(new_parent, node, index)

    def insert_parent(self, node: Node, new_node: Node) -> None:
        """Place `new_node` entre `node` et son parent : il prend la place de `node`, qui devient son enfant."""
        if node is self.root or node.parent is None:
            raise ValueError("la racine n'a pas de parent")
        parent, index = self.detach(node)
        self.insert(parent, new_node, index)
        self.insert(new_node, node)
