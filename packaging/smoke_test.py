"""CI smoke test without any AI: make a small two-column English PDF, analyze it, set fake Korean for every
translatable unit and re-typeset a page. Checks that the pipeline runs and that Korean text lands on the page."""
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "hanpaper"))
import pymupdf  # noqa: E402

import pdfcore  # noqa: E402

PARA = ("Deep reinforcement learning has been widely used for scheduling problems in edge computing, "
        "where tasks are offloaded to nearby servers to reduce latency and energy consumption. ")

tmp = tempfile.mkdtemp()
src = os.path.join(tmp, "in.pdf")
doc = pymupdf.open()
for n in range(2):
    pg = doc.new_page(width=612, height=792)
    if n == 0:
        pg.insert_textbox(pymupdf.Rect(72, 60, 540, 110), "A Smoke Test Paper for Layout-Preserving Translation", fontsize=20, align=1)
    pg.insert_text((560, 30), str(n + 1), fontsize=7)
    pg.insert_textbox(pymupdf.Rect(50, 130, 300, 420), "1 Introduction\n" + PARA * 4, fontsize=10)
    pg.insert_textbox(pymupdf.Rect(312, 130, 562, 420), PARA * 5, fontsize=10)
    pg.draw_rect(pymupdf.Rect(80, 450, 280, 600), color=(0, 0, 1), fill=(0.8, 0.85, 1))
    pg.draw_circle((180, 525), 40, color=(1, 0, 0))
    pg.insert_text((150, 528), "label", fontsize=7)
    pg.insert_textbox(pymupdf.Rect(50, 610, 300, 650), "Fig. %d: A simple figure used for testing." % (n + 1), fontsize=9)
doc.save(src)

a = pdfcore.analyze(src)
units = a["units"]
todo = [u for u in units if u["translate"]]
assert len(a["pages"]) == 2, "page count"
assert todo, "no translatable units"
assert any(u["kind"] == "caption" for u in units), "caption not found"
assert any(u["kind"] == "running" for u in units), "page number not detected"
for u in todo:
    u["ko"] = "한국어 번역 시험 문장입니다. " * max(1, len(u["text"]) // 40)
out = os.path.join(tmp, "ko0.pdf")
fit = pdfcore.render_page(src, 0, units, out, [f["bbox"] for f in a["figures"] if f["page"] == 0])
text = pymupdf.open(out)[0].get_text()
assert "한국어" in text, "Korean text missing from the rendered page"
assert "Deep reinforcement" not in text, "English text was not replaced"
assert min(fit.values()) > 0, "a unit could not be placed"
print(f"ok: {len(units)} units, {len(todo)} translated, figures={len(a['figures'])}, min scale={min(fit.values())}")

# ---- LaTeX sources: splitting, masking for the translator, rebuilding (no TeX engine needed)
import latex  # noqa: E402
import texsrc  # noqa: E402

TEX = r"""\documentclass{article}
\title{A Small Test}
\begin{document}
\maketitle
\begin{abstract}
We study $x_i$ under noise \cite{a} and show gains.
\end{abstract}
\section{Introduction}\label{sec:intro}
The loss is defined as
\begin{equation}
L = \sum_i (y_i - \hat y_i)^2
\end{equation}
where $y_i$ is the target, see Fig.~\ref{fig:a}.
\begin{figure}[t]\centering\includegraphics{a.png}\caption{An example figure.}\label{fig:a}\end{figure}
\begin{itemize}
\item First point with \textbf{bold} words.
\item Second point.
\end{itemize}
\end{document}
"""
sp = texsrc.Splitter(TEX).run()
kinds = [u["kind"] for u in sp.units]
assert kinds.count("title") == 1 and "heading" in kinds and "caption" in kinds and "equation" in kinds, kinds
assert sum(1 for u in sp.units if u.get("prev_i") is not None) == 1, "text after the equation should continue the paragraph"
para = next(TEX[u["a"]:u["b"]] for u in sp.units if u["kind"] == "para")
m, keep = latex.mask(para)
assert "$x_i$" not in m and len(keep) == 2, (m, keep)
ko = "우리는 잡음 아래에서 " + " ".join(keep) + " 를 연구하고 100% 이득을 보인다."
assert latex.check(m, keep, ko) is None
back = latex.unmask(ko, keep, m)
assert "$x_i$" in back and r"\cite{a}" in back and r"100\%" in back, back
assert latex.check(m, keep, "자리표시 없음") is not None
units = [dict(u, id=f"u{i}") for i, u in enumerate(sp.units)]
out, spans = texsrc.build_ko(TEX, units, lambda u: "그림 설명" if u["kind"] == "caption" else None)
assert r"\caption{그림 설명}" in out and r"\usepackage{kotex}" in out and all(isinstance(v, tuple) for v in spans.values())
assert "<b>bold</b>" in latex.to_html(r"with \textbf{bold} words")
print(f"ok: LaTeX {len(sp.units)} units, {len(sp.regions)} regions")
