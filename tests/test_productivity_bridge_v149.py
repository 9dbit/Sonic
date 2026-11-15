"""End-to-end SONIC owner -> durable job -> genuine companion -> result.

Uses isolated local SQLite, synthetic owner/device credentials and FastAPI TestClient.
The Windows-only path runs real bounded diagnostics on the authorized computer,
never calls production or staging and never touches trading software.
"""
from __future__ import annotations
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = str(ROOT / "scripts")


def login(client):
    r = client.post("/api/login", json={"token": "owner-test-token"})
    assert r.status_code == 200, r.text
    return {"X-Sonic-CSRF": r.json()["csrf"]}


def companion(client, monkeypatch, real=False):
    monkeypatch.syspath_prepend(SCRIPTS)
    agent = importlib.import_module("windows_agent_v05")
    from sonic import db
    agent._SOFTWARE_PENDING_RESULT = None
    agent._SOFTWARE_BROKER = None
    agent._SOFTWARE_PREFLIGHT = (0.0, {})
    monkeypatch.setattr(agent, "DEVICE", "TRADEVICEPC")
    monkeypatch.setattr(agent, "extended_stats",
                        lambda: {"ram_total_bytes": 16*2**30,
                                 "ram_available_bytes": 8*2**30})
    monkeypatch.setattr(agent, "software_capabilities", lambda: [])
    monkeypatch.setenv("SONIC_SOFTWARE_DISCOVERY_ENABLED", "0")
    monkeypatch.setenv("SONIC_ENABLE_POWERSHELL_EXEC", "0")
    monkeypatch.setenv("SONIC_WINDOW_CONTROL_ENABLED", "0")
    calls = []

    def mock_transport(route, data):
        calls.append(route)
        response = client.post(route, json=data,
                               headers={"Authorization": "Bearer device-test-token"})
        assert response.status_code == 200, (route, response.status_code, response.text)
        return response.json()

    monkeypatch.setattr(agent, "api", mock_transport)
    if not real:
        monkeypatch.setattr(agent.windows_diagnostics_v148, "run", lambda action: {
            "kind": action, "read_only": True,
            "result": {"source": "synthetic_companion",
                       "action": action}})
    return agent, calls


def test_synthetic_owner_companion_full_job_lifecycle(client, monkeypatch):
    h = login(client)
    agent, calls = companion(client, monkeypatch)
    agent.run_once(only_heartbeat=True)
    caps = client.get("/api/productivity/capabilities").json()
    assert caps["device_connected"] is True
    assert all(t["ready"] for t in caps["tools"]
               if t["id"].startswith("diagnostics."))
    for action in ("diagnostics.clock", "diagnostics.ping",
                   "diagnostics.processes", "diagnostics.events"):
        r = client.post("/api/productivity/diagnostics", headers=h,
                        json={"action": action})
        assert r.status_code == 202, (action, r.status_code, r.text)
        job_id = r.json()["id"]
        assert client.get("/api/device/jobs/"+job_id).json()["state"] == "queued"
        agent.run_once()
        receipt = client.get("/api/device/jobs/"+job_id).json()
        assert receipt["state"] == "done", receipt
        assert receipt["action"] == action
        assert receipt["result"]["kind"] == action
        assert receipt["result"]["read_only"] is True
    assert calls.count("/api/device/result") == 4
    assert "/api/device/operator/result" not in calls
    assert "/api/device/operator/next" in calls
    assert client.get("/api/productivity/briefing").status_code == 200
    assert client.post("/api/productivity/diagnostics", json={
        "action": "diagnostics.clock"}).status_code == 403
    client.post("/api/logout", headers=h)
    assert client.get("/api/productivity/capabilities").status_code == 401
    assert client.get("/api/productivity/missions").status_code == 401


@pytest.mark.skipif(sys.platform != "win32", reason="physical Windows adapter test")
def test_windows_real_diagnostics_full_job_lifecycle(client, monkeypatch):
    h = login(client)
    agent, calls = companion(client, monkeypatch, real=True)
    agent.run_once(only_heartbeat=True)
    for action in ("diagnostics.clock", "diagnostics.ping",
                   "diagnostics.processes", "diagnostics.events"):
        r = client.post("/api/productivity/diagnostics", headers=h,
                        json={"action": action})
        assert r.status_code == 202, (action, r.text)
        agent.run_once()
        receipt = client.get("/api/device/jobs/"+r.json()["id"]).json()
        assert receipt["state"] == "done", (action, receipt)
        data = receipt["result"]["result"]
        if action == "diagnostics.clock":
            assert data["ntp_verified"] is False and "observed_at" in data
        elif action == "diagnostics.ping":
            assert len(data["targets"]) == 2
            assert all(x["target"] in ("cloudflare_dns", "google_dns")
                       for x in data["targets"])
        elif action == "diagnostics.processes":
            if data.get("available") is False:
                assert data["reason"] == "psutil_missing"
            else:
                assert data.get("count", 0) > 1
        elif action == "diagnostics.events":
            assert data["message_text_collected"] is False
    assert calls.count("/api/device/result") == 4
    assert not any(route.endswith("/operator/result") for route in calls)
