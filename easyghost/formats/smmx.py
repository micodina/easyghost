"""SimpleMind (.smmx) : archive zip contenant document/mindmap.xml.

Structure observée (SimpleMind 1.x–2.x, doc-version 3) :
  <topic id parent x y text [palette colorinfo] [guid]>
      <style [borderstyle] ><font bold/></style>
      <fillcolor r g b | none="true"/> <textcolor r g b/> <strokecolor r g b/>
      <note>, <link>, <parent-relation>, …
Les positions x/y sont libres ; ici elles ne servent qu'à déduire le côté
(gauche/droite) des branches principales, la mise en page étant recalculée.
"""

from __future__ import annotations

import base64
import os
import secrets
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

from ..layout import compute_layout, root_split
from ..model import (
    BRANCH_PALETTE,
    MindMap,
    Node,
    NodeStyle,
    hex_to_rgb,
    ICONS,
    normalize_color,
    normalize_link,
    normalize_note,
    normalize_text,
    rgb_to_hex,
)
from . import Format, FormatError, ImportResult, check_xml_bytes

XML_MEMBER = "document/mindmap.xml"
SHAPE_FROM_SMMX = {
    "sbsRectangle": "rect",
    "sbsHalfRound": "rounded",
    "sbsDiamond": "diamond",
    "sbsNone": "none",
}
SHAPE_TO_SMMX = {v: k for k, v in SHAPE_FROM_SMMX.items()}


# --------------------------------------------------------------------- import
def _rgb_attr(el: ET.Element) -> str | None:
    try:
        return rgb_to_hex(int(el.get("r")), int(el.get("g")), int(el.get("b")))
    except (TypeError, ValueError):
        return None


def _read_style(topic: ET.Element) -> NodeStyle:
    style = NodeStyle()
    style_els = topic.findall("style")
    for container in [topic, *style_els]:
        for tag, attr in (("fillcolor", "fill"), ("textcolor", "text_color"), ("strokecolor", "color")):
            el = container.find(tag)
            if el is None:
                continue
            if tag == "fillcolor" and el.get("none") == "true":
                style.fill = "none"
            elif (color := _rgb_attr(el)) is not None:
                setattr(style, attr, color)
    for st in style_els:
        shape = SHAPE_FROM_SMMX.get(st.get("borderstyle", ""))
        if shape:
            style.shape = shape
        font = st.find("font")
        if font is not None:
            if font.get("bold") == "true":
                style.bold = True
            if font.get("italic") == "true":
                style.italic = True
    return style


def _read_content(topic: ET.Element, node: Node) -> None:
    note = topic.find("note")
    if note is not None:
        node.note = normalize_note(note.text or "")
    link = topic.find("link")
    if link is not None:
        node.link = normalize_link(link.get("urllink"))
    # Les icônes de SimpleMind (identifiants « ic8_… ») ne sont pas reprises : EasyGhost a ses propres icônes.
    icon = topic.get("icon")
    node.icon = icon if icon in ICONS else None


def _ignored_features(topics: list[ET.Element], doc: ET.Element) -> list[str]:
    counts = {
        "liens vers un contact ou un élément": sum(
            1 for t in topics for lk in t.findall("link") if not lk.get("urllink")
        ),
        "icônes SimpleMind (EasyGhost a les siennes)": sum(
            1 for t in topics if t.get("icon") and t.get("icon") not in ICONS
        ),
        "images": sum(len(t.findall("embedded-image")) for t in topics),
        "cases à cocher": sum(1 for t in topics if t.get("checkbox")),
        "relations": len(doc.findall("./relations/relation")),
        "textes libres": sum(len(t.findall("./children/text")) for t in topics),
    }
    return [f"{n} {name}" for name, n in counts.items() if n]


def parse_xml(data: bytes) -> ImportResult:
    check_xml_bytes(data)
    try:
        doc = ET.fromstring(data)
    except ET.ParseError as exc:
        raise FormatError(f"XML invalide : {exc}") from exc
    if doc.tag != "simplemind-mindmaps":
        raise FormatError("ce n'est pas un document SimpleMind")
    mm_el = doc.find("mindmap")
    topics_el = mm_el.find("topics") if mm_el is not None else None
    if topics_el is None:
        raise FormatError("aucun sujet dans le document")

    warnings: list[str] = []
    topic_els = topics_el.findall("topic")
    parsed: dict[int, tuple[ET.Element, int]] = {}
    skipped = 0
    for t in topic_els:
        try:
            tid, parent = int(t.get("id")), int(t.get("parent", "-1"))
        except (TypeError, ValueError):
            skipped += 1
            continue
        if tid in parsed:
            skipped += 1
            continue
        parsed[tid] = (t, parent)
    if skipped:
        warnings.append(f"{skipped} sujet(s) invalides ignorés")

    roots = [tid for tid, (_, parent) in parsed.items() if parent == -1]
    if not roots:
        raise FormatError("aucun sujet central dans le document")
    main = mm_el.find("./meta/main-centraltheme")
    try:
        main_id = int(main.get("id")) if main is not None else roots[0]
    except (TypeError, ValueError):
        main_id = roots[0]
    root_id = main_id if main_id in roots else roots[0]

    children: dict[int, list[int]] = {}
    for tid, (_, parent) in parsed.items():
        if tid != root_id:
            children.setdefault(parent, []).append(tid)

    def text_of(el: ET.Element) -> str:
        return normalize_text((el.get("text") or "").replace("\\N", "\n"))

    mindmap = MindMap(text_of(parsed[root_id][0]))
    mindmap.root.style = _read_style(parsed[root_id][0])
    _read_content(parsed[root_id][0], mindmap.root)
    nodes: dict[int, Node] = {root_id: mindmap.root}

    def attach(tid: int, parent_node: Node) -> None:
        el = parsed[tid][0]
        node = mindmap.add_child(parent_node, text_of(el))
        node.style = _read_style(el)
        _read_content(el, node)
        if parent_node is mindmap.root and node.style.color is None:
            try:
                palette = int(el.get("palette", ""))
            except ValueError:
                palette = 0
            if palette >= 2:
                node.style.color = BRANCH_PALETTE[(palette - 2) % len(BRANCH_PALETTE)]
        nodes[tid] = node

    stack = [(c, mindmap.root) for c in reversed(children.get(root_id, []))]
    # file de traitement itérative : évite la récursion sur les cartes profondes
    while stack:
        tid, parent_node = stack.pop()
        if tid in nodes:
            continue
        attach(tid, parent_node)
        stack.extend((c, nodes[tid]) for c in reversed(children.get(tid, [])))

    orphans = [tid for tid in parsed if tid not in nodes]
    if orphans:
        for tid in orphans:
            if tid not in nodes:
                attach(tid, mindmap.root)
        warnings.append(f"{len(orphans)} sujet(s) non rattachés placés sous la racine")

    # Côté des branches principales : d'après la position x par rapport au centre.
    def pos(tid: int) -> tuple[float, float]:
        t = parsed[tid][0]
        try:
            return float(t.get("x", 0)), float(t.get("y", 0))
        except ValueError:
            return 0.0, 0.0

    cx = pos(root_id)[0]
    top = [(tid, n) for tid, n in nodes.items() if n.parent is mindmap.root]
    right = sorted((p for p in top if pos(p[0])[0] >= cx), key=lambda p: pos(p[0])[1])
    left = sorted((p for p in top if pos(p[0])[0] < cx), key=lambda p: pos(p[0])[1])
    for _, n in right:
        n.side = "right"
    for _, n in left:
        n.side = "left"
    mindmap.root.children = [n for _, n in right + left]

    ignored = _ignored_features([t for t, _ in parsed.values()], mm_el)
    if ignored:
        warnings.append("Non pris en charge (ignorés) : " + ", ".join(ignored))
    return ImportResult(mindmap, warnings)


def import_file(path: Path) -> ImportResult:
    try:
        with zipfile.ZipFile(path) as zf:
            try:
                info = zf.getinfo(XML_MEMBER)
            except KeyError as exc:
                raise FormatError(f"{XML_MEMBER} introuvable dans l'archive") from exc
            if info.file_size > 64 * 1024 * 1024:
                raise FormatError("document trop volumineux")
            data = zf.read(info)
    except zipfile.BadZipFile as exc:
        # Certains fichiers .smmx (modèles) sont du XML brut.
        raw = Path(path).read_bytes()
        if raw.lstrip(b"\xef\xbb\xbf \t\r\n").startswith(b"<"):
            return parse_xml(raw)
        raise FormatError("archive .smmx invalide") from exc
    return parse_xml(data)


# --------------------------------------------------------------------- export
def _guid() -> str:
    return base64.urlsafe_b64encode(os.urandom(16)).rstrip(b"=").decode()


def _estimate_size(node: Node) -> tuple[float, float]:
    return 8.0 * max(len(node.text), 4) + 28.0, 32.0


def _color_el(parent: ET.Element, tag: str, color: str) -> None:
    el = ET.SubElement(parent, tag)
    if tag == "fillcolor" and color == "none":
        el.set("none", "true")
        return
    r, g, b = hex_to_rgb(color)
    el.set("r", str(r)); el.set("g", str(g)); el.set("b", str(b))


def build_xml(mindmap: MindMap) -> bytes:
    nodes = list(mindmap.nodes())
    ids = {n.id: i for i, n in enumerate(nodes)}
    centers = {}
    for nid, (x, y) in compute_layout(mindmap, _estimate_size, expand_all=True).items():
        w, h = _estimate_size(mindmap.find(nid))
        centers[nid] = (400.0 + x + w / 2, 400.0 + y + h / 2)

    doc = ET.Element("simplemind-mindmaps", {"doc-version": "3", "generator": "easyghost", "gen-version": "0.1"})
    mm = ET.SubElement(doc, "mindmap")
    meta = ET.SubElement(mm, "meta")
    ET.SubElement(meta, "guid", guid=secrets.token_hex(12).upper())
    ET.SubElement(meta, "title", text=mindmap.root.text)
    ET.SubElement(meta, "style", key="system.bright-palette")
    ET.SubElement(meta, "auto-numbering", style="disabled")
    ET.SubElement(meta, "scrollstate", zoom="100", x="0", y="0")
    ET.SubElement(meta, "main-centraltheme", id="0")
    topics = ET.SubElement(mm, "topics")
    for node in nodes:
        cx, cy = centers[node.id]
        attrs = {
            "id": str(ids[node.id]),
            "parent": str(ids[node.parent.id]) if node.parent else "-1",
            "guid": _guid(),
            "x": f"{cx:.2f}",
            "y": f"{cy:.2f}",
        }
        if node.parent is None:
            attrs["palette"] = attrs["colorinfo"] = "1"
        elif node.parent.parent is None:
            palette = 2 + node.index % 7
            attrs["palette"] = attrs["colorinfo"] = str(palette)
        attrs["text"] = node.text.replace("\n", "\\N")
        attrs["textfmt"] = "plain"
        t = ET.SubElement(topics, "topic", attrs)
        st = node.style
        if st.shape or st.bold or st.italic:
            style_el = ET.SubElement(t, "style")
            if st.shape:
                style_el.set("borderstyle", SHAPE_TO_SMMX[st.shape])
            if st.bold or st.italic:
                font = ET.SubElement(style_el, "font")
                if st.bold:
                    font.set("bold", "true")
                if st.italic:
                    font.set("italic", "true")
        if st.fill:
            _color_el(t, "fillcolor", st.fill)
        if st.text_color:
            _color_el(t, "textcolor", st.text_color)
        if st.color:
            _color_el(t, "strokecolor", st.color)
        if node.link:
            ET.SubElement(t, "link", urllink=node.link)
        if node.note:
            ET.SubElement(t, "note", textfmt="plain").text = node.note
    ET.SubElement(mm, "relations")
    ET.SubElement(mm, "node-groups")
    ET.indent(doc, space="    ")
    body = ET.tostring(doc, encoding="unicode", short_empty_elements=False)
    head = '<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE simplemind-mindmaps>\n\n'
    return b"\xef\xbb\xbf" + (head + body).encode("utf-8")


def _has_unexported_style(node: Node) -> bool:
    st = node.style
    return any(getattr(st, k) is not None for k in (
        "font_family", "font_size", "underline", "strike", "align", "wrap_width",
        "border_style", "border_width", "link_style", "link_width", "border_color"))


def export_file(path: Path, mindmap: MindMap) -> list[str]:
    data = build_xml(mindmap)
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(XML_MEMBER, data)
    warnings = []
    if any(_has_unexported_style(n) for n in mindmap.nodes()):
        warnings.append("Police, taille, soulignement, alignement et types de traits ne sont pas exportés vers SimpleMind.")
    with_icon = sum(1 for n in mindmap.nodes() if n.icon)
    if with_icon:
        warnings.append(f"{with_icon} icône(s) non exportée(s) : SimpleMind a ses propres icônes.")
    if any(n.collapsed for n in mindmap.nodes()):
        warnings.append("L'état replié des branches n'est pas exporté.")
    if any(n.style.italic for n in mindmap.nodes()):
        warnings.append("Le style italique n'a pas pu être vérifié dans SimpleMind.")
    return warnings


FORMAT = Format("smmx", "SimpleMind", ".smmx", import_file, export_file)
