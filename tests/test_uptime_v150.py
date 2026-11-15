"""SONIC 1.5.0 uptime telemetry and 24-hour truthfulness, synthetic only."""
from __future__ import annotations
from uuid import uuid4
from datetime import datetime,timezone
import pytest

from sonic.db import session_factory
from sonic.uptime import UptimeSample, report, is_uptime_question, uptime_reply

DEVICE={"Authorization":"Bearer device-test-token"}


def owner(client):
    login=client.post("/api/login",json={"token":"owner-test-token"})
    assert login.status_code==200,login.text
    return {"X-Sonic-CSRF":login.json()["csrf"]}


def now_ms():
    return int(datetime.now(timezone.utc).timestamp()*1000)


def sample(*, observed=None, goog=True, cloud=True, ident=None):
    return {"sample_id":ident or str(uuid4()),
            "observed_at_ms":observed or now_ms(),
            "google_ok":goog,"cloudflare_ok":cloud,
            "google_ms":45 if goog else None,
            "cloudflare_ms":35 if cloud else None}


def test_owner_only_and_device_only_contract(client):
    assert client.get("/api/uptime/summary").status_code==401
    assert client.post("/api/uptime/ingest",json={
        "device_id":"TRADEVICEPC","samples":[sample()]}).status_code==401
    assert client.get("/api/uptime/summary",headers=DEVICE).status_code==401
    h=owner(client)
    assert client.post("/api/uptime/ingest",headers=h,json={
        "device_id":"TRADEVICEPC","samples":[sample()]}).status_code==401
    assert client.get("/api/uptime/summary?hours=0").status_code==422
    assert client.get("/api/uptime/summary?hours=169").status_code==422
    r=client.get("/api/uptime/summary")
    assert r.status_code==200,r.text
    x=r.json()
    assert x["status"]=="no_data" and x["uptime_pct"] is None
    assert x["observed_uptime_pct"] is None
    assert x["unknown_seconds"]==86400 and x["coverage_pct"]==0
    assert len(x["timeline"])==48


def test_ingest_idempotent_refuses_forged_conflicted_and_future(client):
    s=sample()
    body={"device_id":"TRADEVICEPC","samples":[s]}
    assert client.post("/api/uptime/ingest",headers=DEVICE,json={
        **body,"device_id":"OTHER-PC"}).status_code==403
    assert client.post("/api/uptime/ingest",headers=DEVICE,json=body).json()["new"]==1
    replay=client.post("/api/uptime/ingest",headers=DEVICE,json=body)
    assert replay.status_code==200 and replay.json()["new"]==0
    changed={**s,"cloudflare_ok":False,"cloudflare_ms":None}
    assert client.post("/api/uptime/ingest",headers=DEVICE,json={
        **body,"samples":[changed]}).status_code==409
    assert client.post("/api/uptime/ingest",headers=DEVICE,json={
        **body,"samples":[s,s]}).status_code==422
    assert client.post("/api/uptime/ingest",headers=DEVICE,json={
        **body,"samples":[{**s,"observed_at_ms":now_ms()+3600_000}]}).status_code==422
    assert client.post("/api/uptime/ingest",headers=DEVICE,json={
        **body,"samples":[{**s,"observed_at_ms":now_ms()-31*86400_000}]}).status_code==422
    assert client.post("/api/uptime/ingest",headers=DEVICE,json={
        **body,"samples":[{**s,"google_ms":None}]}).status_code==422
    assert client.post("/api/uptime/ingest",headers=DEVICE,json={
        **body,"samples":[{**s,"sample_id":str(uuid4()),"unexpected":"secret"}]}).status_code==422
    assert client.post("/api/uptime/ingest",headers=DEVICE,json={
        "device_id":"TRADEVICEPC","samples":[sample(goog=False,cloud=False)]}).status_code==200
    owner(client)
    summary=client.get("/api/uptime/summary").json()
    assert summary["status"]=="partial" and summary["uptime_pct"] is None
    assert summary["samples_recorded"] <= 2


def test_24h_coverage_downtime_events_and_degraded_are_not_packet_loss(client):
    owner(client)
    now=1_800_000_000_000
    start=now-86400_000
    omitted={1031,1032}
    fails={211,212,213,912}
    degrade={63,64,65}
    rows=[]
    for slot in range(2880):
        if slot in omitted:continue
        failure=slot in fails
        degraded=slot in degrade
        rows.append(UptimeSample(
            device_id="TRADEVICEPC",sample_id=str(uuid4()),
            observed_at_ms=start+slot*30000+1000,
            google_ok=not failure,
            cloudflare_ok=not failure and not degraded,
            google_ms=None if failure else 45,
            cloudflare_ms=None if failure or degraded else 35))
    with session_factory()() as db:
        db.add_all(rows);db.commit()
        r=report(db,24,now_ms=now)
    assert r["status"]=="ready"
    assert r["samples_recorded"]==2878
    assert r["samples_expected"]==2880
    assert r["unknown_seconds"]==60
    assert r["approx_down_seconds"]==120
    assert r["degraded_seconds"]==90
    assert r["outage_count"]==2
    assert len(r["outages"])==2
    assert r["uptime_pct"]==r["observed_uptime_pct"]
    assert 99.8<r["uptime_pct"]<100
    assert r["coverage_pct"]>99.9
    assert r["avg_https_latency_ms"]>0
    assert r["https_probe_success_pct"]<100
    assert "not ICMP packet loss" in r["measurement_note"]
    assert len(r["timeline"])==48
    assert "99." in uptime_reply(r)


def test_23_hour_start_cannot_be_claimed_as_full_24h(client):
    owner(client)
    now=1_800_000_000_000
    start=now-86400_000
    with session_factory()() as db:
        db.add_all([UptimeSample(device_id="TRADEVICEPC",sample_id=str(uuid4()),
            observed_at_ms=start+i*30000+1000,google_ok=True,
            cloudflare_ok=True,google_ms=40,cloudflare_ms=40)
            for i in range(120,2880)])
        db.commit()
        r=report(db,24,now_ms=now)
    assert r["coverage_pct"]>95
    assert r["status"]=="partial"
    assert r["uptime_pct"] is None
    assert "belum" in uptime_reply(r).lower()


def test_chat_uptime_question_deterministic_without_model(client):
    h=owner(client)
    assert is_uptime_question("Sonic, berapa persen uptime koneksi internet saya dalam 24 jam?")
    assert not is_uptime_question("hapus file internet saya")
    assert not is_uptime_question("cek uptime server Postgres")
    r=client.post("/api/chat",headers=h,json={
        "message":"Sonic, berapa persen uptime internet dalam 24 jam terakhir?"})
    assert r.status_code==200,r.text
    body=r.json()
    assert body["engine"]["route"]=="internet_uptime"
    assert "Belum ada data monitoring" in body["reply"]
    assert "100%" not in body["reply"]


def test_preview_cannot_get_uptime(client,monkeypatch):
    monkeypatch.setenv("SONIC_OPEN_PREVIEW","true")
    monkeypatch.setenv("SONIC_PREVIEW_PAID_ACTIONS","true")
    guest=client.get("/api/session").json()
    assert guest["preview"] is True
    assert client.get("/api/uptime/summary").status_code==401
    assert client.post("/api/uptime/ingest",headers={
        "X-Sonic-Preview-CSRF":guest["preview_csrf"]},json={
        "device_id":"TRADEVICEPC","samples":[sample()]}).status_code==401
