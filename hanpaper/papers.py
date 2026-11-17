"""Papers on disk and the background translation job.

DATA/papers/<id>/
  original.pdf      the English paper as imported
  doc.json          analysis (pages, units with bbox/style/src/ko, figures, tables)
  meta.json         title, status, progress, page revisions
  glossary.json     detected field + term list (editable)
  notes.json        handwritten notes and highlights per side
  chat.json         agent conversation
  ko/p<n>.pdf       Korean page n (one-page PDFs, merged on export)
  cache/            page PNGs and figure crops
"""
import hashlib
import html
import json
import os
import re
import shutil
import threading
import time
import uuid
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed

import pymupdf

import llm
import paths
import pdfcore
import settings
import sources


def jload(p, default=None):
    for k in range(20):
        try:
            with open(p, encoding="utf-8") as f:
                return json.load(f)
        except PermissionError:          # Windows: the file is being swapped in by a writer
            time.sleep(0.03)
        except (OSError, ValueError):
            return default
    return default


def jsave(p, data):
    tmp = f"{p}.{threading.get_ident()}.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)
    for k in range(40):                 # Windows: a reader holding the file open blocks the swap for a moment
        try:
            os.replace(tmp, p)
            return
        except PermissionError:
            if k == 39:
                raise
            time.sleep(0.05)


# ================================================================================================ prompts
TRANSLATE_SYSTEM = """당신은 {field} 분야의 영어 학술 논문을 한국어로 옮기는 전문 번역가다. 번역문은 원문 PDF의 같은 자리에 같은 글자 크기로 조판된다.

규칙
1. 빠짐없이 전부 번역한다. 요약·생략·덧붙임 금지. 영어 어순을 따르기보다 한국 학술 논문다운 자연스러운 문장(~한다, ~이다)으로 쓴다.
2. 용어는 한국의 {field} 학계·교과서·국내 논문에서 실제로 쓰는 말을 쓴다. 아래 용어집이 있으면 반드시 그대로 따른다. 국내 연구자들이 음차나 영어로 쓰는 용어(예: 트랜스포머, 어텐션, 임베딩, 오프로딩, 파인튜닝)는 억지로 우리말로 바꾸지 않고, 우리말로 굳어진 용어(예: 강화학습, 합성곱, 손실 함수, 표본)는 우리말로 쓴다.
3. 그대로 두는 것: 고유명사, 모델·데이터셋·도구 이름, 약어(GNN, MEC 등), 수식과 변수(q, T_i, η), 숫자와 단위, 인용 번호([12], [3]–[5]), URL, 코드, 사람 이름.
4. 인라인 태그 <b> <i> <sub> <sup>는 같은 대상에 그대로 남긴다(예: 변수 <i>q</i>, 아래첨자). 그 밖의 태그나 마크다운은 쓰지 않는다.
5. 제목·절 제목은 짧게 옮긴다: "I. INTRODUCTION"→"I. 서론", "Related Work"→"관련 연구", "Conclusion"→"결론", "Abstract"→"요약". 번호 체계는 유지한다.
6. 캡션 머리: "Fig. 3:"→"그림 3:", "Figure 3."→"그림 3.", "TABLE II"→"표 II", "Algorithm 1"→"알고리즘 1".
7. 표 셀(kind=table)은 원문보다 길지 않은 짧은 명사형으로. 기호·숫자뿐인 셀은 그대로 둔다.
8. 같은 공간에 들어가야 하므로 군더더기 없이 간결하게 쓴다.
9. 항목에 "continues"(다음 조각 id)나 "continued_from"(앞 조각 id)이 있으면, 한 문단이 단·쪽 경계에서 나뉜 것이다. 두 조각을 이어 하나의 문단으로 자연스럽게 번역한 다음, 원문 경계에 해당하는 곳에서 나누어 각 id에 담는다. 한국어 어순 때문에 정확히 같은 곳에서 끊을 수 없으면 가장 가까운 어절 경계에서 나눈다. 내용을 빠뜨리거나 겹치지 않는다. 그 밖에 문장 중간에서 시작·끝나는 항목은 앞뒤 문맥을 참고해 그 조각만 자연스럽게 옮긴다.
10. 저자 이름·소속처럼 번역할 필요가 없는 항목은 원문 그대로 돌려준다.

출력은 JSON 객체 하나뿐이다. 키는 항목 id, 값은 번역문. 설명, 코드펜스, 다른 글은 쓰지 않는다."""

SOURCE_SYSTEM = """당신은 {field} 분야의 영어 학술 논문을 한국어로 옮기는 전문 번역가다. 원고는 {fmt} 원본에서 뽑은 문단이고, 번역문은 원본에 다시 넣어 {engine} 그대로 조판한다. 그래서 그림·수식·표는 원본 그대로 남고, 글만 바뀐다.

규칙
1. 빠짐없이 전부 번역한다. 요약·생략·덧붙임 금지. 영어 어순보다 한국 학술 논문다운 자연스러운 문장(~한다, ~이다)으로 쓴다. 글자 수 제약은 없다.
2. 용어는 한국의 {field} 학계·교과서·국내 논문에서 실제로 쓰는 말을 쓴다. 아래 용어집이 있으면 반드시 그대로 따른다. 국내 연구자들이 음차나 영어로 쓰는 용어(예: 트랜스포머, 어텐션, 임베딩, 파인튜닝)는 억지로 우리말로 바꾸지 않고, 우리말로 굳어진 용어(예: 강화학습, 합성곱, 손실 함수)는 우리말로 쓴다.
3. ⟦1⟧ ⟦2⟧ 같은 자리표시는 수식·인용·참조 등 원본에서 그대로 둘 부분이다. 각 항목의 "keep"에 원래 내용이 있으니 뜻을 이해하는 데 쓰고, 번역문에는 자리표시를 각각 정확히 한 번씩, 문맥상 알맞은 자리에 그대로 쓴다. 자리표시를 풀어 쓰거나 빼거나 새로 만들지 않는다.
4. {markup}
5. 그대로 두는 것: 고유명사, 모델·데이터셋·도구 이름, 약어, 숫자와 단위, 사람 이름, 코드.
6. 제목·절 제목은 짧게 옮긴다("Introduction"→"서론", "Related Work"→"관련 연구", "Conclusion"→"결론"). 번호는 원본이 자동으로 붙이므로 따로 쓰지 않는다(원문에 있으면 유지).
7. 항목에 "continues"(다음 조각 id)나 "continued_from"(앞 조각 id)이 있으면, 한 문단이 사이에 낀 수식 때문에 나뉜 것이다. 이어지는 한 문단으로 자연스럽게 번역하되 각 조각은 제자리에 둔다(예: 수식 뒤 "where x is ..."는 "여기서 x는 ...이다.").
8. 저자 이름·소속처럼 번역할 필요가 없는 항목은 원문 그대로 돌려준다.

출력은 JSON 객체 하나뿐이다. 키는 항목 id, 값은 번역문. 설명, 코드펜스, 다른 글은 쓰지 않는다."""

TEX_MARKUP = ("LaTeX 명령(\\textbf{..}, \\emph{..}, \\textit{..}, \\footnote{..}, \\\\, ~ 등)은 그대로 두고 중괄호 안의 글만 번역한다. "
              "중괄호 짝을 맞춘다. 새 LaTeX 명령이나 마크다운을 만들지 않는다. %, &, #, _ 를 글자로 쓰려면 \\%, \\&, \\#, \\_ 로 쓴다.")
DOCX_MARKUP = "인라인 태그 <b> <i> <u> <sup> <sub>는 같은 대상에 그대로 남긴다. 그 밖의 태그나 마크다운은 쓰지 않는다."

GLOSSARY_SYSTEM = """당신은 영어 학술 논문의 한국어 번역을 위한 용어집을 만드는 편집자다. 논문의 분야를 판단하고, 그 분야 한국 학계·교과서·국내 학술지에서 실제로 통용되는 한국어 용어를 정한다.

- field: 이 논문의 분야를 한국어로 짧게(예: "엣지 컴퓨팅·심층 강화학습", "원격탐사·컴퓨터 비전", "호흡기내과·영상의학").
- terms: 번역에서 일관되게 써야 할 전문용어 40~90개. en은 원문 표기(소문자 기준, 약어는 대문자), ko는 한국어 표기.
  * 국내 연구자가 음차·영어로 쓰는 말은 그 표기를 따른다(attention→어텐션, embedding→임베딩, fine-tuning→파인튜닝).
  * 우리말로 굳은 말은 우리말로(reinforcement learning→강화학습, convolution→합성곱, loss function→손실 함수).
  * 약어는 정의 형태로: "mobile edge computing (MEC)" → "모바일 엣지 컴퓨팅(MEC)". 약어만 쓰일 때는 약어 그대로.
  * 일반 영어 단어(method, result 등)는 넣지 않는다.

출력은 JSON 객체 하나: {"field": "...", "terms": [{"en": "...", "ko": "..."}, ...]}. 다른 글은 쓰지 않는다."""

CHAT_SYSTEM = """당신은 한페이퍼(영-한 논문 번역 뷰어)의 논문 도우미다. 사용자는 아래 논문을 영어 원문과 한국어 번역으로 나란히 읽으며 한국어로 질문한다.

- 답은 한국어로, 핵심부터 간결하게 쓴다. 필요하면 짧은 목록과 **굵게**를 쓴다. 수식은 평문(예: T_i = D_i / B)으로 쓴다.
- 근거가 되는 문단을 [¶u12] 형식(아래 논문의 id)으로 문장 끝에 표시한다. 사용자는 이것을 눌러 PDF의 그 자리로 이동한다. 여러 개면 [¶u12][¶u30].
- 논문에 없는 내용은 논문에 없다고 밝히고, 일반 지식으로 보충할 때는 그렇다고 구분한다.{web}
- 용어는 논문 번역 용어집을 따른다.
- 사용자가 선택한 부분이 주어지면 그 부분에 대한 질문으로 이해한다.

[논문 분야] {field}
[용어집]
{glossary}

[논문 본문 — 읽는 순서, id|종류|쪽]
{paper}"""




# ================================================================================================ paper
class Paper:
    def __init__(self, pid):
        self.id = pid
        self.dir = os.path.join(paths.PAPERS, pid)
        self.lock = threading.RLock()
        self.render_lock = threading.Lock()
        self._doc = None
        self.job = None
        self._want_build = False
        self._builder = None
        self._last_build = 0

    # ---- files
    def f(self, *p):
        return os.path.join(self.dir, *p)

    @property
    def pdf(self):
        return self.f("original.pdf")

    @property
    def kind(self):
        if getattr(self, "_kind", None) is None:
            m = self.meta()
            if not m:
                return "pdf"
            self._kind = m.get("kind") or "pdf"
        return self._kind

    @property
    def is_src(self):
        return self.kind in ("tex", "docx")

    @property
    def ko_pdf(self):
        return self.f("ko.pdf")

    def meta(self):
        return jload(self.f("meta.json"), {})

    def set_meta(self, **kw):
        with self.lock:
            m = self.meta()
            m.update(kw)
            jsave(self.f("meta.json"), m)
            return m

    def doc(self):
        with self.lock:
            if self._doc is None:
                self._doc = jload(self.f("doc.json"))
            return self._doc

    def save_doc(self):
        with self.lock:
            if self._doc is not None:
                jsave(self.f("doc.json"), self._doc)

    def unit(self, uid):
        d = self.doc()
        return next((u for u in d["units"] if u["id"] == uid), None) if d else None

    def glossary(self):
        return jload(self.f("glossary.json"), {"field": "", "terms": []})

    def notes(self):
        return jload(self.f("notes.json"), {"marks": []})

    def save_notes(self, data):
        jsave(self.f("notes.json"), data)
        self.set_meta(notes_rev=time.time())

    def ko_page(self, n):
        return self.f("ko", f"p{n}.pdf")

    def page_rev(self, n):
        return (self.meta().get("page_rev") or {}).get(str(n), 0)

    def bump_page(self, n):
        with self.lock:
            m = self.meta()
            pr = m.setdefault("page_rev", {})
            pr[str(n)] = pr.get(str(n), 0) + 1
            m["rev"] = m.get("rev", 0) + 1
            jsave(self.f("meta.json"), m)

    # ---- summary for the library and the page
    def summary(self):
        m = self.meta()
        return {"id": self.id, "title": m.get("title") or m.get("file") or "제목 없음", "file": m.get("file"),
                "pages": m.get("pages"), "status": m.get("status"), "progress": m.get("progress"),
                "error": m.get("error"), "created": m.get("created"), "opened": m.get("opened"), "field": m.get("field")}

    PUB = ("id", "page", "kind", "translate", "bbox", "lines", "size", "text", "ko", "figure", "table", "err", "sans", "bold", "edited", "prev", "next", "geo", "level")

    def pub(self, u):
        """A unit as the page sees it: ko_html for the reader, ko as plain text."""
        out = {k: u.get(k) for k in self.PUB}
        if self.is_src:
            if u.get("kind") != "equation":
                out["en_html"] = sources.html(self, u, "en")
            if u.get("ko"):
                out["ko_html"] = sources.html(self, u, "ko")
                out["ko_src"] = u["ko"]
                out["ko"] = sources.plain_ko(self, u)
        elif u.get("ko"):
            out["ko_html"] = pdfcore._clean_ko(u["ko"])
            out["ko"] = pdfcore.plain(u["ko"])
        return out

    def state(self):
        d = self.doc() or {}
        m = self.meta()
        with self.lock:
            units = [self.pub(u) for u in d.get("units", [])]
        return {"id": self.id, "meta": m, "kind": self.kind, "pages": d.get("pages", []), "ko_pages": m.get("ko_pages") if self.is_src else None,
                "units": units, "figures": d.get("figures", []), "tables": d.get("tables", []), "equations": d.get("equations", []),
                "body_size": d.get("body_size", 10), "macros": d.get("macros") or {},
                "glossary": self.glossary(), "notes": self.notes(), "running": bool(self.job and self.job.alive())}

    # ---- page images
    def page_png(self, side, n, zoom):
        zoom = min(4.0, max(0.5, round(float(zoom) * 4) / 4))
        rev = self.page_rev(n) if side == "ko" else 0
        os.makedirs(self.f("cache"), exist_ok=True)
        out = self.f("cache", f"{side}_{n}_{zoom}_{rev}.png")
        if not os.path.exists(out):
            if side == "ko" and self.is_src:
                if not os.path.exists(self.ko_pdf):
                    raise ValueError("아직 한국어 PDF가 없습니다")
                src, pno = self.ko_pdf, n
            elif side == "ko" and os.path.exists(self.ko_page(n)):
                src, pno = self.ko_page(n), 0
            else:
                src, pno = self.pdf, n
            tmp = out + f".{threading.get_ident()}.png"
            pdfcore.page_png(src, pno, zoom, tmp)
            os.replace(tmp, out)
            for old in os.listdir(self.f("cache")):         # stale revisions of this page
                if old.startswith(f"{side}_{n}_") and not old.endswith(f"_{rev}.png") and side == "ko":
                    try:
                        os.remove(self.f("cache", old))
                    except OSError:
                        pass
        return out

    def fig_png(self, kind, i, side="en"):
        d = self.doc()
        item = (d["figures"] if kind == "fig" else d["tables"])[i]
        if item.get("media") and (not item.get("bbox") or self.kind == "docx"):
            out = self.media_png(item["media"][0])
            if out:
                return out
        n = item["page"]
        rev = self.page_rev(n) if side == "ko" else 0
        os.makedirs(self.f("cache"), exist_ok=True)
        key = hashlib.md5(json.dumps([n, [round(x, 1) for x in item["bbox"]]]).encode()).hexdigest()[:10]
        out = self.f("cache", f"{kind}{i}_{side}_{rev}_{key}.png")
        if not os.path.exists(out):
            ko = side == "ko" and os.path.exists(self.ko_page(n))
            pdfcore.crop_png(self.ko_page(n) if ko else self.pdf, 0 if ko else n, item["bbox"], out)
        return out

    def media_png(self, name):
        """A picture from the .docx itself, as PNG (None if it is a format we cannot draw, e.g. EMF)."""
        import zipfile
        os.makedirs(self.f("cache"), exist_ok=True)
        out = self.f("cache", "media_" + hashlib.md5(name.encode()).hexdigest()[:12] + ".png")
        if os.path.exists(out):
            return out
        try:
            with zipfile.ZipFile(self.f("source.docx")) as z:
                blob = z.read(name)
            ext = os.path.splitext(name)[1].lower().lstrip(".")
            with pymupdf.open(stream=blob, filetype=ext) as im:
                pix = im[0].get_pixmap(dpi=144) if ext in ("svg",) else pymupdf.Pixmap(blob)
                if pix.alpha and ext not in ("png",):
                    pix = pymupdf.Pixmap(pix, 0)
                pix.save(out)
            return out
        except Exception:  # noqa: BLE001
            return None

    def crop_png(self, side, n, r):
        rev = self.page_rev(n) if side == "ko" else 0
        os.makedirs(self.f("cache"), exist_ok=True)
        key = hashlib.md5(json.dumps([side, n, [round(x, 1) for x in r], rev]).encode()).hexdigest()[:16]
        out = self.f("cache", f"crop_{key}.png")
        if not os.path.exists(out):
            ko = side == "ko" and os.path.exists(self.ko_page(n))
            pdfcore.crop_png(self.ko_page(n) if ko else self.pdf, 0 if ko else n, r, out, zoom=3)
        return out

    # ---- rendering
    def render(self, n):
        if self.is_src:                     # source papers: the whole Korean PDF is rebuilt (soon, coalesced)
            self.build_soon()
            return
        d = self.doc()
        with self.render_lock:
            os.makedirs(self.f("ko"), exist_ok=True)
            tmp = self.ko_page(n) + ".tmp.pdf"
            with self.lock:
                units = [dict(u) for u in d["units"] if u["page"] == n]
            obst = [f["bbox"] for f in d.get("figures", []) if f["page"] == n] + \
                   [e["bbox"] for e in d.get("equations", []) if e["page"] == n] + [t["bbox"] for t in d.get("tables", []) if t["page"] == n]
            fit = pdfcore.render_page(self.pdf, n, units, tmp, obst)
            os.replace(tmp, self.ko_page(n))
            with self.lock:
                for u in d["units"]:
                    if u["id"] in fit:
                        u["fit"] = fit[u["id"]]
            self.bump_page(n)

    def build_soon(self, delay=1.0):
        with self.lock:
            self._want_build = True
            if self._builder and self._builder.is_alive():
                return
            self._builder = threading.Thread(target=self._build_loop, args=(delay,), daemon=True)
            self._builder.start()

    def _build_loop(self, delay):
        time.sleep(delay)
        while True:
            with self.lock:
                if not self._want_build:
                    return
                self._want_build = False
            try:
                self.build_ko()
            except Exception as ex:  # noqa: BLE001
                import traceback
                traceback.print_exc()
                self.set_meta(build_error=str(ex)[:300])

    def building(self):
        return bool(self._builder and self._builder.is_alive())

    def build_ko(self, report=None):
        """Make the Korean PDF from the translated source (LaTeX / docx) and map units onto it."""
        with self.render_lock:
            self._last_build = time.time()
            pages = sources.build(self, report or (lambda msg: None))
            self.save_doc()
            with self.lock:
                m = self.meta()
                kr = m.get("ko_rev", 0) + 1
                m.update(ko_pages=pages, ko_rev=kr, page_rev={str(i): kr for i in range(len(pages))}, rev=m.get("rev", 0) + 1, build_error=None)
                jsave(self.f("meta.json"), m)

    def page_done(self, n):
        d = self.doc()
        return all(u.get("ko") or u.get("err") for u in d["units"] if u["page"] == n and u["translate"])


_papers = {}
_plock = threading.Lock()


def get(pid):
    if not re.fullmatch(r"[0-9a-f]{12}", pid or ""):
        return None
    with _plock:
        if pid not in _papers:
            if not os.path.isdir(os.path.join(paths.PAPERS, pid)):
                return None
            _papers[pid] = Paper(pid)
        return _papers[pid]


def library():
    out = []
    for pid in os.listdir(paths.PAPERS):
        p = get(pid)
        if p and os.path.exists(p.f("meta.json")):
            out.append(p.summary())
    out.sort(key=lambda s: s.get("opened") or s.get("created") or 0, reverse=True)
    return out


def import_file(data, name):
    """A PDF, a LaTeX source archive (.zip/.tar.gz/.tex) or a Word .docx."""
    kind = sources.detect(data, name)
    if kind == "pdf":
        return import_pdf(data, name)
    if kind is None:
        raise ValueError("PDF, LaTeX 소스(.zip·.tar.gz·.tex), Word(.docx) 파일만 열 수 있습니다")
    h = hashlib.sha1(data).hexdigest()[:12]
    p = get(h)
    if p is None:
        d = os.path.join(paths.PAPERS, h)
        os.makedirs(d, exist_ok=True)
        try:
            if kind == "tex":
                import texsrc
                texsrc.unpack(data, name, os.path.join(d, "src"))
            else:
                with open(os.path.join(d, "source.docx"), "wb") as f:
                    f.write(data)
        except Exception as ex:  # noqa: BLE001
            shutil.rmtree(d, ignore_errors=True)
            raise ValueError(f"파일을 풀 수 없습니다: {ex}")
        p = get(h)
        p.set_meta(id=h, file=name, kind=kind, title="", pages=None, created=time.time(), status="queued",
                   progress={"done": 0, "total": 0}, page_rev={}, rev=0)
    start(p)
    return p


def import_pdf(data, name):
    """Copy a PDF in (bytes), start its translation. Same file again -> the existing paper."""
    h = hashlib.sha1(data).hexdigest()[:12]
    p = get(h)
    if p is None:
        d = os.path.join(paths.PAPERS, h)
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "original.pdf"), "wb") as f:
            f.write(data)
        p = get(h)
        try:
            doc = pymupdf.open(p.pdf)
            n = doc.page_count
            title = (doc.metadata or {}).get("title") or ""
            if doc.needs_pass:
                raise ValueError("암호가 걸린 PDF입니다")
            doc.close()
        except Exception as ex:  # noqa: BLE001
            shutil.rmtree(d, ignore_errors=True)
            with _plock:
                _papers.pop(h, None)
            raise ValueError(f"PDF를 열 수 없습니다: {ex}")
        p.set_meta(id=h, file=name, title=title if len(title) > 8 else "", pages=n, created=time.time(), status="queued",
                   progress={"done": 0, "total": 0}, page_rev={}, rev=0)
    start(p)
    return p


def delete(pid):
    p = get(pid)
    if not p:
        return False
    if p.job:
        p.job.stop.set()
    with _plock:
        _papers.pop(pid, None)
    shutil.rmtree(p.dir, ignore_errors=True)
    return True


def start(p, force=False):
    if p.job and p.job.alive():
        return False
    if p.meta().get("status") == "done" and not force:
        return False
    p.job = Job(p)
    p.job.start()
    return True


# ================================================================================================ the job
class Job:
    def __init__(self, paper):
        self.p = paper
        self.stop = threading.Event()
        self.thread = None

    def alive(self):
        return bool(self.thread and self.thread.is_alive())

    def start(self):
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        p = self.p
        try:
            if not os.path.exists(p.f("doc.json")):
                p.set_meta(status="analyzing", error=None, step=None)
                if p.is_src:
                    d = sources.prepare(p, lambda msg: p.set_meta(step=msg))
                    p.set_meta(pages=len(d["pages"]), step=None)
                else:
                    d = pdfcore.analyze(p.pdf)
                st = settings.get()
                for u in d["units"]:
                    if u["kind"] == "table" and not st.get("translate_tables", True):
                        u["translate"] = False
                    if u["kind"] == "ref" and st.get("translate_refs"):
                        u["translate"] = True
                with p.lock:
                    p._doc = d
                p.save_doc()
                m = p.meta()
                if not m.get("title"):
                    t = next((u["text"] for u in d["units"] if u["kind"] == "title"), "") or \
                        max((u for u in d["units"] if u["page"] == 0), key=lambda u: u.get("size") or 0, default={}).get("text", "")
                    p.set_meta(title=t[:200])
            d = p.doc()
            if not jload(p.f("glossary.json")):
                p.set_meta(status="glossary", error=None)
                self._glossary(d)
            self._translate_all()
        except llm.LLMError as ex:
            p.set_meta(status="error", error=str(ex), step=None)
        except (ValueError, RuntimeError) as ex:
            p.set_meta(status="error", error=str(ex), step=None)
        except Exception as ex:  # noqa: BLE001
            import traceback
            traceback.print_exc()
            p.set_meta(status="error", error=f"{type(ex).__name__}: {ex}", step=None)

    # ---- glossary
    def _glossary(self, d):
        p = self.p
        units = d["units"]
        title = p.meta().get("title") or ""
        abstract = next((u["text"] for u in units if re.match(r"\s*abstract", u["text"], re.I)), "")
        if not abstract:
            paras = [u["text"] for u in units if u["kind"] == "para"]
            abstract = " ".join(paras[:2])
        heads = [u["text"] for u in units if u["kind"] == "heading"][:40]
        cands = candidate_terms([u["text"] for u in units if u["translate"]])
        user = (f"[제목]\n{title}\n\n[초록]\n{abstract[:3000]}\n\n[절 제목]\n" + "\n".join(heads) +
                "\n\n[자주 나오는 표현(빈도)]\n" + "\n".join(f"{t} ({n})" for t, n in cands))
        st = settings.get()
        try:
            r = llm.parse_json(llm.complete(GLOSSARY_SYSTEM, user, "translate", st.get("effort_translate") or "low"))
        except llm.LLMError as ex:
            if "해석" not in str(ex):
                raise
            r = {"field": "", "terms": []}
        terms = [t for t in r.get("terms", []) if isinstance(t, dict) and t.get("en") and t.get("ko")]
        g = {"field": str(r.get("field") or "")[:80], "terms": terms, "auto": True}
        jsave(p.f("glossary.json"), g)
        p.set_meta(field=g["field"])

    # ---- translation
    def _translate_all(self, only=None, extra=None):
        p = self.p
        d = p.doc()
        st = settings.get()
        todo = [u for u in d["units"] if u["translate"] and (only is not None and u["id"] in only or only is None and not u.get("ko"))]
        total = sum(1 for u in d["units"] if u["translate"])
        done = total - len(todo) if only is None else total - len(todo)
        p.set_meta(status="translating", error=None, progress={"done": done, "total": total})
        pages_left = sorted({u["page"] for u in d["units"]}) if only is None else sorted({u["page"] for u in todo})
        # pages with nothing to translate are ready at once
        for n in list(pages_left) if not p.is_src else ():
            if only is None and p.page_done(n) and not os.path.exists(p.ko_page(n)):
                p.render(n)
        batches = make_batches(d["units"], todo)
        ctx = {}
        flow = [u for u in d["units"] if u["kind"] in ("para", "note", "heading", "caption", "title")]
        fidx = {u["id"]: i for i, u in enumerate(flow)}
        for b in batches:                             # what comes right before and after the batch, for context
            i0, i1 = fidx.get(b[0]["id"]), fidx.get(b[-1]["id"])
            ctx[id(b)] = (flow[i0 - 1]["text"] if i0 else "", flow[i1 + 1]["text"] if i1 is not None and i1 + 1 < len(flow) else "")
        rendered, processed = set(), set()
        failures = 0
        src = p.is_src
        with ThreadPoolExecutor(max_workers=max(1, min(6, int(st.get("workers") or 3)))) as ex:
            futs = {ex.submit(self._batch, b, ctx[id(b)], extra): b for b in batches}
            for fut in as_completed(futs):
                if self.stop.is_set():
                    break
                b = futs[fut]
                try:
                    res = fut.result()
                except llm.LLMError as e:
                    failures += 1
                    res = {}
                    with p.lock:
                        for u in b:
                            u["err"] = str(e)[:200]
                    if failures >= 3 and failures >= len(batches) // 2:
                        self.stop.set()
                        p.set_meta(status="error", error=str(e))
                        break
                with p.lock:
                    for u in b:
                        if u["id"] in res:
                            u["ko"] = res[u["id"]]
                            u.pop("err", None)
                    done += sum(1 for u in b if u["id"] in res)
                p.save_doc()
                p.set_meta(progress={"done": done, "total": total})
                processed.add(fut)
                if src:                                   # a fresh Korean PDF now and then while translating
                    gap = 25 if not os.path.exists(p.ko_pdf) else 75
                    if time.time() - p._last_build > gap and not p.building() and len(processed) < len(futs):
                        p._last_build = time.time()
                        p.build_soon(0)
                    continue
                for n in sorted({u["page"] for u in b}):
                    if n not in rendered and self._ready(n, futs, processed):
                        p.render(n)
                        rendered.add(n)
        if self.stop.is_set() and p.meta().get("status") == "error":
            return
        if src:
            p.set_meta(status="building", step="한국어 PDF를 조판하는 중…")
            while p.building():
                time.sleep(0.5)
            p.build_ko(lambda msg: p.set_meta(step=msg))
            p.set_meta(step=None)
        for n in pages_left if not src else ():       # anything left (errors) still gets a page
            if n not in rendered:
                p.render(n)
        errs = sum(1 for u in d["units"] if u["translate"] and not u.get("ko"))
        p.set_meta(status="done", error=(f"{errs}개 문단을 번역하지 못해 원문으로 두었습니다. 문단에서 '다시 번역'을 눌러 보세요." if errs else None),
                   finished=time.time())

    def _ready(self, n, futs, processed):
        """Page n is ready when every batch holding one of its units has been processed (its results stored).
        (A batch can be finished but not yet stored: as_completed hands them over one at a time.)"""
        return all(f in processed for f, b in futs.items() if any(u["page"] == n for u in b))

    def _batch(self, units, context=("", ""), extra=None):
        if self.stop.is_set():
            return {}
        p = self.p
        g = p.glossary()
        st = settings.get()
        items, masks = [], {}
        for u in units:
            if p.is_src:
                m, keep = sources.masked(p, u)
                masks[u["id"]] = (m, keep)
                it = {"id": u["id"], "kind": u["kind"], "src": m}
                if keep:
                    it["keep"] = keep
            else:
                it = {"id": u["id"], "kind": u["kind"], "src": u["src"]}
            if u.get("next"):
                it["continues"] = u["next"]
            if u.get("prev"):
                it["continued_from"] = u["prev"]
            items.append(it)
        prev, nxt = context if isinstance(context, tuple) else (context, "")
        gl = "\n".join(f"- {t['en']} → {t['ko']}" for t in g.get("terms", [])) or "(없음)"
        user = (f"[논문 제목] {p.meta().get('title', '')}\n[분야] {g.get('field') or '미상'}\n[용어집]\n{gl}\n\n"
                f"[바로 앞 문맥(참고만, 번역하지 않음)]\n{prev[:700]}\n\n[바로 뒤 문맥(참고만, 번역하지 않음)]\n{nxt[:500]}\n\n")
        if extra:
            user += f"[사용자 요청]\n{extra}\n\n"
        user += "[번역할 항목]\n" + json.dumps(items, ensure_ascii=False)
        if p.is_src:
            tex = p.kind == "tex"
            system = SOURCE_SYSTEM.format(field=g.get("field") or "해당", fmt="LaTeX" if tex else "Word(.docx)",
                                          engine="TeX으로" if tex else "Word로", markup=TEX_MARKUP if tex else DOCX_MARKUP)
        else:
            system = TRANSLATE_SYSTEM.format(field=g.get("field") or "해당")
        out, probs = {}, {}
        for attempt in range(2):
            try:
                r = llm.parse_json(llm.complete(system, user, "translate", st.get("effort_translate") or "low"))
            except llm.LLMError as ex:
                if attempt or "해석" not in str(ex):
                    raise
                continue
            if isinstance(r, list):
                r = {x.get("id"): x.get("ko") or x.get("text") for x in r if isinstance(x, dict)}
            for u in units:
                v = r.get(u["id"])
                if not (isinstance(v, str) and v.strip()) or u["id"] in out:
                    continue
                v = v.strip()
                if p.is_src:
                    m, keep = masks[u["id"]]
                    val, prob = sources.accept(p, u, v, m, keep)
                    if prob:
                        probs[u["id"]] = prob
                        continue
                    probs.pop(u["id"], None)
                    v = val
                out[u["id"]] = v
            missing = [x for x in items if x["id"] not in out]
            if not missing:
                break
            for x in missing:
                if x["id"] in probs:
                    x["problem_last_time"] = probs[x["id"]]
            user = user.rsplit("[번역할 항목]", 1)[0] + "[번역할 항목]\n" + json.dumps(missing, ensure_ascii=False)
        return out


def make_batches(all_units, todo, cap=3800, max_items=45):
    out, cur, n = [], [], 0
    for u in todo:
        size = len(u["src"]) + 40
        linked = bool(cur) and cur[-1].get("next") == u["id"]       # never split a paragraph cut by a page/column break
        if cur and not linked and (n + size > cap or len(cur) >= max_items or (u["page"] != cur[-1]["page"] and n > cap * 0.6)):
            out.append(cur)
            cur, n = [], 0
        cur.append(u)
        n += size
    if cur:
        out.append(cur)
    return out


STOP = set("""a an the of and or in on for to with by from at as is are was were be been being this that these those it its we our
their they them which who whom whose than then such can could may might will would should must not no also into over under between
each both all any some more most other only same so very via using used use based however thus therefore while where when what how
one two three first second new proposed paper method results show shown table fig figure section approach different given""".split())


def candidate_terms(texts, top=150):
    c = Counter()
    for t in texts:
        words = re.findall(r"[A-Za-z][A-Za-z\-]+", t)
        low = [w.lower() for w in words]
        for n in (2, 3):
            for i in range(len(low) - n + 1):
                g = low[i:i + n]
                if g[0] in STOP or g[-1] in STOP or any(len(w) < 3 for w in g):
                    continue
                c[" ".join(g)] += 1
        for m in re.finditer(r"((?:[A-Z][a-z]+[\s-]){1,5}[A-Z]?[a-z]*)\s*\(([A-Z][A-Za-z0-9]{1,9})\)", t):
            c[f"{m.group(1).strip()} ({m.group(2)})"] += 5
        for w in low:
            if w not in STOP and len(w) > 6:
                c[w] += 0.3
    return [(t, round(n)) for t, n in c.most_common(top) if n >= 2]


# ================================================================================================ edits
def retranslate(p, uid, instruction=""):
    u = p.unit(uid)
    if not u:
        raise ValueError("문단을 찾을 수 없습니다")
    job = Job(p)
    extra = (f"이 항목의 현재 번역: {u.get('ko') or '(없음)'}\n요청: {instruction}" if instruction else None)
    # a paragraph cut by a page/column break is re-translated together with its other piece
    group = [x for x in (p.unit(u["prev"]) if u.get("prev") else None, u, p.unit(u["next"]) if u.get("next") else None) if x]
    res = job._batch(group, ("", ""), extra)
    if uid not in res:
        raise llm.LLMError("번역 결과를 받지 못했습니다")
    with p.lock:
        for x in group:
            if x["id"] in res and (x is u or not x.get("edited")):
                x["ko"] = res[x["id"]]
                x.pop("err", None)
        u["translate"] = True
    p.save_doc()
    for n in sorted({x["page"] for x in group}):
        p.render(n)
    return u


def set_translation(p, uid, ko):
    u = p.unit(uid)
    if not u:
        raise ValueError("문단을 찾을 수 없습니다")
    with p.lock:
        u["ko"] = ko if p.kind == "tex" else (html.escape(ko, quote=False) if "<" not in ko else ko)
        u["translate"] = True
        u["edited"] = True
        u.pop("err", None)
    p.save_doc()
    p.render(u["page"])
    return u


def toggle_translate(p, uid, on):
    u = p.unit(uid)
    with p.lock:
        u["translate"] = bool(on)
    p.save_doc()
    if on and not u.get("ko"):
        return retranslate(p, uid)
    p.render(u["page"])
    return u


def apply_glossary(p, terms, field=None):
    old = {t["en"].lower(): t["ko"] for t in p.glossary().get("terms", [])}
    g = p.glossary()
    g["terms"] = [t for t in terms if t.get("en") and t.get("ko")]
    if field is not None:
        g["field"] = field
    g["auto"] = False
    jsave(p.f("glossary.json"), g)
    changed = [t["en"].lower() for t in g["terms"] if old.get(t["en"].lower()) != t["ko"]]
    return changed


def retranslate_terms(p, ens):
    """Re-translate (in the background) every unit whose English contains one of the changed terms."""
    d = p.doc()
    ids = {u["id"] for u in d["units"] if u["translate"] and not u.get("edited") and any(e in u["text"].lower() for e in ens)}
    if not ids or (p.job and p.job.alive()):
        return 0
    job = Job(p)
    p.job = job
    job.thread = threading.Thread(target=lambda: _safe(job, lambda: job._translate_all(only=ids)), daemon=True)
    job.thread.start()
    return len(ids)


def _safe(job, fn):
    try:
        fn()
    except Exception as ex:  # noqa: BLE001
        job.p.set_meta(status="error", error=str(ex))


# ================================================================================================ export
def export(p, kind, out_path, with_marks=True):
    """kind: ko (Korean paper), en (English original), side (English | Korean on one wide page). Highlights optional.
    Source papers also: src (the translated LaTeX as .zip / the Korean .docx)."""
    if p.is_src:
        return export_src(p, kind, out_path, with_marks)
    d = p.doc()
    marks = p.notes().get("marks", []) if with_marks else []
    n = len(d["pages"])
    out = pymupdf.open()
    src_en = pymupdf.open(p.pdf)
    if kind in ("ko", "en"):
        for i in range(n):
            if kind == "ko" and os.path.exists(p.ko_page(i)):
                with pymupdf.open(p.ko_page(i)) as k:
                    out.insert_pdf(k)
            else:
                out.insert_pdf(src_en, from_page=i, to_page=i)
            _marks(out[-1], p, marks, kind, i, 0)
    else:
        for i in range(n):
            W, H = d["pages"][i]["w"], d["pages"][i]["h"]
            page = out.new_page(width=W * 2 + 18, height=H)
            page.show_pdf_page(pymupdf.Rect(0, 0, W, H), src_en, i)
            if os.path.exists(p.ko_page(i)):
                with pymupdf.open(p.ko_page(i)) as k:
                    page.show_pdf_page(pymupdf.Rect(W + 18, 0, W * 2 + 18, H), k, 0)
            page.draw_line((W + 9, 20), (W + 9, H - 20), color=(0.8, 0.8, 0.8), width=0.6)
            _marks(page, p, marks, "en", i, 0)
            _marks(page, p, marks, "ko", i, W + 18)
    src_en.close()
    out.subset_fonts()
    out.save(out_path, garbage=3, deflate=True)
    out.close()
    return out_path


def export_src(p, kind, out_path, with_marks):
    if kind == "src":
        return sources.export_source(p, out_path)
    if not os.path.exists(p.ko_pdf) and kind != "en":
        raise ValueError("아직 한국어 PDF가 없습니다")
    marks = p.notes().get("marks", []) if with_marks else []
    out = pymupdf.open()
    en = pymupdf.open(p.pdf)
    ko = pymupdf.open(p.ko_pdf) if os.path.exists(p.ko_pdf) else None
    if kind in ("ko", "en"):
        out.insert_pdf(ko if kind == "ko" else en)
        for i in range(out.page_count):
            _marks_geo(out[i], p, marks, kind, i, 0)
    else:
        n = max(en.page_count, ko.page_count)
        for i in range(n):
            a = en[i] if i < en.page_count else None
            b = ko[i] if i < ko.page_count else None
            W = max((x.rect.width for x in (a, b) if x is not None), default=612)
            H = max((x.rect.height for x in (a, b) if x is not None), default=792)
            page = out.new_page(width=W * 2 + 18, height=H)
            if a is not None:
                page.show_pdf_page(pymupdf.Rect(0, 0, a.rect.width, a.rect.height), en, i)
                _marks_geo(page, p, marks, "en", i, 0)
            if b is not None:
                page.show_pdf_page(pymupdf.Rect(W + 18, 0, W + 18 + b.rect.width, b.rect.height), ko, i)
                _marks_geo(page, p, marks, "ko", i, W + 18)
            page.draw_line((W + 9, 20), (W + 9, H - 20), color=(0.8, 0.8, 0.8), width=0.6)
    en.close()
    if ko:
        ko.close()
    out.save(out_path, garbage=3, deflate=True)
    out.close()
    return out_path


def _marks_geo(page, p, marks, side, i, dx):
    for m in marks:
        u = p.unit(m.get("unit")) if m.get("unit") else None
        if not u:
            continue
        for r in (u.get("geo") or {}).get(side, []):
            if r[0] != i:
                continue
            a = page.add_rect_annot(pymupdf.Rect(r[1] + dx, r[2] - 0.5, r[3] + dx, r[4] + 0.5))
            a.set_colors(stroke=None, fill=_rgb(m.get("color") or "#ffd43b"))
            a.set_opacity(0.33)
            a.set_border(width=0)
            a.update()


def _marks(page, p, marks, side, i, dx):
    """Highlighter marks as translucent boxes (English: the paragraph's lines, Korean: its box)."""
    for m in marks:
        u = p.unit(m.get("unit")) if m.get("unit") else None
        if not u or u["page"] != i:
            continue
        rects = u["lines"] if side == "en" or not u.get("ko") else [u["bbox"]]
        for r in rects:
            r = pymupdf.Rect(r[0] + dx, r[1] - 0.5, r[2] + dx, r[3] + 0.5)
            a = page.add_rect_annot(r)
            a.set_colors(stroke=None, fill=_rgb(m.get("color") or "#ffd43b"))
            a.set_opacity(0.33)
            a.set_border(width=0)
            a.update()


def _rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[k:k + 2], 16) / 255 for k in (0, 2, 4))


def new_id():
    return uuid.uuid4().hex[:10]
