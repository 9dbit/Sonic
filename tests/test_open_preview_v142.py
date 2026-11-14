"""Anonymous open preview contracts: real adapter, browser CSRF, and no owner authority."""
from __future__ import annotations

import asyncio
import json
from datetime import timedelta
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
    stop_url="/api/preview/voice/sessions/"+session_id+"/stop"
    invalid=client.post(stop_url,json={"reason":"microphone transcript or secret"},headers=headers)
    assert invalid.status_code==422
    stop=client.post(stop_url,json={"reason":"channel_closed"},headers=headers)
    assert stop.status_code==200,stop.text
    assert stop.json()["provider_close_confirmed"] is True
    from sonic.db import session_factory, VoiceSession
    with session_factory()() as db:
        row=db.get(VoiceSession,session_id)
        assert row.close_reason=="preview_channel_closed"


def test_preview_housekeeping_preserves_live_guest_and_stops_expired_guest(guest_session, monkeypatch):
    """Regression for the 15-second background kill that closed iPhone calls."""
    client, headers = guest_session
    from sonic import voice
    from sonic.db import VoiceSession, OwnerSession, session_factory, utcnow
    calls = []
    async def mock_post(self, url, **kwargs):
        calls.append(url)
        if url.endswith('/hangup'):
            return type('Close', (), {'status_code': 204})()
        return type('Connect', (), {
            'status_code': 201, 'headers': {
                'location': '/v1/realtime/calls/rtc_preview_healthcheck'
            }, 'text': 'v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n'
        })()
    monkeypatch.setattr('httpx.AsyncClient.post', mock_post)
    session_id = str(uuid4())
    offer = {'session_id': session_id,
             'sdp': 'v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n',
             'consent': True}
    response = client.post('/api/preview/voice/sessions', json=offer, headers=headers)
    assert response.status_code == 200, response.text
    with session_factory()() as db:
        row = db.get(VoiceSession, session_id)
        assert len(row.owner_sid) == 64 and row.owner_sid.startswith('g_')
        assert db.get(OwnerSession, row.owner_sid) is None
    asyncio.run(voice.sweep_expired())
    with session_factory()() as db:
        row = db.get(VoiceSession, session_id)
        assert row.state == 'active'
        assert row.close_reason == ''
    assert not any(c.endswith('/hangup') for c in calls)

    with session_factory()() as db:
        row = db.get(VoiceSession, session_id)
        row.expires_at = utcnow() - timedelta(seconds=2)
        db.commit()
    asyncio.run(voice.sweep_expired())
    with session_factory()() as db:
        row = db.get(VoiceSession, session_id)
        assert row.state == 'closed'
    assert sum(c.endswith('/hangup') for c in calls) == 1


def test_preview_409_does_not_debit_voice_budget(guest_session, monkeypatch):
    client, headers = guest_session
    from sonic import preview
    from sonic.db import PreviewBudget, session_factory, utcnow
    async def mock_post(self, url, **kwargs):
        if url.endswith('/hangup'):
            return type('Close', (), {'status_code': 204})()
        return type('Connect', (), {
            'status_code': 201, 'headers': {'location': '/v1/realtime/calls/rtc_budget_409'},
            'text': 'v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n'
        })()
    monkeypatch.setattr('httpx.AsyncClient.post', mock_post)
    def offer():
        return {'session_id': str(uuid4()),
                'sdp': 'v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n',
                'consent': True}
    first = client.post('/api/preview/voice/sessions', json=offer(), headers=headers)
    assert first.status_code == 200, first.text
    key = utcnow().strftime('%Y%m%d') + ':global'
    with session_factory()() as db:
        before = db.get(PreviewBudget, key).voice_count
    conflict = client.post('/api/preview/voice/sessions', json=offer(), headers=headers)
    assert conflict.status_code == 409
    with session_factory()() as db:
        after = db.get(PreviewBudget, key).voice_count
    assert before == after == 1
    stop = client.post('/api/preview/voice/sessions/' + first.json()['session_id'] + '/stop',
                       json={'reason': 'owner_stop'}, headers=headers)
    assert stop.status_code == 200


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


def test_guest_cookie_does_not_rotate_when_multiple_components_poll_session(
        guest_session, monkeypatch):
    client, headers = guest_session
    from sonic import preview
    first_cookie = client.cookies.get(preview.COOKIE)
    first_csrf = headers["X-Sonic-Preview-CSRF"]
    for _ in range(4):
        current = client.get("/api/session")
        assert current.status_code == 200
        assert current.json()["preview_csrf"] == first_csrf
        assert client.cookies.get(preview.COOKIE) == first_cookie
        assert "set-cookie" not in current.headers
    # A browser that refetches session after page load must still be able to
    # call paid models using the original CSRF + same-site cookie.
    from sonic import preview as p
    async def stub(_client, request, selection):
        return {"output": [{"type": "message", "content": [
            {"type": "output_text", "text": "stable"}]}]}
    monkeypatch.setattr(p, "complete", stub)
    body = {"message": "Ping", "provider": "deepseek", "model": "deepseek-flash"}
    result = client.post("/api/preview/chat", json=body, headers=headers)
    assert result.status_code == 200, result.text
    assert result.json()["reply"] == "stable"

    # A signed cookie is not eternal even if a client replays it manually.
    old_now = int(p.time())
    monkeypatch.setattr(p, "time", lambda: float(old_now + p.COOKIE_SECONDS + 2))
    denied = client.post("/api/preview/chat", json=body, headers=headers)
    assert denied.status_code == 403
    refreshed = client.get("/api/session").json()
    assert refreshed["preview_csrf"] != first_csrf
    assert client.cookies.get(preview.COOKIE) != first_cookie
