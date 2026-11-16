# PyInstaller spec for Hanpaper (한페이퍼) (Windows .exe folder, macOS .app bundle)
#   Windows: packaging\build.bat      macOS: packaging/build_mac.sh
import os
import sys

ROOT = os.path.abspath(os.path.join(SPECPATH, ".."))
SRC = os.path.join(ROOT, "hanpaper")
MAC = sys.platform == "darwin"
ICON = os.path.join(SPECPATH, "hanpaper.icns" if MAC else "hanpaper.ico")

datas = [(os.path.join(SRC, "static"), "hanpaper/static")]
hidden = ["server", "papers", "pdfcore", "llm", "chat", "settings", "paths", "pymupdf", "anthropic", "openai"]
hidden += ["webview.platforms.cocoa"] if MAC else ["webview.platforms.winforms", "webview.platforms.edgechromium", "clr"]
excludes = ["tkinter", "matplotlib", "numpy.tests", "pytest", "IPython"]

a = Analysis([os.path.join(SRC, "app.py")], pathex=[SRC], datas=datas, hiddenimports=hidden, excludes=excludes)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Hanpaper", icon=ICON if os.path.exists(ICON) else None,
          console=False, version=None if MAC else os.path.join(SPECPATH, "version.txt"))
coll = COLLECT(exe, a.binaries, a.datas, name="Hanpaper")
if MAC:
    app = BUNDLE(coll, name="Hanpaper.app", icon=ICON if os.path.exists(ICON) else None, bundle_identifier="io.github.mingjaam.hanpaper",
                 info_plist={"CFBundleDisplayName": "한페이퍼", "CFBundleShortVersionString": "1.0.0", "NSHighResolutionCapable": True,
                             "CFBundleDocumentTypes": [{"CFBundleTypeName": "PDF", "LSItemContentTypes": ["com.adobe.pdf"], "CFBundleTypeRole": "Viewer"}]})
