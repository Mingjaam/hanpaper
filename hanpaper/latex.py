"""Small LaTeX helpers shared by the TeX pipeline: scanning, masking for the translator, and LaTeX -> HTML for the reader."""
import html
import re
import unicodedata

# ------------------------------------------------------------------------------------------------ scanning
_CMD = re.compile(r"\\([A-Za-z@]+\*?|.)", re.S)


def read_cmd(s, i):
    """s[i] == '\\'. Returns (name, end). Name has no backslash; a star stays attached ('section*')."""
    m = _CMD.match(s, i)
    if not m:
        return "", i + 1
    return m.group(1), m.end()


def skip_group(s, i, open_="{", close="}"):
    """s[i] == open_. Index just after the matching close (backslash escapes respected)."""
    depth, n = 0, len(s)
    while i < n:
        c = s[i]
        if c == "\\":
            i += 2
            continue
        if c == "%" and open_ == "{":
            j = s.find("\n", i)
            i = n if j < 0 else j + 1
            continue
        if c == open_:
            depth += 1
        elif c == close:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return n


def skip_ws(s, i, newlines=True):
    n = len(s)
    while i < n and (s[i] in " \t" or (newlines and s[i] == "\n" and not _blank_after(s, i))):
        i += 1
    return i


def _blank_after(s, i):
    """s[i] == '\\n': is the next line blank (a paragraph break)?"""
    j = i + 1
    while j < len(s) and s[j] in " \t\r":
        j += 1
    return j >= len(s) or s[j] == "\n"


def skip_args(s, i, groups=9, opts=9):
    """Skip a command's arguments: any [..] and up to `groups` {..} directly after it."""
    n = len(s)
    while i < n:
        j = skip_ws(s, i, newlines=False)
        if j < n and s[j] == "*":
            i = j + 1
            continue
        if j < n and s[j] == "[" and opts:
            i = skip_group(s, j, "[", "]")
            opts -= 1
            continue
        if j < n and s[j] == "{" and groups:
            i = skip_group(s, j)
            groups -= 1
            continue
        break
    return i


def skip_math(s, i):
    """At $, $$, \\( or \\[. Index after the closing delimiter."""
    n = len(s)
    if s.startswith("$$", i):
        j = s.find("$$", i + 2)
        return n if j < 0 else j + 2
    if s.startswith("\\(", i) or s.startswith("\\[", i):
        close = "\\)" if s[i + 1] == "(" else "\\]"
        j = i + 2
        while j < n:
            if s.startswith(close, j):
                return j + 2
            j += 2 if s[j] == "\\" else 1
        return n
    j = i + 1
    while j < n:
        if s[j] == "\\":
            j += 2
            continue
        if s[j] == "$":
            return j + 1
        j += 1
    return n


def env_end(s, name, i):
    """i is just after \\begin{name}. Returns (inner_end, after) for the matching \\end{name}."""
    depth, n = 1, len(s)
    pat = re.compile(r"\\(begin|end)\s*\{" + re.escape(name) + r"\}")
    verbatim = name in VERBATIM
    while True:
        m = pat.search(s, i)
        if not m:
            return n, n
        if m.group(1) == "begin" and not verbatim:
            depth += 1
        else:
            depth -= 1
            if depth == 0:
                return m.start(), m.end()
        i = m.end()


def strip_comments(text):
    """Remove % comments but keep the '%' itself so line joining is unchanged. Verbatim-like blocks are left alone."""
    out, verb = [], None
    for line in text.split("\n"):
        if verb:
            out.append(line)
            if re.search(r"\\end\s*\{" + re.escape(verb) + r"\}", line):
                verb = None
            continue
        m = re.search(r"\\begin\s*\{(" + "|".join(re.escape(v) for v in VERBATIM) + r")\}", line)
        if m and not re.search(r"\\end\s*\{" + re.escape(m.group(1)) + r"\}", line):
            verb = m.group(1)
            out.append(line)
            continue
        i, cut = 0, None
        while i < len(line):
            c = line[i]
            if c == "\\":
                if line.startswith("\\verb", i) and i + 5 < len(line) and not line[i + 5].isalpha():
                    d = line[i + 5] if line[i + 5] != "*" else (line[i + 6] if i + 6 < len(line) else "")
                    j = line.find(d, i + 6 + (line[i + 5] == "*")) if d else -1
                    i = len(line) if j < 0 else j + 1
                    continue
                i += 2
                continue
            if c == "%":
                cut = i
                break
            i += 1
        if cut is None:
            out.append(line)
        elif line[:cut].strip() == "":
            out.append("%" if cut else "%")
        else:
            out.append(line[:cut] + "%")
    # whole-line comments: drop them entirely (a line that is only '%' joins nothing visible)
    res = []
    for line in out:
        if line == "%" and res and res[-1].strip() == "":
            continue
        res.append(line)
    return "\n".join(res)


VERBATIM = ("verbatim", "verbatim*", "Verbatim", "lstlisting", "minted", "comment", "filecontents", "filecontents*", "alltt")

# ------------------------------------------------------------------------------------------------ masking for the translator
CITE = re.compile(r"(?:[Cc]ite[a-z]*|[Cc]itep|[Cc]itet|citealp|citealt|citeauthor|citeyear|citeyearpar|parencite|textcite|autocite|footcite|nocite)\*?$")
PROTECT = {  # command -> number of {..} groups to keep with it
    "ref": 1, "eqref": 1, "autoref": 1, "Autoref": 1, "cref": 1, "Cref": 1, "crefrange": 2, "Crefrange": 2, "pageref": 1, "nameref": 1,
    "vref": 1, "Vref": 1, "label": 1, "url": 1, "href": 1, "includegraphics": 1, "footnotemark": 0, "input": 1, "hyperref": 0,
    "ensuremath": 1, "si": 1, "SI": 2, "num": 1, "qty": 2, "ang": 1, "unit": 1, "orcidlink": 1, "thanks": 0, "cmark": 0, "xmark": 0,
    "checkmark": 0, "faIcon": 1, "texttt": 1, "verb": 0,
}


def mask(src):
    """Replace math, citations, references and similar spans with ⟦n⟧ tokens. Returns (masked, {token: original})."""
    out, keep, i, n = [], {}, 0, len(src)
    last = 0

    def put(a, b):
        nonlocal last
        tok = f"⟦{len(keep) + 1}⟧"
        keep[tok] = src[a:b]
        out.append(src[last:a])
        out.append(tok)
        last = b

    while i < n:
        c = src[i]
        if c == "$" and (i == 0 or src[i - 1] != "\\"):
            j = skip_math(src, i)
            put(i, j)
            i = j
            continue
        if c == "\\":
            if i + 1 < n and src[i + 1] in "([":
                j = skip_math(src, i)
                put(i, j)
                i = j
                continue
            name, j = read_cmd(src, i)
            base = name.rstrip("*")
            if base == "verb" and j < n:
                d = src[j]
                k = src.find(d, j + 1)
                k = n if k < 0 else k + 1
                put(i, k)
                i = k
                continue
            if CITE.match(base) or base in PROTECT:
                if base == "href":
                    k = skip_args(src, j, groups=1)
                    put(i, k)         # \href{url}  -- the link text {..} that follows stays translatable
                    i = k
                    continue
                k = skip_args(src, j, groups=PROTECT.get(base, 1))
                put(i, k)
                i = k
                continue
            if name in ("begin", "end"):
                k = skip_args(src, j, groups=1, opts=1 if name == "begin" else 0)
                put(i, k)
                i = k
                continue
            i = j
            continue
        i += 1
    out.append(src[last:])
    return "".join(out), keep


_TOK = re.compile(r"⟦\d+⟧")


def check(masked, keep, ko):
    """Problems with a translation of a masked unit, as a short Korean message (None if fine)."""
    toks = _TOK.findall(ko)
    missing = [t for t in keep if toks.count(t) == 0]
    if missing:
        return f"자리표시 {' '.join(missing[:6])} 이(가) 빠졌습니다"
    extra = [t for t in set(toks) if toks.count(t) > 1 or t not in keep]
    if extra:
        return f"자리표시 {' '.join(extra[:6])} 이(가) 중복되거나 원문에 없습니다"
    d = 0
    i = 0
    while i < len(ko):
        c = ko[i]
        if c == "\\":
            i += 2
            continue
        if c == "{":
            d += 1
        elif c == "}":
            d -= 1
            if d < 0:
                return "중괄호 { } 짝이 맞지 않습니다"
        i += 1
    if d:
        return "중괄호 { } 짝이 맞지 않습니다"
    return None


def unmask(ko, keep, masked_src):
    """Put the kept spans back and escape characters that would break LaTeX."""
    for ch in "%&#_^":
        if not _bare(masked_src, ch):
            ko = _escape_bare(ko, ch)
    if '"' not in masked_src:            # "..." typed by the translator -> real quotes (TeX would print ” ”)
        ko = re.sub(r'"([^"\n]{1,200})"', "“\\1”", ko)
    return _TOK.sub(lambda m: keep.get(m.group(0), m.group(0)), ko)


def _bare(s, ch):
    i = 0
    while True:
        i = s.find(ch, i)
        if i < 0:
            return False
        if i == 0 or s[i - 1] != "\\":
            return True
        i += 1


def _escape_bare(s, ch):
    out, i = [], 0
    while i < len(s):
        c = s[i]
        if c == "\\":
            out.append(s[i:i + 2])
            i += 2
            continue
        out.append(("\\" + c) if c == ch else c)
        i += 1
    return "".join(out).replace("\\^", "\\^{}")


# ------------------------------------------------------------------------------------------------ LaTeX -> HTML (reader)
SIMPLE = {
    "ldots": "…", "dots": "…", "textellipsis": "…", "LaTeX": "LaTeX", "TeX": "TeX", "S": "§", "P": "¶", "textbackslash": "\\",
    "textasciitilde": "~", "textendash": "–", "textemdash": "—", "textquoteright": "’", "textquoteleft": "‘", "textbullet": "•",
    "copyright": "©", "textregistered": "®", "texttrademark": "™", "dag": "†", "ddag": "‡", "textdagger": "†", "textdaggerdbl": "‡",
    "ss": "ß", "ae": "æ", "AE": "Æ", "o": "ø", "O": "Ø", "aa": "å", "AA": "Å", "l": "ł", "L": "Ł", "i": "ı", "item": "• ",
    "newline": "<br>", "linebreak": " ", "par": "<br>", "quad": " ", "qquad": "  ", "enspace": " ", "thinspace": " ",
    "eg": "e.g.", "ie": "i.e.", "etal": "et al.", "etc": "etc.", "vs": "vs.", "wrt": "w.r.t.", "cf": "cf.", "textless": "<",
    "textgreater": ">", "textbar": "|", "textunderscore": "_", "pounds": "£", "euro": "€", "textdegree": "°", "degree": "°",
    "cmark": "✓", "xmark": "✗", "checkmark": "✓", "textasciicircum": "^",
}
WRAP = {
    "textbf": "b", "bf": "b", "bfseries": "b", "textit": "i", "emph": "i", "it": "i", "itshape": "i", "textsl": "i", "sl": "i",
    "texttt": "code", "tt": "code", "underline": "u", "uline": "u", "textsuperscript": "sup", "textsubscript": "sub",
    "textsc": "sc", "sc": "sc", "textsf": "", "textrm": "", "textmd": "", "textup": "", "textnormal": "", "mbox": "", "hbox": "",
    "text": "", "makebox": "", "fbox": "", "framebox": "", "hl": "mark", "textcolor": "", "colorbox": "", "small": "", "footnotesize": "",
    "scriptsize": "", "large": "", "Large": "", "normalsize": "", "tiny": "", "huge": "", "Huge": "", "centering": "", "noindent": "",
    "smallskip": "", "medskip": "", "bigskip": "", "vspace": None, "hspace": None, "label": None, "color": None, "vskip": None,
    "phantom": None, "hphantom": None, "vphantom": None, "index": None, "nocite": None, "pdfbookmark": None, "addcontentsline": None,
    "footnote": "fn", "thanks": "fn", "footnotetext": "fn", "marginpar": None, "todo": None, "protect": "", "nolinkurl": "code", "url": "url",
    "includegraphics": None, "raisebox": "", "resizebox": "", "scalebox": "",
}
ACCENT = {"'": "\u0301", "`": "\u0300", "^": "\u0302", '"': "\u0308", "~": "\u0303", "=": "\u0304", ".": "\u0307", "u": "\u0306",
          "v": "\u030c", "H": "\u030b", "c": "\u0327", "k": "\u0328", "r": "\u030a", "d": "\u0323", "b": "\u0331"}
REFNAME = {"en": {"fig": "Figure", "tab": "Table", "sec": "Section", "eq": "Eq.", "alg": "Algorithm", "app": "Appendix", "thm": "Theorem", "": ""},
           "ko": {"fig": "그림", "tab": "표", "sec": "절", "eq": "식", "alg": "알고리즘", "app": "부록", "thm": "정리", "": ""}}


class Aux:
    """Numbers for \\ref and \\cite, read from the compiled .aux."""

    def __init__(self, text=""):
        self.labels, self.cites = {}, {}
        for m in re.finditer(r"\\newlabel\{([^}]*)\}\{\{([^{}]*)\}", text):
            self.labels.setdefault(m.group(1), m.group(2))
        for m in re.finditer(r"\\bibcite\{([^}]*)\}\{(.*)", text):
            body = m.group(2)
            parts = re.findall(r"\{((?:[^{}]|\{[^{}]*\})*)\}", body)
            if parts and len(parts) >= 3:
                self.cites[m.group(1)] = {"n": parts[0], "year": parts[1], "author": re.sub(r"[{}]|~", " ", parts[2]).strip()}
            else:
                num = re.match(r"\{?([^{}]*)\}?", body.rstrip("}")).group(1) if body else "?"
                self.cites[m.group(1)] = {"n": num}


def _kind_of_label(key):
    k = key.split(":")[0].lower() if ":" in key else ""
    for p, name in (("fig", "fig"), ("tab", "tab"), ("sec", "sec"), ("ssec", "sec"), ("subsec", "sec"), ("eq", "eq"), ("alg", "alg"),
                    ("app", "app"), ("thm", "thm"), ("lem", "thm"), ("prop", "thm")):
        if k.startswith(p):
            return name
    return ""


def to_html(src, aux=None, lang="en"):
    aux = aux or Aux()
    return _Html(src, aux, lang).run()


class _Html:
    def __init__(self, s, aux, lang):
        self.s, self.aux, self.lang = s, aux, lang

    def run(self):
        h = self.conv(0, len(self.s))
        h = re.sub(r"\s+", " ", h).strip()
        return h

    def conv(self, a, b):
        s, out, i = self.s, [], a
        while i < b:
            c = s[i]
            if c == "$" or (c == "\\" and i + 1 < b and s[i + 1] in "(["):
                j = min(skip_math(s, i), b)
                tex = s[i:j]
                disp = tex.startswith("$$") or tex.startswith("\\[")
                inner = tex[2:-2] if (tex.startswith("$$") or tex[:2] in ("\\(", "\\[")) else tex[1:-1]
                out.append(f'<span class="tex{" d" if disp else ""}">{html.escape(inner.strip())}</span>')
                i = j
                continue
            if c == "\\":
                name, j = read_cmd(s, i)
                i = self.cmd(name, j, b, out)
                continue
            if c == "{":
                j = min(skip_group(s, i), b)
                out.append(self.conv(i + 1, j - 1))
                i = j
                continue
            if c == "}":
                i += 1
                continue
            if c == "~":
                out.append("&nbsp;")
                i += 1
                continue
            if s.startswith("---", i):
                out.append("—")
                i += 3
                continue
            if s.startswith("--", i):
                out.append("–")
                i += 2
                continue
            if s.startswith("``", i):
                out.append("“")
                i += 2
                continue
            if s.startswith("''", i):
                out.append("”")
                i += 2
                continue
            if c == "`":
                out.append("‘")
                i += 1
                continue
            if c == "'":
                out.append("’")
                i += 1
                continue
            if c == "&":
                out.append(" ")
                i += 1
                continue
            j = i
            while j < b and s[j] not in "$\\{}~-`'&":
                j += 1
            if j == i:
                out.append(html.escape(c))
                j = i + 1
            else:
                out.append(html.escape(s[i:j]))
            i = j
        return "".join(out)

    def arg(self, i, b):
        """Next {..} argument (after optional [..]). Returns (start, end_inner, after) or None."""
        s = self.s
        j = skip_ws(s, i, newlines=False)
        while j < b and s[j] == "[":
            j = skip_ws(s, skip_group(s, j, "[", "]"), newlines=False)
        if j < b and s[j] == "{":
            k = min(skip_group(s, j), b)
            return j + 1, k - 1, k
        return None

    def cmd(self, name, j, b, out):
        s, base = self.s, name.rstrip("*")
        if len(name) == 1 and not name.isalpha():
            if name in ACCENT:
                a = self.arg(j, b)
                if a:
                    out.append(unicodedata.normalize("NFC", html.escape(s[a[0]:a[1]]) + ACCENT[name]))
                    return a[2]
                if j < b:
                    out.append(unicodedata.normalize("NFC", html.escape(s[j]) + ACCENT[name]))
                    return j + 1
            if name == "\\":
                k = skip_args(s, j, groups=0)
                out.append("<br>")
                return k
            if name in "%&#_${} ":
                out.append(html.escape(name))
                return j
            if name in ",;:!>":
                out.append(" " if name != "!" else "")
                return j
            if name == "-":
                return j
            return j
        if CITE.match(base):
            a = self.arg(j, b)
            if not a:
                return j
            keys = [k.strip() for k in s[a[0]:a[1]].split(",") if k.strip()]
            if base == "nocite":
                return a[2]
            out.append(self.cite(base, keys))
            return a[2]
        if base in ("ref", "eqref", "autoref", "Autoref", "cref", "Cref", "pageref", "nameref", "vref", "Vref", "crefrange", "Crefrange"):
            a = self.arg(j, b)
            if not a:
                return j
            keys = [k.strip() for k in s[a[0]:a[1]].split(",") if k.strip()]
            nums = [self.aux.labels.get(k, "?") for k in keys]
            after = a[2]
            if base in ("crefrange", "Crefrange"):
                a2 = self.arg(after, b)
                if a2:
                    nums = [nums[0], self.aux.labels.get(s[a2[0]:a2[1]].strip(), "?")]
                    after = a2[2]
                txt = "–".join(nums)
            else:
                txt = ", ".join(nums)
            if base == "eqref":
                txt = f"({txt})"
            elif base in ("autoref", "Autoref", "cref", "Cref", "vref", "Vref", "crefrange", "Crefrange"):
                kind = _kind_of_label(keys[0]) if keys else ""
                nm = REFNAME[self.lang if self.lang in REFNAME else "en"].get(kind, "")
                if kind == "eq":
                    txt = f"{nm} ({txt})" if nm else f"({txt})"
                elif nm:
                    txt = f"{nm} {txt}" if self.lang == "en" or True else txt
            out.append(f'<span class="ref">{html.escape(txt)}</span>')
            return after
        if base == "href":
            a = self.arg(j, b)
            if not a:
                return j
            t = self.arg(a[2], b)
            if t:
                out.append(f'<span class="url">{self.conv(t[0], t[1])}</span>')
                return t[2]
            return a[2]
        if base in SIMPLE:
            out.append(SIMPLE[base] if SIMPLE[base].startswith("<") else html.escape(SIMPLE[base]))
            return j
        if base in ("begin", "end"):
            a = self.arg(j, b)
            if not a:
                return j
            env = s[a[0]:a[1]]
            k = a[2]
            if base == "begin":
                k = skip_args(s, k, groups=1 if env in ("tabular", "minipage", "tabularx", "array") else 0)
                if env in ("itemize", "enumerate", "description", "quote", "quotation", "center", "abstract"):
                    out.append("<br>")
            return k
        if base in WRAP:
            tag = WRAP[base]
            if base in ("textcolor", "colorbox"):
                a = self.arg(j, b)             # {color}{text}
                if a:
                    j = a[2]
            if base in ("raisebox", "resizebox", "scalebox", "makebox", "framebox"):
                a = self.arg(j, b)
                if a:
                    j = a[2]
                if base == "resizebox":
                    a = self.arg(j, b)
                    if a:
                        j = a[2]
            a = self.arg(j, b)
            if tag is None:
                return a[2] if a else skip_args(s, j, groups=0)
            if not a:
                if tag in ("b", "i", "code", "sc"):          # {\bf ...} style switch: the rest of the group
                    return j
                return j
            inner = self.conv(a[0], a[1])
            if tag == "":
                out.append(inner)
            elif tag == "fn":
                out.append(f'<span class="fn">{inner}</span>')
            elif tag == "sc":
                out.append(f'<span style="font-variant:small-caps">{inner}</span>')
            elif tag == "url":
                out.append(f'<span class="url">{inner}</span>')
            else:
                out.append(f"<{tag}>{inner}</{tag}>")
            return a[2]
        # unknown command: keep the text of its arguments
        a = self.arg(j, b)
        if a and base not in ("newcommand", "renewcommand", "def", "setlength", "addtolength", "setcounter", "hypersetup"):
            out.append(self.conv(a[0], a[1]))
            return a[2]
        if a:
            return skip_args(s, j)
        if base[:1].isupper() and len(base) <= 12 and base.isalpha():
            out.append(html.escape(base))                  # \ours, \Method style name macros: show the name
        return j

    def cite(self, base, keys):
        cs = [self.aux.cites.get(k) for k in keys]
        nums = [c["n"] if c else "?" for c in cs]
        authoryear = all(c and c.get("year") for c in cs) and any(not re.fullmatch(r"\d+", c["n"]) or c.get("author") for c in cs if c)
        if authoryear and base in ("citet", "Citet", "textcite", "citeauthor", "Citeauthor"):
            parts = [f"{c['author']} ({c['year']})" if base not in ("citeauthor", "Citeauthor") else c["author"] for c in cs]
            return f'<span class="cite">{html.escape("; ".join(parts))}</span>'
        if authoryear and base in ("citep", "Citep", "parencite", "cite", "autocite", "citealp", "citealt"):
            parts = [f"{c['author']}, {c['year']}" for c in cs]
            t = "; ".join(parts)
            return f'<span class="cite">{html.escape(t if base in ("citealp", "citealt") else "(" + t + ")")}</span>'
        if base in ("citeyear", "citeyearpar") and all(c and c.get("year") for c in cs):
            return f'<span class="cite">{html.escape(", ".join(c["year"] for c in cs))}</span>'
        return f'<span class="cite">[{html.escape(", ".join(nums))}]</span>'


def to_plain(src, aux=None):
    h = to_html(src, aux)
    h = re.sub(r'<span class="tex[^"]*">(.*?)</span>', lambda m: "$" + html.unescape(m.group(1)) + "$", h)
    h = re.sub(r"<br>", "\n", h)
    h = re.sub(r"<[^>]+>", "", h)
    return html.unescape(h).replace("\xa0", " ").strip()


TEXTY = {"textbf", "textit", "emph", "textsc", "textsf", "textrm", "text", "underline", "footnote", "thanks", "mbox", "hl", "textup",
         "textmd", "textnormal", "textsl", "uline", "caption", "paragraph", "section", "subsection", "subsubsection", "item", "noindent",
         "textcolor", "colorbox", "fbox", "parbox", "href"}


def has_words(src):
    """Does a span hold prose (not just layout commands, math and code)?"""
    s, out, i, n = src, [], 0, len(src)
    while i < n:
        c = s[i]
        if c == "$" or (c == "\\" and i + 1 < n and s[i + 1] in "(["):
            i = skip_math(s, i)
            out.append(" ")
            continue
        if c == "\\":
            name, j = read_cmd(s, i)
            base = name.rstrip("*")
            if base in TEXTY:
                if base in ("textcolor", "colorbox"):
                    j = skip_args(s, j, groups=1)
                i = j
                continue
            if base in ("begin", "end"):
                i = skip_args(s, j, groups=1, opts=0)
                continue
            i = skip_args(s, j)
            out.append(" ")
            continue
        out.append(c)
        i += 1
    t = "".join(out)
    return len(re.findall(r"[A-Za-z]{2,}", t)) >= 3 or len(re.findall(r"[A-Za-z]{5,}", t)) >= 1


# ------------------------------------------------------------------------------------------------ macros for KaTeX
def macros(preamble):
    """Simple \\newcommand / \\def / \\DeclareMathOperator definitions, for KaTeX in the reader."""
    out = {}
    s = preamble
    for m in re.finditer(r"\\(?:re)?newcommand\*?\s*\{?\\([A-Za-z@]+)\}?\s*(?:\[(\d)\])?\s*(?:\[[^\]]*\])?\s*\{", s):
        j = skip_group(s, m.end() - 1)
        body = s[m.end():j - 1]
        if len(body) < 400 and "\\@" not in body and "#" not in body.replace("#1", "").replace("#2", "").replace("#3", ""):
            out["\\" + m.group(1)] = body
    for m in re.finditer(r"\\def\s*\\([A-Za-z]+)\s*\{", s):
        j = skip_group(s, m.end() - 1)
        body = s[m.end():j - 1]
        if len(body) < 300 and "#" not in body:
            out.setdefault("\\" + m.group(1), body)
    for m in re.finditer(r"\\DeclareMathOperator\*?\s*\{?\\([A-Za-z]+)\}?\s*\{([^{}]*)\}", s):
        out["\\" + m.group(1)] = "\\operatorname{" + m.group(2) + "}"
    return out
