"""Where things live, on Windows and macOS, from source or as a bundled app."""
import os
import shutil
import sys

APP_NAME = "한페이퍼"
APP_ID = "Hanpaper"
VERSION = "1.0.0"
FROZEN = bool(getattr(sys, "frozen", False))
WIN = sys.platform == "win32"
MAC = sys.platform == "darwin"

HERE = os.path.dirname(os.path.abspath(__file__))
RES = os.path.join(getattr(sys, "_MEIPASS", ""), "hanpaper") if FROZEN else HERE
STATIC = os.path.join(RES, "static")

if WIN:
    DATA = os.path.join(os.environ.get("APPDATA") or os.path.expanduser("~"), APP_ID)
elif MAC:
    DATA = os.path.join(os.path.expanduser("~"), "Library", "Application Support", APP_ID)
else:
    DATA = os.path.join(os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share"), APP_ID)
# papers translated with the pre-release name (Paper Bridge) move over once
_OLD = os.path.join(os.path.dirname(DATA), "PaperBridge")
if not os.path.exists(DATA) and os.path.isdir(_OLD):
    try:
        shutil.copytree(_OLD, DATA, ignore=shutil.ignore_patterns("webview", "running.json", "tmp"))
    except OSError:
        pass
PAPERS = os.path.join(DATA, "papers")
SETTINGS = os.path.join(DATA, "settings.json")
os.makedirs(PAPERS, exist_ok=True)

NOWIN = getattr(__import__("subprocess"), "CREATE_NO_WINDOW", 0)


def claude_exe():
    """The Claude Code CLI. GUI apps on macOS do not get the shell PATH, so the usual install places are tried too."""
    found = shutil.which("claude")
    if found:
        return found
    home = os.path.expanduser("~")
    dirs = [os.path.join(home, ".local", "bin"), os.path.join(home, ".claude", "local"),
            os.path.join(home, ".npm-global", "bin"), "/opt/homebrew/bin", "/usr/local/bin"]
    if WIN:
        dirs += [os.path.join(os.environ.get("APPDATA", ""), "npm"), os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs", "claude")]
    names = ("claude.exe", "claude.cmd") if WIN else ("claude",)
    for d in dirs:
        for n in names:
            f = os.path.join(d, n)
            if os.path.isfile(f):
                return f
    nvm = os.path.join(home, ".nvm", "versions", "node")
    if os.path.isdir(nvm):
        for v in sorted(os.listdir(nvm), reverse=True):
            f = os.path.join(nvm, v, "bin", "claude")
            if os.path.isfile(f):
                return f
    return None
