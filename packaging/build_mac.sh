#!/bin/bash
# Builds dist/Hanpaper.app, dist/Hanpaper.dmg and dist/Hanpaper-macos.zip on macOS.   bash packaging/build_mac.sh
#
# Optional, for a build that opens without the "unidentified developer" warning:
#   MAC_SIGN_IDENTITY      "Developer ID Application: ..." in the keychain (otherwise: ad-hoc signature)
#   MAC_NOTARY_KEY_PATH,   App Store Connect API key (.p8), its key ID and issuer ID for notarization
#   MAC_NOTARY_KEY_ID,
#   MAC_NOTARY_ISSUER
set -e
cd "$(dirname "$0")/.."
PY=${PYTHON:-python3}
[ -d .venv ] || "$PY" -m venv .venv
. .venv/bin/activate
pip install -q -r requirements.txt pyinstaller Pillow pyobjc-framework-WebKit
python packaging/make_icon.py
python -m PyInstaller --noconfirm --clean --distpath dist --workpath build packaging/hanpaper.spec

app=dist/Hanpaper.app
ent=packaging/entitlements.plist
if [ -n "$MAC_SIGN_IDENTITY" ]; then
  echo "Signing with: $MAC_SIGN_IDENTITY"
  # every Mach-O inside first (inside out), then the bundle, all with the hardened runtime and a timestamp
  find "$app/Contents" -type f \( -name "*.so" -o -name "*.dylib" -o -perm -u+x \) -print0 | while IFS= read -r -d '' f; do
    if file "$f" | grep -q "Mach-O"; then
      codesign --force --options runtime --timestamp --entitlements "$ent" --sign "$MAC_SIGN_IDENTITY" "$f"
    fi
  done
  codesign --force --options runtime --timestamp --entitlements "$ent" --sign "$MAC_SIGN_IDENTITY" "$app"
else
  echo "No Developer ID: ad-hoc signature (macOS will warn about an unidentified developer)"
  codesign --force --deep --sign - "$app"
fi
codesign --verify --deep --strict --verbose=2 "$app"

notarize() {   # $1 = file to submit (zip or dmg)
  xcrun notarytool submit "$1" --key "$MAC_NOTARY_KEY_PATH" --key-id "$MAC_NOTARY_KEY_ID" --issuer "$MAC_NOTARY_ISSUER" --wait --timeout 30m
}
if [ -n "$MAC_SIGN_IDENTITY" ] && [ -n "$MAC_NOTARY_KEY_PATH" ]; then
  ditto -c -k --keepParent "$app" dist/notarize.zip
  notarize dist/notarize.zip
  xcrun stapler staple "$app"
  rm dist/notarize.zip
fi

rm -f dist/Hanpaper.dmg dist/Hanpaper-macos.zip
ditto -c -k --keepParent "$app" dist/Hanpaper-macos.zip
rm -rf dist/dmg && mkdir -p dist/dmg && cp -R "$app" dist/dmg/ && ln -sf /Applications dist/dmg/Applications
hdiutil create -volname "한페이퍼" -srcfolder dist/dmg -ov -format UDZO dist/Hanpaper.dmg
if [ -n "$MAC_SIGN_IDENTITY" ]; then
  codesign --force --timestamp --sign "$MAC_SIGN_IDENTITY" dist/Hanpaper.dmg
  if [ -n "$MAC_NOTARY_KEY_PATH" ]; then
    notarize dist/Hanpaper.dmg
    xcrun stapler staple dist/Hanpaper.dmg
  fi
fi
spctl --assess --type execute --verbose "$app" || echo "(Gatekeeper assessment above; expected to fail for ad-hoc builds)"
echo "Done: $app, dist/Hanpaper.dmg, dist/Hanpaper-macos.zip"
