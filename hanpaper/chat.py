"""The paper agent: questions about the open paper, answered with the whole paper in context."""
import threading
import time

import llm
import papers
import settings

_sessions = {}


class Chat:
    def __init__(self, paper):
        self.p = paper
        self.items = papers.jload(paper.f("chat.json"), [])
        self.running = False
        self.stop = threading.Event()
        self.rev = 1
        self.lock = threading.Lock()

    def _save(self):
        papers.jsave(self.p.f("chat.json"), [dict(i, streaming=False) for i in self.items])

    def snapshot(self):
        with self.lock:
            return {"items": [dict(i) for i in self.items], "running": self.running, "rev": self.rev}

    def _paper_text(self):
        d = self.p.doc()
        if not d:
            return "(아직 분석 전)"
        out = []
        for u in d["units"]:
            if u["kind"] in ("running", "figtext", "other") or (u["kind"] == "table" and len(u["text"]) < 3):
                continue
            t = u["text"].strip()
            if not t:
                continue
            out.append(f"[{u['id']}|{u['kind']}|p{u['page'] + 1}] {t}")
        return "\n".join(out)

    def system(self):
        g = self.p.glossary()
        st = settings.get()
        web = ("\n- 관련 연구·최신 동향처럼 논문 밖 정보가 필요하면 웹 검색을 써도 된다. 쓴 출처는 링크로 밝힌다."
               if st.get("web_search") else "")
        return papers.CHAT_SYSTEM.format(field=g.get("field") or "미상", web=web,
                                         glossary="\n".join(f"- {t['en']} → {t['ko']}" for t in g.get("terms", [])[:120]) or "(없음)",
                                         paper=self._paper_text())

    def send(self, text, context=None):
        if self.running:
            return False
        q = text.strip()
        shown = q
        if context and context.get("text"):
            q = f"[사용자가 선택한 부분 ({', '.join(context.get('units') or [])})]\n«{context['text'][:3000]}»\n\n{q}"
        with self.lock:
            self.items.append({"role": "user", "text": shown, "context": (context or {}).get("text", "")[:300] or None,
                               "units": (context or {}).get("units"), "prompt": q, "at": time.time()})
            self.items.append({"role": "assistant", "text": "", "streaming": True, "tools": [], "at": time.time()})
            self.rev += 1
            self.running = True
            self.stop.clear()
        threading.Thread(target=self._run, daemon=True).start()
        return True

    def _run(self):
        cur = self.items[-1]
        msgs = []
        for i in self.items[:-1]:
            if i["role"] in ("user", "assistant") and (i.get("prompt") or i.get("text")):
                msgs.append({"role": i["role"], "content": i.get("prompt") or i["text"]})
        msgs = msgs[-20:]
        while msgs and msgs[0]["role"] != "user":
            msgs.pop(0)
        st = settings.get()
        try:
            for piece in llm.stream(self.system(), msgs, "chat", st.get("effort_chat") or "medium",
                                    bool(st.get("web_search")), self.stop):
                with self.lock:
                    if isinstance(piece, dict):
                        cur["tools"].append(piece)
                    else:
                        cur["text"] += piece
                    self.rev += 1
            if self.stop.is_set():
                cur["text"] += "\n\n_(중단됨)_"
        except llm.LLMError as ex:
            cur["error"] = str(ex)
        except Exception as ex:  # noqa: BLE001
            cur["error"] = f"{type(ex).__name__}: {ex}"
        with self.lock:
            cur["streaming"] = False
            self.running = False
            self.rev += 1
        self._save()

    def cancel(self):
        self.stop.set()

    def clear(self):
        if self.running:
            return False
        with self.lock:
            self.items = []
            self.rev += 1
        self._save()
        return True


def of(paper):
    c = _sessions.get(paper.id)
    if c is None:
        c = _sessions[paper.id] = Chat(paper)
    return c
