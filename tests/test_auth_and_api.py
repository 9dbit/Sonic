import hashlib
import pytest


def auth(client):
    r = client.post("/api/login", json={"token": "owner-test-token"})
    assert r.status_code == 200, r.text
    return r.json()["csrf"]


def test_health_without_secrets(client):
    r = client.get("/api/health")
    assert r.status_code == 200
    assert r.json()["service"] == "SONIC"
    assert r.json()["setup_required"] is True


def test_login_rejects_incorrect_token(client):
    assert client.post("/api/login", json={"token": "bad"}).status_code == 401
    assert client.get("/api/history").status_code == 401


def test_csrf_is_required_and_session_is_http_only(client):
    csrf = auth(client)
    cookie = client.cookies.get("sonic_session")
    assert cookie
    assert client.post("/api/memories", json={"text": "I like blue design"}).status_code == 403
    r = client.post("/api/memories", json={"text": "I like blue design"}, headers={"X-Sonic-CSRF": csrf})
    assert r.status_code == 200
    mid = r.json()["id"]
    assert client.get("/api/memories").json()["memories"][0]["text"] == "I like blue design"
    assert client.delete(f"/api/memories/{mid}", headers={"X-Sonic-CSRF":csrf}).json()["deleted"]
    assert client.get("/api/memories").json()["memories"] == []


def test_memory_rejects_credentials(client):
    csrf = auth(client)
    response = client.post("/api/memories", json={"text": "password is abcdefgh"}, headers={"X-Sonic-CSRF":csrf})
    assert response.status_code == 422


def test_brain_cannot_start_without_provider_key(client):
    csrf = auth(client)
    r=client.post("/api/chat", json={"message":"Hello SONIC"}, headers={"X-Sonic-CSRF":csrf})
    assert r.status_code == 503
    assert "OPENAI_API_KEY" in r.json()["detail"]


def test_device_status_and_read_only_queue(client):
    csrf=auth(client)
    assert client.get("/api/device/status").json()["connected"] is False
    assert client.post("/api/device/jobs",json={"action":"shell.exec"},headers={"X-Sonic-CSRF":csrf}).status_code == 403
    device_headers={"Authorization":"Bearer device-test-token"}
    heartbeat={"device_id":"TRADEVICEPC","hostname":"TRADEVICEPC","platform":"Windows Test"}
    assert client.post("/api/device/heartbeat",json=heartbeat).status_code == 401
    assert client.post("/api/device/heartbeat",json=heartbeat,headers=device_headers).status_code == 200
    assert client.get("/api/device/status").json()["connected"] is True
    assert client.post("/api/device/jobs",json={"action":"delete.files"},headers={"X-Sonic-CSRF":csrf}).status_code == 403
    job=client.post("/api/device/jobs",json={"action":"system.status"},headers={"X-Sonic-CSRF":csrf})
    assert job.status_code == 200
    next_job=client.post("/api/device/next",json={},headers=device_headers).json()["job"]
    assert next_job["id"] == job.json()["id"]
    assert next_job["action"] == "system.status"
    result=client.post("/api/device/result",json={
        "device_id":"TRADEVICEPC","job_id":next_job["id"],"success":True,
        "result":{"hostname":"TRADEVICEPC","capabilities":["system.status"]}
    },headers=device_headers)
    assert result.status_code == 200
    query=client.get("/api/device/jobs/"+next_job["id"]).json()
    assert query["state"]=="done"
    assert query["result"]["hostname"] == "TRADEVICEPC"
    assert client.post("/api/device/next",json={},headers=device_headers).json()["job"] is None


def test_wrong_device_id_rejected(client):
    r=client.post("/api/device/heartbeat",headers={"Authorization":"Bearer device-test-token"},
     json={"device_id":"UNTRUSTED","hostname":"other","platform":"Linux"})
    assert r.status_code == 403


def test_hosted_without_postgres_is_fail_closed(client, monkeypatch):
    csrf=auth(client)
    monkeypatch.setenv("SONIC_ENV","production")
    assert client.get("/api/history").status_code == 503
    assert client.post("/api/memories",json={"text":"hello"},headers={"X-Sonic-CSRF":csrf}).status_code == 503
