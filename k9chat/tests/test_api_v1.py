# SPDX-License-Identifier: Apache-2.0
"""The "ask the framework" API contract (api_v1.py): who may call, what they
may change, how refusals look, and the answer shape, simulated and real
(with a stand-in for k9chat.chat, so no model or GPU is needed)."""
import json
import os
import sys
import types
import uuid

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
EXAMPLES_ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
FRAMEWORK_ROOT = os.environ.get("K9AIF_FRAMEWORK_PATH", os.path.join(EXAMPLES_ROOT, "..", "k9-aif-framework"))
for p in (EXAMPLES_ROOT, os.path.abspath(FRAMEWORK_ROOT)):
    if p not in sys.path:
        sys.path.insert(0, p)

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from k9chat import api_v1, gpu_telemetry  # noqa: E402

KEY = "test-key-" + uuid.uuid4().hex


def make_client(simulated=True, anonymous=False, pinned="", roles=("ask", "ask_options"),
                budget=None, anon_per_ip=None, locked=False, secret=""):
    name = "studio" + uuid.uuid4().hex[:6]            # fresh budget counters per test
    config = {"api": {
        "enabled": "true", "simulated": str(simulated).lower(), "max_body_bytes": 2048,
        "callers": {name: {"env": "K", "from_env": "K_FROM", "roles": list(roles),
                           "budget": budget or [{"max": 100, "window_seconds": 600}]}},
        "anonymous": {"enabled": str(anonymous).lower(), "allowed_origins": ["https://k9x.ai"],
                      "turnstile_secret": secret, "turnstile_hostnames": ["k9x.ai"],
                      "per_ip": anon_per_ip or [{"max": 100, "window_seconds": 600}],
                      "global": [{"max": 1000, "window_seconds": 86400}]},
    }}
    api = api_v1.AskApi(config, environ={"K": KEY, "K_FROM": pinned}, framework_locked=lambda: locked)
    app = FastAPI()
    app.include_router(api_v1.build_router(api))
    return TestClient(app)


def bearer(key=KEY):
    return {"Authorization": f"Bearer {key}"}


def ask(client, body=None, headers=None, stream=False):
    body = body or {"question": "How do I add a HIL step in Studio?"}
    body.setdefault("options", {}).setdefault("stream", stream)
    return client.post("/api/v1/ask", json=body, headers=headers or bearer())


def sse_events(text):
    out = []
    for block in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in block.splitlines())
        out.append((lines["event"], json.loads(lines["data"])))
    return out


# ── who may call ─────────────────────────────────────────────────────────────
def test_no_header_is_401_with_bearer_challenge():
    r = make_client().post("/api/v1/ask", json={"question": "hi"})
    assert r.status_code == 401
    assert r.headers["WWW-Authenticate"].startswith("Bearer")
    assert r.json()["error"]["code"] == "unauthorized"


def test_wrong_key_and_wrong_scheme_are_401():
    c = make_client()
    assert ask(c, headers=bearer("nope")).status_code == 401
    assert ask(c, headers={"Authorization": f"Basic {KEY}"}).status_code == 401


def test_key_in_query_string_is_ignored():
    r = make_client().post(f"/api/v1/ask?api_key={KEY}&token={KEY}", json={"question": "hi"})
    assert r.status_code == 401


def test_good_key_answers():
    r = ask(make_client())
    assert r.status_code == 200
    body = r.json()
    assert body["simulated"] is True and body["answer"]
    assert set(body) >= {"answer", "session_id", "sources", "answered_by", "model", "elapsed_ms", "options_applied"}


def test_key_without_ask_role_is_403():
    assert ask(make_client(roles=("ask_options",))).status_code == 403


def test_pinned_key_works_only_from_its_address_and_never_via_tunnel():
    c = make_client(pinned="testclient")                # TestClient's peer name
    assert ask(c).status_code == 200
    via_tunnel = {**bearer(), "CF-Connecting-IP": "203.0.113.9"}
    assert ask(c, headers=via_tunnel).status_code == 401
    assert ask(make_client(pinned="10.89.0.12")).status_code == 401


# ── anonymous (browser on k9x.ai) ────────────────────────────────────────────
def test_anonymous_off_means_bearer_required():
    r = make_client().post("/api/v1/ask", json={"question": "hi"},
                           headers={"Origin": "https://k9x.ai", "X-Turnstile-Token": "t"})
    assert r.status_code == 401


def test_anonymous_needs_allowed_origin_and_turnstile():
    c = make_client(anonymous=True)
    bad_origin = {"Origin": "https://evil.example", "X-Turnstile-Token": "t"}
    assert ask(c, headers=bad_origin).json()["error"]["code"] == "origin_not_allowed"
    no_token = {"Origin": "https://k9x.ai"}
    assert ask(c, headers=no_token).json()["error"]["code"] == "challenge_required"
    ok = ask(c, headers={"Origin": "https://k9x.ai", "X-Turnstile-Token": "t"})
    assert ok.status_code == 200
    assert ok.headers["Access-Control-Allow-Origin"] == "https://k9x.ai"


def test_anonymous_without_turnstile_secret_is_refused_when_real():
    c = make_client(simulated=False, anonymous=True)
    r = ask(c, headers={"Origin": "https://k9x.ai", "X-Turnstile-Token": "t"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "challenge_failed"


def test_turnstile_token_from_another_site_is_refused(monkeypatch):
    c = make_client(anonymous=True, secret="s")
    monkeypatch.setattr(api_v1.AskApi, "_verify_turnstile", lambda self, t, ip: False)
    r = ask(c, headers={"Origin": "https://k9x.ai", "X-Turnstile-Token": "t"})
    assert r.json()["error"]["code"] == "challenge_failed"


def test_preflight_never_allows_authorization_header():
    c = make_client(anonymous=True)
    r = c.options("/api/v1/ask", headers={"Origin": "https://k9x.ai", "Access-Control-Request-Method": "POST"})
    assert r.status_code == 204
    assert "authorization" not in r.headers["Access-Control-Allow-Headers"].lower()
    other = c.options("/api/v1/ask", headers={"Origin": "https://evil.example"})
    assert "Access-Control-Allow-Origin" not in other.headers


# ── options ──────────────────────────────────────────────────────────────────
def test_defaults_framework_faq_on_internet_eval_off_stream_on():
    r = make_client().get("/api/v1/ask/options")
    assert r.json()["defaults"] == {"framework": True, "faq": True, "internet": False, "stream": True, "eval": False}


def test_applied_options_and_one_switch_rule():
    c = make_client()
    applied = ask(c, {"question": "q", "options": {"internet": True}}).json()["options_applied"]
    assert applied["framework"] is False and applied["internet"] is True and applied["faq"] is False
    bad = ask(c, {"question": "q", "options": {"framework": True, "internet": True}})
    assert bad.status_code == 400 and bad.json()["error"]["code"] == "invalid"


def test_anonymous_cannot_change_guarded_options_but_may_change_faq():
    c = make_client(anonymous=True)
    h = {"Origin": "https://k9x.ai", "X-Turnstile-Token": "t"}
    for opt in ({"internet": True}, {"framework": False}, {"eval": True}):
        r = ask(c, {"question": "q", "options": dict(opt)}, headers=h)
        assert r.status_code == 403 and r.json()["error"]["code"] == "option_not_allowed"
    assert ask(c, {"question": "q", "options": {"faq": False}}, headers=h).status_code == 200


def test_key_without_ask_options_role_cannot_turn_internet_on():
    r = ask(make_client(roles=("ask",)), {"question": "q", "options": {"internet": True}})
    assert r.status_code == 403


def test_locked_framework_mode_wins_over_caller():
    applied = ask(make_client(locked=True), {"question": "q", "options": {"internet": True}}).json()["options_applied"]
    assert applied["framework"] is True and applied["internet"] is False


# ── refusals that cost nothing ───────────────────────────────────────────────
def test_body_over_cap_is_413():
    r = ask(make_client(), {"question": "x" * 3000})
    assert r.status_code == 413 and r.json()["error"]["code"] == "too_large"


def test_bad_shapes_are_400():
    c = make_client()
    for body in ({"question": ""}, {"question": "q", "surprise": 1}, {"question": "q", "session_id": "../x"}):
        r = c.post("/api/v1/ask", json=body, headers=bearer())
        assert r.status_code == 400 and r.json()["error"]["code"] == "invalid", body


def test_budget_is_429_with_retry_after():
    c = make_client(budget=[{"max": 2, "window_seconds": 600}])
    assert ask(c).status_code == 200 and ask(c).status_code == 200
    r = ask(c)
    assert r.status_code == 429 and r.headers["Retry-After"] == "600"


# ── streaming (simulated) ────────────────────────────────────────────────────
def test_stream_is_tokens_then_done_with_full_json():
    r = ask(make_client(), stream=True)
    assert r.headers["content-type"].startswith("text/event-stream")
    events = sse_events(r.text)
    assert events[0][0] == "token" and events[-1][0] == "done"
    done = events[-1][1]
    assert "".join(e[1]["text"] for e in events[:-1]).strip() == done["answer"].strip()


# ── real path, with a stand-in for k9chat.chat ───────────────────────────────
@pytest.fixture
def fake_chat(monkeypatch):
    calls = {"internet": [], "faq": None, "blocked": False}
    mod = types.ModuleType("k9chat.chat")
    mod.set_session_internet = lambda v: calls["internet"].append(v) or "token"
    mod.reset_session_internet = lambda t: None
    mod.check_faq_shortcut = lambda text, sid: calls["faq"]
    mod.evaluate_response = lambda q, a: None
    mod.get_chat_runtime_info = lambda: {"model": "fake-model"}

    def send_message(text, session_id="default", sources_out=None, **_):
        if calls["blocked"]:
            raise PermissionError("[PromptInjectionCheck] blocked")
        calls["session_id"] = session_id
        sources_out.extend([{"source": "k9x-videos/uXv8gF3xiXc:0"}, {"source": "k9x-studio-readme:3"}])
        return {"text": "Drag the HIL Orchestrator onto the canvas."}

    async def send_message_stream(text, session_id="default", sources_out=None, **_):
        sources_out.append({"source": "k9x-studio-readme:3"})
        for part in ("Drag the HIL ", "Orchestrator."):
            yield part

    mod.send_message, mod.send_message_stream = send_message, send_message_stream
    monkeypatch.setitem(sys.modules, "k9chat.chat", mod)
    import k9chat
    monkeypatch.setattr(k9chat, "chat", mod, raising=False)
    monkeypatch.setattr(gpu_telemetry, "is_over_temp_limit", lambda: False)
    return calls


def test_real_answer_with_sources_and_namespaced_session(fake_chat):
    body = ask(make_client(simulated=False), {"question": "q", "session_id": "abc"}).json()
    assert body["answered_by"] == "model" and body["model"] == "fake-model" and body["simulated"] is False
    assert {"source": "k9x-videos/uXv8gF3xiXc", "url": "https://www.youtube.com/watch?v=uXv8gF3xiXc"} in body["sources"]
    assert fake_chat["session_id"].startswith("api-studio") and fake_chat["session_id"].endswith("-abc")
    assert fake_chat["internet"] == [False]


def test_real_faq_shortcut_answers_without_model(fake_chat):
    fake_chat["faq"] = {"answer": "From the FAQ.", "source": "k9chat/faq"}
    body = ask(make_client(simulated=False)).json()
    assert body["answered_by"] == "faq" and body["answer"] == "From the FAQ."


def test_real_shield_block_is_422(fake_chat):
    fake_chat["blocked"] = True
    r = ask(make_client(simulated=False))
    assert r.status_code == 422 and r.json()["error"]["code"] == "blocked"


def test_real_stream(fake_chat):
    events = sse_events(ask(make_client(simulated=False), stream=True).text)
    assert [e for e, _ in events] == ["token", "token", "done"]
    assert events[-1][1]["answer"] == "Drag the HIL Orchestrator."


# ── health (for the k9x dashboard) ───────────────────────────────────────────
def test_health_is_public_and_says_simulated(monkeypatch):
    mod = types.ModuleType("k9chat.chat")
    mod.get_k9chat_version = lambda: "abc1234"
    mod.get_health_status = lambda: {"ok": True}
    monkeypatch.setitem(sys.modules, "k9chat.chat", mod)
    import k9chat
    monkeypatch.setattr(k9chat, "chat", mod, raising=False)
    r = make_client().get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok" and r.json()["simulated"] is True and "base_url" not in r.text
