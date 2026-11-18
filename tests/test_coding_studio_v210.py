"""SONIC Coding Studio v2.1: explicit model choice, bounded jobs, no hidden fallback."""
import json
from pathlib import Path

from tests.test_workspace_v088 import owner
from tests.test_local_ai_v152 import heartbeat, device_headers

HTML = """<!doctype html><html lang="id"><head><style>body{font:16px system-ui}</style></head><body>
<h1>Calculator</h1><input id="a" type="number"><output id="out"></output><script>document.getElementById('out').textContent='Ready';</script>
</body></html>"""


def test_owner_security_and_validation(client):
    path = "/api/coding/generate"
    assert client.post(path, json={"provider":"local","prompt":"Buat kalkulator mini"}).status_code == 401
    h = owner(client)
    assert client.post(path, json={"provider":"local","prompt":"Buat kalkulator mini"}).status_code == 403
    assert client.post(path, headers=h, json={"provider":"random","prompt":"Buat kalkulator mini"}).status_code == 422
    assert client.post(path, headers=h, json={"provider":"local","prompt":"short"}).status_code == 422
    assert client.post(path, headers=h, json={"provider":"local","prompt":"a"*451}).status_code == 413
    assert client.post(path, headers=h, json={"provider":"local","prompt":"Buat kalkulator mini", "existing_html": HTML}).status_code == 422
    assert client.post(path, headers=h, json={"provider":"deepseek","prompt":"Buat kalkulator mini"}).status_code == 503


def test_local_coding_uses_signed_companion_and_does_not_switch_model(client, monkeypatch):
    monkeypatch.setenv("SONIC_LOCAL_AI_ENABLED", "true")
    h = owner(client)
    heartbeat(client)
    old = client.get("/api/models").json()["selected"]
    r = client.post("/api/coding/generate",headers=h,
                    json={"provider":"local","prompt":"Buat kalkulator harga sederhana"})
    assert r.status_code == 200, r.text
    assert r.json()["state"] == "queued"
    job_id = r.json()["job_id"]
    assert client.get("/api/coding/local/invalid").status_code == 404
    assert client.get("/api/coding/local/"+job_id).json()["state"] == "queued"
    assert client.get("/api/models").json()["selected"] == old
    another = client.post("/api/coding/generate",headers=h,json={
        "provider":"local","prompt":"Buat stopwatch HTML ringkas"})
    assert another.status_code == 429, another.text
    lease = client.post("/api/device/local-ai/next",headers=device_headers()).json()["job"]
    assert lease["id"] == job_id and lease["action"] == "code"
    assert lease["payload"]["task"] == "code" and "tools" not in lease["payload"]
    assert client.post("/api/device/local-ai/result",headers=device_headers(),json={
        "device_id":"TRADEVICEPC","job_id":job_id,"success":True,
        "result":{"text":HTML,"truncated":False}}).status_code == 200
    finished = client.get("/api/coding/local/"+job_id).json()
    assert finished["state"] == "done" and "Calculator" in finished["html"]
    assert not finished["saved"] and not finished["previewed"]
    assert client.get("/api/artifacts").json()["total"] == 0
    client.post("/api/logout",headers=h)
    assert client.get("/api/coding/local/"+job_id).status_code == 401


def test_local_partial_and_diagnostics(client, monkeypatch):
    monkeypatch.setenv("SONIC_LOCAL_AI_ENABLED", "true")
    h = owner(client)
    heartbeat(client)
    queued=client.post("/api/coding/generate",headers=h,json={
        "provider":"local","prompt":"Buat timer minimal dengan angka"}).json()
    job=client.post("/api/device/local-ai/next",headers=device_headers()).json()["job"]
    assert job["id"]==queued["job_id"]
    assert client.post("/api/device/local-ai/result",headers=device_headers(),json={
        "device_id":"TRADEVICEPC","job_id":job["id"],"success":True,
        "result":{"text":"<!doctype html><html><body>incomplete","truncated":True}}).status_code==200
    reply=client.get("/api/coding/local/"+job["id"]).json()
    assert reply["state"]=="failed" and "terpotong" in reply["error"].lower()
    next_job=client.post("/api/coding/generate",headers=h,json={
        "provider":"local","prompt":"Buat kalkulator RAB sederhana"}).json()
    leased=client.post("/api/device/local-ai/next",headers=device_headers()).json()["job"]
    assert leased["id"]==next_job["job_id"]
    assert client.post("/api/device/local-ai/result",headers=device_headers(),json={
        "device_id":"TRADEVICEPC","job_id":leased["id"],"success":False,
        "result":{"error_code":"LOCAL_INFERENCE_TIMEOUT"}}).status_code==200
    failed=client.get("/api/coding/local/"+leased["id"]).json()
    assert failed["state"]=="failed" and "batas" in failed["error"].lower()


def test_deepseek_explicit_and_no_persistent_model_change(client, monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY","qa-key-never-live")
    monkeypatch.setenv("SONIC_DEEPSEEK_MODEL","deepseek-flash")
    h = owner(client)
    before = client.get("/api/models").json()["selected"]
    calls=[]
    class Reply:
        status_code=200
        def json(self):
            return {"choices":[{"finish_reason":"stop","message":{"content":HTML}}],
                    "usage":{"prompt_tokens":150,"completion_tokens":220}}
    class FakeClient:
        async def __aenter__(self):return self
        async def __aexit__(self,*args):return False
        async def post(self,url,**kwargs):
            calls.append((url, kwargs["json"]))
            return Reply()
    import sonic.coding_studio as coding
    monkeypatch.setattr(coding.httpx,"AsyncClient",lambda **kwargs:FakeClient())
    r=client.post("/api/coding/generate",headers=h,json={
       "provider":"deepseek","prompt":"Build an interior RAB calculator with unit prices"})
    assert r.status_code==200,r.text
    assert r.json()["provider"]=="deepseek" and r.json()["state"]=="done"
    assert not r.json()["saved"] and not r.json()["previewed"]
    assert "Calculator" in r.json()["html"]
    assert calls[0][0]=="https://api.deepseek.com/chat/completions"
    assert calls[0][1]["tools"] if False else True
    assert "tools" not in calls[0][1]
    assert calls[0][1]["thinking"]=={"type":"disabled"}
    assert client.get("/api/models").json()["selected"]==before
    assert client.get("/api/artifacts").json()["total"]==0


def test_incomplete_output_never_becomes_artifact(client,monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY","qa-key-never-live")
    h = owner(client)
    class Response:
        status_code=200
        def json(self):
            return {"choices":[{"finish_reason":"length",
                    "message":{"content":HTML[:95]}}]}
    class FakeClient:
        async def __aenter__(self):return self
        async def __aexit__(self,*args):return False
        async def post(self,*a,**kw):return Response()
    import sonic.coding_studio as coding
    monkeypatch.setattr(coding.httpx,"AsyncClient",lambda **kwargs:FakeClient())
    r=client.post("/api/coding/generate",headers=h,json={
        "provider":"deepseek","prompt":"Buat RAB kalkulator lengkap"})
    assert r.status_code==422
    assert client.get("/api/artifacts").json()["total"]==0


def test_companion_has_bounded_coding_job_and_no_auto_cloud():
    source=(Path(__file__).resolve().parents[1]/"scripts/windows_local_ai_v152.py").read_text()
    assert "125 if code_draft else 75" in source
    assert '"chat", "code", "start", "stop"' in source
    assert '"LOCAL_CODE_OUTPUT_TRUNCATED"' in source
    from sonic.coding_studio import validate_html
    from fastapi import HTTPException
    try: validate_html('<html><body>not complete')
    except HTTPException as e: assert e.status_code==422
    else: assert False, "Truncated HTML must be rejected"
