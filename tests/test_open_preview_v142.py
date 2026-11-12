"""Anonymous open preview contracts: real adapter, browser CSRF, and no owner authority."""
from __future__ import annotations

import json
from uuid import uuid4

import pytest


@pytest.fixture
def guest_session(client, monkeypatch):
    monkeypatch.setenv("SONIC_OPEN_PREVIEW", "true")
    monkeypatch.setenv("SONIC_PREVIEW_PAID_ACTIONS", "true")
    monkeypatch.setenv("SONIC_PASSWORDLESS_LOGIN", "false")
    monkeypatch.setenv("SONIC_PUBLIC_URL", "http://testserver")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "test-synthetic-key")
    monkeypatch.setenv("OPENAI_API_KEY", "test-synthetic-openai-key")
    monkeypatch.setenv("SONIC_REALTIME_ENABLED", "true")
    response = client.get("/api/session")
    assert response.status_code == 200
    assert "HttpOnly" in response.headers["set-cookie"]
    assert response.json()["authenticated"] is False
    return client, {"Origin": "http://testserver",
                    "X-Sonic-Preview-CSRF": response.json()["preview_csrf"]}


def test_public_preview_exposes_only_allowlisted_model_metadata(guest_session):
    client, headers = guest_session
    models = client.get("/api/preview/models").json()
    assert models["enabled"] is True
    assert models["voice"]["enabled"] is True
    assert {m["provider"] for m in models["models"]} == {"deepseek", "openai"}
    assert "test-synthetic" not in json.dumps(models)
    assert "API_KEY" not in json.dumps(models)
    for path in ("/api/history", "/api/memories", "/api/device/status",
                 "/api/models", "/api/knowledge/graph"):
        assert client.get(path).status_code == 401
    assert client.post("/api/chat", json={"message":"hello"}).status_code == 401
    assert client.post("/api/login", json={"token":"owner-test-token"}).status_code == 403


def test_preview_chat_uses_provider_adapter_without_tools_or_storage(guest_session, monkeypatch):
    client, headers = guest_session
    from sonic import preview
    calls = []
    async def fake_complete(_client, request, selection):
        calls.append((request, selection))
        return {"status": "completed", "output": [
            {"type": "message", "content": [{"type": "output_text", "text": "Halo dari DeepSeek"}]}]}
    monkeypatch.setattr(preview, "complete", fake_complete)
    payload = {"message": "Apa kabar SONIC?", "provider": "deepseek", "model": "deepseek-flash"}
    unauthorized = client.post("/api/preview/chat", json=payload)
    assert unauthorized.status_code == 403
    bad = client.post("/api/preview/chat", json=payload, headers={"Origin":"https://attacker.invalid",
                                                                   "X-Sonic-Preview-CSRF": headers["X-Sonic-Preview-CSRF"]})
    assert bad.status_code == 403
    good = client.post("/api/preview/chat", json=payload, headers=headers)
    assert good.status_code == 200, good.text
    assert good.json()["reply"] == "Halo dari DeepSeek"
    request, selection = calls[0]
    assert selection.provider == "deepseek"
    assert request["tools"] == [] and request["store"] is False
    assert request["input"] == [{"role":"user","content": payload["message"]}]
    assert "Device" not in json.dumps(request["input"])
    assert client.get("/api/history").status_code == 401
    assert client.get("/api/memories").status_code == 401


def test_durable_budget_limits_public_requests(guest_session, monkeypatch):
    client, headers = guest_session
    from sonic import preview
    async def fake_complete(_client, request, selection):
        return {"output":[{"type":"message","content":[{"type":"output_text","text":"reply"}]}]}
    monkeypatch.setattr(preview,"complete",fake_complete)
    data={"message":"hai","provider":"deepseek","model":"deepseek-flash"}
    responses=[client.post("/api/preview/chat",json=data,headers=headers).status_code
               for _ in range(preview.CHAT_PER_NETWORK_DAILY+1)]
    assert responses[:-1]==[200]*preview.CHAT_PER_NETWORK_DAILY
    assert responses[-1]==429
    # Reloaded guest cookie may change, but the network/global durable quota remains.
    client.get("/api/session")
    refreshed = client.get("/api/session").json()
    headers["X-Sonic-Preview-CSRF"] = refreshed["preview_csrf"]
    assert client.post("/api/preview/chat",json=data,headers=headers).status_code==429


def test_preview_voice_creates_no_tools_and_does_not_allow_pc_calls(guest_session, monkeypatch):
    client, headers = guest_session
    from sonic import voice
    captured=[]
    class FakeResponse:
        status_code=201
        headers={"location":"https://api.openai.com/v1/realtime/calls/rtc_synthetic"}
        text="v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n"
    async def fake_post(self, url, **kwargs):
        captured.append((url,kwargs))
        if url.endswith("/hangup"):
            class Closed:
                status_code=204
            return Closed()
        return FakeResponse()
    monkeypatch.setattr("httpx.AsyncClient.post",fake_post)
    session_id=str(uuid4())
    req={"session_id":session_id,"sdp":"v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n","consent":True}
    res=client.post("/api/preview/voice/sessions",json=req,headers=headers)
    assert res.status_code==200,res.text
    assert res.json()["max_seconds"]==60
    payload=json.loads(captured[0][1]["files"]["session"][1])
    assert payload["tools"]==[]
    assert payload["tool_choice"]=="none"
    assert "device_id" not in payload["instructions"]
    assert "memory_search" not in json.dumps(payload)
    assert client.post("/api/voice/sessions/"+session_id+"/tools",json={
        "call_id":"x","name":"device_metrics","arguments":{}}).status_code==401
    stop=client.post("/api/preview/voice/sessions/"+session_id+"/stop",json={},headers=headers)
    assert stop.status_code==200,stop.text
    assert stop.json()["provider_close_confirmed"] is True


def test_preview_paid_flag_gates_all_provider_calls(client, monkeypatch):
    monkeypatch.setenv("SONIC_OPEN_PREVIEW","true")
    monkeypatch.setenv("SONIC_PUBLIC_URL","http://testserver")
    monkeypatch.setenv("SONIC_PREVIEW_PAID_ACTIONS","false")
    monkeypatch.setenv("DEEPSEEK_API_KEY","test")
    session=client.get("/api/session").json()
    headers={"Origin":"http://testserver","X-Sonic-Preview-CSRF":session["preview_csrf"]}
    body={"message":"hi","provider":"deepseek","model":"deepseek-flash"}
    assert client.post("/api/preview/chat",json=body,headers=headers).status_code==503
    assert client.get("/api/preview/models").json()["enabled"] is False
