"""SONIC v1.5.1: personal iPhone guest has ONLY read-only uptime rights."""
import json
from uuid import uuid4
import pytest

DEVICE={"Authorization":"Bearer device-test-token"}


@pytest.fixture
def preview(client,monkeypatch):
    monkeypatch.setenv("SONIC_OPEN_PREVIEW","true")
    monkeypatch.setenv("SONIC_PREVIEW_PAID_ACTIONS","true")
    monkeypatch.setenv("SONIC_PASSWORDLESS_LOGIN","false")
    monkeypatch.setenv("SONIC_PUBLIC_URL","http://testserver")
    monkeypatch.setenv("OPENAI_API_KEY","synthetic-test-key")
    monkeypatch.setenv("SONIC_REALTIME_ENABLED","true")
    status=client.get("/api/session")
    assert status.status_code==200
    data=status.json()
    assert data["preview"] and data["trusted_uptime"] is False
    headers={"Origin":"http://testserver",
             "X-Sonic-Preview-CSRF":data["preview_csrf"]}
    return client, headers


def pair(client,headers):
    issued=client.post("/api/preview/trusted/issue",headers=DEVICE,json={})
    assert issued.status_code==200,issued.text
    link=issued.json()["pair_url"]
    assert "#sonic-pair=" in link
    token=link.split("#sonic-pair=",1)[1]
    resp=client.post("/api/preview/trusted/claim",headers=headers,json={"token":token})
    assert resp.status_code==200,resp.text
    assert resp.json()["paired"] is True
    return token,resp


def test_unpaired_preview_blocked_and_no_public_tool(preview):
    client,h=preview
    assert client.get("/api/preview/trusted/uptime",headers={
        "X-Sonic-Preview-CSRF":h["X-Sonic-Preview-CSRF"]}).status_code==403
    assert client.post("/api/preview/trusted/claim",headers=h,json={"token":"X"*43}).status_code==410
    assert client.post("/api/preview/trusted/issue",headers=h,json={}).status_code==401
    assert client.get("/api/uptime/summary").status_code==401
    assert client.get("/api/device/status").status_code==401
    assert client.get("/api/history").status_code==401
    assert client.get("/api/productivity/missions").status_code==401
    assert client.post("/api/preview/trusted/revoke-all",headers=h,json={}).status_code==401


def test_pairing_once_cookie_security_and_narrow_uptime_only(preview):
    client,h=preview
    token,resp=pair(client,h)
    cookie=resp.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=strict" in cookie
    assert token not in cookie
    assert "sonic_personal_preview" in cookie
    assert client.get("/api/session").json()["trusted_uptime"] is True
    good=client.get("/api/preview/trusted/uptime",
        headers={"X-Sonic-Preview-CSRF":h["X-Sonic-Preview-CSRF"]})
    assert good.status_code==200,good.text
    assert good.json()["status"]=="no_data"
    assert good.json()["uptime_pct"] is None
    assert client.get("/api/preview/trusted/uptime").status_code==403
    assert client.get("/api/preview/trusted/uptime",headers={
        **h,"Sec-Fetch-Site":"cross-site"}).status_code==403
    assert client.get("/api/preview/trusted/uptime",headers={
        **h,"Origin":"https://attacker.invalid"}).status_code==403
    assert client.post("/api/preview/trusted/claim",headers=h,
        json={"token":token}).status_code==410
    assert client.get("/api/uptime/summary").status_code==401
    for path in ("/api/device/status","/api/history","/api/memories",
                 "/api/productivity/missions","/api/engine/tasks"):
        assert client.get(path).status_code==401,path
    chat=client.post("/api/preview/chat",headers=h,json={
        "message":"Berapa persen uptime internet dalam 24 jam?",
        "provider":"deepseek","model":"deepseek-flash"})
    assert chat.status_code==200,chat.text
    assert "Belum ada data" in chat.json()["reply"]
    assert "100%" not in chat.json()["reply"]
    assert chat.json()["operator_jobs"]==[]
    removed=client.post("/api/preview/trusted/unpair",headers=h,json={})
    assert removed.status_code==200
    assert client.get("/api/session").json()["trusted_uptime"] is False
    assert client.get("/api/preview/trusted/uptime",headers={
        "X-Sonic-Preview-CSRF":h["X-Sonic-Preview-CSRF"]}).status_code==403


def test_pairing_link_revoked_by_new_issue_and_revoke_all(preview):
    client,h=preview
    old=client.post("/api/preview/trusted/issue",headers=DEVICE,json={}).json()["pair_url"].split("#sonic-pair=",1)[1]
    new=client.post("/api/preview/trusted/issue",headers=DEVICE,json={}).json()["pair_url"].split("#sonic-pair=",1)[1]
    assert client.post("/api/preview/trusted/claim",headers=h,json={"token":old}).status_code==410
    assert client.post("/api/preview/trusted/claim",headers=h,json={"token":new}).status_code==200
    assert client.get("/api/session").json()["trusted_uptime"] is True
    assert client.post("/api/preview/trusted/revoke-all",headers=DEVICE,json={}).status_code==200
    assert client.get("/api/session").json()["trusted_uptime"] is False


def test_trusted_preview_voice_tool_only_uptime(preview,monkeypatch):
    client,h=preview
    token,_=pair(client,h)
    calls=[]
    class FakeResponse:
        status_code=201
        headers={"location":"https://api.openai.com/v1/realtime/calls/rtc_personal_151"}
        text="v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n"
    async def post(self,url,**kwargs):
        calls.append((url,kwargs))
        if url.endswith("/hangup"):
            return type("Closed",(),{"status_code":204})()
        return FakeResponse()
    monkeypatch.setattr("httpx.AsyncClient.post",post)
    sid=str(uuid4())
    res=client.post("/api/preview/voice/sessions",headers=h,json={
        "session_id":sid,"sdp":"v=0\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n","consent":True})
    assert res.status_code==200,res.text
    assert res.json()["personal_uptime_tools"] is True
    config=json.loads(calls[0][1]["files"]["session"][1])
    assert [t["name"] for t in config["tools"]]==["internet_uptime"]
    assert config["tool_choice"]=="auto"
    assert "device controls" in config["instructions"]
    base="/api/preview/voice/sessions/"+sid+"/tools"
    unauthorized=client.post(base,headers=h,json={
        "call_id":"bad1","name":"device_metrics","arguments":{}})
    assert unauthorized.status_code==403
    payload={"call_id":"uptime_1","name":"internet_uptime","arguments":{}}
    first=client.post(base,headers=h,json=payload)
    assert first.status_code==200,first.text
    assert first.json()["output"]["status"]=="no_data"
    assert first.json()["output"]["uptime_pct"] is None
    assert first.json()["ui_actions"]==[]
    assert client.post(base,headers=h,json=payload).json()==first.json()
    assert client.post(base,headers=h,json={
        **payload,"arguments":{"command":"powershell.exec"}}).status_code==403
    assert client.post(base,headers=h,json={
        "call_id":"u2","name":"internet_uptime","arguments":{"x":1}}).status_code==403
    client.post("/api/preview/trusted/unpair",headers=h,json={})
    assert client.post(base,headers=h,json=payload).status_code==403
    assert client.post("/api/voice/sessions/"+sid+"/tools",headers=h,json=payload).status_code==401


def test_latest_trusted_iphone_replaces_previous(preview):
    client,h=preview
    pair(client,h)
    old_cookie=client.cookies.get("sonic_personal_preview")
    assert old_cookie
    pair(client,h)
    newest_cookie=client.cookies.get("sonic_personal_preview")
    assert newest_cookie and newest_cookie!=old_cookie
    client.cookies.set("sonic_personal_preview",old_cookie)
    assert client.get("/api/session").json()["trusted_uptime"] is False
    client.cookies.set("sonic_personal_preview",newest_cookie)
    assert client.get("/api/session").json()["trusted_uptime"] is True
