"""Papers that come as source files (LaTeX archive or Word .docx) instead of a PDF.

The English PDF is made from the source (Tectonic for LaTeX, Word or LibreOffice for .docx), the units are the
source's paragraphs, and the Korean PDF is made the same way from the translated source. Each unit carries
`geo` = {"en": [[page, x0, y0, x1, y1], ...], "ko": [...]} so the viewers can mark it on both PDFs.
"""
import os
import re
import shutil
import time
from collections import Counter

import pymupdf

import latex as L
import texsrc

TEX_KIND = {"para": "para", "item": "para", "heading": "heading", "title": "title", "caption": "caption", "equation": "equation"}


def detect(data, name):
    n = name.lower()
    if data[:4] == b"%PDF":
        return "pdf"
    if data[:2] == b"PK":
        import io
        import zipfile
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = set(z.namelist())
        except zipfile.BadZipFile:
            return None
        if "word/document.xml" in names:
            return "docx"
        if any(x.lower().endswith(".tex") for x in names):
            return "tex"
        return None
    if texsrc.is_tex_archive(data, name):
        return "tex"
    if n.endswith(".docx"):
        return "docx"
    return None


def _pages(pdf):
    with pymupdf.open(pdf) as d:
        return [{"w": round(pg.rect.width, 2), "h": round(pg.rect.height, 2)} for pg in d]


def _body_size(pdf):
    c = Counter()
    with pymupdf.open(pdf) as d:
        for pg in list(d)[:6]:
            for b in pg.get_text("dict")["blocks"]:
                for ln in b.get("lines", []):
                    for s in ln["spans"]:
                        c[round(s["size"], 1)] += len(s["text"])
    return c.most_common(1)[0][0] if c else 10


def _first_page(rects):
    """Page holding most of the rects and the rects on it."""
    if not rects:
        return None, []
    area = Counter()
    for r in rects:
        area[r[0]] += (r[3] - r[1]) * (r[4] - r[2])
    pg = area.most_common(1)[0][0]
    return pg, [r[1:] for r in rects if r[0] == pg]


def _union(rs):
    return [min(r[0] for r in rs), min(r[1] for r in rs), max(r[2] for r in rs), max(r[3] for r in rs)]


def clean_geo(units, geo):
    """Drop boxes that are not text lines of the unit (a picture box can carry the caption's first line number)."""
    kinds = {u["id"]: u["kind"] for u in units}
    for uid, rs in geo.items():
        if kinds.get(uid) == "equation" or len(rs) < 2:
            continue
        hs = sorted(r[4] - r[2] for r in rs)
        med = hs[len(hs) // 2]
        lim = max(3 * med, 28)
        keep = [r for r in rs if r[4] - r[2] <= lim]
        if keep:
            geo[uid] = keep


def fill_by_search(pdf, units, geo, side):
    """Units SyncTeX could not place (run-in headings, some captions): find their first words in the PDF,
    on the pages between their neighbours."""
    if not os.path.exists(pdf):
        return
    with pymupdf.open(pdf) as doc:
        known = [(i, geo[u["id"]][0][0]) for i, u in enumerate(units) if geo.get(u["id"])]
        for i, u in enumerate(units):
            if geo.get(u["id"]) or u["kind"] == "equation":
                continue
            txt = u.get("text") if side == "en" else u.get("_ko_plain")
            if not txt:
                continue
            words = re.sub(r"\$[^$]*\$", " ", txt).split()
            words = [w for w in words if not re.search(r"[\\{}$]", w)]
            if not words:
                continue
            lo = max((pg for j, pg in known if j < i), default=0)
            hi = min((pg for j, pg in known if j > i), default=doc.page_count - 1)
            for n in (6, 4, 3):
                q = " ".join(words[:n])
                if len(q) < 6:
                    continue
                hits = []
                for pg in range(max(0, lo), min(doc.page_count - 1, max(lo, hi)) + 1):
                    hs = doc[pg].search_for(q)
                    if hs:
                        hits = [[pg, r.x0, r.y0, r.x1, r.y1] for r in hs[:1]]
                        break
                if hits:
                    geo[u["id"]] = hits
                    break


def place(u, geo_en, last_page):
    """Fill page / bbox / lines from geo (the first page the unit appears on)."""
    g = geo_en or []
    u["geo"] = {"en": g, "ko": u.get("geo", {}).get("ko", [])}
    if g:
        pg = g[0][0]
        rs = [r[1:] for r in g if r[0] == pg]
        u["page"], u["bbox"], u["lines"] = pg, _union(rs), rs
    else:
        u["page"], u["bbox"], u["lines"] = last_page, [0, 0, 0, 0], []
    return u["page"]


# ================================================================================================ LaTeX
def tex_root(p):
    return p.f("src")


def tex_prepare(p, report):
    root = tex_root(p)
    main = texsrc.find_main(root)
    if not main:
        raise ValueError("압축 파일에서 \\documentclass 가 있는 주 .tex 파일을 찾지 못했습니다")
    text, rel = texsrc.flatten(root, main)
    with open(os.path.join(root, texsrc.EN + ".tex"), "w", encoding="utf-8") as f:
        f.write(text)
    report("원문 PDF를 만드는 중… (TeX 컴파일)")
    pdf, log = texsrc.compile_tex(root, texsrc.EN, report)
    if not pdf:
        errs = texsrc.errors(log)[:4]
        raise ValueError("TeX 컴파일에 실패했습니다. " + (" / ".join(e[6:].strip() for e in errs)[:400] or log[-400:]) +
                         " — 원문 PDF로 열면 PDF 방식으로 번역합니다.")
    shutil.copy(pdf, p.pdf)
    report("논문 구조를 읽는 중…")
    sp = texsrc.Splitter(text).run()
    lof = texsrc.line_of(text)
    aux = _aux(root, texsrc.EN)
    units, spans = [], {}
    for i, s in enumerate(sp.units):
        uid = f"u{i}"
        src = text[s["a"]:s["b"]]
        kind = TEX_KIND.get(s["kind"], "para")
        u = {"id": uid, "kind": kind, "a": s["a"], "b": s["b"], "src": src, "translate": kind != "equation",
             "text": L.to_plain(src, aux) if kind != "equation" else src, "html": L.to_html(src, aux) if kind != "equation" else ""}
        if s.get("level"):
            u["level"] = s["level"]
        if s.get("prev_i") is not None:
            prev = units[s["prev_i"]]
            prev["next"] = uid
            u["prev"] = prev["id"]
        units.append(u)
        # an argument ({caption}, {section title}) is typeset when its closing brace is read: include that line
        if kind in ("caption", "heading", "title"):
            close = text.find("}", s["b"])
            spans[uid] = (lof(s["a"]), lof(close if close >= 0 else s["b"]) + (1 if kind == "heading" else 0))
        else:
            spans[uid] = (lof(s["a"]), lof(max(s["a"], s["b"] - 1)))
    geo = texsrc.geometry(root, texsrc.EN, spans)
    clean_geo(units, geo)
    fill_by_search(p.pdf, units, geo, "en")
    last = 0
    for u in units:
        last = place(u, geo.get(u["id"]), last)
        u["size"] = 10
    byidx = {i: units[i]["id"] for i in range(len(units))}
    pages = _pages(p.pdf)
    figures, equations = [], []
    en_doc = pymupdf.open(p.pdf)
    for r in sp.regions:
        if r["kind"] == "equation":
            uid = byidx[r["unit"]]
            pg, rs = _first_page(geo.get(uid, []))
            if pg is not None:
                equations.append({"page": pg, "bbox": _union(rs), "units": [uid]})
            continue
        caps = [byidx[c] for c in r.get("caps", [])]
        capgeo = [x for c in caps for x in geo.get(c, [])]
        if not capgeo:
            continue
        pg = Counter(x[0] for x in capgeo).most_common(1)[0][0]
        cb = _union([x[1:] for x in capgeo if x[0] == pg])
        # where is the picture: SyncTeX boxes of the float (outside its caption lines) say above or below the caption
        caplines = set()
        for c in caps:
            ca, cbl = spans[c]
            caplines.update(range(ca, cbl + 1))
        l0, l1 = lof(r["a"]), lof(max(r["a"], r["b"] - 1))
        st = _sync(root, texsrc.EN)
        hint = []
        if st:
            tag = st.tag_for(texsrc.EN + ".tex")
            for ln in range(l0, l1 + 1):
                if ln in caplines:
                    continue
                hint += [x[1:] for x in st.lines.get((tag, ln), ()) if x[0] == pg]
        up = r["kind"] != "table"
        if hint:
            hb = _union(hint)
            up = (hb[1] + hb[3]) / 2 < (cb[1] + cb[3]) / 2
        others = [x[1:] for u in units if u["id"] not in caps for x in u["geo"]["en"] if x[0] == pg]
        bb = _float_box(en_doc[pg], cb, up, others)
        if bb:
            figures.append({"page": pg, "bbox": [round(v, 2) for v in bb], "caption": caps[0], "kind": r["kind"]})
    en_doc.close()
    preamble = text[:re.search(r"\\begin\s*\{document\}", text).start()]
    return {"pages": _pages(p.pdf), "units": units, "figures": figures, "tables": [], "equations": equations,
            "body_size": _body_size(p.pdf), "macros": L.macros(preamble), "source": "tex", "main": rel}


def _float_box(page, cb, up, others):
    """The picture of a float: from its caption up (or down) to the nearest body text in the caption's column,
    tightened to the drawings, images and text actually there."""
    W, H = page.rect.width, page.rect.height
    x0, x1 = cb[0] - 4, cb[2] + 4
    cw = cb[2] - cb[0]

    def overlaps(o):
        return min(o[2], x1) - max(o[0], x0) > 0.3 * min(cw, o[2] - o[0])

    if up:
        lim = max([o[3] for o in others if overlaps(o) and o[3] <= cb[1] + 1] + [H * 0.04])
        box = pymupdf.Rect(0, lim + 1, W, cb[1] - 1)
    else:
        lim = min([o[1] for o in others if overlaps(o) and o[1] >= cb[3] - 1] + [H * 0.96])
        box = pymupdf.Rect(0, cb[3] + 1, W, lim - 1)
    if box.height < 6:
        return None
    col = pymupdf.Rect(x0 - 40, box.y0, x1 + 40, box.y1)       # stay near the caption's column
    parts = []
    for dr in page.get_drawings():
        rr = dr["rect"]
        if rr.intersects(col) and rr.width < W * 0.98 and not (rr.height < 1.5 and rr.width > cw * 1.4):
            parts.append(rr & box)
    for im in page.get_image_info():
        rr = pymupdf.Rect(im["bbox"])
        if rr.intersects(col):
            parts.append(rr & box)
    for bl in page.get_text("blocks"):
        rr = pymupdf.Rect(bl[:4])
        if rr.intersects(col) and box.contains(rr):
            parts.append(rr)
    parts = [q for q in parts if not q.is_empty and q.width > 0.5 and q.height > 0.5]
    if not parts:
        return None
    u = pymupdf.Rect(parts[0])
    for q in parts[1:]:
        u |= q
    u &= box
    if u.height < 6 or u.width < 10:
        return None
    return [u.x0 - 1, u.y0 - 1, u.x1 + 1, u.y1 + 1]


def _inside(r, c):
    return r[0] >= c[0] - 1 and r[2] <= c[2] + 1 and r[1] >= c[1] - 1 and r[3] <= c[3] + 1


_sync_cache = {}


def _sync(root, name):
    import synctex
    pth = os.path.join(root, name + ".synctex.gz")
    if not os.path.exists(pth):
        return None
    key = (pth, os.path.getmtime(pth))
    if key not in _sync_cache:
        _sync_cache.clear()
        _sync_cache[key] = synctex.SyncTex(pth)
    return _sync_cache[key]


_aux_cache = {}


def _aux(root, name):
    pth = os.path.join(root, name + ".aux")
    if not os.path.exists(pth):
        return L.Aux()
    key = (pth, os.path.getmtime(pth))
    if key not in _aux_cache:
        _aux_cache[key] = L.Aux(open(pth, encoding="utf-8", errors="replace").read())
    return _aux_cache[key]


def tex_build(p, report):
    """Write and compile the Korean source. Units whose translation breaks the build go back to English."""
    root = tex_root(p)
    d = p.doc()
    text = open(os.path.join(root, texsrc.EN + ".tex"), encoding="utf-8").read()
    texsrc.copy_fonts(root)
    bad = set()
    base_errs = None
    for attempt in range(3):
        with p.lock:
            units = [dict(u) for u in d["units"]]
        ko_tex, spans = texsrc.build_ko(text, units, lambda u: u.get("ko") if u.get("translate") and u.get("ko") and u["id"] not in bad else None)
        with open(os.path.join(root, texsrc.KO + ".tex"), "w", encoding="utf-8") as f:
            f.write(ko_tex)
        pdf, log = texsrc.compile_tex(root, texsrc.KO, report)
        errs = texsrc.errors(log)
        if base_errs is None:
            base_errs = _en_errors(root)
        new = []
        for e in errs:
            m = re.match(r"error:\s*" + re.escape(texsrc.KO) + r"\.tex:(\d+):\s*(.*)", e)
            if m and m.group(2).strip() not in base_errs:
                new.append(int(m.group(1)))
        culprits = {uid for uid, (a, b) in spans.items() for ln in new if a <= ln <= b + 1}
        culprits -= bad
        if pdf and not culprits:
            break
        if not culprits:
            if pdf:
                break
            raise ValueError("한국어 PDF를 만들지 못했습니다: " + " / ".join(x[6:] for x in errs[:3])[:300])
        bad |= culprits
    with p.lock:
        for u in d["units"]:
            if u["id"] in bad:
                u["err"] = "이 번역이 TeX 조판 오류를 일으켜 원문으로 두었습니다. '다시 번역'이나 '직접 수정'으로 고쳐 주세요."
    tmp = p.ko_pdf + ".tmp"
    shutil.copy(pdf, tmp)
    os.replace(tmp, p.ko_pdf)
    geo = texsrc.geometry(root, texsrc.KO, spans)
    clean_geo(d["units"], geo)
    aux = _aux(root, texsrc.KO)
    with p.lock:
        look = [dict(u, _ko_plain=L.to_plain(u["ko"], aux) if u.get("ko") and u["id"] not in bad else u.get("text")) for u in d["units"]]
    fill_by_search(p.ko_pdf, look, geo, "ko")
    with p.lock:
        for u in d["units"]:
            u.setdefault("geo", {})["ko"] = geo.get(u["id"], [])
    return _pages(p.ko_pdf)


def _en_errors(root):
    pth = os.path.join(root, texsrc.EN + ".log")
    out = set()
    if os.path.exists(pth):
        for ln in open(pth, encoding="utf-8", errors="replace"):
            if ln.startswith("! "):
                out.add(ln[2:].strip())
    return out


def tex_html(p, u, side):
    """Reader HTML of a unit (side 'en' or 'ko')."""
    root = tex_root(p)
    if side == "en":
        return u.get("html") or L.to_html(u.get("src", ""), _aux(root, texsrc.EN))
    return L.to_html(u.get("ko") or "", _aux(root, texsrc.KO), "ko")


def tex_plain(p, u):
    return L.to_plain(u.get("ko") or "", _aux(tex_root(p), texsrc.KO))


def tex_export_source(p, out_path):
    """A zip of the Korean source (main file = hp_ko.tex, renamed after the original main)."""
    import zipfile
    root = tex_root(p)
    main = p.doc().get("main") or "main.tex"
    with zipfile.ZipFile(out_path, "w", zipfile.ZIP_DEFLATED) as z:
        for dp, _, fs in os.walk(root):
            for f in fs:
                full = os.path.join(dp, f)
                rel = os.path.relpath(full, root).replace("\\", "/")
                if f.startswith(texsrc.EN) or (f.startswith(texsrc.KO) and not f.endswith(".tex")):
                    continue
                if rel == main.replace("\\", "/"):
                    continue
                if f == texsrc.KO + ".tex":
                    z.write(full, os.path.splitext(main)[0].replace("\\", "/") + ".tex")
                    continue
                z.write(full, rel)
    return out_path


# ================================================================================================ masking for the translator
def masked(p, u):
    """(text the translator sees, {token: original}) for a unit."""
    if p.kind == "tex":
        src = re.sub(r"(?<!\\)%[ \t]*(\n|$)", r"\1", u["src"]).strip()
        return L.mask(src)
    import docxsrc
    return docxsrc.masked(u)


def accept(p, u, ko, msrc, keep):
    """Check a translation of a masked unit; returns (stored value or None, problem)."""
    if p.kind == "tex":
        prob = L.check(msrc, keep, ko)
        if prob:
            return None, prob
        return L.unmask(ko, keep, msrc), None
    import docxsrc
    return docxsrc.accept(u, ko, keep)


# ================================================================================================ dispatch
def prepare(p, report):
    if p.kind == "tex":
        return tex_prepare(p, report)
    import docxsrc
    return docxsrc.prepare(p, report)


def build(p, report):
    if p.kind == "tex":
        return tex_build(p, report)
    import docxsrc
    return docxsrc.build(p, report)


def html(p, u, side):
    if p.kind == "tex":
        return tex_html(p, u, side)
    import docxsrc
    return docxsrc.html_for(p, u, side)


def plain_ko(p, u):
    if p.kind == "tex":
        return tex_plain(p, u)
    import docxsrc
    return docxsrc.plain(u.get("ko") or "")


def export_source(p, out_path):
    if p.kind == "tex":
        return tex_export_source(p, out_path)
    import docxsrc
    return docxsrc.export_source(p, out_path)


def stamp():
    return time.time()
