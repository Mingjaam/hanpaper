"""User settings (DATA/settings.json). The API key is stored only on this PC, readable by this user only."""
import json
import os
import threading

import paths

DEFAULTS = {
    "provider": "claude",                # claude | openai
    "backend": "cli",                    # Claude: cli = Claude Code logged in on this PC, api = Anthropic API key
    "api_key": "",
    "openai_backend": "cli",             # OpenAI: cli = Codex logged in on this PC, api = OpenAI API key
    "openai_key": "",
    "openai_model_translate": "",        # empty = Codex's configured model
    "openai_model_chat": "",
    "model_translate": "claude-opus-5-5",
    "effort_translate": "low",
    "model_chat": "claude-opus-5-5",
    "effort_chat": "medium",
    "workers": 3,
    "translate_refs": False,
    "translate_tables": True,
    "web_search": True,
    "theme": "system",
}
_lock = threading.Lock()
_cache = None


def get():
    global _cache
    with _lock:
        if _cache is None:
            try:
                _cache = {**DEFAULTS, **json.load(open(paths.SETTINGS, encoding="utf-8"))}
            except (OSError, ValueError):
                _cache = dict(DEFAULTS)
        return dict(_cache)


def update(d):
    global _cache
    cur = get()
    for k, v in d.items():
        if k in DEFAULTS:
            cur[k] = v
    with _lock:
        _cache = cur
        tmp = paths.SETTINGS + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(cur, f, ensure_ascii=False, indent=1)
        os.replace(tmp, paths.SETTINGS)
        try:
            os.chmod(paths.SETTINGS, 0o600)
        except OSError:
            pass
    return cur


def public():
    s = get()
    for name in ("api_key", "openai_key"):
        k = s.pop(name, "")
        s[name + "_set"] = bool(k)
        s[name + "_hint"] = (k[:7] + "…" + k[-4:]) if len(k) > 14 else ""
    return s
