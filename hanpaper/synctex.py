"""Minimal SyncTeX reader: input line -> boxes on the PDF pages (PDF points, top-left origin).

Only what the app needs: for every line of one input file, the line boxes (hboxes) that hold material from that line.
"""
import gzip
import os
import re
from collections import defaultdict

_REC = re.compile(r"^([\[\(hvxkg$])(\d+),(\d+):(-?\d+),(-?\d+)(?::(-?\d+)(?:,(-?\d+),(-?\d+))?)?")


class SyncTex:
    def __init__(self, path):
        self.lines = defaultdict(list)          # (tag, line) -> [(page, x0, y0, x1, y1)]  line boxes holding that line
        self.boxes = defaultdict(list)          # (tag, line) -> boxes (h and v) whose own record names that line
        self.inputs = {}                        # tag -> path
        op = gzip.open if path.endswith(".gz") else open
        with op(path, "rt", encoding="utf-8", errors="replace") as f:
            data = f.read()
        self._parse(data)

    def tag_for(self, filename):
        base = os.path.basename(filename).lower()
        for t, p in self.inputs.items():
            if os.path.basename(p.replace("\\", "/")).lower() == base:
                return t
        return None

    def _parse(self, data):
        unit, xoff, yoff, mag = 1, 0, 0, 1000
        page = -1
        stack = []                              # open boxes: [kind, rect or None, set of keys]
        k = 72 / 72.27 / 65536
        content = False
        for raw in data.splitlines():
            if not content:
                if raw.startswith("Input:"):
                    _, t, p = raw.split(":", 2)
                    self.inputs[int(t)] = p
                elif raw.startswith("Unit:"):
                    unit = int(raw[5:])
                elif raw.startswith("X Offset:"):
                    xoff = int(raw[9:])
                elif raw.startswith("Y Offset:"):
                    yoff = int(raw[9:])
                elif raw.startswith("Magnification:"):
                    mag = int(raw[14:])
                elif raw.startswith("Content:"):
                    content = True
                    k = unit * mag / 1000 * 72 / 72.27 / 65536
                continue
            if not raw:
                continue
            c = raw[0]
            if c == "{":
                page = int(raw[1:]) - 1
                stack = []
                continue
            if c == "}":
                stack = []
                continue
            if c in ")]":
                if stack:
                    kind, rect, keys, own = stack.pop()
                    if kind == "(" and rect:
                        for key in keys:
                            self.lines[key].append((page,) + rect)
                    if rect:
                        self.boxes[own].append((page,) + rect)
                continue
            if raw.startswith("Input:"):
                _, t, p = raw.split(":", 2)
                self.inputs[int(t)] = p
                continue
            m = _REC.match(raw)
            if not m:
                continue
            kind, tag, line, x, y, w, h, d = m.groups()
            key = (int(tag), int(line))
            X, Y = (int(x) + xoff) * k, (int(y) + yoff) * k
            if kind in "[(":
                rect = None
                if w is not None and h is not None:
                    W, H, D = int(w) * k, int(h or 0) * k, int(d or 0) * k
                    rect = (X, Y - H, X + W, Y + D)
                keys = {key}
                stack.append([kind, rect, keys, key])
                continue
            # a node inside the innermost hbox: that box line belongs to this source line too
            hb = next((s for s in reversed(stack) if s[0] == "("), None)
            if hb is not None and hb[1] and (hb[1][2] - hb[1][0]) > 1:
                hb[2].add(key)
            elif kind in "hv" and w is not None:
                W, H, D = int(w) * k, int(h or 0) * k, int(d or 0) * k
                self.lines[key].append((page, X, Y - H, X + W, Y + D))
            if kind in "hv" and w is not None:
                W, H, D = int(w) * k, int(h or 0) * k, int(d or 0) * k
                self.boxes[key].append((page, X, Y - H, X + W, Y + D))

    def rects(self, tag, l0, l1):
        """Line boxes for input lines l0..l1 (inclusive), merged per visual line, in page order."""
        out = []
        for ln in range(l0, l1 + 1):
            out.extend(self.lines.get((tag, ln), ()))
        return merge(out)


def merge(rects):
    """Drop tiny and duplicate boxes; merge boxes on the same visual line that touch."""
    rs = {tuple(round(v, 2) for v in r) for r in rects if r[4] - r[2] > 1 and r[3] - r[1] > 1}
    out = []
    for r in sorted(rs, key=lambda r: (r[0], -(r[3] - r[1]), r[2])):      # wide boxes first, so small ones fold in
        for i, o in enumerate(out):
            if o[0] != r[0]:
                continue
            # same line: vertical overlap of most of the smaller height
            ov = min(o[4], r[4]) - max(o[2], r[2])
            if ov > 0.6 * min(o[4] - o[2], r[4] - r[2]) and (r[1] <= o[3] + 6 and r[3] >= o[1] - 6):
                out[i] = (o[0], min(o[1], r[1]), min(o[2], r[2]), max(o[3], r[3]), max(o[4], r[4]))
                break
            # contained box (a box inside a line box)
            if r[1] >= o[1] - 0.5 and r[3] <= o[3] + 0.5 and r[2] >= o[2] - 0.5 and r[4] <= o[4] + 0.5:
                break
        else:
            out.append(r)
    return sorted(out, key=lambda r: (r[0], r[2], r[1]))
