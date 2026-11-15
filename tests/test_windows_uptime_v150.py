"""Windows Companion durable uptime probes: no real credentials, no packet capture."""
import importlib
import sys
import threading
import time
from uuid import uuid4
from pathlib import Path
import pytest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
monitor=importlib.import_module("windows_uptime_v150")
agent=importlib.import_module("windows_agent_v05")


def sample(stamp=None):
    return {"sample_id":str(uuid4()),"observed_at_ms":stamp or monitor.utc_ms(),
            "google_ok":True,"cloudflare_ok":True,"google_ms":18,"cloudflare_ms":27}


def test_probe_204_is_healthy_and_captive_200_not_up(monkeypatch):
    calls=[]
    class Reply:
        def __init__(self,code):self.status=code
        def __enter__(self):return self
        def __exit__(self,*args):pass
    def fake_open(request,timeout):
        calls.append((request.full_url,timeout))
        return Reply(204 if "cloudflare" in request.full_url else 200)
    monkeypatch.setattr(monitor,"urlopen",fake_open)
    s=monitor.sample_once()
    assert s["google_ok"] is False and s["google_ms"] is None
    assert s["cloudflare_ok"] is True and s["cloudflare_ms"] is not None
    assert [x[0] for x in calls]==[url for _,url in monitor.TARGETS]
    assert all(t<=3 for _,t in calls)


def test_offline_journal_retry_and_idempotent_acked_queue(tmp_path,client):
    journal=monitor.UptimeJournal(tmp_path/"private-uptime.sqlite3")
    for _ in range(4):journal.add(sample())
    assert journal.counts()[0]==4
    assert len(journal.pending())==4
    def offline(route,payload):
        raise ConnectionError("synthetic offline")
    with pytest.raises(ConnectionError):
        monitor.upload_pending(journal,offline,"TRADEVICEPC")
    assert len(journal.pending())==4
    # Reopen the exact same journal as after a process restart.
    reopened=monitor.UptimeJournal(journal.path)
    calls=[]
    def delivery(route,payload):
        calls.append((route,payload["device_id"],len(payload["samples"])))
        response=client.post(route,json=payload,headers={
            "Authorization":"Bearer device-test-token"})
        assert response.status_code==200,response.text
        return response.json()
    result=monitor.upload_pending(reopened,delivery,"TRADEVICEPC")
    assert result=={"sent":4}
    assert len(reopened.pending())==0
    assert journal.counts()[0]==4  # local archive is retained after upload
    assert journal.counts()[1]==0
    assert calls==[("/api/uptime/ingest","TRADEVICEPC",4)]
    login=client.post("/api/login",json={"token":"owner-test-token"})
    assert login.status_code==200
    data=client.get("/api/uptime/summary").json()
    assert data["samples_recorded"]<=4
    assert data["status"]=="partial"
    assert data["uptime_pct"] is None


def test_unconfirmed_receipt_does_not_mark_samples_as_uploaded(tmp_path):
    journal=monitor.UptimeJournal(tmp_path/"journal.sqlite3")
    journal.add(sample())
    with pytest.raises(RuntimeError,match="UPTIME_RECEIPT_MISMATCH"):
        monitor.upload_pending(journal,lambda *_:{"acknowledged":[]},
                               "TRADEVICEPC")
    assert len(journal.pending())==1


def test_sampler_runs_at_interval_and_stores_samples_without_cloud(tmp_path):
    journal=monitor.UptimeJournal(tmp_path/"journal.sqlite3")
    readings=[]
    def fake_sample():
        row=sample();readings.append(row);return row
    worker=monitor.UptimeSampler(journal,interval=0.05,sample=fake_sample)
    worker.start()
    deadline=time.monotonic()+1.5
    while len(readings)<2 and time.monotonic()<deadline:
        time.sleep(0.02)
    worker.close()
    assert len(readings)>=2
    assert journal.counts()[0]==len(readings)
    assert journal.counts()[1]==len(readings)


def test_companion_one_cycle_uploads_and_heartbeat_while_read_only(tmp_path,client,monkeypatch):
    journal=monitor.UptimeJournal(tmp_path/"journal.sqlite3")
    journal.add(sample())
    monkeypatch.setattr(agent,"DEVICE","TRADEVICEPC")
    monkeypatch.setattr(agent,"_UPTIME_MONITOR",type("Attached",(),{"journal":journal})())
    monkeypatch.setattr(agent,"extended_stats",lambda:{"ram_total_bytes":8*2**30,"ram_available_bytes":4*2**30})
    monkeypatch.setattr(agent,"software_capabilities",lambda:[])
    monkeypatch.setenv("SONIC_ENABLE_POWERSHELL_EXEC","0")
    monkeypatch.setenv("SONIC_WINDOW_CONTROL_ENABLED","0")
    def request(route,payload):
        response=client.post(route,json=payload,headers={
            "Authorization":"Bearer device-test-token"})
        assert response.status_code==200,(route,response.status_code,response.text)
        return response.json()
    monkeypatch.setattr(agent,"api",request)
    agent.run_once()
    assert journal.counts()[1]==0
    owner=client.post("/api/login",json={"token":"owner-test-token"})
    assert owner.status_code==200
    summary=client.get("/api/uptime/summary").json()
    assert summary["status"]=="partial"
    assert summary["samples_recorded"]==1
    assert summary["observed_uptime_pct"]==100.0
    assert summary["uptime_pct"] is None
