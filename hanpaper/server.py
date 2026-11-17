"""Local HTTP server for the Hanpaper page (127.0.0.1 only; POSTs need the per-run token)."""
import json
import mimetypes
import os
import re
import secrets
import shutil
import sys
import threading
import time
import traceback
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import chat
import llm
import papers
import paths
import pdfcore
import settings

TOKEN = secrets.token_hex(16)
HOOKS = {"app": False, "pick": None, "save": None, "focus": None, "reveal": None, "theme": None}
mimetypes.add_type("font/ttf", ".ttf")
mimetypes.add_type("font/woff2", ".woff2")
mimetypes.add_type("text/javascript", ".js")


class H(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass

    # ---- helpers
    def _send(self, code, body, ctype="application/json; charset=utf-8", headers=None):
        if isinstance(body, (dict, list)):
            body = json.dumps(body, ensure_ascii=False).encode("utf-8")
        elif isinstance(body, str):
            body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)

    def _file(self, path, cache=True):
        if not os.path.isfile(path):
            return self._send(404, {"error": "not found"})
        ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
        with open(path, "rb") as f:
            data = f.read()
        self._send(200, data, ctype, {"Cache-Control": "max-age=31536000, immutable" if cache else "no-cache"})

    def _json(self):
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        return json.loads(raw.decode("utf-8")) if raw else {}

    def _local(self):
        host = (self.headers.get("Host") or "").split(":")[0]
        return host in ("127.0.0.1", "localhost")

    # ---- GET
    def do_GET(self):
        if not self._local():
            return self._send(403, {"error": "forbidden"})
        u = urllib.parse.urlparse(self.path)
        q = dict(urllib.parse.parse_qsl(u.query))
        path = u.path
        try:
            if path in ("/", "/index.html"):
                html = open(os.path.join(paths.STATIC, "index.html"), encoding="utf-8").read()
                html = html.replace("__TOKEN__", TOKEN).replace("__VERSION__", paths.VERSION)
                return self._send(200, html, "text/html; charset=utf-8", {"Cache-Control": "no-cache"})
            if path.startswith("/static/"):
                f = os.path.normpath(os.path.join(paths.STATIC, urllib.parse.unquote(path[8:])))
                if not f.startswith(os.path.normpath(paths.STATIC)):
                    return self._send(403, {"error": "forbidden"})
                return self._file(f, cache=f.endswith((".ttf", ".woff2", ".otf")))
            if path == "/api/state":
                return self._send(200, {"library": papers.library(), "settings": settings.public(), "app": bool(HOOKS["app"]),
                                        "models": llm.MODELS, **llm.status(), "platform": sys.platform,
                                        "version": paths.VERSION})
            m = re.match(r"^/api/p/([0-9a-f]{12})(/.*)?$", path)
            if m:
                p = papers.get(m.group(1))
                if not p:
                    return self._send(404, {"error": "논문을 찾을 수 없습니다"})
                return self._paper_get(p, m.group(2) or "/", q)
            return self._send(404, {"error": "not found"})
        except Exception as ex:  # noqa: BLE001
            traceback.print_exc()
            return self._send(500, {"error": f"{type(ex).__name__}: {ex}"})

    def _paper_get(self, p, sub, q):
        if sub == "/":
            p.set_meta(opened=time.time())
            if p.meta().get("status") in ("queued", "analyzing", "glossary", "translating", "building") and not (p.job and p.job.alive()):
                papers.start(p, force=True)            # the app was closed mid-translation: carry on
            return self._send(200, p.state())
        if sub == "/progress":
            m = p.meta()
            return self._send(200, {"status": m.get("status"), "progress": m.get("progress"), "error": m.get("error"),
                                    "page_rev": m.get("page_rev") or {}, "rev": m.get("rev", 0), "running": bool(p.job and p.job.alive()),
                                    "field": m.get("field"), "title": m.get("title"), "step": m.get("step"),
                                    "ko_pages": m.get("ko_pages") if p.is_src else None, "build_error": m.get("build_error"),
                                    "building": p.building() if p.is_src else False})
        if sub == "/units":
            st = p.state()
            return self._send(200, {"units": st["units"], "glossary": st["glossary"], "tables": st["tables"]})
        m = re.match(r"^/page/(en|ko)/(\d+)\.png$", sub)
        if m:
            return self._file(p.page_png(m.group(1), int(m.group(2)), q.get("z", "2")))
        m = re.match(r"^/(fig|tab)/(\d+)\.png$", sub)
        if m:
            return self._file(p.fig_png(m.group(1), int(m.group(2)), q.get("side", "en")))
        m = re.match(r"^/crop/(en|ko)/(\d+)\.png$", sub)
        if m:
            r = [float(x) for x in q.get("r", "").split(",")]
            return self._file(p.crop_png(m.group(1), int(m.group(2)), r))
        if sub == "/chat":
            c = chat.of(p)
            since = int(q.get("rev", 0))
            snap = c.snapshot()
            if snap["rev"] == since:
                return self._send(200, {"rev": since, "same": True, "running": snap["running"]})
            return self._send(200, snap)
        if sub == "/original.pdf":
            return self._file(p.pdf, cache=False)
        return self._send(404, {"error": "not found"})

    # ---- POST
    def do_POST(self):
        if not self._local() or self.headers.get("X-PB-Token") != TOKEN:
            return self._send(403, {"error": "forbidden"})
        u = urllib.parse.urlparse(self.path)
        path = u.path
        try:
            if path == "/api/upload":
                n = int(self.headers.get("Content-Length") or 0)
                if n > 300 * 1024 * 1024:
                    return self._send(413, {"error": "파일이 너무 큽니다 (300MB 초과)"})
                data = self.rfile.read(n)
                name = urllib.parse.unquote(self.headers.get("X-File-Name") or "paper.pdf")
                p = papers.import_file(data, name)
                return self._send(200, {"id": p.id})
            body = self._json()
            if path == "/api/open":
                f = body.get("path") or (HOOKS["pick"]() if HOOKS["pick"] else "")
                if not f:
                    return self._send(200, {"cancel": True})
                data = open(f, "rb").read()
                p = papers.import_file(data, os.path.basename(f))
                return self._send(200, {"id": p.id})
            if path == "/api/settings":
                cur = settings.update(body)
                return self._send(200, settings.public())
            if path == "/api/check":
                return self._send(200, llm.check())
            if path == "/api/focus":
                if HOOKS["focus"]:
                    HOOKS["focus"]()
                return self._send(200, {"ok": True})
            if path == "/api/theme":
                if HOOKS["theme"]:
                    HOOKS["theme"](body.get("dark"), body.get("color"))
                return self._send(200, {"ok": True})
            m = re.match(r"^/api/p/([0-9a-f]{12})/(\w+)$", path)
            if m:
                p = papers.get(m.group(1))
                if not p:
                    return self._send(404, {"error": "논문을 찾을 수 없습니다"})
                return self._paper_post(p, m.group(2), body)
            return self._send(404, {"error": "not found"})
        except (ValueError, llm.LLMError) as ex:
            return self._send(400, {"error": str(ex)})
        except Exception as ex:  # noqa: BLE001
            traceback.print_exc()
            return self._send(500, {"error": f"{type(ex).__name__}: {ex}"})

    def _paper_post(self, p, act, b):
        if act == "delete":
            return self._send(200, {"ok": papers.delete(p.id)})
        if act == "resume":
            if b.get("restart"):
                for f in ("doc.json", "glossary.json", "ko.pdf"):
                    try:
                        os.remove(p.f(f))
                    except OSError:
                        pass
                if p.is_src:
                    p.set_meta(ko_pages=None, page_rev={})
                p._doc = None
                shutil.rmtree(p.f("cache"), ignore_errors=True)    # page images and crops of the old analysis
            ok = papers.start(p, force=True)
            return self._send(200, {"ok": ok})
        if act == "stop":
            if p.job:
                p.job.stop.set()
            return self._send(200, {"ok": True})
        if act == "retranslate":
            u = papers.retranslate(p, b["unit"], b.get("instruction", ""))
            return self._send(200, {"ok": True, "unit": p.pub(u)})
        if act == "edit":
            u = papers.set_translation(p, b["unit"], b.get("ko", ""))
            return self._send(200, {"ok": True, "unit": p.pub(u)})
        if act == "toggle":
            u = papers.toggle_translate(p, b["unit"], b.get("on", True))
            return self._send(200, {"ok": True, "unit": p.pub(u)})
        if act == "glossary":
            changed = papers.apply_glossary(p, b.get("terms", []), b.get("field"))
            n = papers.retranslate_terms(p, changed) if b.get("apply") else 0
            return self._send(200, {"ok": True, "changed": changed, "retranslating": n})
        if act == "notes":
            data = {"marks": b.get("marks", [])}
            p.save_notes(data)
            return self._send(200, {"ok": True})
        if act == "rects":
            side, page = b["side"], int(b["page"])
            if p.is_src:
                src, pno = (p.ko_pdf, page) if side == "ko" else (p.pdf, page)
            else:
                src = p.ko_page(page) if side == "ko" and os.path.exists(p.ko_page(page)) else p.pdf
                pno = 0 if src != p.pdf else page
            if not os.path.exists(src):
                return self._send(200, {"rects": []})
            return self._send(200, {"rects": pdfcore.search_rects(src, pno, b.get("text", ""))})
        if act == "chat":
            ok = chat.of(p).send(b.get("text", ""), b.get("context"))
            return self._send(200, {"ok": ok})
        if act == "chatstop":
            chat.of(p).cancel()
            return self._send(200, {"ok": True})
        if act == "chatclear":
            return self._send(200, {"ok": chat.of(p).clear()})
        if act == "export":
            kind = b.get("kind", "ko")
            base = re.sub(r"\.(tar\.gz|tgz|zip|tar|gz|tex|docx|pdf)$", "", p.meta().get("file") or "paper", flags=re.I)
            suffix = {"ko": "_한글", "en": "_원문", "side": "_대역", "src": "_한글"}[kind]
            ext = ".pdf" if kind != "src" else (".docx" if p.kind == "docx" else ".zip")
            name = f"{base}{suffix}{ext}"
            if HOOKS["save"]:
                out = HOOKS["save"](name)
                if not out:
                    return self._send(200, {"cancel": True})
            else:
                out = os.path.join(os.path.expanduser("~"), "Downloads", name)
            papers.export(p, kind, out, with_marks=b.get("marks", True))
            if b.get("reveal") and HOOKS["reveal"]:
                HOOKS["reveal"](out)
            return self._send(200, {"ok": True, "path": out})
        if act == "reveal":
            if HOOKS["reveal"]:
                HOOKS["reveal"](b.get("path") or p.pdf)
            return self._send(200, {"ok": True})
        return self._send(404, {"error": "unknown action"})


def _pub(u):
    out = {k: u.get(k) for k in ("id", "page", "kind", "translate", "bbox", "text", "ko", "err")}
    if u.get("ko"):
        out["ko_html"] = pdfcore._clean_ko(u["ko"])
        out["ko"] = pdfcore.plain(u["ko"])
    return out


class Server(ThreadingHTTPServer):
    daemon_threads = True
    # On Windows SO_REUSEADDR lets a second process bind a port that is already in use; never share a port there.
    allow_reuse_address = sys.platform != "win32"


def make_server(port=8790):
    for p in range(port, port + 40):
        try:
            return Server(("127.0.0.1", p), H), p
        except OSError:
            continue
    srv = Server(("127.0.0.1", 0), H)
    return srv, srv.server_address[1]


if __name__ == "__main__":                      # browser mode for development: python hanpaper/server.py
    srv, port = make_server()
    print(f"Hanpaper: http://127.0.0.1:{port}/", flush=True)
    srv.serve_forever()
