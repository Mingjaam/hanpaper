#!/bin/bash
# Builds dist/Hanpaper.app, dist/Hanpaper.dmg and dist/Hanpaper-macos.zip on macOS.   bash packaging/build_mac.sh
set -e
cd "$(dirname "$0")/.."
PY=${PYTHON:-python3}
[ -d .venv ] || "$PY" -m venv .venv
. .venv/bin/activate
pip install -q -r requirements.txt pyinstaller Pillow pyobjc-framework-WebKit
python packaging/make_icon.py
python -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging/hanpaper.spec
rm -f dist/Hanpaper.dmg dist/Hanpaper-macos.zip
ditto -c -k --keepParent dist/Hanpaper.app dist/Hanpaper-macos.zip
mkdir -p dist/dmg && rm -rf dist/dmg/* && cp -R dist/Hanpaper.app dist/dmg/ && ln -sf /Applications dist/dmg/Applications
hdiutil create -volname "한페이퍼" -srcfolder dist/dmg -ov -format UDZO dist/Hanpaper.dmg
echo "Done: dist/Hanpaper.app, dist/Hanpaper.dmg, dist/Hanpaper-macos.zip"
