"""PDF analysis and Korean re-typesetting.

analyze(pdf)  -> page sizes, translation units (paragraph-level, with inline <b>/<i>/<sub>/<sup>), figures, tables
render_page() -> one Korean page: the original page with only the translated text removed (images, vector art,
                 equations and untranslated text stay untouched) and the Korean text set into the same boxes at the
                 same font size, alignment, indent and colour (shrunk only as far as needed to fit).
"""
import html
import os
import re
import statistics
import unicodedata
from collections import Counter

import pymupdf

import paths

FONT_DIR = os.path.join(paths.STATIC, "fonts")
MATH_FONT = re.compile(r"CMMI|CMSY|CMEX|CMBSY|MSBM|MSAM|NewTXMI|NewTXBMI|txsys|txex|txsy|TXMI|Math|Symbol|STIX|rsfs|LMMath|"
                       r"Cambria-?Math|eufm|wasy|stmary|esint|MnSymbol|cmmib", re.I)
CAPTION = re.compile(r"^\s*(fig\.?|figure|table|tab\.|algorithm|alg\.|listing)\s*([0-9]+|[IVXL]+)(\s*[:.|—–\-]|\s*$)", re.I)
REF_HEAD = re.compile(r"^\s*([0-9IVX]+\.?\s*)?(references|bibliography|reference|참고\s*문헌)\s*$", re.I)
ACK_HEAD = re.compile(r"^\s*([0-9IVX]+\.?\s*)?(acknowledge?ments?)\s*$", re.I)
WORD = re.compile(r"[A-Za-z][A-Za-z'’\-]{2,}")
ALGO_CAP = re.compile(r"^\s*(algorithm|alg\.|procedure|pseudocode)\s*\d+(?!\d)", re.I)
FIG_CAP = re.compile(r"^\s*(fig\.?|figure)\s*\d+", re.I)
MONO_FONT = re.compile(r"Courier|Mono|CMTT|SFTT|Consol|Inconsolata|Menlo|Typewriter|txtt|LMMono|Source ?Code|Fira ?Code|DejaVuSansM", re.I)
LIST_MARK = re.compile(r"^\s*(\(?\d{1,2}[).]|\(?[a-z][).]|\(?[ivx]{1,4}[).]|[•●▪◦■□\-–—*])\s*$", re.I)
EQNO = re.compile(r"^\s*\(\s*\d{1,3}[a-z]?\s*\)\s*$")
URLISH = re.compile(r"^\s*(\S+@\S+|https?://\S+|www\.\S+|doi:\s*\S+|arxiv:\s*\S+)\s*$", re.I)


def _flags():
    f = pymupdf.TEXTFLAGS_DICT & ~pymupdf.TEXT_PRESERVE_LIGATURES
    return f | pymupdf.TEXT_PRESERVE_WHITESPACE


def _is_math_span(s):
    if MATH_FONT.search(s["font"]):
        return True
    t = s["text"]
    return any(0x1D400 <= ord(c) <= 0x1D7FF for c in t)


def _hex(c):
    return "#%06x" % (c or 0)


class Line:
    __slots__ = ("bbox", "spans", "size", "base")

    def __init__(self, ln):
        self.bbox = pymupdf.Rect(ln["bbox"])
        self.spans = [s for s in ln["spans"] if s["text"]]
        sizes = Counter()
        for s in self.spans:
            sizes[round(s["size"], 1)] += len(s["text"].strip()) or 0
        self.size = sizes.most_common(1)[0][0] if sizes and sizes.most_common(1)[0][1] else (self.spans[0]["size"] if self.spans else 0)
        main = [s for s in self.spans if abs(s["size"] - self.size) < 0.6]
        self.base = statistics.median([s["origin"][1] for s in main]) if main else self.bbox.y1

    @property
    def text(self):
        return "".join(s["text"] for s in self.spans)


class Unit:
    """One piece of text that is translated and re-set as a whole (a paragraph, a heading, a caption, a table cell)."""

    def __init__(self, page, lines):
        self.page, self.lines = page, lines
        self.kind = "para"
        self.translate = True
        self.figure = None

    @property
    def bbox(self):
        r = pymupdf.Rect(self.lines[0].bbox)
        for ln in self.lines[1:]:
            r |= ln.bbox
        return r

    def spans(self):
        return [s for ln in self.lines for s in ln.spans]

    def stats(self):
        sp = self.spans()
        chars = Counter()
        bold = ital = sans = 0
        colors = Counter()
        tot = 0
        for s in sp:
            n = len(s["text"].strip())
            if not n:
                continue
            tot += n
            chars[round(s["size"], 1)] += n
            if not _is_math_span(s):
                f = s["font"].lower()
                bold += n if (s["flags"] & 16 or "bold" in f or "medi" in f or "black" in f or "semibold" in f) else 0
                ital += n if (s["flags"] & 2 or "ital" in f or "obli" in f) else 0
                sans += n if ("sans" in f or "helvet" in f or "arial" in f or "sanl" in f or "gothic" in f or "calibri" in f) else 0
            colors[s["color"]] += n
        tot = tot or 1
        size = chars.most_common(1)[0][0] if chars else 10
        return {"size": size, "bold": bold / tot > 0.6, "italic": ital / tot > 0.6, "sans": sans / tot > 0.5,
                "color": _hex(colors.most_common(1)[0][0]) if colors else "#000000"}

    def to_html(self, st):
        """Inline markup kept through translation: <b>, <i>, <sub>, <sup> (only where they differ from the unit's style)."""
        out = []
        for i, ln in enumerate(self.lines):
            parts = []
            prev = None
            for s in ln.spans:
                t = s["text"]
                if prev is not None and t and not t[0].isspace() and not prev["text"][-1:].isspace() \
                        and s["bbox"][0] - prev["bbox"][2] > 0.18 * ln.size and s["size"] >= ln.size * 0.85:
                    parts.append(" ")                    # a gap drawn by position, not by a space character
                prev = s
                if any(0x1D400 <= ord(c) <= 0x1D7FF for c in t):
                    t = unicodedata.normalize("NFKC", t)
                t = html.escape(re.sub(r"\s+", " ", t), quote=False)
                if not t.strip():
                    parts.append(t)
                    continue
                f = s["font"].lower()
                math = _is_math_span(s)
                b = (s["flags"] & 16 or "bold" in f or "medi" in f) and not st["bold"] and not math
                it = (math and (s["flags"] & 2 or "mi" in f or "ital" in f)) or ((s["flags"] & 2 or "ital" in f) and not st["italic"] and not math)
                small = s["size"] < ln.size * 0.85
                dy = s["origin"][1] - ln.base
                if small and dy > ln.size * 0.12:
                    t = f"<sub>{t.strip()}</sub>"
                elif small and dy < -ln.size * 0.12:
                    t = f"<sup>{t.strip()}</sup>"
                if it:
                    t = f"<i>{t}</i>"
                if b:
                    t = f"<b>{t}</b>"
                parts.append(t)
            line = "".join(parts).strip()
            if not out:
                out.append(line)
            elif re.search(r"[A-Za-z]-$", out[-1]) and re.match(r"[a-z]", line):
                out[-1] = out[-1][:-1] + line
            else:
                out.append(" " + line)
        h = "".join(out)
        h = re.sub(r"</(b|i|sub|sup)>(\s*)<\1>", r"\2", h)
        return re.sub(r"\s{2,}", " ", h).strip()


def plain(h):
    return html.unescape(re.sub(r"<[^>]+>", "", h or ""))


def _yoverlap(a, b):
    return max(0.0, min(a.y1, b.y1) - max(a.y0, b.y0))


def _contains(outer, inner, pad=2):
    o = pymupdf.Rect(outer.x0 - pad, outer.y0 - pad, outer.x1 + pad, outer.y1 + pad)
    i = inner & o
    return not i.is_empty and i.get_area() >= 0.8 * max(inner.get_area(), 1e-6)


def _merge_rects(rects, pad=4):
    rects = [pymupdf.Rect(r) for r in rects]
    changed = True
    while changed:
        changed = False
        out = []
        while rects:
            r = rects.pop()
            for j, q in enumerate(out):
                if pymupdf.Rect(q.x0 - pad, q.y0 - pad, q.x1 + pad, q.y1 + pad).intersects(r):
                    out[j] = q | r
                    changed = True
                    break
            else:
                out.append(r)
        rects = out
    return rects


def _figures(page, W, H):
    """Picture regions: raster images plus clusters of vector drawings (not table rules, not page frames)."""
    rects = []
    for im in page.get_image_info():
        r = pymupdf.Rect(im["bbox"]) & page.rect
        if r.width > 30 and r.height > 30:
            rects.append(r)
    try:
        for r in page.cluster_drawings(x_tolerance=6, y_tolerance=6):
            if r.width > 40 and r.height > 30 and r.width < W * 0.98 and r.get_area() < W * H * 0.85:
                rects.append(pymupdf.Rect(r))
    except Exception:  # noqa: BLE001  older PyMuPDF
        pass
    return _merge_rects(rects, pad=3)


def _tables(page):
    """Ruled tables (full grid). Tables with only horizontal rules are found per text block by _tabular()."""
    out = []
    for kw in ({"strategy": "lines"},):
        try:
            for t in page.find_tables(**kw).tables:
                if t.row_count >= 2 and t.col_count >= 2:
                    r = pymupdf.Rect(t.bbox)
                    if not any((r & o).get_area() > 0.5 * min(r.get_area(), o.get_area()) for o in out):
                        out.append(r)
        except Exception:  # noqa: BLE001
            pass
    return out


def _tabular(lines):
    """A text block laid out as a grid: several visual rows hold more than one line side by side."""
    rows = {}
    for ln in lines:
        rows.setdefault(round(ln.base), []).append(ln)
    # a list item ("1)" + text, "•" + text) is not a table row
    rows = {k: [ln for ln in v if not LIST_MARK.match(ln.text)] for k, v in rows.items()}
    rows = {k: len(v) for k, v in rows.items() if v}
    if not rows:
        return False
    multi = sum(1 for v in rows.values() if v >= 2)
    # a justified paragraph can split one row into pieces now and then; a table does it on most rows
    return (multi >= 2 and multi / len(rows) >= 0.5) or (len(rows) <= 2 and max(rows.values(), default=0) >= 3)


def analyze(pdf_path):
    doc = pymupdf.open(pdf_path)
    pages, units = [], []
    rawfigs, rules = {}, {}
    dicts = [pg.get_text("dict", flags=_flags()) for pg in doc]
    sizes = Counter()
    for d in dicts:
        for b in d["blocks"]:
            for ln in b.get("lines", []):
                for s in ln["spans"]:
                    sizes[round(s["size"])] += len(s["text"].strip())
    body0 = sizes.most_common(1)[0][0] if sizes else 10
    for pno, page in enumerate(doc):
        W, H = page.rect.width, page.rect.height
        pages.append({"w": W, "h": H})
        d = dicts[pno]
        blocks, seen = [], set()
        for b in d["blocks"]:
            if b["type"] != 0:
                continue
            lines = []
            for ln in b["lines"]:
                if abs(ln["dir"][0] - 1) > 0.02 or not any(s["text"].strip() for s in ln["spans"]):
                    continue
                key = ("".join(s["text"] for s in ln["spans"]).strip(), tuple(round(x) for x in ln["bbox"]))
                if key in seen:                  # text drawn twice (fake bold, shadows)
                    continue
                seen.add(key)
                lines.append(Line(ln))
            lines = [ln for ln in lines if ln.spans]
            for grp in _split_heads(lines):
                blocks.append(Unit(pno, grp))
        tabs = _tables(page)
        figs = [f for f in _figures(page, W, H) if not any(_contains(t, f, 6) or (f & t).get_area() > 0.5 * f.get_area() for t in tabs)]

        # 1) table text -> one unit per line (a cell); figure text -> kept, never translated
        rest = []
        for u in blocks:
            r = u.bbox
            st = u.stats()
            if not CAPTION.match(plain(u.to_html(st))):
                near = next((f for f in figs if _contains(f, r, 3) or (st["size"] < body0 * 0.95 and _contains(f, r, 14))), None)
                if near is not None:
                    u.kind, u.translate = "figtext", False
                    rest.append(u)
                    continue
            if any(_contains(t, r) for t in tabs) or _tabular(u.lines):
                for ln in u.lines:
                    v = Unit(pno, [ln])
                    v.kind = "table"
                    rest.append(v)
                continue
            if len(u.lines) > 1:
                u.lines = _join_same_row(u.lines)      # pieces of one justified row -> one line
            rest.append(u)

        # 2) glue fragments that overlap vertically (sub/superscripts split a paragraph into pieces)
        merged = []
        for u in sorted(rest, key=lambda x: (x.bbox.y0, x.bbox.x0)):
            if u.kind in ("table", "figtext") or EQNO.match(u.lines[0].text if len(u.lines) == 1 else "x") \
                    or CAPTION.match(u.lines[0].text) or ALGO_CAP.match(u.lines[0].text):
                merged.append(u)
                continue
            st = u.stats()
            host = None
            for m in merged:
                if m.kind != "para":
                    continue
                a, b = m.bbox, u.bbox
                ov = _yoverlap(a, b)
                xin = max(0.0, min(a.x1, b.x1) - max(a.x0, b.x0))
                xgap = max(a.x0 - b.x1, b.x0 - a.x1, 0)
                narrow = min(a.width, b.width)
                inside = xin >= 0.7 * narrow                      # one lies within the other's columns
                piece = narrow < 0.3 * max(a.width, b.width) and xgap < 0.6 * st["size"] and len(u.lines) <= 2   # a small fragment right next to it
                hs = m.stats()["size"]
                if ov > 0.3 * min(a.height, b.height) and (inside or piece) and (abs(hs - st["size"]) < 1.2 or (st["size"] < hs and inside and b.width < 0.5 * a.width)):
                    host = m
                    break
            if host is not None:
                host.lines = sorted(host.lines + u.lines, key=lambda ln: (round(ln.base / max(ln.size, 1) * 1.5), ln.bbox.x0))
                host.lines = _join_same_row(host.lines)
            else:
                merged.append(u)
        # 3a) a paragraph the PDF stored as two blocks (e.g. its last line apart): join when the lower block
        #     continues without an indent and the upper one has not finished its sentence
        merged.sort(key=lambda x: (x.bbox.y0, x.bbox.x0))
        k = 0
        while k < len(merged):
            a = merged[k]
            if a.kind == "para":
                sa = a.stats()
                for b in merged[k + 1:]:
                    if b.kind != "para" or b is a:
                        continue
                    sb = b.stats()
                    gap = b.bbox.y0 - a.bbox.y1
                    if gap > sa["size"] * 0.9 or gap < -1:
                        continue
                    if abs(b.bbox.x0 - a.bbox.x0) > 2.5 or abs(sa["size"] - sb["size"]) > 0.6 or sa["bold"] != sb["bold"]:
                        continue
                    last = a.lines[-1].text.rstrip()
                    first = b.lines[0].text.lstrip()
                    if (len(a.lines) == 1 and HEADNUM.match(a.lines[0].text)) or sa["italic"] != sb["italic"] \
                            or CAPTION.match(a.lines[0].text) or ALGO_CAP.match(a.lines[0].text) or CAPTION.match(first) \
                            or ALGO_CAP.match(first) or re.match(r"^\d{1,3}[:.]?\s", first) or LIST_MARK.match(first.split(" ")[0] if first else ""):
                        break
                    indented = b.lines[0].bbox.x0 - b.bbox.x0 > sb["size"] * 0.6 if len(b.lines) > 1 else False
                    if indented or HEADNUM.match(first) and _line_style(b.lines[0])[1]:
                        continue
                    if not re.search(r"[.!?:;]\s*$", last) or (first[:1].islower()):
                        a.lines = a.lines + b.lines
                        merged.remove(b)
                        sa = a.stats()
                        continue
                    break
            k += 1
        # 3) a large title set on several lines/blocks is one sentence: translate it as one unit
        big = sorted([u for u in merged if u.kind == "para" and u.stats()["size"] >= body0 * 1.3], key=lambda x: x.bbox.y0)
        for a, b in zip(big, big[1:]):
            if a not in merged or b not in merged:
                continue
            sa, sb = a.stats()["size"], b.stats()["size"]
            gap = b.bbox.y0 - a.bbox.y1
            xin = min(a.bbox.x1, b.bbox.x1) - max(a.bbox.x0, b.bbox.x0)
            if abs(sa - sb) < 0.6 and -2 < gap < sa * 0.9 and xin > 0:
                b.lines = a.lines + b.lines
                merged.remove(a)
        units.extend(merged)
        rawfigs[pno] = figs
        rules[pno] = _hrules(page)
    body = _body_size(units)
    _classify(units, pages, body)
    out_units = []
    for i, u in enumerate(_reading_order(units, pages)):
        st = u.stats()
        r = u.bbox
        h = u.to_html(st)
        n = len(u.lines)
        lh = 1.2
        if n >= 2:
            gaps = [u.lines[k + 1].base - u.lines[k].base for k in range(n - 1) if u.lines[k + 1].base - u.lines[k].base > st["size"] * 0.6]
            if gaps:
                lh = max(1.0, min(2.0, statistics.median(gaps) / st["size"]))
        out_units.append({
            "id": f"u{i}", "page": u.page, "kind": u.kind, "translate": u.translate, "bbox": [round(x, 2) for x in r],
            "lines": [[round(x, 2) for x in ln.bbox] for ln in u.lines], "size": st["size"], "bold": st["bold"],
            "italic": st["italic"], "sans": st["sans"], "color": st["color"], "lh": round(lh, 3),
            "align": _align(u, st), "indent": _indent(u, st), "src": h, "text": plain(h), "ko": None,
            "nlines": n,
        })
    figures = _figure_regions(out_units, rawfigs, pages, body)
    figures += _algorithm_regions(out_units, rules, pages, body)
    figures += _code_regions(out_units, pages, body, figures)
    figures.sort(key=lambda f: (f["page"], f["bbox"][1], f["bbox"][0]))
    equations = _eq_regions(out_units, pages, body)
    _attach_captions(out_units, figures, pages)
    tables = []
    for pno in range(len(pages)):
        cells = [u for u in out_units if u["page"] == pno and u["kind"] == "table"]
        for r in _merge_rects([pymupdf.Rect(u["bbox"]) for u in cells], pad=14):
            ids = [u["id"] for u in cells if _contains(r, pymupdf.Rect(u["bbox"]), 1)]
            if len(ids) >= 4:
                tables.append({"page": pno, "bbox": [round(x, 2) for x in r], "units": ids})
            else:                                       # a lone "table" line is just text
                for u in cells:
                    if u["id"] in ids and u["translate"]:
                        u["kind"] = "para" if u["size"] >= body * 0.9 else "note"
    for t in tables:                                   # caption of a table: the caption unit right above or below it
        r = pymupdf.Rect(t["bbox"])
        caps = [u for u in out_units if u["page"] == t["page"] and u["kind"] == "caption" and u.get("figure") is None
                and not ALGO_CAP.match(u["text"]) and not FIG_CAP.match(u["text"])]
        caps.sort(key=lambda u: min(abs(u["bbox"][3] - r.y0), abs(r.y1 - u["bbox"][1])))
        if caps and min(abs(caps[0]["bbox"][3] - r.y0), abs(r.y1 - caps[0]["bbox"][1])) < 60:
            t["caption"] = caps[0]["id"]
            caps[0]["table"] = tables.index(t)
    _link_continuations(out_units, pages)
    for u in out_units:
        u.pop("nlines", None)
    doc.close()
    return {"pages": pages, "units": out_units, "figures": figures, "tables": tables, "equations": equations, "body_size": body}


# ---------------------------------------------------------------------------------------------------- regions
def _hrules(page):
    """Horizontal rules (thin lines / thin filled rects) on the page: algorithm boxes, booktabs tables."""
    out = []
    try:
        for d in page.get_drawings():
            for it in d.get("items", []):
                if it[0] == "l":
                    a, b = it[1], it[2]
                    if abs(a.y - b.y) < 1.2 and abs(a.x - b.x) > 30:
                        out.append(pymupdf.Rect(min(a.x, b.x), a.y - 0.3, max(a.x, b.x), a.y + 0.3))
                elif it[0] == "re":
                    r = pymupdf.Rect(it[1])
                    if r.height < 2.5 and r.width > 30:
                        out.append(r)
    except Exception:  # noqa: BLE001
        pass
    return out


def _span_of(bbox, W, wide=0.55):
    x0, y0, x1, y1 = bbox
    if x1 - x0 > W * wide:
        return 0.0, W
    return (0.0, W / 2 + 4) if (x0 + x1) / 2 < W / 2 else (W / 2 - 4, W)


def _paraish(u, body):
    """Running body text: a boundary that a figure/algorithm region never crosses."""
    return u["kind"] in ("para", "heading", "title", "note", "ref", "caption") and u["translate"] and \
        (u["nlines"] >= 2 or len(u["text"]) > 60) and u["size"] >= body * 0.85


def _inside(r, u, pad=3, frac=0.75):
    b = pymupdf.Rect(u["bbox"])
    i = b & pymupdf.Rect(r.x0 - pad, r.y0 - pad, r.x1 + pad, r.y1 + pad)
    return not i.is_empty and i.get_area() >= frac * max(b.get_area(), 1e-6)


def _figure_regions(units, rawfigs, pages, body):
    """Pictures: drawing/image clusters, grown to everything between a figure caption and the body text above it.
    All text inside (axis labels, boxes, legends) belongs to the picture: never translated, never read as body text."""
    out = []
    for pno, pg in enumerate(pages):
        W, H = pg["w"], pg["h"]
        us = [u for u in units if u["page"] == pno]
        figs = [pymupdf.Rect(f) for f in rawfigs.get(pno, [])]
        for c in us:
            if not (c["kind"] == "caption" and FIG_CAP.match(c["text"])):
                continue
            cy0 = c["bbox"][1]
            wide = any(f.width > W * 0.55 and cy0 - 80 < f.y1 <= cy0 + 4 for f in figs)
            sx0, sx1 = (0.0, W) if wide else _span_of(c["bbox"], W)
            above = [u["bbox"][3] for u in us if u is not c and _paraish(u, body) and u["bbox"][3] <= cy0 + 1
                     and u["bbox"][0] < sx1 and u["bbox"][2] > sx0 and not any(_inside(f, u, 2) for f in figs)]
            top = max(above, default=H * 0.06)
            zone = pymupdf.Rect(sx0, top, sx1, cy0)
            if zone.height < 12:
                continue
            fm = [f for f in figs if (f & zone).get_area() > 0.3 * f.get_area()]
            um = [pymupdf.Rect(u["bbox"]) for u in us if u is not c and u["kind"] != "running" and _inside(zone, u, 1, 0.9)]
            if fm or len(um) >= 3:
                r = (fm + um)[0]
                for m in (fm + um)[1:]:
                    r = r | m
                figs.append(r)
        figs = _merge_rects(figs, pad=4)
        for f in figs:
            for u in us:
                if u["kind"] in ("caption", "running", "ref"):
                    continue
                small = u["size"] < body * 0.95 and not _paraish(u, body)
                if _inside(f, u, 3) or (small and _inside(f, u, 14)):
                    u["kind"], u["translate"] = "figtext", False
        for f in sorted(figs, key=lambda r: (r.y0, r.x0)):
            out.append({"page": pno, "bbox": [round(x, 2) for x in f], "kind": "figure"})
    return out


ALGO_LINE = re.compile(r"^\s*(\d{1,3}[:.]?\s|input|output|require|ensure|for\b|while\b|if\b|else|end\b|return\b|repeat|until|procedure|function|initiali[sz]e)", re.I)


def _algorithm_regions(units, rules, pages, body):
    """Pseudocode: the box under an 'Algorithm N' caption, bounded by its rules; kept in English exactly as printed."""
    out = []
    for c in units:
        if not ALGO_CAP.match(c["text"]) or c["kind"] not in ("caption", "para", "heading", "note"):
            continue
        c["kind"] = "caption"
        pno = c["page"]
        W = pages[pno]["w"]
        sx0, sx1 = _span_of(c["bbox"], W)
        cx0, cy0, cx1, cy1 = c["bbox"]
        rs = sorted([r for r in rules.get(pno, []) if r.x0 < sx1 and r.x1 > sx0 and r.width > 0.4 * (sx1 - sx0)
                     and r.y0 >= cy1 - 4], key=lambda r: r.y0)
        if rs and rs[0].y0 - cy1 < 8:                  # the rule right under the caption
            start, rs = rs[0].y1, rs[1:]
        else:
            start = cy1
        rs = [r for r in rs if r.y0 > start + 12]
        bottom = rs[0].y0 if rs else None
        if bottom is None:                             # no rules: numbered / keyword lines below the caption
            bottom = start
            below = sorted([u for u in units if u["page"] == pno and u is not c and u["bbox"][1] >= start - 2
                            and u["bbox"][0] < sx1 and u["bbox"][2] > sx0], key=lambda u: u["bbox"][1])
            for u in below:
                if u["kind"] in ("heading", "title") or (u["kind"] == "para" and u["nlines"] >= 3 and not ALGO_LINE.match(u["text"])):
                    break
                if bottom > start and u["bbox"][1] - bottom > body * 2.5:
                    break
                bottom = max(bottom, u["bbox"][3])
        if bottom - start < 10:
            continue
        r = pymupdf.Rect(sx0 + 1, start, sx1 - 1, bottom)
        xs = [u for u in units if u["page"] == pno and u is not c and _inside(r, u, 2, 0.6)]
        if xs:
            r = pymupdf.Rect(min(min(u["bbox"][0] for u in xs) - 3, cx0 - 2), start + 0.5,
                             max(max(u["bbox"][2] for u in xs) + 3, cx1), bottom + 1)
        for u in xs:
            u["kind"], u["translate"], u["in_algo"] = "code", False, True
        out.append({"page": pno, "bbox": [round(x, 2) for x in r], "kind": "algorithm", "caption": c["id"]})
    return out


def _code_regions(units, pages, body, taken):
    """Listings printed in a monospace font outside an algorithm box: one picture per block."""
    out = []
    for pno in range(len(pages)):
        cs = [u for u in units if u["page"] == pno and u["kind"] == "code" and not u.get("in_algo")]
        for r in _merge_rects([pymupdf.Rect(u["bbox"]) for u in cs], pad=body * 0.9):
            if any(f["page"] == pno and r.intersects(pymupdf.Rect(f["bbox"])) for f in taken):
                continue
            out.append({"page": pno, "bbox": [round(x, 2) for x in r], "kind": "code"})
    return out


MATHY = re.compile(r"[=∑∫≤≥∈±×÷√∞∂∇∀∃⊂⊆∪∩→←]|\(\d+\)")


def _eq_regions(units, pages, body):
    """Display equations: equation pieces grouped per block, plus stray pieces on the same rows ('min', 'where', '(10)')."""
    out = []
    for pno, pg in enumerate(pages):
        W = pg["w"]
        us = [u for u in units if u["page"] == pno]
        cand = [u for u in us if u["kind"] == "equation" or (u["kind"] == "other" and (EQNO.match(u["text"]) or MATHY.search(u["text"])))]
        regs = []                                      # [rect, [units]]
        for u in sorted(cand, key=lambda u: u["bbox"][1]):
            b = pymupdf.Rect(u["bbox"])
            for g in regs:
                r = g[0]
                xov = min(r.x1, b.x1) - max(r.x0, b.x0)
                vgap = max(b.y0 - r.y1, r.y0 - b.y1, 0)
                if vgap <= body * 1.6 and xov > -70 and _span_of(list(r), W, 0.6) == _span_of(list(b), W, 0.6):
                    g[0] = r | b
                    g[1].append(u)
                    break
            else:
                regs.append([b, [u]])
        merged_any = True                              # pieces of one equation can form separate groups first
        while merged_any:
            merged_any = False
            for i in range(len(regs)):
                for j in range(i + 1, len(regs)):
                    a, b = regs[i][0], regs[j][0]
                    if pymupdf.Rect(a.x0 - 6, a.y0 - body * 0.6, a.x1 + 6, a.y1 + body * 0.6).intersects(b) and \
                            _span_of(list(a), W, 0.6) == _span_of(list(b), W, 0.6):
                        regs[i] = [a | b, regs[i][1] + regs[j][1]]
                        del regs[j]
                        merged_any = True
                        break
                if merged_any:
                    break
        for g in regs:
            for _ in range(2):                         # absorb short pieces on the same rows
                for u in us:
                    if u in g[1] or u["kind"] in ("figtext", "code", "table", "running", "caption", "heading", "title"):
                        continue
                    r = g[0]
                    b = pymupdf.Rect(u["bbox"])
                    yov = min(r.y1, b.y1) - max(r.y0, b.y0)
                    short = (u["nlines"] == 1 and len(u["text"]) <= 30) or \
                            (u["nlines"] <= 4 and len(u["text"]) <= 60 and len(WORD.findall(u["text"])) <= 3)   # stacked pieces: log, 1/(1+exp ...)
                    inside_rows = b.y0 >= r.y0 - 3 and b.y1 <= r.y1 + 3
                    if short and (yov > 0.5 * b.height or inside_rows) and b.x0 > r.x0 - 120 and b.x1 < r.x1 + 120 \
                            and _span_of(list(r), W, 0.6) == _span_of(list(b), W, 0.6):
                        u["kind"], u["translate"] = "equation", False
                        g[1].append(u)
                        g[0] = r | b
        # groups that now share rows or units are one equation (e.g. the formula and its number "(10)")
        changed = True
        while changed:
            changed = False
            for i in range(len(regs)):
                for j in range(i + 1, len(regs)):
                    a, b = regs[i][0], regs[j][0]
                    yov = min(a.y1, b.y1) - max(a.y0, b.y0)
                    shared = any(u in regs[j][1] for u in regs[i][1])
                    if (shared or a.intersects(b) or yov > 0.3 * min(a.height, b.height)) and \
                            _span_of(list(a), W, 0.6) == _span_of(list(b), W, 0.6):
                        regs[i] = [a | b, regs[i][1] + [u for u in regs[j][1] if u not in regs[i][1]]]
                        del regs[j]
                        changed = True
                        break
                if changed:
                    break
        for g in regs:
            if not any(u["kind"] == "equation" for u in g[1]) and not any(MATHY.search(u["text"]) for u in g[1]):
                continue
            for u in g[1]:
                u["kind"], u["translate"] = "equation", False
            out.append({"page": pno, "bbox": [round(x, 2) for x in g[0]], "units": [u["id"] for u in g[1]]})
    return out


SENT_END = re.compile(r"[.!?:;”\"')\]]\s*$")


def _link_continuations(units, pages):
    """A paragraph cut by a column or page break: link the two pieces (translated together, joined when reading)."""
    flow = [u for u in units if u["kind"] in ("para", "note") and u["translate"]]
    for a, b in zip(flow, flow[1:]):
        if a["kind"] != b["kind"] or abs(a["size"] - b["size"]) > 0.8:
            continue
        brk = b["page"] != a["page"] or b["bbox"][1] < a["bbox"][1] - 20       # next page, or back up into the next column
        if not brk or SENT_END.search(a["text"]):
            continue
        first = b["text"].lstrip()[:1]
        if first and (first.islower() or first in ",;)]–-" or a["text"].rstrip().endswith("-")):
            a["next"], b["prev"] = b["id"], a["id"]


def _line_style(ln):
    n = sum(len(s["text"].strip()) for s in ln.spans) or 1
    b = sum(len(s["text"].strip()) for s in ln.spans if s["flags"] & 16 or "bold" in s["font"].lower()) / n
    return ln.size, b > 0.6


HEADNUM = re.compile(r"^\s*((?:[IVX]{1,5}|\d{1,2}(?:\.\d{1,2}){0,3}|[A-H])\.?)\s+\S")


def _split_heads(lines):
    """A heading printed in the same text block as the paragraph after it becomes its own group."""
    if len(lines) < 2:
        return [lines] if lines else []
    # judge by visual rows: a row may be stored as several pieces ("4.2.4" + "DRL Training")
    rows = []
    for ln in lines:
        if rows and abs(rows[-1][0].base - ln.base) < ln.size * 0.45:
            rows[-1].append(ln)
        else:
            rows.append([ln])
    if len(rows) < 2:
        return [lines]
    rtext = lambda r: " ".join(x.text.strip() for x in sorted(r, key=lambda x: x.bbox.x0))
    rwidth = lambda r: max(x.bbox.x1 for x in r) - min(x.bbox.x0 for x in r)
    rstyle = lambda r: _line_style(max(r, key=lambda x: len(x.text)))
    width = max(ln.bbox.x1 for ln in lines) - min(ln.bbox.x0 for ln in lines)
    groups, cur = [], [rows[0]]
    for prev, row in zip(rows, rows[1:]):
        if len(cur) == 1 and EQNO.match(rtext(cur[0])):                    # an equation number stored above "where ..."
            groups.append(cur)
            cur = [row]
            continue
        if ALGO_CAP.match(rtext(cur[0])) and ALGO_LINE.match(rtext(row)):      # "Algorithm 1 ..." then "Require: ..."
            groups.append(cur)
            cur = [row]
            continue
        (s0, b0), (s1, b1) = rstyle(prev), rstyle(row)
        short = rwidth(prev) < 0.8 * width
        if len(cur) <= 2 and short and (abs(s0 - s1) >= 0.9 or b0 != b1 or HEADNUM.match(rtext(prev))):
            if HEADNUM.match(rtext(cur[0])) or abs(s0 - s1) >= 0.9 or b0 != b1:
                groups.append(cur)
                cur = [row]
                continue
        cur.append(row)
    groups.append(cur)
    return [[ln for r in g for ln in r] for g in groups]


def _join_same_row(lines):
    """Lines on the same text row (fragments) become one Line-like row, ordered left to right."""
    rows = []
    for ln in sorted(lines, key=lambda x: x.base):
        if rows and abs(rows[-1][-1].base - ln.base) < ln.size * 0.45:
            rows[-1].append(ln)
        else:
            rows.append([ln])
    out = []
    for row in rows:
        row.sort(key=lambda x: x.bbox.x0)
        first = row[0]
        for other in row[1:]:
            first.spans = first.spans + [{**s, "text": (" " + s["text"]) if not s["text"].startswith(" ") and first.spans and not first.spans[-1]["text"].endswith(" ") and s is other.spans[0] else s["text"]} for s in other.spans]
            first.bbox = first.bbox | other.bbox
        out.append(first)
    return out


def _body_size(units):
    c = Counter()
    for u in units:
        for s in u.spans():
            c[round(s["size"])] += len(s["text"])
    return c.most_common(1)[0][0] if c else 10


def _band_key(txt):
    return re.sub(r"\d+", "#", txt.lower()).strip()[:60]


def _running_keys(units, pages):
    """Header/footer lines that repeat on several pages (journal name, running title, page numbers)."""
    seen = {}
    for u in units:
        H = pages[u.page]["h"]
        r = u.bbox
        if r.y1 < H * 0.085 or r.y0 > H * 0.92:
            seen.setdefault(_band_key(u.lines[0].text), set()).add(u.page)
    need = 2 if len(pages) >= 3 else 99
    return {k for k, v in seen.items() if len(v) >= need}


PAGENO = re.compile(r"^\s*(page\s*)?(\d{1,4}|[ivxlc]{1,6})(\s*(of|/)\s*\d{1,4})?\s*$", re.I)


def _classify(units, pages, body):
    in_refs = False
    rkeys = _running_keys(units, pages)
    for u in _reading_order(units, pages):
        st = u.stats()
        txt = plain(u.to_html(st)).strip()
        if u.kind == "figtext":
            continue
        W, H = pages[u.page]["w"], pages[u.page]["h"]
        r = u.bbox
        spans = u.spans()
        math_n = sum(len(s["text"].strip()) for s in spans if _is_math_span(s))
        tot = sum(len(s["text"].strip()) for s in spans) or 1
        words = WORD.findall("".join(s["text"] for s in spans if not _is_math_span(s)))
        letters = sum(len(w) for w in words)
        head = ((st["bold"] or st["size"] > body * 1.12) and len(txt) < 120 and len(u.lines) <= 2) or \
               (len(u.lines) == 1 and len(txt) < 80 and bool(HEADNUM.match(txt)) and not txt.rstrip().endswith((",", ";")) and
                (st["italic"] or st["bold"] or txt.upper() == txt or len(txt.split()) <= 8))
        if head and REF_HEAD.match(txt):
            in_refs = True
            u.kind = "heading"
            continue
        if head and in_refs and not REF_HEAD.match(txt):
            in_refs = bool(re.match(r"^\s*(appendix|[A-Z]\.)", txt, re.I)) is False and in_refs
            if re.match(r"^\s*(appendix|supplement)", txt, re.I):
                in_refs = False
        if u.kind == "table":
            u.translate = len(words) >= 1 and letters / tot > 0.45
            continue
        if in_refs:
            u.kind, u.translate = "ref", False
            continue
        band = r.y1 < H * 0.085 or r.y0 > H * 0.92
        if band and len(u.lines) <= 2 and (_band_key(u.lines[0].text) in rkeys or PAGENO.match(txt)):
            u.kind, u.translate = "running", False       # page number / running head / footer line
            continue
        mono = sum(len(s["text"].strip()) for s in spans if MONO_FONT.search(s["font"]))
        if mono / tot > 0.6 and u.kind != "table":
            u.kind, u.translate = "code", False          # source code / listings stay as printed
            continue
        if not words or URLISH.match(txt) or re.fullmatch(r"[\d\s.,:;()\[\]\-–—/%]+", txt):
            u.kind, u.translate = "other", False
            continue
        eqno = bool(re.search(r"\(\s*\d{1,3}[a-z]?\s*\)\s*$", txt)) and (math_n > 0 or "=" in txt) and len(u.lines) <= 4
        brace = (txt[:1] in "{[" and math_n > 0) or any(0xFE00 <= ord(c) <= 0xFE0F for c in txt)   # cases / big delimiters
        if ALGO_CAP.match(txt) and len(u.lines) <= 3:
            u.kind = "caption"
            continue
        if eqno or brace or math_n / tot > 0.35 or (len(words) < 3 and math_n > 0) or letters / tot < 0.3:
            u.kind, u.translate = "equation", False
            continue
        if CAPTION.match(txt):
            u.kind = "caption"
        elif head:
            u.kind = "title" if st["size"] > body * 1.6 else "heading"
        elif st["size"] < body * 0.9:
            u.kind = "note"
        else:
            u.kind = "para"


def _columns(units, W):
    return [0 if (u.bbox.width < W * 0.6 and (u.bbox.x0 + u.bbox.x1) / 2 < W / 2) else (1 if u.bbox.width < W * 0.6 else -1) for u in units]


def _reading_order(units, pages):
    out = []
    for pno in sorted({u.page for u in units}):
        us = [u for u in units if u.page == pno]
        W = pages[pno]["w"]
        cols = _columns(us, W)
        fulls = sorted([u for u, c in zip(us, cols) if c == -1], key=lambda u: u.bbox.y0)
        bands, last = [], -1e9
        cuts = [u.bbox.y0 for u in fulls] + [1e9]
        prev = -1e9
        for cut in cuts:
            band = [(u, c) for u, c in zip(us, cols) if c != -1 and prev <= (u.bbox.y0 + u.bbox.y1) / 2 < cut]
            band.sort(key=lambda t: (t[1], t[0].bbox.y0, t[0].bbox.x0))
            out.extend(u for u, _ in band)
            full = next((f for f in fulls if f.bbox.y0 == cut), None)
            if full is not None:
                out.append(full)
            prev = cut
        seen = set(map(id, out))
        out.extend(u for u in us if id(u) not in seen)
    return out


def _align(u, st):
    if len(u.lines) == 1:
        r = u.bbox
        return "left"
    rights = [ln.bbox.x1 for ln in u.lines[:-1]]
    lefts = [ln.bbox.x0 for ln in u.lines]
    if max(rights) - min(rights) < st["size"] * 0.6:
        return "justify"
    cent = [(ln.bbox.x0 + ln.bbox.x1) / 2 for ln in u.lines]
    if max(cent) - min(cent) < st["size"] * 0.6 and max(lefts) - min(lefts) > st["size"]:
        return "center"
    return "left"


def _indent(u, st):
    if len(u.lines) < 2:
        return 0
    d = u.lines[0].bbox.x0 - min(ln.bbox.x0 for ln in u.lines[1:])
    return round(d, 1) if st["size"] * 0.5 < d < st["size"] * 4 else 0


def _attach_captions(units, figures, pages):
    ids = {u["id"]: u for u in units}
    for i, f in enumerate(figures):                    # algorithm boxes already know their caption
        if f.get("caption") in ids:
            ids[f["caption"]]["figure"] = i
    for u in units:
        if u["kind"] != "caption" or "figure" in u or not FIG_CAP.match(u["text"]):
            continue
        r = pymupdf.Rect(u["bbox"])
        best, bd = None, 1e9
        for i, f in enumerate(figures):
            if f["page"] != u["page"] or f.get("kind") != "figure" or f.get("caption"):
                continue
            fr = pymupdf.Rect(f["bbox"])
            if fr.x1 < r.x0 - 20 or fr.x0 > r.x1 + 20:
                continue
            dist = min(abs(r.y0 - fr.y1), abs(fr.y0 - r.y1))
            if dist < bd:
                best, bd = i, dist
        if best is not None and bd < 80:
            u["figure"] = best
            figures[best].setdefault("caption", u["id"])


# ---------------------------------------------------------------------------------------------------- rendering
_ARCHIVE = None


def archive():
    global _ARCHIVE
    if _ARCHIVE is None:
        _ARCHIVE = pymupdf.Archive(FONT_DIR)
    return _ARCHIVE


CSS_FONTS = """
@font-face {font-family: kserif; src: url(NanumMyeongjo-Regular.ttf);}
@font-face {font-family: kserif; src: url(NanumMyeongjo-Bold.ttf); font-weight: bold;}
@font-face {font-family: ksans; src: url(NanumGothic-Regular.ttf);}
@font-face {font-family: ksans; src: url(NanumGothic-Bold.ttf); font-weight: bold;}
@font-face {font-family: kserif; src: url(NanumMyeongjo-Regular.ttf); font-style: italic;}
@font-face {font-family: kserif; src: url(NanumMyeongjo-Bold.ttf); font-weight: bold; font-style: italic;}
@font-face {font-family: ksans; src: url(NanumGothic-Regular.ttf); font-style: italic;}
@font-face {font-family: ksans; src: url(NanumGothic-Bold.ttf); font-weight: bold; font-style: italic;}
@font-face {font-family: kmath; src: url(NotoSansMath-Regular.ttf);}
"""


def _clean_ko(h):
    """Translation markup -> safe HTML for MuPDF (only the inline tags we produced survive)."""
    h = h or ""
    h = re.sub(r"<(?!/?(b|i|sub|sup|br)\b)[^>]*>", "", h)
    h = re.sub(r"&(?!(amp|lt|gt|quot|#\d+|#x[0-9a-fA-F]+);)", "&amp;", h)
    return h


def unit_css(u, scale=1.0):
    fam = ("ksans" if u.get("sans") else "kserif") + ", kmath"
    sz = u["size"] * scale
    lh = max(1.05, min(u.get("lh") or 1.2, 1.9))
    return (CSS_FONTS + f"* {{font-family: {fam}; font-size: {sz:.2f}pt; line-height: {lh:.3f}; color: {u.get('color') or '#000'}; "
            f"margin: 0; padding: 0;}} body {{text-align: {u.get('align') or 'left'}; "
            f"text-indent: {u.get('indent') or 0}pt; font-weight: {'bold' if u.get('bold') else 'normal'}; "
            "font-style: normal;} sub, sup {font-size: 70%;}")


def render_page(src_pdf, pno, units, out_path, obstacles=()):
    """Write a one-page PDF: page pno of src_pdf with the translated units re-set in Korean."""
    src = pymupdf.open(src_pdf)
    doc = pymupdf.open()
    doc.insert_pdf(src, from_page=pno, to_page=pno)
    src.close()
    page = doc[0]
    mine = [u for u in units if u["page"] == pno]
    todo = [u for u in mine if u.get("translate") and u.get("ko")]
    for u in todo:
        for lb in u["lines"]:
            r = pymupdf.Rect(lb)
            inset = r.height * 0.18
            page.add_redact_annot(pymupdf.Rect(r.x0, r.y0 + inset, r.x1, r.y1 - inset), fill=False)
    if todo:
        page.apply_redactions(images=pymupdf.PDF_REDACT_IMAGE_NONE, graphics=pymupdf.PDF_REDACT_LINE_ART_NONE,
                              text=pymupdf.PDF_REDACT_TEXT_REMOVE)
    others = [pymupdf.Rect(u["bbox"]) for u in mine] + [pymupdf.Rect(o) for o in obstacles]
    fit = {}
    for u in todo:
        fit[u["id"]] = place(page, u, others, obstacles)
    doc.subset_fonts()
    doc.save(out_path, garbage=3, deflate=True)
    doc.close()
    return fit


def _room(u, others, W, H):
    """The box of u grown into the empty space below it (and, for a one-line box, to its right): used before shrinking text."""
    r = pymupdf.Rect(u["bbox"])
    below = [o.y0 for o in others if o.y0 >= r.y1 - 0.5 and o.x0 < r.x1 - 1 and o.x1 > r.x0 + 1 and o != r]
    y1 = min(below + [H * 0.94]) - 1.5
    x1 = r.x1
    if len(u["lines"]) == 1 and u["kind"] not in ("table", "title"):
        right = [o.x0 for o in others if o.x0 >= r.x1 - 0.5 and o.y0 < r.y1 and o.y1 > r.y0]
        col = W / 2 - 6 if r.x1 < W / 2 else W - 40
        x1 = max(r.x1, min(right + [col]) - 2)
    return pymupdf.Rect(r.x0, r.y0, x1, max(r.y1, y1))


def _beside(b, pics):
    """A paragraph that flows around a picture: the box narrowed to the side away from it."""
    for f in pics:
        f = pymupdf.Rect(f)
        i = b & f
        if i.is_empty or i.height < 4 or i.width < 4 or i.get_area() > 0.6 * b.get_area():   # (a table cell sits inside its table)
            continue
        if f.x0 > b.x0 + b.width * 0.35:                # picture on the right
            b = pymupdf.Rect(b.x0, b.y0, min(b.x1, f.x0 - 4), b.y1)
        elif f.x1 < b.x1 - b.width * 0.35:              # picture on the left
            b = pymupdf.Rect(max(b.x0, f.x1 + 4), b.y0, b.x1, b.y1)
    return b


def place(page, u, others=(), pics=()):
    """Set u's Korean text into its box at the original size if at all possible. Order: own box, own box grown
    into free space, then (only then) a smaller font. Never over a picture. Returns the scale used (1 = original)."""
    body = _clean_ko(u["ko"])
    css = unit_css(u)
    b = _beside(pymupdf.Rect(u["bbox"]), pics)
    own = pymupdf.Rect(b.x0, b.y0 - u["size"] * 0.08, b.x1 + 0.5 + (2 if u["kind"] == "table" else 0), b.y1 + u["size"] * 0.25)
    W, H = page.rect.width, page.rect.height
    big = _room(dict(u, bbox=list(b)), list(others), W, H) if u["kind"] != "table" else own
    big = _beside(pymupdf.Rect(big.x0, own.y0, max(big.x1, own.x1), max(big.y1, own.y1)), pics)
    for rect, low in ((own, 1), (big, 1), (own, 0.92), (big, 0.85), (big, 0.7), (big, 0)):
        spare, scale = page.insert_htmlbox(rect, body, css=css, archive=archive(), scale_low=low)
        if spare >= 0:
            return round(scale, 3)
    return 0.0


def page_png(pdf_path, pno, zoom, out_path):
    doc = pymupdf.open(pdf_path)
    pg = doc[pno if doc.page_count > 1 else 0]
    pix = pg.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), alpha=False)
    pix.save(out_path)
    doc.close()


def crop_png(pdf_path, pno, rect, out_path, zoom=2.5):
    doc = pymupdf.open(pdf_path)
    pg = doc[pno if doc.page_count > 1 else 0]
    r = pymupdf.Rect(rect)
    r = pymupdf.Rect(r.x0 - 3, r.y0 - 3, r.x1 + 3, r.y1 + 3) & pg.rect
    pg.get_pixmap(matrix=pymupdf.Matrix(zoom, zoom), clip=r, alpha=False).save(out_path)
    doc.close()


def search_rects(pdf_path, pno, text):
    """Rectangles of `text` on one page (for precise highlights of a selection)."""
    doc = pymupdf.open(pdf_path)
    pg = doc[pno if doc.page_count > 1 else 0]
    t = re.sub(r"\s+", " ", text).strip()
    hits = pg.search_for(t, quads=False) if t else []
    if not hits and len(t) > 40:                 # long selection: match the beginning and the end
        a, b = pg.search_for(t[:30]), pg.search_for(t[-30:])
        if a and b:
            hits = [a[0], b[-1]]
    doc.close()
    return [[round(x, 2) for x in r] for r in hits]
