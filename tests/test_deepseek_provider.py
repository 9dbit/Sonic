"""Native DeepSeek contract and execution boundaries, using synthetic replies only.

No real provider credentials, paid requests, Windows actions or external network.
"""
from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from sqlalchemy import select

from sonic import providers
from sonic.db import BrainUsage, ChatMessage, session_factory
from tests.test_engine_v04 import login


SELECTION = {"provider": "deepseek", "model": "deepseek-flash"}
FAKE_KEY = "synthetic-deepseek-secret"


@pytest.fixture(autouse=True)
def isolate_provider_settings(monkeypatch):
    # Also isolate the stand-alone adapter tests that do not use the shared
    # client fixture. Never inherit a real key or deployment's selected model.
    for name in (
        "OPENAI_API_KEY", "OPENROUTER_API_KEY", "DEEPSEEK_API_KEY",
        "SONIC_BRAIN_PROVIDER", "SONIC_MODEL", "SONIC_OPENROUTER_MODEL",
        "SONIC_DEEPSEEK_MODEL",
    ):
        monkeypatch.delenv(name, raising=False)


def text_result(text="SONIC_OK", **message_fields):
    return {"choices": [{"finish_reason": "stop", "message": {
        "role": "assistant", "content": text, **message_fields,
    }}]}


def tool_call(call_id="call_clock", name="current_time", arguments='{"timezone":"Asia/Jakarta"}'):
    return {"id": call_id, "type": "function",
            "function": {"name": name, "arguments": arguments}}


def tool_result(calls=None, finish="tool_calls"):
    return {"choices": [{"finish_reason": finish, "message": {
        "role": "assistant", "content": None,
        "tool_calls": [tool_call()] if calls is None else calls,
    }}]}


def mock_provider_http(monkeypatch, replies):
    """Every attempted paid call is observed; unexpected calls fail the test."""
    requests = []
    remaining = list(replies)

    class MockClient:
        def __init__(self, **kwargs):
            assert kwargs.get("timeout") == 75

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            pass

        async def post(self, url, *, headers, json):
            requests.append({"url": url, "headers": headers, "payload": json})
            assert remaining, "Unexpected provider call or automatic retry"
            reply = remaining.pop(0)
            if isinstance(reply, Exception):
                raise reply
            return reply if isinstance(reply, httpx.Response) else httpx.Response(200, json=reply)

    monkeypatch.setattr(providers.httpx, "AsyncClient", MockClient)
    return requests


def select_deepseek(client, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
    headers = login(client)
    response = client.put("/api/models/selection", json=SELECTION, headers=headers)
    assert response.status_code == 200, response.text
    return headers


def test_catalog_key_metadata_auth_and_existing_default_are_preserved(client, monkeypatch):
    requests = mock_provider_http(monkeypatch, [])
    assert client.get("/api/models").status_code == 401
    assert client.get("/api/setup/status").status_code == 401
    assert client.post("/api/setup/test-provider").status_code == 401
    headers = login(client)
    status = client.get("/api/models").json()
    assert status["selected"] == {
        "provider": "openai", "model": "gpt-4.1-mini", "key_configured": False,
    }
    deepseek = next(m for m in status["models"] if m["provider"] == "deepseek")
    assert deepseek["model"] == "deepseek-flash"
    assert deepseek["key_configured"] is False
    assert client.put("/api/models/selection", json=SELECTION).status_code == 403
    missing = client.put("/api/models/selection", json=SELECTION, headers=headers)
    assert missing.status_code == 409
    assert "DEEPSEEK_API_KEY" in missing.json()["detail"]
    monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
    status = client.get("/api/models").json()
    assert status["selected"]["provider"] == "openai"
    assert next(m for m in status["models"] if m["provider"] == "deepseek")["key_configured"]
    assert status["voice"]["provider"] == status["vision"]["provider"] == "openai"
    assert "API_KEY" not in json.dumps(status)
    assert FAKE_KEY not in json.dumps(status)
    assert requests == []


@pytest.mark.parametrize("extra_or_model", [
    {"model": "unreviewed-model"},
    {"model": "https://evil.invalid/model"},
    {"model": "../private"},
    {"base_url": "https://evil.invalid"},
    {"url": "https://evil.invalid"},
    {"api_key": "client-supplied-key"},
    {"thinking": {"type": "enabled"}},
])
def test_client_cannot_override_model_endpoint_secret_or_thinking(client, monkeypatch, extra_or_model):
    monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
    requests = mock_provider_http(monkeypatch, [])
    response = client.put("/api/models/selection", json={**SELECTION, **extra_or_model},
                          headers=login(client))
    assert response.status_code == 422
    assert client.get("/api/models").json()["selected"]["provider"] == "openai"
    assert requests == []


def test_choice_survives_restart_and_server_default_changes(client, monkeypatch):
    requests = mock_provider_http(monkeypatch, [])
    headers = select_deepseek(client, monkeypatch)
    import sonic.db as storage
    storage._engine.dispose()
    storage._engine, storage._Session = None, None
    monkeypatch.setenv("SONIC_BRAIN_PROVIDER", "openrouter")
    assert client.get("/api/models").json()["selected"] == {**SELECTION, "key_configured": True}
    assert client.get("/api/session").json()["provider"] == "deepseek"
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-openai-secret")
    assert client.put("/api/models/selection", json={
        "provider": "openai", "model": "gpt-4.1-mini",
    }, headers=headers).status_code == 200
    monkeypatch.setenv("SONIC_BRAIN_PROVIDER", "deepseek")
    assert client.get("/api/models").json()["selected"]["provider"] == "openai"
    assert requests == []


def test_trusted_server_model_override_is_available_without_automatic_calls(client, monkeypatch):
    monkeypatch.setenv("SONIC_BRAIN_PROVIDER", "deepseek")
    monkeypatch.setenv("SONIC_DEEPSEEK_MODEL", "deepseek-server-model")
    monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
    requests = mock_provider_http(monkeypatch, [])
    headers = login(client)
    status = client.get("/api/models").json()
    assert status["selected"] == {
        "provider": "deepseek", "model": "deepseek-server-model", "key_configured": True,
    }
    assert any(m["provider"] == "deepseek" and m["model"] == "deepseek-flash"
               for m in status["models"])
    assert client.put("/api/models/selection", json=SELECTION, headers=headers).status_code == 200
    assert requests == []


def test_deepseek_only_setup_and_health_do_not_require_openai(client, monkeypatch):
    monkeypatch.setenv("SONIC_BRAIN_PROVIDER", "deepseek")
    requests = mock_provider_http(monkeypatch, [])
    assert client.get("/api/health").json()["setup_required"] is True
    monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
    assert client.get("/api/health").json()["setup_required"] is False
    login(client)
    response = client.get("/api/setup/status")
    status = response.json()
    assert status["provider"] == "deepseek"
    assert status["model"] == "deepseek-flash"
    assert status["deepseek_key_configured"] is True
    assert status["provider_key_configured"] is True
    assert status["ready_for_chat_request"] is True
    assert status["provider_verified"] is False
    assert status["openai_key_configured"] is status["openrouter_key_configured"] is False
    assert status["remaining"] == []
    assert client.get("/api/voice/status").json()["configured"] is False
    assert FAKE_KEY not in response.text
    assert requests == []


def test_missing_deepseek_key_is_named_and_never_uses_another_provider(client, monkeypatch):
    monkeypatch.setenv("SONIC_BRAIN_PROVIDER", "deepseek")
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-openai-secret")
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-openrouter-secret")
    requests = mock_provider_http(monkeypatch, [])
    headers = login(client)
    status = client.get("/api/setup/status").json()
    assert status["remaining"] == ["DEEPSEEK_API_KEY"]
    assert status["deepseek_key_configured"] is status["ready_for_chat_request"] is False
    for path, body in (("/api/chat", {"message": "Halo, Sonic"}),
                       ("/api/setup/test-provider", None)):
        response = client.post(path, json=body, headers=headers)
        assert response.status_code == 503
        assert "DEEPSEEK_API_KEY" in response.json()["detail"]
        assert "synthetic-" not in response.text
    assert requests == []


def test_native_payload_key_isolation_and_private_reasoning_omission(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", FAKE_KEY)
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-openai-secret")
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-openrouter-secret")
    requested = []

    def handler(request):
        requested.append(request)
        assert str(request.url) == "https://api.deepseek.com/chat/completions"
        assert request.headers["Authorization"] == "Bearer " + FAKE_KEY
        assert "X-Title" not in request.headers
        sent = json.loads(request.content)
        assert sent["model"] == "deepseek-flash"
        assert sent["thinking"] == {"type": "disabled"}
        assert sent["stream"] is False
        assert sent["max_tokens"] == 1000
        assert sent["tool_choice"] == "auto"
        assert sent["tools"][0]["function"]["name"] == "current_time"
        assert not {"store", "parallel_tool_calls", "reasoning", "reasoning_effort",
                    "usage", "temperature", "top_p"} & sent.keys()
        assert "PRIVATE_REASONING" not in request.content.decode()
        assert "synthetic-openai" not in request.content.decode()
        response = text_result("Halo!", reasoning_content="PRIVATE_REASONING_RESPONSE")
        response["usage"] = {"prompt_tokens": 30, "completion_tokens": 5,
                             "prompt_cache_hit_tokens": 20, "prompt_cache_miss_tokens": 10}
        return httpx.Response(200, json=response)

    async def check():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as transport:
            result = await providers.complete(transport, {
                "instructions": "SONIC system",
                "input": [{"type": "reasoning", "summary": "PRIVATE_REASONING_INPUT"},
                          {"role": "user", "content": "Halo"}],
                "tools": [{"type": "function", "name": "current_time", "description": "Clock",
                           "parameters": {"type": "object", "properties": {},
                                          "additionalProperties": False}}],
                "store": False, "parallel_tool_calls": False, "max_output_tokens": 1000,
            }, providers.Selection(**SELECTION))
            assert result["output"][0]["content"][0]["text"] == "Halo!"
            assert result["usage"] == {"input_tokens": 30, "output_tokens": 5, "cost": None}
            assert "PRIVATE_REASONING" not in json.dumps(result)

    asyncio.run(check())
    assert len(requested) == 1


def test_valid_native_multi_round_tools_and_usage_privacy(client, monkeypatch):
    import sonic.brain as brain
    first = tool_result([tool_call("call_jakarta")])
    first["choices"][0]["message"]["reasoning_content"] = "PRIVATE_PROVIDER_REASONING"
    first["usage"] = {"prompt_tokens": 30, "completion_tokens": 8}
    second = tool_result([tool_call("call_utc", arguments='{"timezone":"UTC"}')])
    second["usage"] = {"prompt_tokens": 50, "completion_tokens": 9}
    final = text_result("Waktu Jakarta dan UTC sudah diperiksa.")
    final["usage"] = {"prompt_tokens": 70, "completion_tokens": 10}
    requests = mock_provider_http(monkeypatch, [first, second, final])
    executed = []
    original = brain.run_tool

    def track_tool(db, name, arguments, user_text):
        executed.append((name, arguments))
        return original(db, name, arguments, user_text)

    monkeypatch.setattr(brain, "run_tool", track_tool)
    headers = select_deepseek(client, monkeypatch)
    user_text = "Cek jam Jakarta kemudian UTC untuk saya."
    response = client.post("/api/chat", json={"message": user_text}, headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["reply"] == "Waktu Jakarta dan UTC sudah diperiksa."
    assert executed == [("current_time", {"timezone": "Asia/Jakarta"}),
                        ("current_time", {"timezone": "UTC"})]
    assert len(requests) == 3
    for request in requests:
        assert request["url"] == providers.DEEPSEEK_URL
        assert request["headers"]["Authorization"] == "Bearer " + FAKE_KEY
        assert request["payload"]["thinking"] == {"type": "disabled"}
        assert "PRIVATE_PROVIDER_REASONING" not in json.dumps(request["payload"])
    replay = requests[2]["payload"]["messages"][-4:]
    assert [m["role"] for m in replay] == ["assistant", "tool", "assistant", "tool"]
    for assistant, receipt in ((replay[0], replay[1]), (replay[2], replay[3])):
        assert assistant["content"] is None
        assert assistant["tool_calls"][0]["id"] == receipt["tool_call_id"]
        assert isinstance(json.loads(receipt["content"]), dict)
    with session_factory()() as db:
        usage = list(db.scalars(select(BrainUsage).order_by(BrainUsage.id)))
        assert [(u.provider, u.input_tokens, u.output_tokens, u.status) for u in usage] == [
            ("deepseek", 30, 8, "ok"), ("deepseek", 50, 9, "ok"), ("deepseek", 70, 10, "ok"),
        ]
        telemetry = json.dumps([{c.name: str(getattr(u, c.name)) for c in BrainUsage.__table__.columns}
                                for u in usage])
        assert user_text not in telemetry
        assert "PRIVATE_PROVIDER_REASONING" not in telemetry
        assert FAKE_KEY not in telemetry
        assert all("PRIVATE_PROVIDER_REASONING" not in m.content
                   for m in db.scalars(select(ChatMessage)))


INVALID_RESULTS = [
    None, [], {}, {"choices": None}, {"choices": {}}, {"choices": []},
    {"choices": [None]}, {"choices": [0]}, {"choices": ["malformed"]},
    {"choices": [{"message": None, "finish_reason": "stop"}]},
    text_result(""), text_result("partial", tool_calls={}),
    tool_result([]), tool_result({}, finish="tool_calls"),
    tool_result([None]), tool_result([{}]),
    tool_result([{"id": "call_bad", "type": "function", "function": None}]),
    tool_result([{"id": "call_bad", "type": "function", "function": {"name": "current_time"}}]),
    tool_result([tool_call(arguments="not json")]),
    tool_result([tool_call(arguments="[]")]),
    tool_result([tool_call(arguments="null")]),
    tool_result([tool_call(arguments='"text"')]),
    tool_result([tool_call(arguments="{}" * 5001)]),
    tool_result([tool_call(call_id="bad call id")]),
    tool_result([tool_call(), tool_call()]),
    tool_result([tool_call(name="memory_save", arguments='{"text":"unapproved write"}')]),
    tool_result([tool_call(name="shell_exec", arguments='{"command":"unapproved"}')]),
    tool_result([{"id": "call_bad", "type": "function_call_output", "output": "fake receipt"}]),
    tool_result([tool_call(str(i)) for i in range(11)]),
    tool_result(finish="stop"),
    *[tool_result(finish=reason) for reason in (
        "length", "content_filter", "insufficient_system_resource", "aborted", None,
    )],
    httpx.Response(200, text="not valid JSON: PRIVATE_UPSTREAM_CONTENT"),
]


@pytest.mark.parametrize("reply", INVALID_RESULTS)
def test_malformed_incomplete_or_unapproved_calls_never_reach_executor(client, monkeypatch, reply):
    import sonic.brain as brain
    requests = mock_provider_http(monkeypatch, [reply])
    executed = []
    monkeypatch.setattr(brain, "run_tool", lambda *args: executed.append(args))
    headers = select_deepseek(client, monkeypatch)
    response = client.post("/api/chat", json={"message": "Please check the time in Jakarta"}, headers=headers)
    assert response.status_code == 502, response.text
    assert response.json()["detail"] == "SONIC brain provider response could not be verified"
    assert "PRIVATE_UPSTREAM_CONTENT" not in response.text
    assert executed == []
    assert len(requests) == 1
    usage = client.get("/api/models").json()["usage"]
    assert len(usage) == 1
    assert usage[0]["provider"] == "deepseek" and usage[0]["status"] == "error"


@pytest.mark.parametrize("failure", [
    *[httpx.Response(status, text="PRIVATE_UPSTREAM_CONTENT " + FAKE_KEY)
      for status in (400, 401, 402, 429, 503)],
    httpx.ConnectTimeout("PRIVATE_UPSTREAM_CONTENT " + FAKE_KEY),
])
def test_native_errors_are_sanitized_and_never_retry_or_fallback(client, monkeypatch, failure):
    monkeypatch.setenv("OPENAI_API_KEY", "synthetic-openai-secret")
    monkeypatch.setenv("OPENROUTER_API_KEY", "synthetic-openrouter-secret")
    requests = mock_provider_http(monkeypatch, [failure])
    headers = select_deepseek(client, monkeypatch)
    response = client.post("/api/chat", json={"message": "Halo, Sonic"}, headers=headers)
    assert response.status_code == 502
    assert "PRIVATE_UPSTREAM_CONTENT" not in response.text
    assert FAKE_KEY not in response.text
    assert len(requests) == 1
    assert requests[0]["url"] == providers.DEEPSEEK_URL
    usage = client.get("/api/models").json()["usage"]
    assert len(usage) == 1 and usage[0]["status"] == "error"
    assert usage[0]["provider"] == "deepseek"
    assert usage[0]["input_tokens"] is None


@pytest.mark.parametrize("answer, expected_status", [
    ("SONIC_OK", 200), ("  SONIC_OK\n", 200), ("SONIC_OK EXTRA", 502),
])
def test_connection_check_is_explicit_bounded_and_requires_exact_reply(client, monkeypatch,
                                                                      answer, expected_status):
    requests = mock_provider_http(monkeypatch, [text_result(answer)])
    headers = select_deepseek(client, monkeypatch)
    assert client.get("/api/setup/status").json()["provider_verified"] is False
    assert client.post("/api/setup/test-provider").status_code == 403
    assert requests == []
    response = client.post("/api/setup/test-provider", headers=headers)
    assert response.status_code == expected_status
    assert len(requests) == 1
    assert requests[0]["url"] == providers.DEEPSEEK_URL
    payload = requests[0]["payload"]
    assert payload["max_tokens"] == 280
    assert payload["thinking"] == {"type": "disabled"}
    assert "tools" not in payload and "tool_choice" not in payload
    if expected_status == 200:
        assert response.json()["verified"] is True
        assert response.json()["provider"] == "deepseek"
        assert response.json()["model"] == "deepseek-flash"
    usage = client.get("/api/models").json()["usage"]
    assert len(usage) == 1
    assert usage[0]["status"] == ("ok" if expected_status == 200 else "error")
