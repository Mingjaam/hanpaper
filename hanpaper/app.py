"""Hanpaper (한페이퍼) desktop app: the local server in a native window (Edge WebView2 on Windows, WKWebView on macOS).

  python hanpaper/app.py        from source
  Hanpaper.exe / Hanpaper.app      installed

One instance per user: starting it again brings the open window to the front.
"""
import json
import os
import subprocess
import sys
import threading
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import paths  # noqa: E402

RUNNING = os.path.join(paths.DATA, "running.json")
WINSTATE = os.path.join(paths.DATA, "window.json")


def _already_running():
    """Ask a running copy (if any) to show itself. True when it answered."""
    try:
        info = json.load(open(RUNNING, encoding="utf-8"))
        req = urllib.request.Request(f"http://127.0.0.1:{info['port']}/api/focus", b"{}",
                                     {"Content-Type": "application/json", "X-PB-Token": info["token"]})
        urllib.request.urlopen(req, timeout=2)
        return True
    except Exception:  # noqa: BLE001  no running copy (or a stale file)
        return False


def _hwnd():
    import ctypes
    from ctypes import wintypes
    u32, me, found = ctypes.windll.user32, os.getpid(), []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def each(h, _):
        pid = wintypes.DWORD()
        u32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        if pid.value == me and u32.IsWindowVisible(h) and u32.GetWindowTextLengthW(h):
            found.append(h)
        return True
    u32.EnumWindows(each, 0)
    return found[0] if found else None


def _caption(dark, color):
    """Windows 11: title bar in the app's colour so frame and page read as one surface."""
    if not paths.WIN:
        return
    try:
        import ctypes
        hwnd = _hwnd()
        if not hwnd:
            return
        dwm = ctypes.windll.dwmapi
        v = ctypes.c_int(1 if dark else 0)
        dwm.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(v), 4)
        if color and color.startswith("#") and len(color) == 7:
            r, g, b = int(color[1:3], 16), int(color[3:5], 16), int(color[5:7], 16)
            c = ctypes.c_int(r | (g << 8) | (b << 16))
            dwm.DwmSetWindowAttribute(hwnd, 35, ctypes.byref(c), 4)
            t = ctypes.c_int(0xF0F0F0 if dark else 0x1F1F1F)
            dwm.DwmSetWindowAttribute(hwnd, 36, ctypes.byref(t), 4)
    except Exception:  # noqa: BLE001
        pass


def _system_dark():
    if paths.WIN:
        try:
            import winreg
            k = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize")
            return winreg.QueryValueEx(k, "AppsUseLightTheme")[0] == 0
        except OSError:
            return False
    if paths.MAC:
        try:
            r = subprocess.run(["defaults", "read", "-g", "AppleInterfaceStyle"], capture_output=True, text=True, timeout=2)
            return "Dark" in r.stdout
        except Exception:  # noqa: BLE001
            return False
    return False


def reveal(path):
    try:
        if paths.WIN:
            subprocess.Popen(["explorer", "/select,", os.path.normpath(path)])
        elif paths.MAC:
            subprocess.Popen(["open", "-R", path])
        else:
            subprocess.Popen(["xdg-open", os.path.dirname(path)])
    except OSError:
        pass


def main():
    if _already_running():
        return
    import webview
    import server

    srv, port = server.make_server(8790)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    json.dump({"port": port, "token": server.TOKEN, "pid": os.getpid()}, open(RUNNING, "w", encoding="utf-8"))

    try:
        geo = json.load(open(WINSTATE, encoding="utf-8"))
    except (OSError, ValueError):
        geo = {}
    dark = _system_dark()
    window = webview.create_window(
        paths.APP_NAME, f"http://127.0.0.1:{port}/",
        width=geo.get("w", 1560), height=geo.get("h", 960), x=geo.get("x"), y=geo.get("y"),
        maximized=bool(geo.get("max")), min_size=(1100, 680), text_select=True,
        background_color="#17181b" if dark else "#f5f5f2")

    def pick():
        r = window.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False, file_types=("논문 파일 (*.pdf;*.zip;*.tar.gz;*.tgz;*.tar;*.gz;*.tex;*.docx)", "PDF (*.pdf)", "LaTeX 소스 (*.zip;*.tar.gz;*.tgz;*.tar;*.gz;*.tex)", "Word (*.docx)", "모든 파일 (*.*)"))
        return os.path.normpath(r[0]) if r else ""

    def save(name):
        start = os.path.join(os.path.expanduser("~"), "Documents")
        ext = os.path.splitext(name)[1].lower() or ".pdf"
        label = {".pdf": "PDF (*.pdf)", ".zip": "LaTeX 소스 압축 (*.zip)", ".docx": "Word (*.docx)"}.get(ext, f"(*{ext})")
        r = window.create_file_dialog(webview.SAVE_DIALOG, directory=start if os.path.isdir(start) else "", save_filename=name,
                                      file_types=(label,))
        if not r:
            return ""
        f = r if isinstance(r, str) else r[0]
        return f if f.lower().endswith(ext) else f + ext

    def focus():
        try:
            window.restore()
            window.show()
        except Exception:  # noqa: BLE001
            pass
        if paths.WIN:
            import ctypes
            h = _hwnd()
            if h:
                if ctypes.windll.user32.IsIconic(h):
                    ctypes.windll.user32.ShowWindow(h, 9)
                ctypes.windll.user32.SetForegroundWindow(h)

    server.HOOKS.update(app=True, pick=pick, save=save, focus=focus, reveal=reveal, theme=lambda d, c: _caption(bool(d), c))

    maxed = {"on": bool(geo.get("max"))}

    def on_closing():
        try:
            st = dict(geo, max=maxed["on"])
            if not maxed["on"]:
                st.update(w=window.width, h=window.height, x=window.x, y=window.y)
            json.dump(st, open(WINSTATE, "w", encoding="utf-8"))
        except Exception:  # noqa: BLE001
            pass
        return True

    window.events.maximized += lambda *a: maxed.update(on=True)
    window.events.restored += lambda *a: maxed.update(on=False)
    window.events.closing += on_closing
    window.events.shown += lambda *a: _caption(dark, "#17181b" if dark else "#f5f5f2")

    webview.start(private_mode=False, storage_path=os.path.join(paths.DATA, "webview"), debug="--debug" in sys.argv)
    try:
        os.remove(RUNNING)
    except OSError:
        pass


if __name__ == "__main__":
    main()
