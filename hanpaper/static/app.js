/* 한페이퍼 Hanpaper — English | Korean | Reader | Agent, all linked. */
"use strict";
const TOKEN = document.querySelector('meta[name="pb-token"]').content;
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
const store = {
  get(k, d) { try { const v = localStorage.getItem("pb." + k); return v == null ? d : JSON.parse(v); } catch (e) { return d; } },
  set(k, v) { try { localStorage.setItem("pb." + k, JSON.stringify(v)); } catch (e) { /* storage unavailable */ } },
};

function h(tag, attrs, ...kids) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === "class") e.className = v;
    else if (k === "html") e.innerHTML = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k === "style" && typeof v === "object") Object.assign(e.style, v);
    else e.setAttribute(k, v === true ? "" : v);
  }
  for (const c of kids.flat()) if (c != null && c !== false) e.append(c instanceof Node ? c : document.createTextNode(c));
  return e;
}

const I = {
  open: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  layout: '<rect x="3" y="4" width="18" height="16" rx="2"/><path d="M9 4v16M15 4v16"/>',
  save: '<path d="M12 4v11M7 10l5 5 5-5M5 20h14"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z"/>',
  grip: '<circle cx="9" cy="6" r="1"/><circle cx="15" cy="6" r="1"/><circle cx="9" cy="12" r="1"/><circle cx="15" cy="12" r="1"/><circle cx="9" cy="18" r="1"/><circle cx="15" cy="18" r="1"/>',
  minus: '<path d="M5 12h14"/>', plus: '<path d="M12 5v14M5 12h14"/>',
  fit: '<path d="M4 9V5h4M20 9V5h-4M4 15v4h4M20 15v4h-4"/>',
  collapse: '<path d="M15 6l-6 6 6 6"/>', expand: '<path d="M9 6l6 6-6 6"/>',
  link: '<path d="M10 13a5 5 0 0 0 7.5.5l3-3a5 5 0 0 0-7-7l-1.7 1.7"/><path d="M14 11a5 5 0 0 0-7.5-.5l-3 3a5 5 0 0 0 7 7l1.7-1.7"/>',
  pen: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
  hl: '<path d="M9 11l-6 6v3h3l6-6"/><path d="M22 6l-3-3-9 9 3 3z"/>',
  ask: '<path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/>',
  redo: '<path d="M21 12a9 9 0 1 1-3-6.7L21 8"/><path d="M21 3v5h-5"/>',
  edit: '<path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"/><path d="M18.5 2.5a2.1 2.1 0 0 1 3 3L12 15l-4 1 1-4z"/>',
  copy: '<rect x="9" y="9" width="12" height="12" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
  send: '<path d="M5 12h14M13 6l6 6-6 6"/>', stop: '<rect x="7" y="7" width="10" height="10" rx="1.5" fill="currentColor"/>',
  x: '<path d="M6 6l12 12M18 6L6 18"/>', trash: '<path d="M3 6h18M8 6V4h8v2M6 6l1 14h10l1-14"/>',
  search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>', up: '<path d="M6 15l6-6 6 6"/>', down: '<path d="M6 9l6 6 6-6"/>',
  file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5"/>',
  note: '<path d="M4 4h16v12l-4 4H4z"/><path d="M16 20v-4h4"/>', globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
  sparkle: '<path d="M12 3l1.8 5.2L19 10l-5.2 1.8L12 17l-1.8-5.2L5 10l5.2-1.8z"/>', clear: '<path d="M4 7h16M10 11v6M14 11v6M5 7l1 13h12l1-13M9 7V4h6v3"/>',
};
const ic = (n, cls = "i") => `<svg class="${cls}" viewBox="0 0 24 24">${I[n] || ""}</svg>`;
const icEl = n => h("span", { html: ic(n), style: { display: "inline-flex" } });

/* ------------------------------------------------------------------ api */
const api = {
  async get(u) { const r = await fetch(u); const j = await r.json(); if (!r.ok) throw new Error(j.error || r.status); return j; },
  async post(u, body) {
    const r = await fetch(u, { method: "POST", headers: { "Content-Type": "application/json", "X-PB-Token": TOKEN }, body: JSON.stringify(body || {}) });
    const j = await r.json().catch(() => ({})); if (!r.ok) throw new Error(j.error || ("오류 " + r.status)); return j;
  },
};
function toast(msg, kind, action) {
  const t = h("div", { class: "toast" + (kind === "err" ? " err" : "") }, msg);
  if (action) t.append(h("button", { onclick: () => { action.fn(); t.remove(); } }, action.label));
  $("#toast").append(t);
  setTimeout(() => t.remove(), kind === "err" ? 7000 : 3200);
}

/* ------------------------------------------------------------------ app state */
const app = {
  st: null, paper: null, units: new Map(), order: [], pid: null,
  sel: { ids: [], text: "", from: null, precise: {} },
  marks: [], pageRev: {}, rev: -1, status: null,
  sync: store.get("sync", true), readMode: store.get("readMode", "ko"), rfs: store.get("rfs", 14.5),
};

/* ================================================================== layout */
const PANES = { en: "원문 (English)", ko: "번역 (한국어)", reader: "읽기", chat: "질문" };
const DEFAULT_LAYOUT = { order: ["en", "ko", "reader", "chat"], w: { en: 1.2, ko: 1.2, reader: 1, chat: 0.82 }, collapsed: {}, stack: false, stackH: 0.58 };
const Layout = {
  L: Object.assign(structuredClone(DEFAULT_LAYOUT), store.get("layout", {})),
  panes: {},
  save() { store.set("layout", this.L); },
  columns() {
    const cols = [];
    for (const k of this.L.order) {
      if (this.L.stack && (k === "reader" || k === "chat")) {
        const c = cols.find(c => c.stack);
        if (c) continue;
        cols.push({ key: "stack", stack: true, panes: this.L.order.filter(x => x === "reader" || x === "chat") });
      } else cols.push({ key: k, panes: [k] });
    }
    return cols;
  },
  weight(col) { return col.stack ? (this.L.w.reader + this.L.w.chat) / 2 * 1.1 : this.L.w[col.key]; },
  isCollapsed(col) { return col.panes.every(p => this.L.collapsed[p]); },
  render() {
    const shell = $("#shell");
    const keep = {};
    for (const [k, p] of Object.entries(this.panes)) { const sc = p.querySelector(".viewer, .reader, .chatlog"); if (sc) keep[k] = [sc.scrollTop, sc.scrollLeft]; }
    shell.innerHTML = "";
    const cols = this.columns();
    cols.forEach((c, i) => {
      if (i) shell.append(this.gutter(cols[i - 1], c));
      const col = h("div", { class: "col" + (this.isCollapsed(c) && !c.stack ? " collapsed" : ""), "data-col": c.key });
      col.style.flex = `${this.weight(c)} 1 0`;
      if (c.stack && c.panes.every(p => this.L.collapsed[p])) col.classList.add("collapsed");
      c.panes.forEach((k, j) => {
        const p = this.panes[k];
        p.classList.toggle("collapsed", !!this.L.collapsed[k]);
        p.classList.toggle("instack", !!c.stack);
        if (c.stack) {
          const anyCol = c.panes.some(x => this.L.collapsed[x]);
          p.style.flex = this.L.collapsed[k] ? "0 0 42px" : anyCol ? "1 1 0" : (j === 0 ? `${this.L.stackH} 1 0` : `${1 - this.L.stackH} 1 0`);
          if (this.L.collapsed[k]) p.classList.remove("collapsed"), p.classList.add("mini");
          else p.classList.remove("mini");
        } else { p.style.flex = "1 1 0"; p.classList.remove("mini"); }
        if (j) col.append(this.hgutter(c));
        col.append(p);
      });
      shell.append(col);
    });
    for (const [k, v] of Object.entries(keep)) { const sc = this.panes[k].querySelector(".viewer, .reader, .chatlog"); if (sc) { sc.scrollTop = v[0]; sc.scrollLeft = v[1]; } }
    requestAnimationFrame(() => { Viewers.en?.layout(); Viewers.ko?.layout(); });
    this.save();
  },
  gutter(a, b) {
    const g = h("div", { class: "gutter" });
    g.addEventListener("pointerdown", e => {
      if (this.isCollapsed(a) || this.isCollapsed(b)) return;
      e.preventDefault(); g.setPointerCapture(e.pointerId); g.classList.add("on"); document.body.classList.add("col-resize");
      const ca = g.previousElementSibling, cb = g.nextElementSibling;
      const wa = ca.getBoundingClientRect().width, wb = cb.getBoundingClientRect().width;
      const sa = this.weight(a), sb = this.weight(b), x0 = e.clientX;
      const move = ev => {
        const dx = clamp(ev.clientX - x0, 240 - wa, wb - 240);
        const na = (sa + sb) * (wa + dx) / (wa + wb), nb = (sa + sb) - na;
        this.setW(a, na); this.setW(b, nb);
        ca.style.flex = `${na} 1 0`; cb.style.flex = `${nb} 1 0`;
        Viewers.en?.layout(); Viewers.ko?.layout();
      };
      const up = () => { g.classList.remove("on"); document.body.classList.remove("col-resize"); g.removeEventListener("pointermove", move); g.removeEventListener("pointerup", up); this.save(); };
      g.addEventListener("pointermove", move); g.addEventListener("pointerup", up);
    });
    return g;
  },
  setW(col, v) {
    if (col.stack) { const r = this.L.w.reader / (this.L.w.reader + this.L.w.chat); const t = v / 1.1 * 2; this.L.w.reader = t * r; this.L.w.chat = t * (1 - r); }
    else this.L.w[col.key] = v;
  },
  hgutter(c) {
    const g = h("div", { class: "hgutter" });
    g.addEventListener("pointerdown", e => {
      e.preventDefault(); g.setPointerCapture(e.pointerId); g.classList.add("on"); document.body.classList.add("row-resize");
      const col = g.parentElement, r = col.getBoundingClientRect();
      const [pa, pb] = [g.previousElementSibling, g.nextElementSibling];
      const move = ev => { const f = clamp((ev.clientY - r.top) / r.height, .15, .85); this.L.stackH = f; pa.style.flex = `${f} 1 0`; pb.style.flex = `${1 - f} 1 0`; };
      const up = () => { g.classList.remove("on"); document.body.classList.remove("row-resize"); g.removeEventListener("pointermove", move); g.removeEventListener("pointerup", up); this.save(); };
      g.addEventListener("pointermove", move); g.addEventListener("pointerup", up);
    });
    return g;
  },
  toggle(k, force) { this.L.collapsed[k] = force ?? !this.L.collapsed[k]; this.render(); },
  preset(name) {
    const P = {
      four: { order: ["en", "ko", "reader", "chat"], collapsed: {}, stack: false },
      three: { order: ["en", "ko", "reader", "chat"], collapsed: {}, stack: true },
      pair: { order: ["en", "ko", "reader", "chat"], collapsed: { reader: true, chat: true }, stack: false },
      study: { order: ["en", "ko", "reader", "chat"], collapsed: { en: true }, stack: false },
      read: { order: ["en", "ko", "reader", "chat"], collapsed: { en: true, ko: true }, stack: false },
    }[name];
    Object.assign(this.L, structuredClone(P));
    this.render();
  },
  reset() { this.L = structuredClone(DEFAULT_LAYOUT); this.render(); },
  /* reorder by dragging a pane's grip */
  startDrag(key, e) {
    const x0 = e.clientX, y0 = e.clientY; let started = false, ghost, mark, target = null;
    const move = ev => {
      if (!started) { if (Math.hypot(ev.clientX - x0, ev.clientY - y0) < 5) return; started = true; document.body.classList.add("dragging"); this.panes[key].classList.add("drag-src");
        ghost = h("div", { class: "dragghost" }, PANES[key]); mark = h("div", { class: "dropmark" }); document.body.append(ghost, mark); }
      ghost.style.left = ev.clientX + 12 + "px"; ghost.style.top = ev.clientY + 8 + "px";
      target = null;
      for (const col of $$("#shell > .col")) {
        const r = col.getBoundingClientRect();
        if (ev.clientX >= r.left && ev.clientX <= r.right) {
          const after = ev.clientX > r.left + r.width / 2;
          target = { col: col.dataset.col, after };
          Object.assign(mark.style, { left: (after ? r.right - 2 : r.left - 2) + "px", top: r.top + "px", height: r.height + "px" });
        }
      }
      mark.style.display = target ? "block" : "none";
    };
    const up = () => {
      window.removeEventListener("pointermove", move); window.removeEventListener("pointerup", up);
      if (!started) return;
      document.body.classList.remove("dragging"); this.panes[key].classList.remove("drag-src"); ghost.remove(); mark.remove();
      if (!target) return;
      const order = this.L.order.filter(k => k !== key);
      let tk = target.col === "stack" ? (target.after ? (order.includes("chat") ? "chat" : "reader") : (order.includes("reader") ? "reader" : "chat")) : target.col;
      if (tk === key) return;
      let idx = order.indexOf(tk);
      if (this.L.stack && target.col === "stack") idx = target.after ? Math.max(order.indexOf("reader"), order.indexOf("chat")) : Math.min(...["reader", "chat"].map(k => order.indexOf(k)).filter(i => i >= 0));
      order.splice(target.after ? idx + 1 : idx, 0, key);
      this.L.order = order; this.render();
    };
    window.addEventListener("pointermove", move); window.addEventListener("pointerup", up);
  },
  makePane(key, headKids, body) {
    const grip = h("span", { class: "grip", title: "끌어서 위치 바꾸기", html: ic("grip") });
    grip.addEventListener("pointerdown", e => { e.preventDefault(); this.startDrag(key, e); });
    const col = h("button", { class: "icon", title: "접기", html: ic("collapse"), onclick: e => { e.stopPropagation(); this.toggle(key, true); } });
    const rail = h("div", { class: "rail" }, h("span", {}, PANES[key]));
    const head = h("div", { class: "phead" }, rail, grip, ...headKids, col);
    const p = h("section", { class: "pane", "data-pane": key }, head, h("div", { class: "pbody" }, body));
    p.addEventListener("click", e => {
      if (p.classList.contains("collapsed") || (p.classList.contains("mini") && e.target.closest(".phead") && !e.target.closest("button"))) this.toggle(key, false);
    });
    this.panes[key] = p;
    return p;
  },
};

/* ================================================================== PDF viewers */
const Viewers = {};
class Viewer {
  constructor(side) {
    this.side = side; this.zf = store.get("zoom." + side, 1); this.scale = 1; this.pages = [];
    this.el = h("div", { class: "viewer", tabindex: "0" });
    this.inner = h("div", { class: "pages" });
    this.el.append(this.inner);
    this.pnoEl = h("span", { class: "sub" }, "");
    this.zoomEl = h("button", { class: "zoomv", title: "폭에 맞춤", onclick: () => this.zoom(1, true) }, "100%");
    const head = [
      h("span", { class: "ttl" }, side === "en" ? "원문" : "번역"), this.pnoEl, h("div", { class: "grow" }),
      ...(side === "ko" ? [h("button", { class: "icon" + (app.sync ? " on" : ""), id: "syncBtn", title: "원문과 스크롤 맞추기", html: ic("link"), onclick: e => { app.sync = !app.sync; store.set("sync", app.sync); $$("#syncBtn").forEach(b => b.classList.toggle("on", app.sync)); } })] : []),
      h("button", { class: "icon", title: "축소", html: ic("minus"), onclick: () => this.zoom(this.zf / 1.15) }),
      this.zoomEl,
      h("button", { class: "icon", title: "확대", html: ic("plus"), onclick: () => this.zoom(this.zf * 1.15) }),
    ];
    Layout.makePane(side, head, this.el);
    this.io = new IntersectionObserver(es => es.forEach(e => { if (e.isIntersecting) this.loadImg(+e.target.dataset.n); }), { root: this.el, rootMargin: "900px 0px" });
    this.el.addEventListener("scroll", () => this.onScroll(), { passive: true });
    this.el.addEventListener("wheel", e => { if (e.ctrlKey || e.metaKey) { e.preventDefault(); this.zoom(this.zf * (e.deltaY < 0 ? 1.1 : 1 / 1.1)); } }, { passive: false });
    new ResizeObserver(() => this.layout()).observe(this.el);
  }
  load() {
    this.inner.innerHTML = ""; this.pages = [];
    (app.paper?.pages || []).forEach((pg, n) => {
      const img = h("img", { alt: "", draggable: "false" });
      const ov = h("div", { class: "ov" });
      const d = h("div", { class: "pg", "data-n": n }, img, ov, h("span", { class: "pno" }, `${n + 1}`));
      ov.addEventListener("click", e => this.onPageClick(e, n));
      this.inner.append(d);
      this.pages.push({ d, img, ov, w: pg.w, h: pg.h, src: "" });
      this.io.observe(d);
    });
    this.layout(); this.drawHits(); this.drawAll();
  }
  layout() {
    if (!this.pages.length) return;
    const maxW = Math.max(...this.pages.map(p => p.w));
    const avail = Math.max(120, this.el.clientWidth - 28);
    this.scale = avail / maxW * this.zf;
    this.inner.style.setProperty("--sc", this.scale);
    for (const p of this.pages) { p.d.style.width = p.w * this.scale + "px"; p.d.style.height = p.h * this.scale + "px"; }
    this.zoomEl.textContent = Math.round(this.zf * 100) + "%";
    clearTimeout(this._lt); this._lt = setTimeout(() => this.pages.forEach((p, n) => { if (p.src) this.loadImg(n, true); }), 250);
  }
  zoom(z, reset) {
    const el = this.el, fy = el.scrollTop / Math.max(1, el.scrollHeight), fx = (el.scrollLeft + el.clientWidth / 2) / Math.max(1, el.scrollWidth);
    this.zf = reset ? 1 : clamp(z, 0.4, 4); store.set("zoom." + this.side, this.zf); this.layout();
    el.scrollTop = fy * el.scrollHeight; el.scrollLeft = fx * el.scrollWidth - el.clientWidth / 2;
  }
  zbucket() { return clamp(Math.ceil(this.scale * (window.devicePixelRatio || 1) * 4) / 4, 1, 4); }
  url(n) {
    const rev = this.side === "ko" ? (app.pageRev[n] || 0) : 0;
    return `/api/p/${app.pid}/page/${this.side}/${n}.png?z=${this.zbucket()}&v=${rev}`;
  }
  pending(n) { return this.side === "ko" && !app.pageRev[n] && app.status !== "done" && app.status !== "error"; }
  loadImg(n, force) {
    const p = this.pages[n]; if (!p) return;
    const u = this.url(n);
    p.d.classList.toggle("pending", this.pending(n));
    let w = p.d.querySelector(".wait");
    if (this.pending(n) && !w) p.d.append(h("div", { class: "wait" }, h("div", { class: "shimmer" }), h("span", {}, h("i", { class: "spin" }), "번역 중…")));
    if (!this.pending(n) && w) w.remove();
    if (p.src === u && !force) return;
    if (p.src === u) return;
    const pre = new Image(); pre.onload = () => { p.img.src = u; }; pre.src = u; p.src = u;
  }
  refreshPage(n) { if (this.pages[n] && this.pages[n].src) this.loadImg(n); else if (this.pages[n]) this.pages[n].d.classList.toggle("pending", this.pending(n)); }
  refreshAll() { this.pages.forEach((p, n) => this.refreshPage(n)); }
  pct(b, p) { return { left: b[0] / p.w * 100 + "%", top: b[1] / p.h * 100 + "%", width: (b[2] - b[0]) / p.w * 100 + "%", height: (b[3] - b[1]) / p.h * 100 + "%" }; }
  drawHits() {
    this.pages.forEach(p => $$(".hit", p.ov).forEach(x => x.remove()));
    for (const u of app.units.values()) {
      if (["running", "figtext", "other"].includes(u.kind) && !u.translate) continue;
      const p = this.pages[u.page]; if (!p) continue;
      const d = h("div", { class: "hit", "data-id": u.id, style: this.pct(u.bbox, p), title: "" });
      d.addEventListener("click", e => { e.stopPropagation(); selectUnits([u.id], this.side, { scroll: true }); });
      d.addEventListener("dblclick", e => { e.stopPropagation(); if (u.translate || u.ko) editUnit(u.id); });
      p.ov.prepend(d);
    }
  }
  rectsFor(u, kind) {
    if (this.side === "en" || !u.ko) return u.lines && u.lines.length ? u.lines : [u.bbox];
    return [u.bbox];
  }
  drawAll() { this.drawHL(); }
  drawHL() {
    this.pages.forEach(p => $$(".hlr", p.ov).forEach(x => x.remove()));
    const add = (n, b, cls, color) => {
      const p = this.pages[n]; if (!p) return;
      const d = h("div", { class: "hlr " + cls, style: this.pct([b[0] - .5, b[1] - .5, b[2] + .5, b[3] + .5], p) });
      if (color) d.style.background = color + "55";
      p.ov.append(d);
    };
    for (const m of app.marks) { const u = app.units.get(m.unit); if (u) this.rectsFor(u).forEach(b => add(u.page, b, "mark", m.color)); }
    if (FindState.hits.length) for (const id of FindState.hits) { const u = app.units.get(id); if (u) add(u.page, u.bbox, "find"); }
    const pr = app.sel.precise[this.side];
    for (const id of app.sel.ids) {
      const u = app.units.get(id); if (!u) continue;
      this.rectsFor(u).forEach(b => add(u.page, b, pr ? "selp" : "sel"));
    }
    if (pr) pr.rects.forEach(b => add(pr.page, b, "sel"));
  }
  scrollToUnit(id, smooth = true) {
    const u = app.units.get(id); if (!u) return;
    const p = this.pages[u.page]; if (!p) return;
    const top = p.d.offsetTop + u.bbox[1] / p.h * p.d.offsetHeight - this.el.clientHeight * 0.28;
    const left = p.d.offsetLeft + u.bbox[0] / p.w * p.d.offsetWidth - 20;
    this._noSync = true;
    this.el.scrollTo({ top: Math.max(0, top), left: this.el.scrollWidth > this.el.clientWidth ? Math.max(0, left) : 0, behavior: smooth ? "smooth" : "auto" });
    setTimeout(() => { this._noSync = false; }, 600);
  }
  scrollToPage(n, y = 0) {
    const p = this.pages[n]; if (!p) return;
    this.el.scrollTo({ top: p.d.offsetTop + y / p.h * p.d.offsetHeight - this.el.clientHeight * 0.3, behavior: "smooth" });
  }
  currentPage() {
    const mid = this.el.scrollTop + this.el.clientHeight * 0.4;
    let cur = 0;
    this.pages.forEach((p, n) => { if (p.d.offsetTop <= mid) cur = n; });
    return cur;
  }
  position() {
    const n = this.currentPage(), p = this.pages[n]; if (!p) return null;
    return { n, f: (this.el.scrollTop - p.d.offsetTop) / p.d.offsetHeight };
  }
  onScroll() {
    const n = this.currentPage();
    this.pnoEl.textContent = this.pages.length ? `${n + 1} / ${this.pages.length}` : "";
    if (!app.sync || this._noSync || this._fromSync) return;
    const other = Viewers[this.side === "en" ? "ko" : "en"]; if (!other || !other.pages.length) return;
    const pos = this.position(); if (!pos) return;
    const q = other.pages[pos.n]; if (!q) return;
    other._fromSync = true;
    other.el.scrollTop = q.d.offsetTop + pos.f * q.d.offsetHeight;
    other.el.scrollLeft = this.el.scrollLeft / Math.max(1, this.el.scrollWidth - this.el.clientWidth) * Math.max(0, other.el.scrollWidth - other.el.clientWidth) || 0;
    requestAnimationFrame(() => requestAnimationFrame(() => { other._fromSync = false; }));
  }
  onPageClick(e, n) { selectUnits([], null); }
}
const uid = () => Math.random().toString(16).slice(2, 12);
let _ns;
function saveNotes() { clearTimeout(_ns); _ns = setTimeout(() => api.post(`/api/p/${app.pid}/notes`, { marks: app.marks }).catch(e => toast("형광펜 저장 실패: " + e.message, "err")), 400); }

/* ================================================================== selection & linking */
function selectUnits(ids, from, opt = {}) {
  app.sel = { ids: [...new Set(ids)], text: opt.text || "", from, precise: opt.precise || {} };
  Viewers.en.drawHL(); Viewers.ko.drawHL();
  Reader.markSel();
  Chat.updateCtx();
  if (opt.scroll && ids.length) {
    const id = ids[0];
    if (from !== "en") Viewers.en.scrollToUnit(id);
    if (from !== "ko") Viewers.ko.scrollToUnit(id);
    if (from !== "reader") Reader.scrollTo(id);
  }
}

/* ================================================================== find in paper */
const FindState = { q: "", hits: [], i: -1 };

/* ================================================================== reader */
const Reader = {
  tab: "text",
  build() {
    this.el = h("div", { class: "reader" });
    this.doc = h("div", { class: "doc" });
    this.el.append(this.doc);
    this.cnt = h("span", { class: "cnt" });
    this.q = h("input", { placeholder: "본문 찾기 (한/영)", oninput: () => this.find(), onkeydown: e => { if (e.key === "Enter") this.findNext(e.shiftKey ? -1 : 1); if (e.key === "Escape") { this.q.value = ""; this.find(); } } });
    this.modeSeg = h("div", { class: "seg" }, ...[["ko", "한글"], ["both", "대역"], ["en", "원문"]].map(([k, l]) => h("button", { "data-k": k, class: app.readMode === k ? "on" : "", onclick: () => this.setMode(k) }, l)));
    this.tabSeg = h("div", { class: "seg" }, ...[["text", "본문"], ["figs", "그림·표"], ["gloss", "용어집"]].map(([k, l]) => h("button", { "data-k": k, class: k === this.tab ? "on" : "", onclick: () => this.setTab(k) }, l)));
    const tools = h("div", { class: "rtools" }, this.modeSeg, h("div", { class: "search", html: ic("search") }, this.q, this.cnt),
      h("div", { class: "grow" }),
      h("button", { class: "icon", title: "글자 작게", onclick: () => this.font(-1), html: "<b style='font-size:11px'>가</b>" }),
      h("button", { class: "icon", title: "글자 크게", onclick: () => this.font(1), html: "<b style='font-size:15px'>가</b>" }));
    $(".search", tools).firstElementChild.style.cssText = "width:14px;height:14px;flex:none";
    this.tools = tools;
    Layout.makePane("reader", [h("span", { class: "ttl" }, "읽기"), this.tabSeg, h("div", { class: "grow" })], h("div", { style: { display: "contents" } }, tools, this.el));
    this.el.addEventListener("mouseup", e => setTimeout(() => this.onMouseUp(e), 0));
    this.font(0);
  },
  setMode(k) { app.readMode = k; store.set("readMode", k); $$("button", this.modeSeg).forEach(b => b.classList.toggle("on", b.dataset.k === k)); this.render(); },
  setTab(k) { this.tab = k; $$("button", this.tabSeg).forEach(b => b.classList.toggle("on", b.dataset.k === k)); this.tools.style.display = k === "text" ? "" : "none"; this.render(); },
  font(d) { app.rfs = clamp(app.rfs + d, 12, 22); store.set("rfs", app.rfs); this.el.style.setProperty("--rfs", app.rfs + "px"); },
  render() {
    const top = this.el.scrollTop;
    this.doc.innerHTML = "";
    this.blocks = new Map();                       // unit id -> block element (a paragraph cut by a page break shares one)
    if (!app.paper) return;
    if (this.tab === "figs") return this.renderFigs();
    if (this.tab === "gloss") return this.renderGloss();
    const d = app.paper, units = app.order.map(id => app.units.get(id)).filter(Boolean);
    // where each picture goes: figures before their caption, algorithm/code boxes after it, loose ones by position
    const before = {}, after = {}, loose = {};
    d.figures.forEach((f, i) => {
      if (f.caption && app.units.has(f.caption)) (f.kind === "figure" ? before : after)[f.caption] = [...((f.kind === "figure" ? before : after)[f.caption] || []), i];
      else (loose[f.page] = loose[f.page] || []).push(i);
    });
    const eqAt = {}, eqSkip = new Set();
    (d.equations || []).forEach((e, i) => {
      const ids = e.units.filter(id => app.units.has(id)).sort((a, b) => app.order.indexOf(a) - app.order.indexOf(b));
      if (!ids.length) return;
      eqAt[ids[0]] = i; ids.forEach(id => eqSkip.add(id));
    });
    const tableAt = {}, tableCells = new Set();
    (d.tables || []).forEach((t, i) => { tableAt[t.units[0]] = i; t.units.forEach(x => tableCells.add(x)); });
    const refs = [];
    const placed = new Set();
    const putLoose = (page, y) => {
      for (const i of loose[page] || []) {
        if (placed.has("f" + i) || d.figures[i].bbox[1] > y) continue;
        placed.add("f" + i); this.doc.append(this.figEl("fig", i));
      }
    };
    let lastPage = -1;
    for (const u of units) {
      if (u.page !== lastPage) { if (lastPage >= 0) putLoose(lastPage, 1e9); lastPage = u.page; }
      putLoose(u.page, u.bbox[1]);
      if (u.kind === "ref") { refs.push(u); continue; }
      if (u.id in eqAt) { this.doc.append(this.eqEl(eqAt[u.id])); continue; }
      if (eqSkip.has(u.id)) continue;
      if (tableCells.has(u.id)) { if (u.id in tableAt) this.doc.append(this.figEl("tab", tableAt[u.id])); continue; }
      if (["running", "figtext", "other", "code", "equation"].includes(u.kind)) continue;
      (before[u.id] || []).forEach(i => { placed.add("f" + i); this.doc.append(this.figEl("fig", i)); });
      const prev = u.prev && this.blocks.get(u.prev);
      if (prev) { prev.dataset.ids += "," + u.id; this.blocks.set(u.id, prev); this.fillBlk(prev); }
      else this.doc.append(this.blk(u));
      (after[u.id] || []).forEach(i => { placed.add("f" + i); this.doc.append(this.figEl("fig", i)); });
    }
    if (lastPage >= 0) putLoose(lastPage, 1e9);
    if (refs.length) {
      const det = h("details", { class: "refs" }, h("summary", {}, `참고문헌 (${refs.length})`));
      refs.forEach(u => det.append(this.blk(u, true)));
      this.doc.append(det);
    }
    this.el.scrollTop = top;
    this.markSel(); this.markMarks();
  },
  headLevel(u) {
    if (u.kind === "title") return "h1";
    if (u.kind !== "heading") return "";
    const m = (u.text || "").trim().match(/^(\d+(?:\.\d+)*)|^([A-Z])\.\s|^([IVX]+)\.\s/);
    if (m && m[1] && m[1].split(".").length >= 2) return "h3";
    if (m && m[2]) return "h3";
    return "h2";
  },
  blk(u, isRef) {
    const lv = this.headLevel(u);
    const cls = lv || ({ caption: "cap", note: "note-k" }[u.kind] || "p");
    const el = h("div", { class: `blk ${cls}`, "data-id": u.id, "data-ids": u.id });
    if (isRef) el.dataset.ref = "1";
    this.blocks.set(u.id, el);
    this.fillBlk(el);
    el.addEventListener("click", e => {
      if (e.target.closest(".btools")) return;
      const s = getSelection(); if (s && !s.isCollapsed && s.toString().trim()) return;
      selectUnits(el.dataset.ids.split(","), "reader", { scroll: true });
    });
    return el;
  },
  fillBlk(el) {
    const us = el.dataset.ids.split(",").map(id => app.units.get(id)).filter(Boolean);
    const u = us[0];
    el.innerHTML = "";
    const mode = el.dataset.ref ? "en" : app.readMode;
    const koOf = x => x.ko_html || (x.translate ? (x.err ? esc(x.text) : '<span class="pend"></span>') : esc(x.text));
    const glue = (parts) => parts.join(" ").replace(/\s+-\s+/g, "-");
    const err = us.some(x => x.err && !x.ko);
    el.classList.toggle("err", err);
    if (mode !== "en") el.append(h("div", { class: "ko", html: glue(us.map(koOf)) }));
    if (mode !== "ko") el.append(h("div", { class: mode === "en" ? "ko en-only" : "en", html: esc(glue(us.map(x => x.text))) }));
    el.append(h("div", { class: "btools" },
      h("button", { title: "이 문단에 대해 질문", html: ic("ask") + "질문", onclick: e => { e.stopPropagation(); selectUnits(us.map(x => x.id), "reader"); Chat.focus(); } }),
      h("button", { title: "형광펜", html: ic("hl"), onclick: e => { e.stopPropagation(); toggleMark(us.map(x => x.id)); } }),
      h("button", { title: "다시 번역", html: ic("redo"), onclick: e => { e.stopPropagation(); retranslateDlg(u.id); } }),
      h("button", { title: "번역 직접 수정", html: ic("edit"), onclick: e => { e.stopPropagation(); editUnit(u.id); } })));
  },
  update(ids) {
    const done = new Set();
    for (const id of ids) {
      const el = this.blocks?.get(id);
      if (el && !done.has(el)) { done.add(el); this.fillBlk(el); }
    }
    $$(".fig[data-tab]", this.doc).forEach(f => { const img = f.querySelector("img"); const u = this.tabUrl(+f.dataset.tab); if (img.getAttribute("src") !== u) img.src = u; });
  },
  tabUrl(i) { const t = app.paper.tables[i]; const rev = app.pageRev[t.page] || 0; return `/api/p/${app.pid}/tab/${i}.png?side=${rev ? "ko" : "en"}&v=${rev}`; },
  pxPerPt() { return app.rfs / (app.paper.body_size || 10); },
  figEl(kind, i) {
    const item = kind === "fig" ? app.paper.figures[i] : app.paper.tables[i];
    const src = kind === "fig" ? `/api/p/${app.pid}/fig/${i}.png` : this.tabUrl(i);
    const wpt = item.bbox[2] - item.bbox[0];
    const k = item.kind === "algorithm" || item.kind === "code" ? "algo" : kind === "tab" ? "tab" : "pic";
    const img = h("img", { loading: "lazy", src, style: { width: `min(100%, ${Math.round(wpt * this.pxPerPt() * (k === "pic" ? 1.25 : 1.05))}px)` } });
    const f = h("div", { class: `fig ${k}`, ...(kind === "tab" ? { "data-tab": i } : {}) }, img);
    f.addEventListener("click", () => lightbox(img.src));
    return f;
  },
  eqEl(i) {
    const e = app.paper.equations[i];
    const b = e.bbox, wpt = b[2] - b[0];
    const img = h("img", { loading: "lazy", src: `/api/p/${app.pid}/crop/en/${e.page}.png?r=${b.map(x => x.toFixed(1)).join(",")}`,
      style: { width: `min(100%, ${Math.round(wpt * this.pxPerPt())}px)` } });
    const el = h("div", { class: "eq", "data-ids": e.units.join(",") }, img);
    el.addEventListener("click", () => selectUnits(e.units, "reader", { scroll: true }));
    return el;
  },
  renderFigs() {
    const d = app.paper, g = h("div", { class: "gallery" });
    const capText = id => { const u = app.units.get(id); return u ? (u.ko || u.text) : ""; };
    d.figures.forEach((f, i) => { const e = this.figEl("fig", i); e.append(h("div", { class: "c" }, `${f.page + 1}쪽 · ${capText(f.caption) || "그림"}`)); e.onclick = () => { if (f.caption) selectUnits([f.caption], "reader", { scroll: true }); else { Viewers.en.scrollToPage(f.page, f.bbox[1]); Viewers.ko.scrollToPage(f.page, f.bbox[1]); } }; g.append(e); });
    (d.tables || []).forEach((t, i) => { const e = this.figEl("tab", i); e.append(h("div", { class: "c" }, `${t.page + 1}쪽 · ${capText(t.caption) || "표"}`)); e.onclick = () => selectUnits(t.units, "reader", { scroll: true }); g.append(e); });
    if (!d.figures.length && !(d.tables || []).length) g.append(h("div", { class: "empty" }, "찾은 그림·표가 없습니다"));
    this.doc.append(g);
  },
  renderGloss() {
    const g = app.paper.glossary || { field: "", terms: [] };
    const field = h("input", { class: "txt", value: g.field || "", placeholder: "분야 (예: 컴퓨터 비전)" });
    const tb = h("tbody");
    const row = (t = { en: "", ko: "" }) => {
      const tr = h("tr", {}, h("td", {}, h("input", { value: t.en, placeholder: "English" })), h("td", {}, h("input", { value: t.ko, placeholder: "한국어" })),
        h("td", { style: { width: "30px" } }, h("button", { class: "icon del", title: "삭제", html: ic("x"), onclick: () => tr.remove() })));
      tb.append(tr);
    };
    (g.terms || []).forEach(row);
    const collect = () => ({ field: field.value.trim(), terms: $$("tr", tb).map(tr => { const [a, b] = $$("input", tr); return { en: a.value.trim(), ko: b.value.trim() }; }).filter(t => t.en && t.ko) });
    const saveBtn = async apply => {
      try {
        const r = await api.post(`/api/p/${app.pid}/glossary`, { ...collect(), apply });
        app.paper.glossary = collect();
        toast(apply ? (r.retranslating ? `${r.retranslating}개 문단을 새 용어로 다시 번역합니다` : "바뀐 용어가 들어간 문단이 없습니다") : "용어집을 저장했습니다");
        if (r.retranslating) Poll.kick();
      } catch (e) { toast(e.message, "err"); }
    };
    this.doc.append(h("div", { class: "gloss" },
      h("p", { class: "hint" }, "번역할 때 따르는 용어입니다. 논문 분야를 자동으로 파악해 한국 학계에서 쓰는 말로 정했습니다. 고친 뒤 '적용'을 누르면 그 용어가 들어간 문단만 다시 번역합니다."),
      h("div", { class: "field" }, h("b", { style: { fontSize: "12px", whiteSpace: "nowrap" } }, "분야"), field),
      h("table", {}, h("thead", {}, h("tr", {}, h("th", {}, "원어"), h("th", {}, "번역어"), h("th"))), tb),
      h("div", { class: "actions" }, h("button", { class: "ghost", html: ic("plus") + "용어 추가", onclick: () => { row(); $$("input", tb.lastElementChild)[0].focus(); } }), h("div", { class: "grow" }),
        h("button", { class: "ghost", onclick: () => saveBtn(false) }, "저장만"), h("button", { class: "primary", onclick: () => saveBtn(true) }, "저장하고 다시 번역"))));
  },
  markSel() {
    $$(".blk.sel", this.doc).forEach(e => e.classList.remove("sel"));
    for (const id of app.sel.ids) this.blocks?.get(id)?.classList.add("sel");
  },
  markMarks() {
    $$(".blk.mark", this.doc).forEach(e => e.classList.remove("mark"));
    for (const m of app.marks) this.blocks?.get(m.unit)?.classList.add("mark");
  },
  scrollTo(id) {
    if (this.tab !== "text") return;
    const el = this.blocks?.get(id) || [...this.doc.querySelectorAll(".eq")].find(e => e.dataset.ids.split(",").includes(id));
    if (!el) return;
    const det = el.closest("details"); if (det) det.open = true;
    const top = el.offsetTop - this.el.clientHeight * 0.25;
    this.el.scrollTo({ top, behavior: "smooth" });
  },
  onMouseUp(e) {
    hideSelbar();
    const s = getSelection(); if (!s || s.isCollapsed) return;
    const text = s.toString().trim(); if (!text) return;
    const range = s.getRangeAt(0);
    if (!this.el.contains(range.commonAncestorContainer)) return;
    const ids = [...new Set($$(".blk", this.doc).filter(b => range.intersectsNode(b)).flatMap(b => b.dataset.ids.split(",")))];
    if (!ids.length) return;
    const inEn = !!(range.startContainer.parentElement?.closest(".en, .en-only"));
    selectUnits(ids, "reader", { text, scroll: false });
    Viewers.en.scrollToUnit(ids[0]); Viewers.ko.scrollToUnit(ids[0]);
    if (ids.length === 1 && text.length >= 2) {
      const u = app.units.get(ids[0]);
      const side = inEn || app.readMode === "en" ? "en" : "ko";
      if (side === "en" || app.pageRev[u.page]) api.post(`/api/p/${app.pid}/rects`, { side, page: u.page, text }).then(r => {
        if (r.rects?.length && app.sel.text === text) { app.sel.precise = { [side]: { page: u.page, rects: r.rects } }; Viewers.en.drawHL(); Viewers.ko.drawHL(); }
      }).catch(() => {});
    }
    const rr = range.getBoundingClientRect();
    showSelbar(rr, ids, text);
  },
  find() {
    const q = this.q.value.trim().toLowerCase(); FindState.q = q; FindState.i = -1;
    $$(".blk.find", this.doc).forEach(e => e.classList.remove("find"));
    FindState.hits = q.length < 2 ? [] : app.order.filter(id => { const u = app.units.get(id); return u && ((u.text || "").toLowerCase().includes(q) || (u.ko || "").toLowerCase().includes(q)); });
    FindState.hits.forEach(id => this.blocks?.get(id)?.classList.add("find"));
    this.cnt.textContent = q.length < 2 ? "" : `${FindState.hits.length}건`;
    Viewers.en.drawHL(); Viewers.ko.drawHL();
    if (FindState.hits.length) this.findNext(1);
  },
  findNext(d) {
    if (!FindState.hits.length) return;
    FindState.i = (FindState.i + d + FindState.hits.length) % FindState.hits.length;
    const id = FindState.hits[FindState.i];
    this.cnt.textContent = `${FindState.i + 1}/${FindState.hits.length}`;
    this.scrollTo(id); Viewers.en.scrollToUnit(id); Viewers.ko.scrollToUnit(id);
  },
};
let selbar = null;
function hideSelbar() { selbar?.remove(); selbar = null; }
function showSelbar(rr, ids, text) {
  hideSelbar();
  selbar = h("div", { class: "selbar" },
    h("button", { html: ic("ask") + "질문하기", onclick: () => { hideSelbar(); Chat.focus(); } }),
    h("button", { html: ic("sparkle") + "쉽게 설명", onclick: () => { hideSelbar(); Chat.send("선택한 부분을 쉽게 풀어서 설명해줘. 배경 지식이 필요하면 함께."); } }),
    h("button", { html: ic("hl") + "형광펜", onclick: () => { hideSelbar(); toggleMark(ids); getSelection().removeAllRanges(); } }),
    h("button", { html: ic("copy") + "복사", onclick: () => { navigator.clipboard?.writeText(text); hideSelbar(); toast("복사했습니다"); } }));
  document.body.append(selbar);
  const w = selbar.offsetWidth;
  selbar.style.left = clamp(rr.left + rr.width / 2 - w / 2, 8, innerWidth - w - 8) + "px";
  selbar.style.top = (rr.top > 60 ? rr.top - 42 : rr.bottom + 8) + "px";
}
document.addEventListener("mousedown", e => { if (selbar && !selbar.contains(e.target)) hideSelbar(); });

function toggleMark(ids) {
  const all = ids.every(id => app.marks.some(m => m.unit === id));
  if (all) app.marks = app.marks.filter(m => !ids.includes(m.unit));
  else ids.forEach(id => { if (!app.marks.some(m => m.unit === id)) app.marks.push({ id: uid(), unit: id, side: "both", color: "#ffd43b" }); });
  Viewers.en.drawHL(); Viewers.ko.drawHL(); Reader.markMarks(); saveNotes();
}

/* ================================================================== chat */
const Chat = {
  rev: 0, items: [], running: false,
  build() {
    this.log = h("div", { class: "chatlog" });
    this.ta = h("textarea", { rows: 1, placeholder: "이 논문에 대해 물어보세요 (Enter 보내기 · Shift+Enter 줄바꿈)" });
    this.btn = h("button", { class: "send", title: "보내기", html: ic("send"), onclick: () => this.running ? this.stop() : this.send() });
    this.ctx = h("div", { class: "ctxchip", hidden: true });
    this.ta.addEventListener("input", () => this.grow());
    this.ta.addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); this.send(); } });
    const comp = h("div", { class: "composer" }, this.ctx, h("div", { class: "inbox" }, this.ta, this.btn));
    this.webBtn = h("button", { class: "icon", title: "웹 검색 허용", html: ic("globe"), onclick: async () => { const v = !app.st.settings.web_search; app.st.settings = await api.post("/api/settings", { web_search: v }); this.webBtn.classList.toggle("on", v); toast(v ? "필요하면 웹 검색도 합니다" : "논문 내용으로만 답합니다"); } });
    Layout.makePane("chat", [h("span", { class: "ttl" }, "질문"), h("span", { class: "sub", id: "chatModel" }), h("div", { class: "grow" }), this.webBtn,
      h("button", { class: "icon", title: "대화 지우기", html: ic("clear"), onclick: () => this.clear() })], h("div", { style: { display: "contents" } }, this.log, comp));
  },
  grow() { this.ta.style.height = "auto"; this.ta.style.height = Math.min(180, this.ta.scrollHeight) + "px"; this.btn.disabled = !this.running && !this.ta.value.trim(); },
  focus() { if (Layout.L.collapsed.chat) Layout.toggle("chat", false); this.ta.focus(); },
  updateCtx() {
    const ids = app.sel.ids;
    if (!ids.length) { this.ctx.hidden = true; return; }
    const u = app.units.get(ids[0]);
    const label = app.sel.text ? `“${app.sel.text.slice(0, 60)}${app.sel.text.length > 60 ? "…" : ""}”` : `${u ? u.page + 1 : ""}쪽 문단${ids.length > 1 ? ` 외 ${ids.length - 1}개` : ""}: ${(u?.ko || u?.text || "").slice(0, 50)}…`;
    this.ctx.innerHTML = ""; this.ctx.append(h("span", {}, "선택 포함 · " + label), h("button", { title: "선택 빼기", html: ic("x"), onclick: () => selectUnits([], null) }));
    this.ctx.hidden = false;
  },
  context() {
    if (!app.sel.ids.length) return null;
    const text = app.sel.text || app.sel.ids.map(id => { const u = app.units.get(id); return u ? `${u.text}\n(번역: ${u.ko || "-"})` : ""; }).join("\n\n");
    return { text, units: app.sel.ids };
  },
  async send(text) {
    text = (text ?? this.ta.value).trim(); if (!text || this.running || !app.pid) return;
    if (Layout.L.collapsed.chat) Layout.toggle("chat", false);
    try {
      await api.post(`/api/p/${app.pid}/chat`, { text, context: this.context() });
      this.ta.value = ""; this.grow(); this.running = true; this.poll();
    } catch (e) { toast(e.message, "err"); }
  },
  async stop() { await api.post(`/api/p/${app.pid}/chatstop`).catch(() => {}); },
  async clear() { if (this.running) return; await api.post(`/api/p/${app.pid}/chatclear`); this.rev = -1; this.poll(); },
  async poll() {
    if (!app.pid) return;
    clearTimeout(this._t);
    const pid = app.pid;
    try {
      const r = await api.get(`/api/p/${pid}/chat?rev=${this.rev}`);
      if (pid !== app.pid) return;
      if (!r.same) { this.items = r.items; this.rev = r.rev; this.render(); }
      this.running = r.running;
    } catch (e) { /* retry */ }
    this.btn.classList.toggle("stop", this.running); this.btn.innerHTML = ic(this.running ? "stop" : "send"); this.btn.title = this.running ? "멈추기" : "보내기"; this.grow();
    if (this.running) this._t = setTimeout(() => this.poll(), 350);
  },
  render() {
    const atBottom = this.log.scrollHeight - this.log.scrollTop - this.log.clientHeight < 80;
    this.log.innerHTML = "";
    if (!this.items.length) {
      const sug = ["이 논문을 3줄로 요약해줘", "핵심 기여가 뭐야?", "제안 방법을 단계별로 설명해줘", "실험 설정과 결과를 표로 정리해줘", "한계점과 후속 연구 방향은?", "모르는 용어를 쉽게 풀어줘"];
      this.log.append(h("div", { class: "chatempty" }, h("div", { class: "t" }, "이 논문에 대해 무엇이든 물어보세요"),
        h("div", { class: "hint" }, "읽기 화면에서 문단을 누르거나 글을 드래그하면 그 부분을 두고 질문할 수 있어요. 답의 ¶ 표시를 누르면 근거 문단으로 이동합니다."),
        h("div", { class: "sugg" }, ...sug.map(s => h("button", { onclick: () => this.send(s) }, s)))));
      return;
    }
    this.items.forEach((m, i) => {
      if (m.role === "user") {
        this.log.append(h("div", { class: "msg user" }, m.context ? h("div", { class: "ctx", title: m.context }, "↳ " + m.context) : null, h("div", { class: "bub" }, m.text)));
      } else {
        const bub = h("div", { class: "bub", html: m.text ? md(m.text) : "" });
        if (!m.text && m.streaming) bub.append(h("span", { class: "typing" }, h("i"), h("i"), h("i")));
        $$(".cite", bub).forEach(c => c.addEventListener("click", () => selectUnits([c.dataset.id], "chat", { scroll: true })));
        const tools = (m.tools || []).length ? h("div", { class: "tools" }, ...m.tools.map(t => h("span", {}, (t.tool === "WebFetch" ? "🔗 " : "🔎 ") + (t.arg || "웹 검색")))) : null;
        const acts = !m.streaming && m.text ? h("div", { class: "acts" },
          h("button", { html: ic("copy") + "복사", onclick: () => { navigator.clipboard?.writeText(m.text); toast("복사했습니다"); } })) : null;
        this.log.append(h("div", { class: "msg ai" }, tools, bub, m.error ? h("div", { class: "err" }, m.error) : null, acts));
      }
    });
    if (atBottom || this.running) this.log.scrollTop = this.log.scrollHeight;
  },
};

function md(src) {
  const blocks = [];
  let s = String(src).replace(/```([\s\S]*?)```/g, (_, c) => { blocks.push(`<pre><code>${esc(c.replace(/^\w*\n/, ""))}</code></pre>`); return `\u0000${blocks.length - 1}\u0000`; });
  s = esc(s);
  const inline = t => t
    .replace(/`([^`]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*]+)\*\*/g, "<b>$1</b>")
    .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<i>$2</i>")
    .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
    .replace(/\[¶\s*(u\d+)\]/g, (_, id) => { const u = app.units.get(id); return `<span class="cite" data-id="${id}" title="${esc((u?.ko || u?.text || "").slice(0, 120))}">¶${u ? u.page + 1 + "쪽" : ""}</span>`; });
  const out = []; let list = null;
  for (const line of s.split("\n")) {
    const m = line.match(/^\s*([-*•]|\d+[.)])\s+(.*)$/);
    if (m) { const t = /\d/.test(m[1]) ? "ol" : "ul"; if (!list || list.t !== t) { if (list) out.push(`</${list.t}>`); list = { t }; out.push(`<${t}>`); } out.push(`<li>${inline(m[2])}</li>`); continue; }
    if (list) { out.push(`</${list.t}>`); list = null; }
    const hd = line.match(/^#{1,4}\s+(.*)$/);
    if (hd) { out.push(`<h4>${inline(hd[1])}</h4>`); continue; }
    if (/^\u0000\d+\u0000$/.test(line.trim())) { out.push(line.trim()); continue; }
    if (!line.trim()) { out.push("\n"); continue; }
    out.push(`<p>${inline(line)}</p>`);
  }
  if (list) out.push(`</${list.t}>`);
  return out.join("").replace(/\u0000(\d+)\u0000/g, (_, i) => blocks[i]);
}

/* ================================================================== dialogs */
function modal(title, body, foot, wide) {
  const sc = h("div", { class: "scrim" });
  const close = () => { sc.remove(); document.removeEventListener("keydown", key); };
  const key = e => { if (e.key === "Escape") close(); };
  const m = h("div", { class: "modal" + (wide ? " wide" : "") }, h("div", { class: "mhd" }, h("h3", {}, title), h("button", { class: "icon", html: ic("x"), onclick: close })), h("div", { class: "mbd" }, body), foot ? h("div", { class: "mft" }, foot) : null);
  sc.append(m); sc.addEventListener("mousedown", e => { if (e.target === sc) close(); });
  document.body.append(sc); document.addEventListener("keydown", key);
  return { close, el: m };
}
function lightbox(src) { const lb = h("div", { class: "lightbox", onclick: () => lb.remove() }, h("img", { src })); document.body.append(lb); }

function editUnit(id) {
  const u = app.units.get(id); if (!u) return;
  const ta = h("textarea", { class: "txt", rows: 7, style: { width: "100%", lineHeight: "1.6", fontFamily: "var(--read)", fontSize: "14.5px" } });
  ta.value = u.ko || "";
  const d = modal("번역 직접 수정", [h("div", { class: "hint", style: { maxHeight: "120px", overflow: "auto", background: "var(--sunken)", borderRadius: "8px", padding: "8px 10px" } }, u.text), ta,
    h("div", { class: "hint" }, "고친 번역은 한글 PDF에 바로 다시 조판됩니다. 용어집을 다시 적용해도 직접 고친 문단은 바뀌지 않습니다.")],
    [h("button", { class: "ghost", onclick: () => d.close() }, "취소"), h("button", { class: "primary", onclick: async () => {
      try { const r = await api.post(`/api/p/${app.pid}/edit`, { unit: id, ko: ta.value.trim() }); applyUnit(r.unit); d.close(); toast("번역을 고쳤습니다"); } catch (e) { toast(e.message, "err"); }
    } }, "저장")], true);
  setTimeout(() => ta.focus(), 50);
}
function retranslateDlg(id) {
  const u = app.units.get(id); if (!u) return;
  const inp = h("input", { class: "txt", placeholder: "요청 (비워 두면 그냥 다시 번역) 예: 더 자연스럽게, 'agent'는 '에이전트'로", style: { width: "100%" } });
  const go = async () => {
    btn.disabled = true; btn.innerHTML = '<i class="spin"></i> 번역 중';
    try { const r = await api.post(`/api/p/${app.pid}/retranslate`, { unit: id, instruction: inp.value.trim() }); applyUnit(r.unit); d.close(); toast("다시 번역했습니다"); }
    catch (e) { toast(e.message, "err"); btn.disabled = false; btn.textContent = "다시 번역"; }
  };
  const btn = h("button", { class: "primary", onclick: go }, "다시 번역");
  inp.addEventListener("keydown", e => { if (e.key === "Enter") go(); });
  const d = modal("다시 번역", [h("div", { class: "hint", style: { background: "var(--sunken)", borderRadius: "8px", padding: "8px 10px", maxHeight: "140px", overflow: "auto" } }, u.ko || u.text), inp],
    [h("button", { class: "ghost", onclick: () => d.close() }, "취소"), btn]);
  setTimeout(() => inp.focus(), 50);
}
function applyUnit(nu) {
  const u = app.units.get(nu.id); if (!u) return;
  Object.assign(u, nu);
  Reader.update([nu.id]);
  Poll.kick();
}

/* settings */
async function settingsDialog() {
  try { app.st = await api.get("/api/state"); } catch (e) { /* use what we have */ }
  const s = app.st.settings;
  const st = { provider: s.provider || "claude", backend: s.backend || "cli", openai_backend: s.openai_backend || "cli" };
  const card = (on, title, desc, onclick, extra) => h("div", { class: "opt" + (on ? " on" : ""), onclick }, h("span", { class: "radio" }), h("div", {}, h("b", {}, title), h("span", {}, desc), extra || ""));
  const sel = (val, list) => h("select", { class: "txt" }, ...list.map(m => h("option", { value: m.id, selected: m.id === val }, m.label)));
  const claudeModels = app.st.models;
  const oaModels = [{ id: "", label: `Codex 기본값${app.st.codex_default ? " (" + app.st.codex_default + ")" : ""}` }, ...(app.st.openai_models || [])];
  const keyIn = (set, hint, ph) => h("input", { class: "txt", type: "password", autocomplete: "off", style: { width: "100%" }, placeholder: set ? `저장됨 (${hint}) — 바꾸려면 새 키 입력` : ph });
  const aKey = keyIn(s.api_key_set, s.api_key_hint, "sk-ant-…"), oKey = keyIn(s.openai_key_set, s.openai_key_hint, "sk-…");
  const mT = sel(s.model_translate, claudeModels), mC = sel(s.model_chat, claudeModels);
  const oT = sel(s.openai_model_translate || "", oaModels), oC = sel(s.openai_model_chat || "", oaModels);
  const eff = sel(s.effort_translate, [{ id: "low", label: "빠르게 (low)" }, { id: "medium", label: "보통 (medium)" }, { id: "high", label: "꼼꼼하게 (high)" }]);
  const workers = h("select", { class: "txt" }, ...[1, 2, 3, 4, 5, 6].map(n => h("option", { value: n, selected: n === +s.workers }, `${n}개 동시`)));
  const sw = (k, label) => { const i = h("input", { type: "checkbox", checked: !!s[k] }); i.dataset.k = k; return h("label", { class: "switch" }, label, i); };
  const theme = h("div", { class: "seg" }, ...[["system", "시스템"], ["light", "밝게"], ["dark", "어둡게"]].map(([k, l]) => h("button", { class: (s.theme || "system") === k ? "on" : "", "data-k": k, onclick: e => { $$("button", theme).forEach(b => b.classList.toggle("on", b === e.target)); applyTheme(k); } }, l)));
  const conn = h("div", { class: "fld" });
  const models = h("div", { class: "fld" });
  const drawConn = () => {
    conn.innerHTML = "";
    const prov = h("div", { class: "seg big" }, ...[["claude", "Claude"], ["openai", "Codex (OpenAI)"]].map(([k, l]) =>
      h("button", { class: st.provider === k ? "on" : "", onclick: () => { st.provider = k; drawConn(); } }, l)));
    conn.append(h("label", {}, "AI 선택"), prov);
    if (st.provider === "claude") {
      conn.append(h("label", { style: { marginTop: "8px" } }, "Claude 연결 방식"),
        card(st.backend === "cli", "이 PC에 로그인된 Claude 사용",
          app.st.claude ? "설치된 Claude Code의 로그인(구독)을 그대로 씁니다. 키가 필요 없습니다." : "Claude Code가 설치되어 있지 않습니다. 설치 후 터미널에서 claude 를 실행해 로그인하세요.",
          () => { st.backend = "cli"; drawConn(); }),
        card(st.backend === "api", "Anthropic API 키 사용", "Anthropic Console에서 발급한 키로 호출합니다. 사용량만큼 과금됩니다.",
          () => { st.backend = "api"; drawConn(); }));
      if (st.backend === "api") conn.append(aKey);
    } else {
      conn.append(h("label", { style: { marginTop: "8px" } }, "Codex 연결 방식"),
        card(st.openai_backend === "cli", "이 PC에 로그인된 Codex 사용",
          app.st.codex ? "설치된 Codex CLI의 로그인(ChatGPT 계정 또는 키)을 그대로 씁니다." : "Codex CLI가 설치되어 있지 않습니다. 설치 후 터미널에서 codex login 으로 로그인하세요.",
          () => { st.openai_backend = "cli"; drawConn(); }),
        card(st.openai_backend === "api", "OpenAI API 키 사용", "OpenAI Platform에서 발급한 키로 호출합니다. 사용량만큼 과금됩니다.",
          () => { st.openai_backend = "api"; drawConn(); }));
      if (st.openai_backend === "api") conn.append(oKey);
    }
    conn.append(h("div", { class: "hint" }, "키는 이 PC의 사용자 폴더에만 저장됩니다."));
    models.innerHTML = "";
    const claude = st.provider === "claude";
    models.append(h("div", { class: "row" },
      h("div", { class: "fld", style: { flex: 1 } }, h("label", {}, "번역 모델"), claude ? mT : oT),
      h("div", { class: "fld", style: { flex: 1 } }, h("label", {}, "질문 모델"), claude ? mC : oC)));
  };
  drawConn();
  const status = h("div", { class: "status" });
  const collect = () => {
    const o = { provider: st.provider, backend: st.backend, openai_backend: st.openai_backend, model_translate: mT.value, model_chat: mC.value,
      openai_model_translate: oT.value, openai_model_chat: oC.value, effort_translate: eff.value, workers: +workers.value, theme: $("button.on", theme).dataset.k };
    for (const i of $$(".switch input", d.el)) o[i.dataset.k] = i.checked;
    if (aKey.value.trim()) o.api_key = aKey.value.trim();
    if (oKey.value.trim()) o.openai_key = oKey.value.trim();
    return o;
  };
  const save = async () => { app.st.settings = await api.post("/api/settings", collect()); aKey.value = ""; oKey.value = ""; setChatModel(); };
  const test = async () => {
    status.className = "status"; status.innerHTML = '<i class="spin"></i> 연결 확인 중…';
    try { await save(); const r = await api.post("/api/check"); status.className = "status " + (r.ok ? "ok" : "bad"); status.textContent = (r.ok ? "✓ " : "✕ ") + r.msg; }
    catch (e) { status.className = "status bad"; status.textContent = e.message; }
  };
  const d = modal("설정", [
    conn, models,
    h("div", { class: "row" }, h("div", { class: "fld", style: { flex: 1 } }, h("label", {}, "번역 꼼꼼함"), eff), h("div", { class: "fld", style: { flex: 1 } }, h("label", {}, "번역 속도"), workers)),
    h("div", { class: "fld" }, h("label", {}, "번역 범위"), sw("translate_tables", "표 안의 글자도 번역"), sw("translate_refs", "참고문헌 목록도 번역"), sw("web_search", "질문할 때 필요하면 웹 검색")),
    h("div", { class: "fld" }, h("label", {}, "화면"), theme),
    h("div", { class: "hint" }, "번역 범위는 새로 여는 논문부터 적용됩니다. 이미 연 논문은 상단 진행 표시에서 '처음부터 다시 번역'을 누르세요.")],
    [status, h("div", { class: "grow" }), h("button", { class: "ghost", onclick: test }, "연결 테스트"),
      h("button", { class: "primary", onclick: async () => { try { await save(); d.close(); toast("설정을 저장했습니다"); } catch (e) { toast(e.message, "err"); } } }, "저장")], true);
}
function applyTheme(t) {
  store.set("theme", t);
  if (t === "system") delete document.documentElement.dataset.theme; else document.documentElement.dataset.theme = t;
  const dark = t === "dark" || (t === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  api.post("/api/theme", { dark, color: getComputedStyle(document.body).backgroundColor.match(/\d+/g)?.slice(0, 3).reduce((a, x) => a + (+x).toString(16).padStart(2, "0"), "#") }).catch(() => {});
}
function setChatModel() {
  const st = app.st.settings, oa = st.provider === "openai";
  const id = oa ? (st.openai_model_chat || app.st.codex_default || "") : st.model_chat;
  const m = oa ? null : app.st.models.find(x => x.id === id);
  $("#chatModel").textContent = (oa ? "Codex · " : "") + (m ? m.label.replace(/\s*\(.*\)/, "") : id);
  Chat.webBtn.classList.toggle("on", !!st.web_search);
}

/* ================================================================== menus */
function menu(anchor, items) {
  $$(".menu").forEach(m => m.remove());
  const m = h("div", { class: "menu" });
  for (const it of items) {
    if (it === "-") { m.append(h("hr")); continue; }
    if (it.head) { m.append(h("div", { class: "mh" }, it.head)); continue; }
    const b = h("button", { onclick: () => { if (!it.keep) m.remove(); it.fn(b); } }, it.pre || "", it.icon ? icEl(it.icon) : "", h("span", {}, it.label), it.sub ? h("span", { class: "sub" }, it.sub) : "");
    if (it.disabled) b.disabled = true, b.style.opacity = .45;
    m.append(b);
  }
  document.body.append(m);
  const r = anchor.getBoundingClientRect();
  m.style.top = r.bottom + 6 + "px"; m.style.left = clamp(r.right - m.offsetWidth, 8, innerWidth - m.offsetWidth - 8) + "px";
  setTimeout(() => document.addEventListener("mousedown", function off(e) { if (!m.contains(e.target)) { m.remove(); document.removeEventListener("mousedown", off); } }), 0);
}
const presetIcon = cells => h("span", { class: "preset" }, ...cells.map(c => h("i", { class: c })));
function layoutMenu(btn) {
  const L = Layout.L;
  const chk = on => h("span", { class: "chk" + (on ? " on" : "") });
  menu(btn, [
    { head: "배치" },
    { label: "4분할 (원문 · 번역 · 읽기 · 질문)", pre: presetIcon(["k", "k", "", ""]), fn: () => Layout.preset("four") },
    { label: "3분할 (읽기와 질문을 위아래로)", pre: presetIcon(["k", "k", "", ""]), fn: () => Layout.preset("three") },
    { label: "원문과 번역만", pre: presetIcon(["k", "k", "x", "x"]), fn: () => Layout.preset("pair") },
    { label: "번역 · 읽기 · 질문", pre: presetIcon(["x", "k", "", ""]), fn: () => Layout.preset("study") },
    { label: "읽기 집중", pre: presetIcon(["x", "x", "", ""]), fn: () => Layout.preset("read") },
    "-", { head: "창 보이기" },
    ...Object.keys(PANES).map(k => ({ label: PANES[k], pre: chk(!L.collapsed[k]), fn: () => Layout.toggle(k) })),
    "-",
    { label: "읽기와 질문을 위아래로 합치기", pre: chk(L.stack), fn: () => { L.stack = !L.stack; Layout.render(); } },
    { label: "배치 초기화", icon: "redo", fn: () => Layout.reset() },
    { head: "창 머리의 ⋮⋮ 를 끌면 순서를, 경계선을 끌면 폭을 바꿉니다" },
  ]);
}
function exportMenu(btn) {
  if (!app.pid) return toast("먼저 논문을 여세요");
  const ex = async (kind, marks) => {
    try { const r = await api.post(`/api/p/${app.pid}/export`, { kind, marks, reveal: true }); if (!r.cancel) toast("저장했습니다: " + r.path); } catch (e) { toast(e.message, "err"); }
  };
  menu(btn, [
    { head: "PDF로 저장" },
    { label: "한글 논문 (형광펜 포함)", icon: "file", fn: () => ex("ko", true) },
    { label: "한글 논문 (깨끗하게)", icon: "file", fn: () => ex("ko", false) },
    { label: "영어 원문 (형광펜 포함)", icon: "file", fn: () => ex("en", true) },
    { label: "대역본 (원문 | 번역 나란히)", icon: "layout", fn: () => ex("side", true) },
  ]);
}

/* ================================================================== progress / polling */
const Poll = {
  kick() { clearTimeout(this.t); this.tick(); },
  async tick() {
    clearTimeout(this.t);
    if (!app.pid) return;
    const pid = app.pid;
    let r;
    try { r = await api.get(`/api/p/${pid}/progress`); } catch (e) { this.t = setTimeout(() => this.tick(), 3000); return; }
    if (pid !== app.pid) return;
    const prevStatus = app.status;
    app.status = r.status;
    let changedPages = [];
    for (const [n, v] of Object.entries(r.page_rev || {})) if (app.pageRev[n] !== v) { app.pageRev[n] = v; changedPages.push(+n); }
    if (r.rev !== app.rev) {
      app.rev = r.rev;
      try {
        const u = await api.get(`/api/p/${pid}/units`);
        const changed = [];
        for (const x of u.units) { const o = app.units.get(x.id); if (!o || o.ko !== x.ko || o.err !== x.err || o.translate !== x.translate) changed.push(x.id); app.units.set(x.id, x); }
        app.paper.glossary = u.glossary; app.paper.tables = u.tables;
        if (Reader.tab === "text") { if (changed.length > 60) Reader.render(); else Reader.update(changed); }
        if (r.title && r.title !== app.paper.meta.title) { app.paper.meta.title = r.title; setTitle(); }
      } catch (e) { /* next tick */ }
    }
    changedPages.forEach(n => Viewers.ko.refreshPage(n));
    if (prevStatus !== r.status) { Viewers.ko.refreshAll(); if (r.status === "done" && prevStatus) toast("번역이 끝났습니다"); }
    if (r.field && app.paper.meta.field !== r.field) { app.paper.meta.field = r.field; setTitle(); }
    showProgress(r);
    const busy = r.running || ["queued", "analyzing", "glossary", "translating"].includes(r.status);
    this.t = setTimeout(() => this.tick(), busy ? 1200 : 6000);
  },
};
function showProgress(r) {
  const el = $("#prog"); el.hidden = false; el.innerHTML = ""; el.className = "";
  const p = r.progress || {}; const pct = p.total ? Math.round(p.done / p.total * 100) : 0;
  const label = { queued: "준비 중", analyzing: "논문 구조 분석 중", glossary: "분야·용어 파악 중", translating: `번역 중 ${pct}%` }[r.status];
  if (label && r.running !== false) el.append(h("i", { class: "spin" }), h("span", {}, label), r.status === "translating" ? h("span", { class: "bar" }, h("i", { style: { width: pct + "%" } })) : "");
  else if (r.status === "error") { el.className = "err"; el.append(h("span", { class: "dot" }), h("span", {}, "번역 중단됨 — 눌러서 확인")); }
  else if (r.status === "done") { el.className = "done"; el.append(h("span", { class: "dot" }), h("span", {}, r.error ? "번역 완료 (일부 실패)" : "번역 완료")); }
  else { el.append(h("span", {}, "대기")); }
  el.onclick = () => menu(el, [
    { head: r.error ? r.error.slice(0, 120) : (r.field ? `분야: ${r.field}` : "번역 상태") },
    ...(r.running ? [{ label: "번역 멈추기", icon: "stop", fn: () => api.post(`/api/p/${app.pid}/stop`).then(() => Poll.kick()) }]
      : [{ label: r.status === "done" ? "빠진 문단만 다시 번역" : "이어서 번역", icon: "redo", fn: () => api.post(`/api/p/${app.pid}/resume`).then(() => Poll.kick()) },
         { label: "처음부터 다시 번역", icon: "redo", fn: () => { if (confirmInline("처음부터 다시 번역할까요? 직접 고친 번역도 사라집니다.")) api.post(`/api/p/${app.pid}/resume`, { restart: true }).then(() => openPaper(app.pid)); } }]),
    { label: "설정 열기", icon: "gear", fn: settingsDialog },
  ]);
}
function confirmInline(msg) { return window.confirm(msg); }

/* ================================================================== home / library */
function setTitle() {
  const t = $("#docTitle"); t.innerHTML = "";
  if (!app.paper) return;
  const m = app.paper.meta;
  const tu = [...app.units.values()].find(u => u.kind === "title" && u.ko);
  const ko = tu ? [...app.units.values()].filter(u => u.kind === "title" && u.page === tu.page && u.ko).map(u => u.ko).join(" ") : "";
  t.append(h("span", { class: "t", title: (m.title || m.file) + (ko ? " / " + ko : "") }, ko || m.title || m.file || ""), m.field ? h("span", { class: "chip", title: "논문 분야(용어집 기준)" }, m.field) : "");
}
async function showHome() {
  app.pid = null; app.paper = null; clearTimeout(Poll.t);
  $("#prog").hidden = true; setTitle();
  const homeEl = $("#home"); homeEl.hidden = false;
  try { app.st = await api.get("/api/state"); } catch (e) { /* keep old */ }
  const lib = app.st.library;
  const drop = h("div", { class: "drop", onclick: openFile },
    h("div", { class: "big", html: ic("file") }), h("b", {}, "영어 논문 PDF를 끌어다 놓거나 눌러서 여세요"),
    h("span", {}, "레이아웃과 그림은 그대로 두고 글만 한국어로 바꾼 PDF를 만듭니다"));
  const list = h("div", { class: "lib" });
  if (!lib.length) list.append(h("div", { class: "empty" }, "아직 연 논문이 없습니다"));
  for (const p of lib) {
    const run = ["queued", "analyzing", "glossary", "translating"].includes(p.status);
    const pct = p.progress?.total ? Math.round(p.progress.done / p.progress.total * 100) : 0;
    const st = p.status === "done" ? h("span", { class: "st done" }, "번역 완료") : p.status === "error" ? h("span", { class: "st err" }, "중단됨") : h("span", { class: "st run" }, run ? `번역 중 ${pct}%` : "대기");
    const card = h("div", { class: "card", onclick: () => openPaper(p.id) },
      h("div", { class: "thumb" }, h("img", { loading: "lazy", src: `/api/p/${p.id}/page/ko/0.png?z=0.5&v=${p.status === "done" ? 1 : 0}`, onerror: function () { this.src = `/api/p/${p.id}/page/en/0.png?z=0.5`; } })),
      h("div", { class: "info" }, h("b", {}, p.title || p.file), h("span", {}, [p.field, p.pages && `${p.pages}쪽`, p.file].filter(Boolean).join(" · "))),
      st,
      h("button", { class: "icon", title: "목록에서 지우기", html: ic("trash"), onclick: async e => { e.stopPropagation(); if (!confirmInline(`'${p.title || p.file}'을(를) 지울까요? 번역·형광펜도 함께 지워집니다.`)) return; await api.post(`/api/p/${p.id}/delete`); showHome(); } }));
    list.append(card);
  }
  homeEl.innerHTML = "";
  homeEl.append(h("div", { class: "homein" },
    h("div", { class: "hero" }, h("h1", {}, "영어 논문을 한국어로, 나란히 읽기"), h("p", {}, "원문과 번역을 양옆에 두고, 읽기 쉬운 본문과 논문 도우미를 함께 씁니다.")),
    drop,
    h("div", { class: "howto" },
      h("div", {}, h("b", {}, "분야 맞춤 번역"), "논문 분야를 먼저 파악해 한국 학계에서 쓰는 용어로 옮깁니다. 용어집은 직접 고칠 수 있어요."),
      h("div", {}, h("b", {}, "모두 연결된 화면"), "읽기 화면에서 문단을 누르거나 드래그하면 원문과 번역 PDF의 같은 자리가 함께 표시됩니다."),
      h("div", {}, h("b", {}, "논문 도우미"), "논문에 대해 묻고 답의 근거 문단으로 바로 이동합니다. 중요한 곳은 형광펜으로 표시해 PDF로 저장할 수 있어요.")),
    h("div", { class: "libh" }, h("h2", {}, "최근 논문"), h("div", { class: "grow" })), list));
  if (!app.st.claude && app.st.settings.backend === "cli")
    homeEl.querySelector(".hero").append(h("p", { style: { color: "var(--warn)", marginTop: "8px" } }, "이 PC에서 Claude Code를 찾지 못했습니다. 설정에서 API 키를 넣거나 Claude Code를 설치·로그인하세요. ", h("a", { href: "#", onclick: e => { e.preventDefault(); settingsDialog(); } }, "설정 열기")));
  if (lib.some(p => ["queued", "analyzing", "glossary", "translating"].includes(p.status))) setTimeout(() => { if (!app.pid && !$("#home").hidden) showHome(); }, 4000);
}
async function openFile() {
  if (app.st?.app) {
    try { const r = await api.post("/api/open", {}); if (r.id) openPaper(r.id); } catch (e) { toast(e.message, "err"); }
  } else $("#fileIn").click();
}
async function uploadFile(f) {
  if (!f) return;
  if (!/\.pdf$/i.test(f.name) && f.type !== "application/pdf") return toast("PDF 파일만 열 수 있습니다", "err");
  toast(`'${f.name}'을(를) 여는 중…`);
  try {
    const r = await fetch("/api/upload", { method: "POST", headers: { "X-PB-Token": TOKEN, "X-File-Name": encodeURIComponent(f.name) }, body: await f.arrayBuffer() });
    const j = await r.json(); if (!r.ok) throw new Error(j.error); openPaper(j.id);
  } catch (e) { toast(e.message, "err"); }
}
async function openPaper(id) {
  let st;
  try { st = await api.get(`/api/p/${id}`); } catch (e) { return toast(e.message, "err"); }
  $("#home").hidden = true;
  app.pid = id; app.paper = st; app.units = new Map(st.units.map(u => [u.id, u])); app.order = st.units.map(u => u.id);
  app.pageRev = Object.fromEntries(Object.entries(st.meta.page_rev || {}).map(([k, v]) => [k, v]));
  app.rev = st.meta.rev ?? 0; app.status = st.meta.status;
  app.marks = (st.notes && st.notes.marks) || [];
  app.sel = { ids: [], text: "", from: null, precise: {} }; FindState.hits = []; Reader.q.value = ""; Reader.cnt.textContent = "";
  setTitle();
  Viewers.en.load(); Viewers.ko.load(); Reader.render();
  Chat.rev = -1; Chat.items = []; Chat.poll();
  Poll.kick();
  store.set("last", id);
}

/* ================================================================== boot */
async function boot() {
  app.st = await api.get("/api/state");
  const t = app.st.settings.theme || "system"; applyTheme(t);
  $("#openBtn").innerHTML = ic("open") + "열기"; $("#layoutBtn").innerHTML = ic("layout") + "배치"; $("#exportBtn").innerHTML = ic("save") + "저장"; $("#settingsBtn").innerHTML = ic("gear");
  $("#openBtn").onclick = openFile; $("#layoutBtn").onclick = e => layoutMenu(e.currentTarget); $("#exportBtn").onclick = e => exportMenu(e.currentTarget); $("#settingsBtn").onclick = settingsDialog;
  $("#homeBtn").onclick = showHome;
  $("#fileIn").onchange = e => { uploadFile(e.target.files[0]); e.target.value = ""; };
  Viewers.en = new Viewer("en"); Viewers.ko = new Viewer("ko"); Reader.build(); Chat.build();
  Layout.render(); setChatModel();
  // drag & drop a PDF anywhere
  let dz = 0;
  addEventListener("dragover", e => { if ([...e.dataTransfer.types].includes("Files")) { e.preventDefault(); $(".drop")?.classList.add("over"); } });
  addEventListener("dragleave", () => $(".drop")?.classList.remove("over"));
  addEventListener("drop", e => { if (!e.dataTransfer.files.length) return; e.preventDefault(); $(".drop")?.classList.remove("over"); uploadFile(e.dataTransfer.files[0]); });
  addEventListener("keydown", e => {
    const mod = e.ctrlKey || e.metaKey;
    if (mod && e.key.toLowerCase() === "o") { e.preventDefault(); openFile(); }
    else if (mod && e.key.toLowerCase() === "k") { e.preventDefault(); Chat.focus(); }
    else if (mod && e.key.toLowerCase() === "f" && app.pid) { e.preventDefault(); if (Layout.L.collapsed.reader) Layout.toggle("reader", false); Reader.setTab("text"); Reader.q.focus(); Reader.q.select(); }
    else if (e.key === "Escape" && !document.querySelector(".scrim")) { if (app.sel.ids.length) selectUnits([], null); hideSelbar(); }
  });
  matchMedia("(prefers-color-scheme: dark)").addEventListener("change", () => applyTheme(store.get("theme", "system")));
  const last = store.get("last", null);
  if (last && app.st.library.some(p => p.id === last)) openPaper(last); else showHome();
}
boot().catch(e => { document.body.innerHTML = `<pre style="padding:20px">시작 실패: ${esc(e.message)}</pre>`; });
