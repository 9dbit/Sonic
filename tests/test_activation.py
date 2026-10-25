import copy
from sqlalchemy import select
from sonic.db import session_factory, OwnerSession
from tests.test_auth_and_api import auth


def test_owner_only_setup_and_secret_redaction(client):
    assert client.get("/api/setup/status").status_code == 401
    csrf = auth(client)
    status = client.get("/api/setup/status")
    assert status.status_code == 200
    assert status.json()["database_connected"] is True
    assert status.json()["provider_key_configured"] is False
    assert "owner-test-token" not in status.text
    assert "device-test-token" not in status.text
    assert client.post("/api/setup/test-provider").status_code == 403
    assert client.post("/api/setup/test-provider", headers={"X-Sonic-CSRF": csrf}).status_code == 503


def test_logout_revokes_replayed_cookie(client):
    csrf = auth(client)
    cookie = client.cookies.get("sonic_session")
    assert client.get("/api/history").status_code == 200
    assert client.post("/api/logout", headers={"X-Sonic-CSRF": csrf}).status_code == 200
    client.cookies.set("sonic_session", cookie)
    assert client.get("/api/history").status_code == 401


def test_headers_and_whitespace_memory(client):
    r = client.get("/")
    assert r.headers["x-frame-options"] == "DENY"
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    csrf = auth(client)
    r = client.post("/api/memories", json={"text": "    "}, headers={"X-Sonic-CSRF": csrf})
    assert r.status_code == 422
    assert client.get("/api/history").headers["cache-control"] == "no-store"


def test_mocked_provider_tool_roundtrip(client, monkeypatch):
    import sonic.brain as brain
    monkeypatch.setenv("OPENAI_API_KEY", "unit-test-only-not-a-real-key")
    requests=[]
    outputs=[
        {"status":"completed","output":[{"type":"function_call","name":"current_time","arguments":"{\"timezone\":\"Asia/Jakarta\"}","call_id":"time_1","id":"fc1"}]},
        {"status":"completed","output":[{"type":"message","content":[{"type":"output_text","text":"SONIC tool roundtrip verified."}]}]}
    ]
    class Reply:
        status_code=200
        def __init__(self, data): self.data=data
        def json(self): return self.data
    class MockClient:
        def __init__(self, **kwargs): pass
        async def __aenter__(self): return self
        async def __aexit__(self, *args): pass
        async def post(self, url, **kwargs):
            requests.append(copy.deepcopy(kwargs["json"]))
            return Reply(outputs.pop(0))
    monkeypatch.setattr(brain.httpx,"AsyncClient",MockClient)
    csrf=auth(client)
    r=client.post("/api/chat",json={"message":"Cek jam Jakarta"},headers={"X-Sonic-CSRF":csrf})
    assert r.status_code==200
    assert r.json()["reply"]=="SONIC tool roundtrip verified."
    assert len(requests)==2 and all(x["store"] is False for x in requests)
    assert any(x.get("type")=="function_call_output" for x in requests[1]["input"])
    assert len(client.get("/api/history").json()["messages"])==2
