"""FreeMind / Freeplane (.mm).

<map version="1.0.1"><node TEXT COLOR BACKGROUND_COLOR STYLE POSITION FOLDED>
    <font NAME SIZE BOLD ITALIC/> <edge COLOR/> <node>…</node></node></map>
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from ..layout import root_split
from ..model import MindMap, Node, NodeStyle, normalize_color, normalize_link, normalize_note, normalize_text
from . import Format, FormatError, ImportResult, check_xml_bytes

# clé d'icône interne -> icône intégrée de FreeMind
ICON_TO_FREEMIND = {
    "idea": "idea", "question": "help", "check": "button_ok", "cross": "button_cancel",
    "flag": "flag", "warning": "messagebox_warning", "bookmark": "bookmark", "info": "info",
    "clock": "clock", "key": "password", "mail": "kmail",
}
FREEMIND_TO_ICON = {v: k for k, v in ICON_TO_FREEMIND.items()}

DEFAULT_FONT_NAMES = ("SansSerif", "Dialog")
DEFAULT_FONT_SIZE = 12

HEADER = (
    "<!-- To view this file, download free mind mapping software FreeMind "
    "from http://freemind.sourceforge.net -->\n"
)


# --------------------------------------------------------------------- import
def _text_of(el: ET.Element) -> str:
    text = el.get("TEXT")
    if text is None:
        rich = el.find("richcontent[@TYPE='NODE']")
        text = "".join(rich.itertext()) if rich is not None else ""
    return normalize_text(text)


def _note_of(el: ET.Element) -> str:
    """Note : <richcontent TYPE="NOTE"> (HTML) ou ancien crochet NodeNote."""
    rich = el.find("richcontent[@TYPE='NOTE']")
    if rich is not None:
        paragraphs = ["".join(p.itertext()).split() for p in rich.iter("p")]
        lines = [" ".join(words) for words in paragraphs]
        return normalize_note("\n".join(lines) if any(lines) else "".join(rich.itertext()))
    for hook in el.findall("hook"):
        if "NodeNote" in (hook.get("NAME") or ""):
            text = hook.find("text")
            if text is not None and text.text:
                return normalize_note(text.text)
    return ""


def _read_content(el: ET.Element, node: Node, counts: dict) -> None:
    node.note = _note_of(el)
    node.link = normalize_link(el.get("LINK"))
    builtins = [i.get("BUILTIN") for i in el.findall("icon")]
    mapped = [FREEMIND_TO_ICON[b] for b in builtins if b in FREEMIND_TO_ICON]
    node.icon = mapped[0] if mapped else None
    counts["icônes sans équivalent"] += len(builtins) - (1 if mapped else 0)


def _style_of(el: ET.Element) -> NodeStyle:
    style = NodeStyle()
    style.text_color = normalize_color(el.get("COLOR"))
    style.fill = normalize_color(el.get("BACKGROUND_COLOR"))
    shape = el.get("STYLE")
    if shape == "bubble":
        style.shape = "rounded"
    elif shape == "fork":
        style.shape = "none"
    edge = el.find("edge")
    if edge is not None:
        style.color = normalize_color(edge.get("COLOR"))
    font = el.find("font")
    if font is not None:
        if font.get("BOLD") == "true":
            style.bold = True
        if font.get("ITALIC") == "true":
            style.italic = True
        name = font.get("NAME")
        if name and name not in DEFAULT_FONT_NAMES:        # « SansSerif » : valeur par défaut de FreeMind
            style.font_family = NodeStyle.from_dict({"font_family": name}).font_family
        try:
            size = int(font.get("SIZE", ""))
            if size != DEFAULT_FONT_SIZE:                  # 12 : valeur par défaut de FreeMind
                style.font_size = NodeStyle.from_dict({"font_size": size}).font_size
        except ValueError:
            pass
    return style


def parse_xml(data: bytes) -> ImportResult:
    check_xml_bytes(data)
    try:
        doc = ET.fromstring(data)
    except ET.ParseError as exc:
        raise FormatError(f"XML invalide : {exc}") from exc
    if doc.tag != "map":
        raise FormatError("ce n'est pas un document FreeMind")
    top = doc.find("node")
    if top is None:
        raise FormatError("la carte ne contient aucun nœud")

    mindmap = MindMap(_text_of(top))
    mindmap.root.style = _style_of(top)
    mindmap.root.collapsed = top.get("FOLDED") == "true"
    counts = {"icônes sans équivalent": 0, "flèches": 0}
    _read_content(top, mindmap.root, counts)

    stack = [(top, mindmap.root)]
    while stack:
        el, node = stack.pop()
        counts["flèches"] += len(el.findall("arrowlink"))
        pending = []
        for child_el in el.findall("node"):
            child = mindmap.add_child(node, _text_of(child_el))
            child.style = _style_of(child_el)
            child.collapsed = child_el.get("FOLDED") == "true"
            _read_content(child_el, child, counts)
            if node is mindmap.root and child_el.get("POSITION") in ("left", "right"):
                child.side = child_el.get("POSITION")
            pending.append((child_el, child))
        stack.extend(reversed(pending))
    warnings = []
    ignored = [f"{n} {name}" for name, n in counts.items() if n]
    if ignored:
        warnings.append("Non pris en charge (ignorés) : " + ", ".join(ignored))
    return ImportResult(mindmap, warnings)


def import_file(path: Path) -> ImportResult:
    return parse_xml(Path(path).read_bytes())


# --------------------------------------------------------------------- export
def _node_el(node: Node, sides: dict[int, str]) -> ET.Element:
    el = ET.Element("node", {"ID": f"ID_{node.id}", "TEXT": node.text})
    st = node.style
    if node.id in sides:
        el.set("POSITION", sides[node.id])
    if st.text_color:
        el.set("COLOR", st.text_color.lower())
    if st.fill and st.fill != "none":
        el.set("BACKGROUND_COLOR", st.fill.lower())
    if st.shape:
        el.set("STYLE", "fork" if st.shape == "none" else "bubble")
    if node.collapsed and node.children:
        el.set("FOLDED", "true")
    if node.link:
        el.set("LINK", node.link)
    if st.color:
        ET.SubElement(el, "edge", COLOR=st.color.lower())
    if st.bold or st.italic or st.font_family or st.font_size:
        font = ET.SubElement(el, "font", NAME=st.font_family or "SansSerif", SIZE=str(st.font_size or 12))
        if st.bold:
            font.set("BOLD", "true")
        if st.italic:
            font.set("ITALIC", "true")
    if node.icon in ICON_TO_FREEMIND:
        ET.SubElement(el, "icon", BUILTIN=ICON_TO_FREEMIND[node.icon])
    if node.note:
        rich = ET.SubElement(el, "richcontent", TYPE="NOTE")
        html = ET.SubElement(rich, "html")
        ET.SubElement(html, "head")
        body = ET.SubElement(html, "body")
        for line in node.note.split("\n"):
            ET.SubElement(body, "p").text = line
    return el


def build_xml(mindmap: MindMap) -> str:
    right, left = root_split(mindmap.root, expand_all=True)
    sides = {n.id: "right" for n in right} | {n.id: "left" for n in left}
    doc = ET.Element("map", version="1.0.1")
    root_el = _node_el(mindmap.root, sides)
    doc.append(root_el)
    # Les enfants de la racine : FreeMind lit les « right » avant les « left ».
    stack = [(mindmap.root, root_el)]
    while stack:
        node, el = stack.pop()
        children = [*right, *left] if node is mindmap.root else node.children
        for child in children:
            child_el = _node_el(child, sides if node is mindmap.root else {})
            el.append(child_el)
            stack.append((child, child_el))
    ET.indent(doc, space="    ")
    return HEADER + ET.tostring(doc, encoding="unicode")


def _has_unexported_style(node: Node) -> bool:
    st = node.style
    return any(getattr(st, k) is not None for k in (
        "underline", "strike", "align", "wrap_width", "border_style", "border_width",
        "link_style", "link_width", "border_color"))


def export_file(path: Path, mindmap: MindMap) -> list[str]:
    Path(path).write_text(build_xml(mindmap), encoding="utf-8")
    warnings = []
    if any(_has_unexported_style(n) for n in mindmap.nodes()):
        warnings.append("Soulignement, alignement et types de traits ne sont pas exportés vers FreeMind.")
    lost = sum(1 for n in mindmap.nodes() if n.icon and n.icon not in ICON_TO_FREEMIND)
    if lost:
        warnings.append(f"{lost} icône(s) sans équivalent FreeMind non exportée(s).")
    if any(n.style.shape in ("rect", "diamond") for n in mindmap.nodes()):
        warnings.append("Les formes rectangle et losange sont exportées comme « bulle ».")
    return warnings


FORMAT = Format("freemind", "FreeMind", ".mm", import_file, export_file)
