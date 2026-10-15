import os
import sys

from PySide6.QtCore import QEvent, QObject, Signal
from PySide6.QtWidgets import QApplication

from .icons import app_icon
from .main_window import MainWindow


class FileOpenHandler(QObject):
    """Fichier ouvert depuis le Finder (double-clic, glisser sur l'icône du Dock) : macOS envoie
    un événement système, pas un argument de ligne de commande."""

    opened = Signal(str)

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.FileOpen:
            path = event.file() or event.url().toLocalFile()
            if path:
                self.opened.emit(path)
            return True
        return False


def configure(app: QApplication) -> None:
    app.setApplicationName("EasyGhost")
    app.setWindowIcon(app_icon())   # icône du Dock (macOS) et des fenêtres


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    if "--self-check" in argv:
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")   # sans affichage
        from .selfcheck import run

        return run()
    app = QApplication(argv)
    configure(app)
    args = [a for a in argv[1:] if not a.startswith("-")]
    window = MainWindow(args[0] if args else None)
    handler = FileOpenHandler(app)
    app.installEventFilter(handler)
    handler.opened.connect(window.open_requested)
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
