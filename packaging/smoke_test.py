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
