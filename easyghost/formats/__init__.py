"""Import/export vers des formats tiers (SimpleMind, FreeMind…)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

from ..model import MindMap


class FormatError(ValueError):
    """Fichier illisible ou invalide pour le format demandé."""


@dataclass
class ImportResult:
    mindmap: MindMap
    warnings: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class Format:
    key: str
    label: str
    extension: str  # avec le point
    import_file: Callable[[Path], ImportResult] | None  # None : export seul
    export_file: Callable[[Path, MindMap], list[str]]  # renvoie les avertissements


def all_formats() -> tuple[Format, ...]:
    from . import freemind, markdown, opml, smmx, xmind

    return (smmx.FORMAT, freemind.FORMAT, opml.FORMAT, markdown.FORMAT, xmind.FORMAT)


def importable_formats() -> tuple[Format, ...]:
    return tuple(f for f in all_formats() if f.import_file is not None)


def format_for_path(path: str | Path, for_import: bool = False) -> Format | None:
    suffix = Path(path).suffix.lower()
    candidates = importable_formats() if for_import else all_formats()
    return next((f for f in candidates if f.extension == suffix), None)


# Limites contre les fichiers piégés (XML à entités, archives zip énormes).
MAX_XML_BYTES = 64 * 1024 * 1024


def check_xml_bytes(data: bytes) -> None:
    if len(data) > MAX_XML_BYTES:
        raise FormatError("fichier XML trop volumineux")
    if b"<!ENTITY" in data:
        raise FormatError("les déclarations d'entités XML ne sont pas acceptées")
