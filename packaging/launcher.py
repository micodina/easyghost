"""Point d'entrée de l'application empaquetée (PyInstaller n'aime pas les imports relatifs de __main__)."""

import sys

from easyghost.__main__ import main

if __name__ == "__main__":
    sys.exit(main())
