"""Word (.docx) papers: paragraphs become units, translations go back into the same paragraphs (formatting, equations,
pictures, fields and footnote marks stay), and Word or LibreOffice turns both documents into PDFs.
"""
import copy
import html
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
from collections import Counter

import pymupdf
from lxml import etree

NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main",
      "m": "http://schemas.openxmlformats.org/officeDocument/2006/math",
      "r": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
      "a": "http://schemas.openxmlformats.org/drawingml/2006/main",
      "wp": "http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing",
      "v": "urn:schemas-microsoft-com:vml"}
W = "{%s}" % NS["w"]
M = "{%s}" % NS["m"]
R = "{%s}" % NS["r"]
XML_SPACE = "{http://www.w3.org/XML/1998/namespace}space"
PARTS = ("word/document.xml", "word/footnotes.xml", "word/endnotes.xml")
TOK = re.compile(r"⟦(\d+)⟧")


# ================================================================================================ conversion to PDF
def _soffice():
    for c in ("soffice", "libreoffice"):
        p = shutil.which(c)
        if p:
            return p
    for p in (r"C:\Program Files\LibreOffice\program\soffice.exe", r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
              "/Applications/LibreOffice.app/Contents/MacOS/soffice"):
        if os.path.exists(p):
            return p
    return None


_WORD_PS = r"""
$ErrorActionPreference = 'Stop'
$w = New-Object -ComObject Word.Application
$w.Visible = $false
$w.DisplayAlerts = 0
try {
  $d = $w.Documents.Open($env:HP_IN, $false, $true, $false)
  $d.ExportAsFixedFormat($env:HP_OUT, 17)
  $d.Close(0)
} finally { $w.Quit() }
"""


def to_pdf(src, out, timeout=300):
    """docx -> pdf with Microsoft Word (Windows, macOS) or LibreOffice."""
    errs = []
    if sys.platform == "win32":
        try:
            env = dict(os.environ, HP_IN=os.path.abspath(src), HP_OUT=os.path.abspath(out))
            r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", _WORD_PS], env=env, capture_output=True,
                               timeout=timeout, creationflags=0x08000000)
            if os.path.exists(out) and os.path.getsize(out) > 500:
                return "Word"
            errs.append("Word: " + (r.stderr or r.stdout).decode("utf-8", "replace").strip()[:200])
        except Exception as ex:  # noqa: BLE001
            errs.append(f"Word: {ex}")
    so = _soffice()
    if so:
        with tempfile.TemporaryDirectory() as td:
            tmp_in = os.path.join(td, "in.docx")
            shutil.copy(src, tmp_in)
            try:
                subprocess.run([so, "--headless", "--norestore", "--convert-to", "pdf", "--outdir", td, tmp_in], capture_output=True,
                               timeout=timeout, creationflags=0x08000000 if sys.platform == "win32" else 0)
            except Exception as ex:  # noqa: BLE001
                errs.append(f"LibreOffice: {ex}")
            res = os.path.join(td, "in.pdf")
            if os.path.exists(res):
                shutil.copy(res, out)
                return "LibreOffice"
            errs.append("LibreOffice: 변환 실패")
    if sys.platform == "darwin" and os.path.exists("/Applications/Microsoft Word.app"):
        script = f'''tell application "Microsoft Word"
  open POSIX file "{os.path.abspath(src)}"
  set d to active document
  save as d file name "{os.path.abspath(out)}" file format format PDF
  close d saving no
end tell'''
        try:
            subprocess.run(["osascript", "-e", script], capture_output=True, timeout=timeout)
            if os.path.exists(out):
                return "Word"
        except Exception as ex:  # noqa: BLE001
            errs.append(f"Word: {ex}")
    raise ValueError("Word 문서를 PDF로 바꾸려면 Microsoft Word나 LibreOffice가 필요합니다. " + " / ".join(errs)[:300])


# ================================================================================================ reading paragraphs
def _load(path):
    z = zipfile.ZipFile(path)
    parts = {}
    for name in PARTS:
        if name in z.namelist():
            parts[name] = etree.fromstring(z.read(name))
    rels = {}
    if "word/_rels/document.xml.rels" in z.namelist():
        for rel in etree.fromstring(z.read("word/_rels/document.xml.rels")):
            rels[rel.get("Id")] = rel.get("Target")
    styles = {}
    if "word/styles.xml" in z.namelist():
        for st in etree.fromstring(z.read("word/styles.xml")).iter(W + "style"):
            nm = st.find(W + "name")
            styles[st.get(W + "styleId")] = (nm.get(W + "val") if nm is not None else st.get(W + "styleId")) or ""
    return z, parts, rels, styles


def paragraphs(parts):
    """(part, index, <w:p>) for every paragraph, in a fixed order."""
    out = []
    for name in PARTS:
        root = parts.get(name)
        if root is None:
            continue
        for i, p in enumerate(root.iter(W + "p")):
            out.append((name, i, p))
    return out


def _flags(rpr):
    f = set()
    if rpr is None:
        return f
    for tag, key in (("b", "b"), ("i", "i"), ("u", "u")):
        e = rpr.find(W + tag)
        if e is not None and e.get(W + "val") not in ("0", "false", "none"):
            f.add(key)
    va = rpr.find(W + "vertAlign")
    if va is not None and va.get(W + "val") in ("superscript", "subscript"):
        f.add("sup" if va.get(W + "val") == "superscript" else "sub")
    return f


class Para:
    """A paragraph split into text pieces (with formatting) and opaque items (kept as they are)."""

    def __init__(self, p):
        self.p = p
        self.pieces = []      # ("t", text, flags, run) or ("o", [elements], legend)
        self.lead = []        # zero-width items kept at the start (bookmarks, comment marks)
        self._walk(p)

    def _walk(self, parent):
        field = None
        for el in list(parent):
            tag = etree.QName(el).localname if isinstance(el.tag, str) else ""
            ns = etree.QName(el).namespace if isinstance(el.tag, str) else ""
            if field is not None:                     # inside a complex field: everything up to its end is one item
                field.append(el)
                if tag == "r" and el.find(W + "fldChar") is not None and el.find(W + "fldChar").get(W + "fldCharType") == "end":
                    self.pieces.append(("o", field, _field_text(field)))
                    field = None
                continue
            if tag == "pPr" or tag == "proofErr" or not tag:
                continue
            if tag in ("bookmarkStart", "bookmarkEnd", "commentRangeStart", "commentRangeEnd", "permStart", "permEnd"):
                self.lead.append(el)
                continue
            if ns == NS["m"]:                          # oMath / oMathPara
                self.pieces.append(("o", [el], "수식: " + omml_tex(el)))
                continue
            if tag == "r":
                fc = el.find(W + "fldChar")
                if fc is not None and fc.get(W + "fldCharType") == "begin":
                    field = [el]
                    continue
                self._run(el)
                continue
            if tag in ("ins", "smartTag", "customXml", "sdt", "sdtContent"):
                self._walk(el if tag != "sdt" else (el.find(W + "sdtContent") if el.find(W + "sdtContent") is not None else el))
                continue
            if tag == "del" or tag == "moveFrom":
                continue
            if tag == "hyperlink":
                self.pieces.append(("o", [el], "링크: " + "".join(el.itertext())[:80]))
                continue
            if tag == "fldSimple":
                self.pieces.append(("o", [el], "필드: " + "".join(el.itertext())[:60]))
                continue
            self.pieces.append(("o", [el], tag))
        if field:
            self.pieces.append(("o", field, _field_text(field)))

    def _run(self, r):
        rpr = r.find(W + "rPr")
        fl = _flags(rpr)
        buf = []

        def flush():
            if buf:
                self.pieces.append(("t", "".join(buf), fl, r))
                buf.clear()
        for c in r:
            tag = etree.QName(c).localname if isinstance(c.tag, str) else ""
            if tag == "rPr":
                continue
            if tag == "t":
                buf.append(c.text or "")
            elif tag == "tab":
                buf.append("\t")
            elif tag == "noBreakHyphen":
                buf.append("-")
            elif tag in ("softHyphen", "lastRenderedPageBreak"):
                continue
            else:                                       # br, drawing, footnoteReference, sym, object ...
                flush()
                legend = {"br": "줄바꿈", "drawing": "그림", "pict": "그림", "object": "개체", "footnoteReference": "각주 번호",
                          "endnoteReference": "미주 번호", "sym": "기호", "cr": "줄바꿈"}.get(tag, tag)
                nr = etree.Element(W + "r")
                if rpr is not None:
                    nr.append(copy.deepcopy(rpr))
                nr.append(c)
                self.pieces.append(("o", [nr], legend))
        flush()

    def text_runs(self):
        return [x for x in self.pieces if x[0] == "t"]

    def markup(self):
        """Text with <b>/<i>/<u>/<sup>/<sub> and ⟦n⟧ tokens, plus the token legend."""
        out, keep, n = [], {}, 0
        for x in self.pieces:
            if x[0] == "t":
                t = html.escape(x[1], quote=False)
                for tg in ("sub", "sup", "u", "i", "b"):
                    if tg in x[2]:
                        t = f"<{tg}>{t}</{tg}>"
                out.append(t)
            else:
                n += 1
                tok = f"⟦{n}⟧"
                keep[tok] = x[2]
                out.append(tok)
        m = "".join(out)
        for tg in ("b", "i", "u", "sup", "sub"):          # <b>a</b><b>b</b> -> <b>ab</b>
            m = m.replace(f"</{tg}><{tg}>", "")
        return m, keep

    def plain(self):
        return "".join(x[1] if x[0] == "t" else (" " if x[2] != "각주 번호" else "") for x in self.pieces).strip()


def _field_text(els):
    instr = "".join(t.text or "" for e in els for t in e.iter(W + "instrText")).strip()
    shown, on = [], False
    for e in els:
        fc = e.find(W + "fldChar")
        if fc is not None:
            on = fc.get(W + "fldCharType") == "separate"
            continue
        if on:
            shown.extend(t.text or "" for t in e.iter(W + "t"))
    kind = instr.split()[0] if instr else "필드"
    return f"{kind}: {''.join(shown)[:60]}"


def _kind(p, styles, part):
    if part != "word/document.xml":
        return "note"
    ps = p.find(W + "pPr/" + W + "pStyle")
    name = styles.get(ps.get(W + "val"), ps.get(W + "val")) if ps is not None else ""
    low = (name or "").lower()
    if low == "title" or low.startswith("title"):
        return "title"
    if low.startswith("heading") or re.match(r"^(제목|머리글)\s*\d", name or ""):
        return "heading"
    if "caption" in low or name == "캡션":
        return "caption"
    if "bibliograph" in low or low in ("references", "reference"):
        return "ref"
    if p.getparent() is not None and etree.QName(p.getparent()).localname == "tc":
        return "table"
    return "para"


def _in_table(p):
    e = p.getparent()
    while e is not None:
        if etree.QName(e).localname == "tc":
            return True
        e = e.getparent()
    return False


# ================================================================================================ OMML -> LaTeX
NARY = {"∑": "\\sum", "∏": "\\prod", "∫": "\\int", "∬": "\\iint", "∭": "\\iiint", "∮": "\\oint", "⋃": "\\bigcup", "⋂": "\\bigcap", "∐": "\\coprod"}
ACC = {"̂": "\\hat", "̃": "\\tilde", "̄": "\\bar", "⃗": "\\vec", "̇": "\\dot", "̈": "\\ddot", "̆": "\\breve", "̌": "\\check", "́": "\\acute", "̀": "\\grave"}


def _val(el, path, default=None):
    e = el.find(path)
    return e.get(M + "val") if e is not None else default


def omml_tex(el):
    try:
        return _om(el).strip()
    except Exception:  # noqa: BLE001
        return "".join(el.itertext())


def _om(el):
    if el is None:
        return ""
    tag = etree.QName(el).localname
    ch = lambda name: el.find(M + name)            # noqa: E731
    if tag in ("oMathPara",):
        return " \\\\ ".join(_om(x) for x in el.findall(M + "oMath"))
    if tag == "r":
        t = "".join(x.text or "" for x in el.iter(M + "t"))
        sty = _val(el, M + "rPr/" + M + "sty")
        nor = el.find(M + "rPr/" + M + "nor") is not None
        t = "".join({"{": "\\{", "}": "\\}", "%": "\\%", "#": "\\#", "&": "\\&", "_": "\\_", "$": "\\$", "\\": "\\backslash "}.get(c, c) for c in t)
        if nor or (len(t) > 1 and t.isalpha() and sty in ("p", None) and t not in ("sin", "cos", "tan", "log", "ln", "exp", "max", "min", "lim")):
            return "\\text{" + t + "}" if nor else t
        if sty == "b":
            return "\\mathbf{" + t + "}"
        return t
    if tag == "f":
        typ = _val(el, M + "fPr/" + M + "type")
        num, den = _om(ch("num")), _om(ch("den"))
        if typ == "lin":
            return f"{num}/{den}"
        if typ == "noBar":
            return f"\\genfrac{{}}{{}}{{0pt}}{{}}{{{num}}}{{{den}}}"
        return f"\\frac{{{num}}}{{{den}}}"
    if tag == "sSup":
        return f"{{{_om(ch('e'))}}}^{{{_om(ch('sup'))}}}"
    if tag == "sSub":
        return f"{{{_om(ch('e'))}}}_{{{_om(ch('sub'))}}}"
    if tag == "sSubSup":
        return f"{{{_om(ch('e'))}}}_{{{_om(ch('sub'))}}}^{{{_om(ch('sup'))}}}"
    if tag == "sPre":
        return f"{{}}_{{{_om(ch('sub'))}}}^{{{_om(ch('sup'))}}}{{{_om(ch('e'))}}}"
    if tag == "rad":
        hide = _val(el, M + "radPr/" + M + "degHide") in ("1", "on", "true")
        deg = _om(ch("deg"))
        return f"\\sqrt[{deg}]{{{_om(ch('e'))}}}" if deg and not hide else f"\\sqrt{{{_om(ch('e'))}}}"
    if tag == "d":
        beg = _val(el, M + "dPr/" + M + "begChr", "(")
        end = _val(el, M + "dPr/" + M + "endChr", ")")
        sep = _val(el, M + "dPr/" + M + "sepChr", "|")
        conv = {"{": "\\{", "}": "\\}", "": ".", "⟨": "\\langle", "⟩": "\\rangle", "‖": "\\|", "⌈": "\\lceil", "⌉": "\\rceil", "⌊": "\\lfloor", "⌋": "\\rfloor"}
        inner = f" {sep} ".join(_om(x) for x in el.findall(M + "e"))
        return f"\\left{conv.get(beg, beg)} {inner} \\right{conv.get(end, end)}"
    if tag == "nary":
        c = _val(el, M + "naryPr/" + M + "chr", "∫")
        op = NARY.get(c, c)
        sub, sup = _om(ch("sub")), _om(ch("sup"))
        s = op + (f"_{{{sub}}}" if sub else "") + (f"^{{{sup}}}" if sup else "")
        return s + " " + _om(ch("e"))
    if tag == "func":
        name = _om(ch("fName")).strip()
        known = {"sin", "cos", "tan", "log", "ln", "exp", "max", "min", "lim", "arg", "det", "sup", "inf", "tanh", "sigmoid"}
        n = "\\" + name if name in known - {"sigmoid"} else f"\\operatorname{{{name}}}" if re.fullmatch(r"[A-Za-z]+", name) else name
        return f"{n} {_om(ch('e'))}"
    if tag == "acc":
        c = _val(el, M + "accPr/" + M + "chr", "̂")
        return f"{ACC.get(c, chr(92) + 'hat')}{{{_om(ch('e'))}}}"
    if tag == "bar":
        pos = _val(el, M + "barPr/" + M + "pos", "top")
        return f"\\{'overline' if pos == 'top' else 'underline'}{{{_om(ch('e'))}}}"
    if tag == "groupChr":
        return f"\\underbrace{{{_om(ch('e'))}}}"
    if tag == "limLow":
        return f"\\underset{{{_om(ch('lim'))}}}{{{_om(ch('e'))}}}"
    if tag == "limUpp":
        return f"\\overset{{{_om(ch('lim'))}}}{{{_om(ch('e'))}}}"
    if tag == "m":
        rows = [" & ".join(_om(e) for e in mr.findall(M + "e")) for mr in el.findall(M + "mr")]
        return "\\begin{matrix} " + " \\\\ ".join(rows) + " \\end{matrix}"
    if tag == "eqArr":
        return "\\begin{aligned} " + " \\\\ ".join(_om(e).replace("&", "", 0) for e in el.findall(M + "e")) + " \\end{aligned}"
    if tag.endswith("Pr") or tag == "ctrlPr":
        return ""
    return "".join(_om(x) for x in el)


# ================================================================================================ units
def extract(path):
    z, parts, rels, styles = _load(path)
    units, figs, eqs = [], [], []
    for part, i, p in paragraphs(parts):
        media = []
        for blip in p.iter("{%s}blip" % NS["a"]):
            rid = blip.get(R + "embed")
            if rid and rid in rels:
                t = rels[rid].lstrip("/")
                media.append(t if t.startswith("word/") else "word/" + t)
        para = Para(copy.deepcopy(p))          # Para moves elements around; read a copy
        plain = para.plain()
        kind = _kind(p, styles, part)
        if _in_table(p):
            kind = "table"
        has_math_para = p.find(".//" + M + "oMathPara") is not None
        has_pic = any(x[0] == "o" and x[2] in ("그림", "개체") for x in para.pieces)
        letters = len(re.findall(r"[A-Za-z]", plain))
        if has_math_para and letters < 3:
            tex = " \\\\ ".join(omml_tex(m) for m in p.iter(M + "oMathPara"))
            units.append({"part": part, "pi": i, "kind": "equation", "translate": False, "text": tex, "tex": tex, "src": ""})
            continue
        if has_pic and letters < 3:
            units.append({"part": part, "pi": i, "kind": "figure", "translate": False, "text": "", "src": "", "media": media})
            continue
        if letters < 2:
            continue
        m, keep = para.markup()
        u = {"part": part, "pi": i, "kind": kind, "translate": kind != "ref", "src": m, "keep": keep, "text": plain}
        if kind == "heading":
            ps = p.find(W + "pPr/" + W + "pStyle")
            lv = re.search(r"(\d)", styles.get(ps.get(W + "val"), "") if ps is not None else "")
            u["level"] = "h2" if not lv or lv.group(1) == "1" else "h3"
        units.append(u)
    z.close()
    return units


def masked(u):
    return u["src"], dict(u.get("keep") or {})


_TAGS = re.compile(r"</?(b|i|u|sup|sub)>")


def accept(u, ko, keep):
    toks = TOK.findall(ko)
    want = [t.strip("⟦⟧") for t in keep]
    miss = [t for t in want if toks.count(t) != 1]
    if miss:
        return None, "자리표시 " + " ".join(f"⟦{t}⟧" for t in miss[:6]) + " 이(가) 빠졌거나 중복입니다"
    extra = [t for t in toks if t not in want]
    if extra:
        return None, "원문에 없는 자리표시를 썼습니다"
    clean = re.sub(r"<(?!/?(b|i|u|sup|sub)>)[^>]*>", "", ko)      # only the five inline tags survive
    return clean, None


# ================================================================================================ writing the Korean docx
def _set_text_props(rpr, sans):
    if rpr is None:
        rpr = etree.Element(W + "rPr")
    fonts = rpr.find(W + "rFonts")
    if fonts is None:
        fonts = etree.Element(W + "rFonts")
        rpr.insert(0, fonts)
    fonts.set(W + "eastAsia", "Malgun Gothic" if sans else "Batang")
    for a in ("eastAsiaTheme",):
        fonts.attrib.pop(W + a, None)
    lang = rpr.find(W + "lang")
    if lang is None:
        lang = etree.SubElement(rpr, W + "lang")
    lang.set(W + "eastAsia", "ko-KR")
    return rpr


def _strip_flags(rpr):
    rpr = copy.deepcopy(rpr) if rpr is not None else etree.Element(W + "rPr")
    for tag in ("b", "bCs", "i", "iCs", "u", "vertAlign"):
        for e in rpr.findall(W + tag):
            rpr.remove(e)
    return rpr


def _with_flags(base, fl):
    rpr = copy.deepcopy(base)
    order = []
    if "b" in fl:
        order.append(etree.Element(W + "b"))
    if "i" in fl:
        order.append(etree.Element(W + "i"))
    if "u" in fl:
        e = etree.Element(W + "u")
        e.set(W + "val", "single")
        order.append(e)
    if "sup" in fl or "sub" in fl:
        e = etree.Element(W + "vertAlign")
        e.set(W + "val", "superscript" if "sup" in fl else "subscript")
        order.append(e)
    # schema order: rStyle, rFonts, b, bCs, i, iCs, ... vertAlign ... lang; put flags after rFonts/rStyle
    pos = 0
    for k, c in enumerate(rpr):
        if etree.QName(c).localname in ("rStyle", "rFonts"):
            pos = k + 1
    for e in reversed([x for x in order if etree.QName(x).localname != "vertAlign"]):
        rpr.insert(pos, e)
    for e in order:
        if etree.QName(e).localname == "vertAlign":
            lang = rpr.find(W + "lang")
            if lang is not None:
                lang.addprevious(e)
            else:
                rpr.append(e)
    return rpr


def _parse_markup(ko):
    """[(text, flags)] and [('tok', n)] in order."""
    out, stack, i = [], [], 0
    for m in re.finditer(r"</?(b|i|u|sup|sub)>|⟦(\d+)⟧", ko):
        if m.start() > i:
            out.append(("t", html.unescape(ko[i:m.start()]), set(stack)))
        if m.group(2):
            out.append(("o", int(m.group(2))))
        elif m.group(0).startswith("</"):
            if m.group(1) in stack:
                stack.remove(m.group(1))
        else:
            stack.append(m.group(1))
        i = m.end()
    if i < len(ko):
        out.append(("t", html.unescape(ko[i:]), set(stack)))
    return out


def rewrite(p, ko):
    """Replace the text of paragraph element p with the Korean markup, keeping formatting and opaque items."""
    para = Para(p)
    runs = para.text_runs()
    if not runs:
        return
    # base run properties: the run holding most of the text
    weight = Counter()
    for x in runs:
        weight[id(x[3])] += len(x[1])
    main = max(runs, key=lambda x: weight[id(x[3])])[3]
    base = _strip_flags(main.find(W + "rPr"))
    fonts = base.find(W + "rFonts")
    ascii_font = (fonts.get(W + "ascii") or fonts.get(W + "asciiTheme") or "") if fonts is not None else ""
    sans = bool(re.search(r"arial|calibri|helvetica|segoe|gothic|sans|minor|major", ascii_font, re.I))
    by_flags = {}
    for x in runs:
        by_flags.setdefault(frozenset(x[2]), x[3].find(W + "rPr"))
    opaque = [x for x in para.pieces if x[0] == "o"]
    # remove old content (except pPr), keep lead items
    for c in list(p):
        if isinstance(c.tag, str) and etree.QName(c).localname == "pPr":
            continue
        p.remove(c)
    for e in para.lead:
        if etree.QName(e).localname in ("bookmarkStart", "commentRangeStart", "permStart"):
            p.append(e)
    for item in _parse_markup(ko):
        if item[0] == "o":
            k = item[1] - 1
            if 0 <= k < len(opaque):
                for e in opaque[k][1]:
                    p.append(e)
            continue
        text, fl = item[1], item[2]
        if not text:
            continue
        src_rpr = by_flags.get(frozenset(fl))
        rpr = copy.deepcopy(src_rpr) if src_rpr is not None else _with_flags(base, fl)
        rpr = _set_text_props(rpr, sans)
        r = etree.SubElement(p, W + "r")
        r.append(rpr)
        for k, part in enumerate(text.split("\t")):
            if k:
                etree.SubElement(r, W + "tab")
            if part:
                t = etree.SubElement(r, W + "t")
                t.text = part
                t.set(XML_SPACE, "preserve")
    for e in para.lead:
        if etree.QName(e).localname not in ("bookmarkStart", "commentRangeStart", "permStart"):
            p.append(e)


def write_ko(src, out, units):
    """Copy src to out with every translated unit's paragraph rewritten."""
    z, parts, rels, styles = _load(src)
    todo = {(u["part"], u["pi"]): u for u in units if u.get("ko") and u.get("translate")}
    for part, i, p in paragraphs(parts):
        u = todo.get((part, i))
        if u:
            rewrite(p, u["ko"])
    # Korean line breaking: let Word break between Korean words like Latin ones
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zo:
        for info in z.infolist():
            if info.filename in parts:
                zo.writestr(info, etree.tostring(parts[info.filename], xml_declaration=True, encoding="UTF-8", standalone=True))
            else:
                zo.writestr(info, z.read(info.filename))
    z.close()
    return out


# ================================================================================================ where paragraphs land on the PDF
def _norm(s):
    s = unicodedata.normalize("NFKC", s).lower()
    return "".join(c for c in s if c.isalnum())


class Stream:
    def __init__(self, pdf):
        self.chars, self.owner, self.words = [], [], []
        with pymupdf.open(pdf) as d:
            for pg in d:
                for w in pg.get_text("words", sort=False):
                    k = len(self.words)
                    self.words.append((pg.number, w[0], w[1], w[2], w[3], w[5], w[6]))
                    for c in _norm(w[4]):
                        self.chars.append(c)
                        self.owner.append(k)
        self.s = "".join(self.chars)

    def locate(self, text, cursor):
        key = _norm(text)
        if len(key) < 2:
            return None, cursor
        for n in (24, 14, 8):
            head = key[:n]
            if len(head) < min(n, len(key)):
                continue
            pos = self.s.find(head, cursor, cursor + 120000)
            if pos < 0:
                pos = self.s.find(head)
            if pos >= 0:
                break
        else:
            return None, cursor
        end = pos + len(key)
        tail = key[-12:]
        if len(key) > 30:
            q = self.s.find(tail, pos + int(len(key) * 0.6), pos + int(len(key) * 1.4) + 60)
            if q >= 0:
                end = q + len(tail)
        end = min(end, len(self.s))
        ws = sorted(set(self.owner[pos:end]))
        lines = {}
        for k in ws:
            pg, x0, y0, x1, y1, b, ln = self.words[k]
            key2 = (pg, b, ln)
            if key2 in lines:
                r = lines[key2]
                lines[key2] = [pg, min(r[1], x0), min(r[2], y0), max(r[3], x1), max(r[4], y1)]
            else:
                lines[key2] = [pg, x0, y0, x1, y1]
        rects = sorted(lines.values(), key=lambda r: (r[0], r[2], r[1]))
        return [[round(v, 2) for v in r] for r in rects], end


def align(pdf, units, side):
    st = Stream(pdf)
    cur = 0
    geo = {}
    for u in units:
        txt = u.get("text") if side == "en" else u.get("_ko_plain")
        if not txt or u["kind"] in ("equation", "figure"):
            continue
        rects, nxt = st.locate(txt, 0 if u["kind"] == "note" else cur)
        if rects:
            geo[u["id"]] = rects
            if u["kind"] != "note":
                cur = nxt
    # pictures and display equations: the gap between the neighbours on the same page
    with pymupdf.open(pdf) as d:
        for k, u in enumerate(units):
            if u["kind"] not in ("equation", "figure"):
                continue
            prev = next((geo[x["id"]][-1] for x in reversed(units[:k]) if geo.get(x["id"]) and x["kind"] != "note"), None)
            nxt = next((geo[x["id"]][0] for x in units[k + 1:] if geo.get(x["id"]) and x["kind"] != "note"), None)
            box = None
            if prev and nxt and prev[0] == nxt[0] and nxt[2] - prev[4] > 8:
                pg = d[prev[0]]
                box = pymupdf.Rect(36, prev[4] + 1, pg.rect.width - 36, nxt[2] - 1)
            elif nxt and nxt[2] > 60:                        # first thing on its page
                pg = d[nxt[0]]
                box = pymupdf.Rect(36, 30, pg.rect.width - 36, nxt[2] - 1)
            elif prev:                                       # last thing on its page
                pg = d[prev[0]]
                box = pymupdf.Rect(36, prev[4] + 1, pg.rect.width - 36, pg.rect.height - 30)
            if box is not None and box.height > 8:
                parts = [pymupdf.Rect(i["bbox"]) & box for i in pg.get_image_info() if pymupdf.Rect(i["bbox"]).intersects(box)]
                parts += [dr["rect"] & box for dr in pg.get_drawings() if dr["rect"].intersects(box)]
                parts += [pymupdf.Rect(b[:4]) for b in pg.get_text("blocks") if box.contains(pymupdf.Rect(b[:4]))]
                parts = [q for q in parts if not q.is_empty]
                if parts:
                    r = parts[0]
                    for q in parts[1:]:
                        r |= q
                    geo[u["id"]] = [[pg.number, round(r.x0 - 1, 2), round(r.y0 - 1, 2), round(r.x1 + 1, 2), round(r.y1 + 1, 2)]]
    return geo


# ================================================================================================ the paper interface (see sources.py)
def prepare(p, report):
    src = p.f("source.docx")
    report("원문 PDF를 만드는 중… (Word 문서 변환)")
    to_pdf(src, p.pdf)
    report("논문 구조를 읽는 중…")
    raw = extract(src)
    units = []
    for i, u in enumerate(raw):
        u["id"] = f"u{i}"
        units.append(u)
    geo = align(p.pdf, units, "en")
    import sources
    last = 0
    for u in units:
        last = sources.place(u, geo.get(u["id"]), last)
        u["size"] = 10
    figures, equations = [], []
    for k, u in enumerate(units):
        if u["kind"] == "figure":
            cap = next((x["id"] for x in units[k + 1:k + 3] if x["kind"] == "caption"), None) or \
                next((x["id"] for x in reversed(units[max(0, k - 2):k]) if x["kind"] == "caption"), None)
            g = u["geo"]["en"]
            figures.append({"page": g[0][0] if g else u["page"], "bbox": g[0][1:] if g else None, "caption": cap, "kind": "figure",
                            "media": u.get("media") or [], "unit": u["id"]})
        elif u["kind"] == "equation":
            g = u["geo"]["en"]
            equations.append({"page": g[0][0] if g else u["page"], "bbox": g[0][1:] if g else None, "units": [u["id"]], "tex": u.get("tex", "")})
    figures = [f for f in figures if f["bbox"] or f["media"]]
    return {"pages": sources._pages(p.pdf), "units": units, "figures": figures, "tables": [], "equations": equations,
            "body_size": sources._body_size(p.pdf), "macros": {}, "source": "docx"}


def build(p, report):
    d = p.doc()
    with p.lock:
        units = [dict(u) for u in d["units"]]
    out_docx = p.f("ko.docx")
    tmp = p.f("ko.tmp.docx")
    write_ko(p.f("source.docx"), tmp, units)
    os.replace(tmp, out_docx)
    report("한국어 PDF를 만드는 중… (Word 문서 변환)")
    tmp_pdf = p.f("ko.tmp.pdf")
    to_pdf(out_docx, tmp_pdf)
    os.replace(tmp_pdf, p.ko_pdf)
    for u in units:
        u["_ko_plain"] = plain(u["ko"]) if u.get("ko") and u.get("translate") else u.get("text")
    geo = align(p.ko_pdf, units, "ko")
    with p.lock:
        for u in d["units"]:
            u.setdefault("geo", {})["ko"] = geo.get(u["id"], [])
    import sources
    return sources._pages(p.ko_pdf)


def plain(markup):
    t = TOK.sub(" ", markup or "")
    t = re.sub(r"<[^>]+>", "", t)
    return html.unescape(t).strip()


def html_of(u, markup):
    legend = u.get("keep") or {}

    def tok(m):
        lg = legend.get(m.group(0), "")
        if lg.startswith("수식: "):
            return f'<span class="tex">{html.escape(lg[4:])}</span>'
        if lg.startswith(("링크: ", "필드: ")):
            return html.escape(lg.split(": ", 1)[1])
        if " " in lg and ":" in lg:
            return html.escape(lg.split(": ", 1)[1])
        if lg == "각주 번호":
            return "<sup>*</sup>"
        return ""
    s = TOK.sub(tok, markup or "")
    s = s.replace("\t", " ")
    return s


def html_for(p, u, side):
    if side == "en":
        return html_of(u, u.get("src", ""))
    return html_of(u, u.get("ko") or "")


def export_source(p, out_path):
    if not os.path.exists(p.f("ko.docx")):
        raise ValueError("아직 한국어 Word 문서가 없습니다")
    shutil.copy(p.f("ko.docx"), out_path)
    return out_path
