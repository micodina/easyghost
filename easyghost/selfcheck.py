"""Auto-vérification : `easyghost --self-check` (utile pour tester l'application empaquetée).

Contrôle que les ressources et les modules indispensables sont présents et fonctionnent :
icônes, exports d'images, formats, enregistrement, création de la fenêtre. Sans affichage.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from PySide6.QtWidgets import QApplication

CHECKS: list[tuple[str, object]] = []


def check(name: str):
    def register(fn):
        CHECKS.append((name, fn))
        return fn
    return register


@check("icône de l'application")
def _app_icon():
    from .icons import app_icon

    icon = app_icon()
    return not icon.isNull() and 512 in {s.width() for s in icon.availableSizes()}


@check("icônes d'interface et de nœuds (SVG)")
def _svg_icons():
    from .icons import svg_renderer
    from .iconset import ICON_TABLE, UI_ICONS

    return (all(svg_renderer("ui", n, "#000000") for n in UI_ICONS)
            and all(svg_renderer("node", svg, "#000000") for _k, svg, *_ in ICON_TABLE))


@check("formats d'import / export")
def _formats():
    from . import formats

    return [f.key for f in formats.all_formats()] == ["smmx", "freemind", "opml", "markdown", "xmind"]


@check("fenêtre, enregistrement et réouverture")
def _window_and_storage():
    from . import storage
    from .main_window import MainWindow

    win = MainWindow()
    try:
        root = win.scene.mindmap.root
        child = win.scene.mindmap.add_child(root, "Enfant")
        child.note = "note"
        win.scene.sync()
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "test.easyghost"
            storage.save(path, win.scene.mindmap)
            return [n.text for n in storage.load(path).nodes()] == [root.text, "Enfant"]
    finally:
        win.stack.setClean()
        win.close()


@check("exports PNG, SVG, PDF et formats texte")
def _exports():
    from . import export_image, formats
    from .main_window import MainWindow

    win = MainWindow()
    try:
        win.scene.mindmap.add_child(win.scene.mindmap.root, "Enfant")
        win.scene.sync()
        with tempfile.TemporaryDirectory() as tmp:
            tmp = Path(tmp)
            export_image.export_png(win.scene, tmp / "a.png")
            export_image.export_svg(win.scene, tmp / "a.svg")
            export_image.export_pdf(win.scene, tmp / "a.pdf")
            for fmt in formats.all_formats():
                fmt.export_file(tmp / f"a{fmt.extension}", win.scene.mindmap)
            return all(p.stat().st_size > 0 for p in tmp.iterdir()) and len(list(tmp.iterdir())) == 8
    finally:
        win.stack.setClean()
        win.close()


def run() -> int:
    """Lance les contrôles ; code de sortie 0 si tout passe."""
    app = QApplication.instance() or QApplication([])
    failures = 0
    for name, fn in CHECKS:
        try:
            ok = bool(fn())
            detail = ""
        except Exception as exc:  # noqa: BLE001 - on veut rapporter n'importe quelle erreur
            ok, detail = False, f" ({type(exc).__name__}: {exc})"
        print(f"{'OK  ' if ok else 'ÉCHEC'} {name}{detail}")
        failures += not ok
    app.processEvents()
    print("auto-vérification réussie" if not failures else f"{failures} contrôle(s) en échec")
    return 1 if failures else 0
