"""Talking to Claude in one of two ways, chosen in Settings:

  cli  the Claude Code CLI already logged in on this PC (`claude -p`, the user's own subscription/login)
  api  an Anthropic API key (official `anthropic` SDK)

Both expose the same two calls: complete() for one-shot work (translation, glossary, note summaries) and
stream() for the chat agent (yields text deltas).
"""
import json
import os
import shutil
import subprocess
import tempfile
import threading
import time

import paths
import settings

MODELS = [
    {"id": "claude-opus-5-5", "label": "Claude Opus 5.5 (권장)"},
    {"id": "claude-sonnet-5-5", "label": "Claude Sonnet 5.5 (빠름)"},
    {"id": "claude-haiku-5-5", "label": "Claude Haiku 5.5 (가장 빠르고 저렴)"},
    {"id": "claude-fable-5-2", "label": "Claude Fable 5.2 (최고 성능)"},
]


class LLMError(Exception):
    pass


def _env():
    env = {k: v for k, v in os.environ.items() if k not in ("CLAUDECODE", "ANTHROPIC_API_KEY")}
    if paths.MAC:                                     # GUI apps on macOS start with a bare PATH; node may be needed
        env["PATH"] = ":".join([env.get("PATH", ""), "/opt/homebrew/bin", "/usr/local/bin", os.path.expanduser("~/.local/bin")])
    return env


# ------------------------------------------------------------------------------------------------ CLI backend
def _tmpdir():
    d = os.path.join(paths.DATA, "tmp")
    os.makedirs(d, exist_ok=True)
    return d


def _cleanup(cmd):
    if "--system-prompt-file" in cmd:
        try:
            os.remove(cmd[cmd.index("--system-prompt-file") + 1])
        except OSError:
            pass


def _cli_base(model, system, effort=None, tools=""):
    exe = paths.claude_exe()
    if not exe:
        raise LLMError("Claude Code(claude)를 찾을 수 없습니다. 설정에서 API 키 방식으로 바꾸거나 Claude Code를 설치하고 로그인하세요.")
    # the system prompt goes through a file: it holds the whole paper, longer than a Windows command line allows
    fd, spf = tempfile.mkstemp(prefix="pb_sys_", suffix=".txt", dir=_tmpdir())
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(system)
    cmd = [exe, "-p", "--model", model, "--no-session-persistence", "--strict-mcp-config", "--setting-sources", "",
           "--tools", tools, "--system-prompt-file", spf]
    if effort:
        cmd += ["--effort", effort]
    return cmd


def _popen(cmd):
    return subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            env=_env(), cwd=paths.DATA, creationflags=paths.NOWIN)


def _cli_complete(system, user, model, effort, timeout):
    cmd = _cli_base(model, system, effort) + ["--output-format", "json"]
    p = _popen(cmd)
    try:
        out, err = p.communicate(user.encode("utf-8"), timeout=timeout)
    except subprocess.TimeoutExpired:
        p.kill()
        raise LLMError("응답 시간이 초과되었습니다")
    finally:
        _cleanup(cmd)
    try:
        r = json.loads(out.decode("utf-8", "replace"))
    except ValueError:
        raise LLMError((err.decode("utf-8", "replace") or out.decode("utf-8", "replace") or "claude 실행 실패").strip()[-500:])
    if r.get("is_error"):
        msg = str(r.get("result") or r.get("subtype") or "오류")
        if "login" in msg.lower() or "auth" in msg.lower():
            msg += "\n(터미널에서 `claude`를 실행해 로그인했는지 확인하세요)"
        raise LLMError(msg[:600])
    return r.get("result") or ""


def _cli_stream(system, messages, model, effort, web, stop):
    convo = []
    for m in messages[:-1]:
        convo.append(("[사용자]\n" if m["role"] == "user" else "[어시스턴트]\n") + m["content"])
    prompt = (("[이전 대화]\n" + "\n\n".join(convo) + "\n\n") if convo else "") + "[지금 질문]\n" + messages[-1]["content"]
    cmd = _cli_base(model, system, effort, tools="WebSearch,WebFetch" if web else "")
    cmd += ["--output-format", "stream-json", "--verbose", "--include-partial-messages"]
    if web:
        cmd += ["--permission-mode", "dontAsk", "--allowedTools", "WebSearch", "WebFetch"]
    p = _popen(cmd)
    try:
        yield from _cli_events(p, prompt, stop)
    finally:
        _cleanup(cmd)
        if p.poll() is None:
            p.kill()


def _cli_events(p, prompt, stop):
    p.stdin.write(prompt.encode("utf-8"))
    p.stdin.close()
    got_text, result = False, None
    for raw in p.stdout:
        if stop and stop.is_set():
            p.kill()
            return
        try:
            e = json.loads(raw.decode("utf-8", "replace"))
        except ValueError:
            continue
        t = e.get("type")
        if t == "stream_event" and e.get("parent_tool_use_id") is None:
            ev = e.get("event", {})
            if ev.get("type") == "content_block_delta" and ev.get("delta", {}).get("type") == "text_delta":
                got_text = True
                yield ev["delta"]["text"]
            elif ev.get("type") == "content_block_start" and ev.get("content_block", {}).get("type") == "text" and got_text:
                yield "\n\n"
        elif t == "assistant":
            for c in e.get("message", {}).get("content", []):
                if c.get("type") == "tool_use":
                    yield {"tool": c.get("name"), "arg": str((c.get("input") or {}).get("query") or (c.get("input") or {}).get("url") or "")[:120]}
        elif t == "result":
            result = e
    p.wait()
    if result is not None and result.get("is_error"):
        raise LLMError(str(result.get("result") or result.get("subtype"))[:600])
    if result is None and p.returncode:
        raise LLMError((p.stderr.read().decode("utf-8", "replace") or f"claude 종료 코드 {p.returncode}").strip()[-500:])
    if not got_text and result is not None and result.get("result"):
        yield result["result"]


# ------------------------------------------------------------------------------------------------ API backend
_client = None
_client_key = None
_lock = threading.Lock()


def _api():
    global _client, _client_key
    key = settings.get().get("api_key", "").strip()
    if not key:
        raise LLMError("API 키가 없습니다. 설정에서 Anthropic API 키를 입력하세요.")
    with _lock:
        if _client is None or _client_key != key:
            import anthropic
            _client, _client_key = anthropic.Anthropic(api_key=key, max_retries=3), key
    return _client


def _api_err(ex):
    import anthropic
    if isinstance(ex, anthropic.AuthenticationError):
        return LLMError("API 키가 올바르지 않습니다 (인증 실패)")
    if isinstance(ex, anthropic.RateLimitError):
        return LLMError("요청 한도를 넘었습니다. 잠시 후 다시 시도하세요 (rate limit)")
    if isinstance(ex, anthropic.APIStatusError):
        return LLMError(f"API 오류 {ex.status_code}: {str(ex.message)[:300]}")
    if isinstance(ex, anthropic.APIConnectionError):
        return LLMError("API 서버에 연결할 수 없습니다 (네트워크 확인)")
    return LLMError(repr(ex)[:300])


def _fallback_kw(model):
    if model in ("claude-opus-5-5", "claude-sonnet-5-5", "claude-fable-5-2"):
        return {"betas": ["server-side-fallback-2026-07-01"], "fallbacks": "default"}
    return {}


def _api_stream_call(model, system, messages, effort, max_tokens, tools=None):
    c = _api()
    kw = dict(model=model, max_tokens=max_tokens, system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
              messages=messages)
    if effort and not model.startswith("claude-haiku-4"):
        kw["output_config"] = {"effort": effort}
    if tools:
        kw["tools"] = tools
    fb = _fallback_kw(model)
    if fb:
        try:
            return c.beta.messages.stream(**kw, **fb)
        except TypeError:                              # SDK without the fallback parameters
            pass
    return c.messages.stream(**kw)


def _api_complete(system, user, model, effort):
    import anthropic
    try:
        with _api_stream_call(model, system, [{"role": "user", "content": user}], effort, 64000) as s:
            msg = s.get_final_message()
    except anthropic.APIError as ex:
        raise _api_err(ex)
    if msg.stop_reason == "refusal":
        raise LLMError("모델이 이 요청을 거절했습니다")
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


def _api_stream(system, messages, model, effort, web, stop):
    import anthropic
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 5}] if web else None
    try:
        with _api_stream_call(model, system, messages, effort, 32000, tools) as s:
            for ev in s:
                if stop and stop.is_set():
                    return
                if ev.type == "content_block_start" and getattr(ev.content_block, "type", "") == "server_tool_use":
                    yield {"tool": "WebSearch", "arg": ""}
                elif ev.type == "content_block_delta" and getattr(ev.delta, "type", "") == "text_delta":
                    yield ev.delta.text
            msg = s.get_final_message()
            if msg.stop_reason == "refusal":
                raise LLMError("모델이 이 요청을 거절했습니다")
    except anthropic.APIError as ex:
        raise _api_err(ex)


# ------------------------------------------------------------------------------------------------ OpenAI: Codex CLI
def _codex_exe():
    found = shutil.which("codex")
    if found:
        return found
    home = os.path.expanduser("~")
    cands = [os.path.join(os.environ.get("APPDATA", ""), "npm", "codex.cmd"), os.path.join(home, ".local", "bin", "codex"),
             "/opt/homebrew/bin/codex", "/usr/local/bin/codex", os.path.join(home, ".npm-global", "bin", "codex")]
    return next((c for c in cands if os.path.isfile(c)), None)


def codex_models():
    """Models the local Codex knows (its model cache), and its configured default."""
    home = os.path.join(os.path.expanduser("~"), ".codex")
    out, default = [], None
    try:
        d = json.load(open(os.path.join(home, "models_cache.json"), encoding="utf-8"))
        for m in d.get("models", []):
            slug = m.get("slug") or m.get("id")
            if slug and "review" not in slug:
                out.append({"id": slug, "label": m.get("display_name") or slug})
    except (OSError, ValueError, AttributeError):
        pass
    try:
        for line in open(os.path.join(home, "config.toml"), encoding="utf-8"):
            s = line.strip()
            if s.startswith("model ") or s.startswith("model="):
                default = s.split("=", 1)[1].strip().strip("\"'")
                break
    except OSError:
        pass
    if not out:
        out = [{"id": m, "label": m} for m in ("gpt-6.1-sol", "gpt-6-sol", "gpt-5.6-sol", "gpt-5.5")]
    return out, default


def _codex_cmd(model, effort, web):
    exe = _codex_exe()
    if not exe:
        raise LLMError("Codex CLI(codex)를 찾을 수 없습니다. 설정에서 OpenAI API 키 방식으로 바꾸거나 Codex를 설치하고 로그인하세요.")
    cmd = [exe, "exec", "--skip-git-repo-check", "--ephemeral", "--sandbox", "read-only", "--color", "never", "--json",
           "-C", _tmpdir()]
    if model:
        cmd += ["-m", model]
    if effort:
        cmd += ["-c", f"model_reasoning_effort={effort}"]
    if web:
        cmd += ["-c", "tools.web_search=true"]
    return cmd + ["-"]


def _codex_events(system, prompt, model, effort, web, stop=None, timeout=900):
    """Run `codex exec` and yield ("text", str) / ("tool", dict) events."""
    p = _popen(_codex_cmd(model, effort, web))
    p.stdin.write(f"<instructions>\n{system}\n</instructions>\n\n{prompt}".encode("utf-8"))
    p.stdin.close()
    err = None
    t0 = time.time()
    try:
        for raw in p.stdout:
            if stop is not None and stop.is_set():
                p.kill()
                return
            if time.time() - t0 > timeout:
                p.kill()
                raise LLMError("응답 시간이 초과되었습니다")
            try:
                e = json.loads(raw.decode("utf-8", "replace"))
            except ValueError:
                continue
            t = e.get("type", "")
            item = e.get("item") or {}
            if t == "item.completed" and item.get("type") in ("agent_message", "assistant_message"):
                yield "text", item.get("text") or ""
            elif t == "item.started" and item.get("type") in ("web_search", "web_search_call"):
                yield "tool", {"tool": "WebSearch", "arg": str(item.get("query") or "")[:120]}
            elif t == "turn.failed":
                err = (e.get("error") or {}).get("message") or "Codex 오류"
            elif t == "error" and not str(e.get("message", "")).startswith("Reconnecting"):
                err = e.get("message")
        p.wait()
    finally:
        if p.poll() is None:
            p.kill()
    if err:
        low = err.lower()
        if "rate limit" in low or "tokens per min" in low:
            err = "Codex 계정의 요청 한도를 넘었습니다 (rate limit). " + err[:300]
        elif "login" in low or "auth" in low:
            err += "\n(터미널에서 `codex login`으로 로그인했는지 확인하세요)"
        raise LLMError(err[:700])
    if p.returncode:
        raise LLMError((p.stderr.read().decode("utf-8", "replace") or f"codex 종료 코드 {p.returncode}").strip()[-500:])


def _codex_complete(system, user, model, effort, timeout):
    parts = [v for k, v in _codex_events(system, user, model, effort, False, timeout=timeout) if k == "text"]
    if not parts:
        raise LLMError("Codex가 답을 주지 않았습니다")
    return parts[-1]


def _codex_stream(system, messages, model, effort, web, stop):
    convo = [("[사용자]\n" if m["role"] == "user" else "[어시스턴트]\n") + m["content"] for m in messages[:-1]]
    prompt = (("[이전 대화]\n" + "\n\n".join(convo) + "\n\n") if convo else "") + "[지금 질문]\n" + messages[-1]["content"]
    first = True
    for k, v in _codex_events(system, prompt, model, effort, web, stop):
        if k == "text":
            yield ("" if first else "\n\n") + v
            first = False
        else:
            yield v


# ------------------------------------------------------------------------------------------------ OpenAI: API key
_oa = {"client": None, "key": None}


def _openai():
    key = settings.get().get("openai_key", "").strip()
    if not key:
        raise LLMError("OpenAI API 키가 없습니다. 설정에서 키를 입력하세요.")
    with _lock:
        if _oa["client"] is None or _oa["key"] != key:
            import openai
            _oa["client"], _oa["key"] = openai.OpenAI(api_key=key, max_retries=3), key
    return _oa["client"]


def _oa_err(ex):
    import openai
    if isinstance(ex, openai.AuthenticationError):
        return LLMError("OpenAI API 키가 올바르지 않습니다 (인증 실패)")
    if isinstance(ex, openai.RateLimitError):
        return LLMError("OpenAI 요청 한도를 넘었습니다 (rate limit). 잠시 후 다시 시도하거나 결제·한도를 확인하세요")
    if isinstance(ex, openai.APIStatusError):
        return LLMError(f"OpenAI API 오류 {ex.status_code}: {str(ex.message)[:300]}")
    if isinstance(ex, openai.APIConnectionError):
        return LLMError("OpenAI 서버에 연결할 수 없습니다 (네트워크 확인)")
    return LLMError(repr(ex)[:300])


def _oa_kwargs(model, system, inp, effort, tools=None):
    kw = {"model": model, "instructions": system, "input": inp}
    if effort:
        kw["reasoning"] = {"effort": effort}
    if tools:
        kw["tools"] = tools
    return kw


def _oa_complete(system, user, model, effort):
    import openai
    c = _openai()
    kw = _oa_kwargs(model, system, user, effort)
    try:
        try:
            r = c.responses.create(**kw)
        except openai.BadRequestError:
            kw.pop("reasoning", None)                  # a model without reasoning settings
            r = c.responses.create(**kw)
    except openai.APIError as ex:
        raise _oa_err(ex)
    return r.output_text or ""


def _oa_stream(system, messages, model, effort, web, stop):
    import openai
    c = _openai()
    inp = [{"role": m["role"], "content": m["content"]} for m in messages]
    tries = [_oa_kwargs(model, system, inp, effort, [{"type": "web_search"}] if web else None),
             _oa_kwargs(model, system, inp, None, None)]
    for i, kw in enumerate(tries):
        try:
            with c.responses.stream(**kw) as s:
                for ev in s:
                    if stop is not None and stop.is_set():
                        return
                    t = getattr(ev, "type", "")
                    if t == "response.output_text.delta":
                        yield ev.delta
                    elif t == "response.web_search_call.in_progress":
                        yield {"tool": "WebSearch", "arg": ""}
            return
        except openai.BadRequestError as ex:
            if i == len(tries) - 1:
                raise _oa_err(ex)
        except openai.APIError as ex:
            raise _oa_err(ex)


# ------------------------------------------------------------------------------------------------ public
def provider():
    return settings.get().get("provider", "claude")


def backend():
    st = settings.get()
    return st.get("openai_backend", "cli") if provider() == "openai" else st.get("backend", "cli")


def model_for(role):
    st = settings.get()
    if provider() == "openai":
        key = "openai_model_translate" if role == "translate" else "openai_model_chat"
        return st.get(key) or codex_models()[1] or "gpt-5.6-sol"
    return st.get("model_translate" if role == "translate" else "model_chat")


def complete(system, user, role="translate", effort=None, timeout=900):
    model = model_for(role)
    if provider() == "openai":
        if backend() == "api":
            return _oa_complete(system, user, model, effort)
        return _codex_complete(system, user, model, effort, timeout)
    if backend() == "api":
        return _api_complete(system, user, model, effort)
    return _cli_complete(system, user, model, effort, timeout)


def stream(system, messages, role="chat", effort=None, web=False, stop=None):
    model = model_for(role)
    if provider() == "openai":
        gen = _oa_stream if backend() == "api" else _codex_stream
    else:
        gen = _api_stream if backend() == "api" else _cli_stream
    yield from gen(system, messages, model, effort, web, stop)


def status():
    """What the Settings dialog shows: which local CLIs exist and the OpenAI models Codex knows."""
    models, default = codex_models()
    return {"claude": bool(paths.claude_exe()), "codex": bool(_codex_exe()), "openai_models": models, "codex_default": default}


def check():
    """Quick connection test for the Settings dialog."""
    if provider() == "openai":
        name = "Codex" if backend() == "cli" else "OpenAI API"
    else:
        name = "Claude Code" if backend() == "cli" else "Claude API"
    try:
        complete("Reply with exactly: OK", "ping", role="translate", effort="low", timeout=150)
        return {"ok": True, "msg": f"{name} 연결됨 · {model_for('translate')}"}
    except LLMError as ex:
        return {"ok": False, "msg": f"{name}: {ex}"}


def parse_json(text):
    """The first JSON object/array in a model reply (tolerates code fences and chatter)."""
    t = text.strip()
    if t.startswith("```"):
        t = t.split("\n", 1)[1] if "\n" in t else t
        t = t.rsplit("```", 1)[0]
    for opener, closer in (("{", "}"), ("[", "]")):
        i = t.find(opener)
        j = t.rfind(closer)
        if i != -1 and j > i:
            try:
                return json.loads(t[i:j + 1])
            except ValueError:
                continue
    raise LLMError("모델 응답을 해석하지 못했습니다")
