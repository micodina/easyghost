#!/bin/bash
# Construit dist/EasyGhost.app puis dist/EasyGhost-<version>.dmg (macOS, architecture de la machine).
#   .venv/bin/pip install -e '.[build]'     # une fois : installe PyInstaller
#   tools/build_macos.sh
set -euo pipefail
cd "$(dirname "$0")/.."
PY=.venv/bin/python
APP=dist/EasyGhost.app

"$PY" -m PyInstaller packaging/easyghost.spec --noconfirm --clean \
    --distpath dist --workpath build/pyinstaller

rm -rf dist/EasyGhost                      # dossier intermédiaire de PyInstaller (doublon de l'application)
echo "--- auto-vérification de l'application empaquetée"
"$APP/Contents/MacOS/EasyGhost" --self-check

VERSION=$("$PY" -c "import tomllib;print(tomllib.load(open('pyproject.toml','rb'))['project']['version'])")
DMG="dist/EasyGhost-$VERSION.dmg"
STAGE=$(mktemp -d)
trap 'rm -rf "$STAGE"' EXIT
cp -R "$APP" "$STAGE/"
ln -s /Applications "$STAGE/Applications"          # glisser l'application sur « Applications »
rm -f "$DMG"
hdiutil create -volname "EasyGhost" -srcfolder "$STAGE" -ov -format UDZO "$DMG" >/dev/null
echo "--- terminé"
du -sh "$APP" "$DMG"
