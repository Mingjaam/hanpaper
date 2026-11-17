"""LaTeX source papers: unpack, flatten, split into translation units, rebuild in Korean and compile with Tectonic.

The English PDF is compiled from the same flattened file, so SyncTeX maps every unit to its lines on both PDFs.
"""
import gzip
import io
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import threading
import urllib.request
import zipfile

import latex as L
import paths
import synctex

TECTONIC_VER = "0.17.0"
EN, KO = "hp_en", "hp_ko"
FONT_DIR = "hpfonts"

# ================================================================================================ unpacking
def is_tex_archive(data, name=""):
    n = name.lower()
    if n.endswith((".tex", ".ltx")):
        return True
    if data[:2] == b"\x1f\x8b" or n.endswith((".tar.gz", ".tgz", ".tar", ".gz")):
        return True
    if data[:2] == b"PK":
        try:
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = [x.lower() for x in z.namelist()]
            return any(x.endswith(".tex") for x in names) and not any(x == "word/document.xml" for x in names)
        except zipfile.BadZipFile:
            return False
    return False


def unpack(data, name, dest):
    """Write the source files under dest. Paths are kept inside dest."""
    os.makedirs(dest, exist_ok=True)
    root = os.path.realpath(dest)

    def safe(p):
        p = p.replace("\\", "/").lstrip("/")
        full = os.path.realpath(os.path.join(root, p))
        if not (full == root or full.startswith(root + os.sep)):
            return None
        return full

    def write(rel, blob):
        full = safe(rel)
        if not full or rel.endswith("/"):
            return
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "wb") as f:
            f.write(blob)

    n = name.lower()
    if data[:2] == b"PK":
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for info in z.infolist():
                if info.is_dir() or info.file_size > 200 << 20:
                    continue
                write(info.filename, z.read(info))
    elif data[:2] == b"\x1f\x8b" or n.endswith((".tar", ".tgz", ".tar.gz")):
        raw = gzip.decompress(data) if data[:2] == b"\x1f\x8b" else data
        try:
            with tarfile.open(fileobj=io.BytesIO(raw)) as t:
                for m in t.getmembers():
                    if m.isfile() and m.size < 200 << 20:
                        write(m.name, t.extractfile(m).read())
        except tarfile.ReadError:                   # arXiv: a single gzipped .tex
            write("main.tex", raw)
    else:
        write(os.path.basename(name) if n.endswith((".tex", ".ltx")) else "main.tex", data)
    # a single top folder: use it as the root
    entries = [e for e in os.listdir(dest) if not e.startswith((".", "__MACOSX"))]
    if len(entries) == 1 and os.path.isdir(os.path.join(dest, entries[0])):
        inner = os.path.join(dest, entries[0])
        for e in os.listdir(inner):
            shutil.move(os.path.join(inner, e), os.path.join(dest, e))
        os.rmdir(inner)


def find_main(root):
    best, score = None, -1
    for dp, _, fs in os.walk(root):
        for f in fs:
            if not f.lower().endswith(".tex") or f.startswith((EN, KO)):
                continue
            p = os.path.join(dp, f)
            try:
                t = open(p, encoding="utf-8", errors="replace").read()
            except OSError:
                continue
            t2 = L.strip_comments(t)
            if not re.search(r"\\documentclass", t2) or "\\begin{document}" not in t2.replace(" ", ""):
                continue
            s = len(t2) / 1000 + 40 * (os.path.splitext(f)[0].lower() in ("main", "paper", "ms", "manuscript", "article")) \
                + 5 * len(re.findall(r"\\(?:input|include)\b", t2)) - 20 * (dp != root)
            if s > score:
                best, score = p, s
    return best


# ================================================================================================ flattening
def flatten(root, main):
    """Inline \\input / \\include, drop comments, put the .bbl in place of \\bibliography."""
    seen = set()
    rel_main = os.path.relpath(main, root)

    def load(path, depth):
        try:
            t = open(path, encoding="utf-8", errors="replace").read()
        except OSError:
            return ""
        t = L.strip_comments(t.replace("\r\n", "\n").replace("\r", "\n"))
        if depth > 12:
            return t

        def rep(m):
            cmd, arg = m.group(1), m.group(2).strip()
            for cand in (arg, arg + ".tex"):
                full = os.path.join(root, cand)
                if os.path.isfile(full) and os.path.realpath(full).startswith(os.path.realpath(root)):
                    key = os.path.realpath(full)
                    if key in seen and cmd != "input":
                        return ""
                    seen.add(key)
                    body = load(full, depth + 1).rstrip("\n")
                    return ("\\clearpage\n" if cmd == "include" else "") + body + ("\n\\clearpage" if cmd == "include" else "") + "\n"
            return m.group(0)
        return re.sub(r"\\(input|include|subfile)\s*\{([^}]+)\}", rep, t)

    text = load(main, 0)
    stem = os.path.splitext(main)[0]
    bbl = stem + ".bbl"
    if not os.path.exists(bbl):
        cands = [os.path.join(dp, f) for dp, _, fs in os.walk(root) for f in fs if f.endswith(".bbl") and not f.startswith((EN, KO))]
        bbl = cands[0] if len(cands) == 1 else None
    if bbl and os.path.exists(bbl):
        b = open(bbl, encoding="utf-8", errors="replace").read()
        if re.search(r"\\bibliography\s*\{", text):
            text = re.sub(r"\\bibliography\s*\{[^}]*\}", lambda m: b, text, count=1)
        elif re.search(r"\\printbibliography", text) is None:
            pass
    return text, rel_main


# ================================================================================================ splitting into units
DISPLAY = {"equation", "equation*", "align", "align*", "alignat", "alignat*", "gather", "gather*", "multline", "multline*", "eqnarray",
           "eqnarray*", "displaymath", "flalign", "flalign*", "dmath", "dmath*", "subequations", "IEEEeqnarray", "IEEEeqnarray*"}
SKIP = set(L.VERBATIM) | {"tabular", "tabular*", "tabularx", "tabulary", "longtable", "array", "tikzpicture", "pgfpicture", "axis", "picture",
                          "algorithmic", "algorithmicx", "thebibliography", "lstlisting", "minted", "forest", "tikzcd", "math", "lrbox",
                          "titlepage", "CCSXML", "acks*", "references"}
FLOATS = {"figure": "figure", "figure*": "figure", "wrapfigure": "figure", "SCfigure": "figure", "subfigure": "figure", "table": "table",
          "table*": "table", "wraptable": "table", "algorithm": "algorithm", "algorithm*": "algorithm", "algorithm2e": "algorithm",
          "listing": "code", "lstlisting*": "code", "sidewaystable": "table", "sidewaysfigure": "figure", "SCtable": "table"}
LISTS = {"itemize", "enumerate", "description", "compactitem", "compactenum", "inparaenum", "asparaenum", "outline"}
SECTIONS = {"part": "h2", "chapter": "h2", "section": "h2", "subsection": "h3", "subsubsection": "h3", "paragraph": "h4", "subparagraph": "h4"}
TITLES = {"title", "icmltitle", "Title", "IEEEtitle", "papertitle"}
RAW_CMDS = {"maketitle", "label", "vspace", "vskip", "hspace", "newpage", "clearpage", "cleardoublepage", "pagebreak", "appendix", "centering",
            "bibliography", "bibliographystyle", "printbibliography", "includegraphics", "author", "icmlauthor", "affiliation", "icmlaffiliation",
            "icmlcorrespondingauthor", "icmlkeywords", "printAffiliationsAndNotice", "icmlsetsymbol", "IEEEauthorblockN", "IEEEauthorblockA",
            "institute", "email", "address", "date", "thanks", "newcommand", "renewcommand", "providecommand", "def", "let", "setlength",
            "addtolength", "setcounter", "addtocounter", "linenumbers", "nolinenumbers", "thispagestyle", "pagestyle", "tableofcontents",
            "listoffigures", "listoftables", "medskip", "smallskip", "bigskip", "bigbreak", "noindent", "par", "hline", "toprule", "midrule",
            "bottomrule", "small", "footnotesize", "normalsize", "raggedbottom", "flushbottom", "onecolumn", "IEEEoverridecommandlockouts",
            "IEEEpeerreviewmaketitle", "keywords", "ccsdesc", "settopmatter", "orcid", "authornote", "authorsaddresses", "renewenvironment",
            "newenvironment", "newtheorem", "theoremstyle", "graphicspath", "captionsetup", "hypersetup", "input", "include", "FloatBarrier",
            "balance", "nocite", "acknowledgments", "vfill", "hfill", "null", "markboth", "AtBeginDocument", "DeclareMathOperator",
            "newcolumntype", "definecolor", "usetikzlibrary", "pgfplotsset", "tikzset", "addbibresource", "makeatletter", "makeatother",
            "pdfbookmark", "phantomsection", "addcontentsline", "IEEEPARstart", "nobreak", "relax", "selectfont", "fontsize", "linespread",
            "doublespacing", "singlespacing", "onehalfspacing", "restoregeometry", "newgeometry", "enlargethispage", "allowdisplaybreaks",
            "titlespacing", "renewcommand*", "newcommand*", "providecommand*", "global", "stepcounter", "refstepcounter", "begingroup",
            "endgroup", "bgroup", "egroup", "arraystretch", "renewcommand", "rowcolors", "scriptsize", "tiny", "resizebox", "adjustbox"}


class Splitter:
    def __init__(self, text):
        self.t = text
        self.units = []          # {kind, a, b} spans of text to translate (a..b offsets), in reading order
        self.regions = []        # {kind, a, b, caps: [unit index]} figures, tables, algorithms, equations
        self._link = False       # next paragraph continues the previous one (split by a display equation)

    # -- helpers
    def unit(self, kind, a, b):
        while a < b and self.t[a] in " \t\n":
            a += 1
        while b > a and self.t[b - 1] in " \t\n":
            b -= 1
        if b <= a:
            return None
        src = self.t[a:b]
        if kind in ("para", "item") and not L.has_words(src):
            return None
        u = {"kind": kind, "a": a, "b": b}
        if kind in ("para", "item") and self._link and self.units:
            last = next((x for x in reversed(self.units) if x["kind"] in ("para", "item", "equation")), None)
            prev = next((x for x in reversed(self.units) if x["kind"] in ("para", "item")), None)
            if last is not None and last["kind"] == "equation" and prev is not None:
                u["prev_i"] = self.units.index(prev)
        self._link = False
        self.units.append(u)
        return len(self.units) - 1

    def run(self):
        t = self.t
        m = re.search(r"\\begin\s*\{document\}", t)
        if not m:
            raise ValueError("\\begin{document}를 찾지 못했습니다")
        # title in the preamble
        for tm in re.finditer(r"\\(" + "|".join(TITLES) + r")\s*(\[[^\]]*\])?\s*\{", t[:m.start()]):
            j = L.skip_group(t, tm.end() - 1)
            self.unit("title", tm.end(), j - 1)
        e = re.search(r"\\end\s*\{document\}", t)
        self.body = (m.end(), e.start() if e else len(t))
        self.scan(m.end(), self.body[1])
        return self

    def scan(self, i, end):
        t = self.t
        pa = None                                   # paragraph start

        def flush(upto):
            nonlocal pa
            if pa is not None:
                self.unit("para", pa, upto)
            pa = None

        while i < end:
            c = t[i]
            if c == "\n":
                if L._blank_after(t, i):
                    flush(i)
                    self._link = False
                i += 1
                continue
            if c in " \t":
                i += 1
                continue
            if c == "$" and t.startswith("$$", i):
                j = L.skip_math(t, i)
                self.display(i, j, pa, flush)
                pa = None
                i = j
                continue
            if c == "$":
                if pa is None:
                    pa = i
                i = L.skip_math(t, i)
                continue
            if c == "\\":
                if t.startswith("\\[", i):
                    j = L.skip_math(t, i)
                    self.display(i, j, pa, flush)
                    pa = None
                    i = j
                    continue
                if t.startswith("\\(", i):
                    if pa is None:
                        pa = i
                    i = L.skip_math(t, i)
                    continue
                name, j = L.read_cmd(t, i)
                base = name.rstrip("*")
                if name == "begin":
                    g = L.skip_ws(t, j, newlines=False)
                    if g < end and t[g] == "{":
                        k = L.skip_group(t, g)
                        env = t[g + 1:k - 1].strip()
                        inner_end, after = L.env_end(t, env, k)
                        after = min(after, end)
                        if env in DISPLAY:
                            self.display(i, after, pa, flush)
                            pa = None
                        elif env in FLOATS:
                            flush(i)
                            self.float(env, i, k, inner_end, after)
                        elif env in SKIP:
                            flush(i)
                        elif env in LISTS:
                            flush(i)
                            self.items(L.skip_args(t, k, groups=0), inner_end)
                        else:                       # abstract, theorem, center, minipage, quote ...: look inside
                            flush(i)
                            body = L.skip_args(t, k, groups=1 if env in ("minipage", "adjustbox", "tcolorbox", "wrapfigure") else 0)
                            self.scan(body, inner_end)
                        i = after
                        continue
                if name == "end":
                    flush(i)
                    i = L.skip_args(t, j, groups=1, opts=0)
                    continue
                if base in SECTIONS:
                    flush(i)
                    k = L.skip_ws(t, j, newlines=False)
                    if k < end and t[k] == "[":
                        k = L.skip_group(t, k, "[", "]")
                    k = L.skip_ws(t, k)
                    if k < end and t[k] == "{":
                        g = L.skip_group(t, k)
                        ix = self.unit("heading", k + 1, g - 1)
                        if ix is not None:
                            self.units[ix]["level"] = SECTIONS[base]
                        i = g
                    else:
                        i = k
                    continue
                if base in TITLES:
                    flush(i)
                    k = L.skip_args(t, j, groups=0)
                    k = L.skip_ws(t, k)
                    if k < end and t[k] == "{":
                        g = L.skip_group(t, k)
                        self.unit("title", k + 1, g - 1)
                        i = g
                    else:
                        i = k
                    continue
                if base in ("caption", "captionof", "subcaption"):
                    flush(i)
                    i = self.caption(i, j)
                    continue
                if base == "twocolumn":
                    flush(i)
                    k = L.skip_ws(t, j, newlines=False)
                    if k < end and t[k] == "[":
                        g = L.skip_group(t, k, "[", "]")
                        self.scan(k + 1, g - 1)
                        i = g
                    else:
                        i = k
                    continue
                if base == "item":
                    flush(i)
                    i = L.skip_args(t, j, groups=0, opts=1)
                    continue
                if base in RAW_CMDS and pa is None:
                    i = L.skip_args(t, j)
                    continue
                if base in ("section", "def") or (base.startswith("new") and pa is None):
                    i = L.skip_args(t, j)
                    continue
                if pa is None:
                    pa = i
                i = j
                continue
            if c == "{" and pa is None:
                pa = i
            if c == "%":
                i += 1
                continue
            if pa is None:
                pa = i
            i += 1
        flush(end)

    def display(self, a, b, pa, flush):
        flush(a)
        idx = self.unit_eq(a, b)
        self._link = True
        return idx

    def unit_eq(self, a, b):
        self.units.append({"kind": "equation", "a": a, "b": b})
        self.regions.append({"kind": "equation", "a": a, "b": b, "unit": len(self.units) - 1})
        return len(self.units) - 1

    def caption(self, i, j):
        t = self.t
        k = L.skip_ws(t, j, newlines=False)
        if t.startswith("captionof", i + 1):
            if k < len(t) and t[k] == "{":
                k = L.skip_ws(t, L.skip_group(t, k), newlines=False)
        while k < len(t) and t[k] == "[":
            k = L.skip_ws(t, L.skip_group(t, k, "[", "]"), newlines=False)
        k = L.skip_ws(t, k)
        if k < len(t) and t[k] == "{":
            g = L.skip_group(t, k)
            self.unit("caption", k + 1, g - 1)
            return g
        return k

    def float(self, env, a, inner, inner_end, after):
        t = self.t
        caps = []
        for m in re.finditer(r"\\(caption|captionof|subcaption)\b\*?", t[inner:inner_end]):
            pos = inner + m.start()
            if any(r["a"] <= pos < r["b"] for r in self.regions if r.get("kind") == "_cap"):
                continue
            n0 = len(self.units)
            g = self.caption(pos, inner + m.end())
            if len(self.units) > n0:
                caps.append(n0)
                self.regions.append({"kind": "_cap", "a": pos, "b": g})
        self.regions = [r for r in self.regions if r.get("kind") != "_cap"]
        self.regions.append({"kind": FLOATS[env], "a": a, "b": after, "caps": caps})

    def items(self, a, b):
        """List body: one unit per \\item (nested lists and math handled by scan)."""
        t = self.t
        pos, i = [], a
        while i < b:
            c = t[i]
            if c == "\\":
                name, j = L.read_cmd(t, i)
                if name == "item":
                    pos.append(i)
                    i = j
                    continue
                if name == "begin":
                    g = L.skip_ws(t, j, newlines=False)
                    if g < b and t[g] == "{":
                        k = L.skip_group(t, g)
                        _, after = L.env_end(t, t[g + 1:k - 1].strip(), k)
                        i = after
                        continue
                i = j
                continue
            if c == "{":
                i = L.skip_group(t, i)
                continue
            if c == "$":
                i = L.skip_math(t, i)
                continue
            i += 1
        if not pos:
            self.scan(a, b)
            return
        if pos[0] > a:
            self.scan(a, pos[0])
        for k, p in enumerate(pos):
            nxt = pos[k + 1] if k + 1 < len(pos) else b
            _, j = L.read_cmd(t, p)
            body = L.skip_args(t, j, groups=0, opts=1)
            self.scan(body, nxt)


# ================================================================================================ Tectonic
def tectonic_exe():
    name = "tectonic.exe" if sys.platform == "win32" else "tectonic"
    p = os.path.join(paths.DATA, "tools", "tectonic", name)
    if os.path.exists(p):
        return p
    return shutil.which("tectonic")


_dl_lock = threading.Lock()


def ensure_tectonic(report=None):
    """Download Tectonic (about 20 MB) on first use."""
    with _dl_lock:
        p = tectonic_exe()
        if p:
            return p
        if sys.platform == "win32":
            asset = f"tectonic-{TECTONIC_VER}-x86_64-pc-windows-msvc.zip"
        elif sys.platform == "darwin":
            arch = "aarch64" if platform.machine().lower() in ("arm64", "aarch64") else "x86_64"
            asset = f"tectonic-{TECTONIC_VER}-{arch}-apple-darwin.tar.gz"
        else:
            asset = f"tectonic-{TECTONIC_VER}-x86_64-unknown-linux-musl.tar.gz"
        url = f"https://github.com/tectonic-typesetting/tectonic/releases/download/tectonic%40{TECTONIC_VER}/{asset}"
        if report:
            report("TeX 엔진(Tectonic)을 내려받는 중… (처음 한 번)")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Hanpaper"})
            with urllib.request.urlopen(req, timeout=120) as r:
                blob = r.read()
        except Exception as ex:  # noqa: BLE001
            raise RuntimeError(f"TeX 엔진을 내려받지 못했습니다 (인터넷 연결 확인): {ex}")
        d = os.path.join(paths.DATA, "tools", "tectonic")
        os.makedirs(d, exist_ok=True)
        if asset.endswith(".zip"):
            with zipfile.ZipFile(io.BytesIO(blob)) as z:
                z.extractall(d)
        else:
            with tarfile.open(fileobj=io.BytesIO(blob)) as t:
                for m in t.getmembers():
                    if m.isfile() and os.path.basename(m.name) == "tectonic":
                        with open(os.path.join(d, "tectonic"), "wb") as f:
                            f.write(t.extractfile(m).read())
        p = tectonic_exe()
        if not p:
            raise RuntimeError("TeX 엔진을 풀지 못했습니다")
        if sys.platform != "win32":
            os.chmod(p, 0o755)
        return p


def compile_tex(root, name, report=None, timeout=1500):
    """Compile root/name.tex. Returns (pdf path or None, log text)."""
    exe = ensure_tectonic(report)
    for ext in (".pdf", ".synctex.gz"):
        try:
            os.remove(os.path.join(root, name + ext))
        except OSError:
            pass
    cmd = [exe, "-Z", "continue-on-errors", "--synctex", "--keep-intermediates", "--keep-logs", name + ".tex"]
    flags = 0x08000000 if sys.platform == "win32" else 0         # CREATE_NO_WINDOW
    try:
        r = subprocess.run(cmd, cwd=root, capture_output=True, timeout=timeout, creationflags=flags)
        log = (r.stdout + r.stderr).decode("utf-8", "replace")
    except subprocess.TimeoutExpired:
        return None, "TeX 컴파일이 너무 오래 걸려 멈췄습니다"
    pdf = os.path.join(root, name + ".pdf")
    return (pdf if os.path.exists(pdf) and os.path.getsize(pdf) > 1000 else None), log


def errors(log):
    return [ln for ln in log.splitlines() if ln.startswith("error:") and "halted on" not in ln and "unrecoverable" not in ln
            and "something bad happened" not in ln]


# ================================================================================================ Korean preamble
KO_NAMES = {"figurename": "그림", "tablename": "표", "abstractname": "요약", "refname": "참고문헌", "bibname": "참고문헌",
            "appendixname": "부록", "contentsname": "차례", "listfigurename": "그림 차례", "listtablename": "표 차례", "proofname": "증명",
            "algorithmname": "알고리즘", "figureautorefname": "그림", "tableautorefname": "표", "sectionautorefname": "절",
            "subsectionautorefname": "절", "subsubsectionautorefname": "절", "equationautorefname": "식", "appendixautorefname": "부록",
            "algorithmautorefname": "알고리즘", "lstlistingname": "코드"}
CREF = {"figure": "그림", "table": "표", "section": "절", "subsection": "절", "subsubsection": "절", "equation": "식", "appendix": "부록",
        "algorithm": "알고리즘", "subfigure": "그림", "subtable": "표", "line": "줄", "theorem": "정리", "lemma": "보조정리",
        "definition": "정의", "corollary": "따름정리", "proposition": "명제", "remark": "비고", "chapter": "장"}


def ko_preamble():
    fam = "Path=./" + FONT_DIR + "/, Extension=.ttf, UprightFont=*-Regular, BoldFont=*-Bold, ItalicFont=*-Regular, BoldItalicFont=*-Bold"
    gyre = "[Extension=.otf, UprightFont=*-regular, BoldFont=*-bold, ItalicFont=*-italic, BoldItalicFont=*-bolditalic]"
    names = "".join(f"\\ifdefined\\{k}\\renewcommand\\{k}{{{v}}}\\fi" for k, v in KO_NAMES.items())
    cref = "".join(f"\\crefname{{{k}}}{{{v}}}{{{v}}}\\Crefname{{{k}}}{{{v}}}{{{v}}}" for k, v in CREF.items())
    return "\n".join([
        "% ---- 한페이퍼: Korean typesetting",
        "\\makeatletter",
        "\\edef\\hp@rm{\\rmdefault}\\edef\\hp@sf{\\sfdefault}\\edef\\hp@tt{\\ttdefault}",
        "\\def\\hp@try#1#2#3{\\def\\hp@x{#2}\\ifx#1\\hp@x #3\\fi}",
        "\\makeatother",
        "\\usepackage{kotex}",
        "\\xetexkofontregime{latin}",
        f"\\setmainhangulfont{{NanumMyeongjo}}[{fam}]",
        f"\\setsanshangulfont{{NanumGothic}}[{fam}]",
        f"\\setmonohangulfont{{NanumGothic}}[{fam}]",
        "\\makeatletter",
        f"\\hp@try\\hp@rm{{ptm}}{{\\setmainfont{{texgyretermes}}{gyre}}}",
        f"\\hp@try\\hp@rm{{ptmx}}{{\\setmainfont{{texgyretermes}}{gyre}}}",
        f"\\hp@try\\hp@rm{{ntxtlf}}{{\\setmainfont{{texgyretermes}}{gyre}}}",
        f"\\hp@try\\hp@rm{{ppl}}{{\\setmainfont{{texgyrepagella}}{gyre}}}",
        f"\\hp@try\\hp@rm{{pplx}}{{\\setmainfont{{texgyrepagella}}{gyre}}}",
        f"\\hp@try\\hp@rm{{pnc}}{{\\setmainfont{{texgyreschola}}{gyre}}}",
        f"\\hp@try\\hp@rm{{pbk}}{{\\setmainfont{{texgyrebonum}}{gyre}}}",
        f"\\hp@try\\hp@sf{{phv}}{{\\setsansfont{{texgyreheros}}{gyre}}}",
        f"\\hp@try\\hp@sf{{uhv}}{{\\setsansfont{{texgyreheros}}{gyre}}}",
        f"\\hp@try\\hp@tt{{pcr}}{{\\setmonofont{{texgyrecursor}}{gyre}}}",
        "\\makeatother",
        "\\ifdefined\\crefname " + cref + "\\fi",
        names,
        "\\AtBeginDocument{" + names + "}",
        "\\ifdefined\\floatname\\floatname{algorithm}{알고리즘}\\fi",
        "% ---- end 한페이퍼",
        "",
    ])


def copy_fonts(root):
    d = os.path.join(root, FONT_DIR)
    os.makedirs(d, exist_ok=True)
    for f in ("NanumMyeongjo-Regular.ttf", "NanumMyeongjo-Bold.ttf", "NanumGothic-Regular.ttf", "NanumGothic-Bold.ttf"):
        src = os.path.join(paths.STATIC, "fonts", f)
        dst = os.path.join(d, f)
        if os.path.exists(src) and not os.path.exists(dst):
            shutil.copy(src, dst)


def build_ko(text, units, ko_of):
    """The flattened text with each unit replaced by its Korean (ko_of(unit) -> LaTeX or None).
    Returns (text, {unit id: (line0, line1)}) with 1-based line numbers in the new text, preamble included."""
    m = re.search(r"\\begin\s*\{document\}", text)
    pre = ko_preamble()
    out, lines, pos, ln = [], {}, 0, 1
    ins = m.start()
    spans = sorted((u for u in units if u.get("a") is not None), key=lambda u: u["a"])
    events = [(ins, "pre", None)] + [(u["a"], "u", u) for u in spans]
    events.sort(key=lambda e: (e[0], e[1] != "pre"))
    for at, kind, u in events:
        if at < pos:
            continue
        chunk = text[pos:at]
        out.append(chunk)
        ln += chunk.count("\n")
        pos = at
        if kind == "pre":
            out.append(pre)
            ln += pre.count("\n")
            continue
        ko = ko_of(u)
        piece = ko if ko else text[u["a"]:u["b"]]
        l0 = ln
        out.append(piece)
        ln += piece.count("\n")
        extra = 0
        if u.get("kind") in ("caption", "heading", "title"):      # typeset when the closing brace is read
            close = text.find("}", u["b"])
            extra = text[u["b"]:close].count("\n") if close >= 0 else 0
        lines[u["id"]] = (l0, ln + extra)
        pos = u["b"]
    out.append(text[pos:])
    return "".join(out), lines


def line_of(text):
    """offset -> 1-based line number function."""
    import bisect
    starts = [0] + [m.end() for m in re.finditer("\n", text)]
    return lambda off: bisect.bisect_right(starts, off)


def geometry(root, name, spans):
    """{id: [(page, x0, y0, x1, y1), ...]} for line spans {id: (l0, l1)} from root/name.synctex.gz."""
    p = os.path.join(root, name + ".synctex.gz")
    if not os.path.exists(p):
        return {}
    st = synctex.SyncTex(p)
    tag = st.tag_for(name + ".tex")
    if tag is None:
        return {}
    return {k: [list(r) for r in st.rects(tag, a, b)] for k, (a, b) in spans.items()}
