"""SONIC productivity core owner isolation, safe transitions, diagnostics broker."""
def login(client):
    r=client.post("/api/login",json={"token":"owner-test-token"})
    assert r.status_code == 200
    return {"X-Sonic-CSRF":r.json()["csrf"]}

def test_tools_are_owner_only_and_registered(client):
    assert client.get("/api/productivity/capabilities").status_code == 401
    assert client.get("/api/productivity/missions").status_code == 401
    assert client.get("/api/productivity/projects/sonic/facts").status_code == 401
    h=login(client)
    r=client.get("/api/productivity/capabilities")
    assert r.status_code == 200
    tools=r.json()["tools"]
    assert next(x for x in tools if x["id"]=="diagnostics.ping")["ready"] is False
    assert next(x for x in tools if x["id"]=="router.syslog")["ready"] is False
    assert client.post("/api/productivity/missions",json={
        "project_key":"sonic","goal":"Develop this secure mission",
        "steps":["Implement this first"]}).status_code == 403

def test_project_facts_persist_search_and_reject_secrets(client):
    h=login(client)
    good={"project_key":"sonic","title":"Network decision","content":"Use read-only diagnostics by default"}
    result=client.post("/api/productivity/facts",headers=h,json=good)
    assert result.status_code == 201, result.text
    fact=result.json()["fact"]
    assert fact["source"]=="owner_entry"
    r=client.get("/api/productivity/projects/sonic/facts",params={"query":"READ-ONLY"})
    assert r.status_code==200 and [x["id"] for x in r.json()["facts"]]==[fact["id"]]
    assert client.get("/api/productivity/projects/another/facts").json()["facts"]==[]
    assert client.post("/api/productivity/facts",headers=h,json={
        **good,"content":"secret api_key is abc"}).status_code==422
    assert client.post("/api/productivity/facts",headers=h,json={
        **good,"project_key":"../private"}).status_code==422
    assert client.delete("/api/productivity/facts/"+fact["id"]).status_code==403
    assert client.delete("/api/productivity/facts/"+fact["id"],headers=h).status_code==200
    assert client.get("/api/productivity/projects/sonic/facts").json()["facts"]==[]

def test_mission_requires_manual_progress_and_verified_evidence(client):
    h=login(client)
    item={"project_key":"sonic","goal":"Test manual mission lifecycle",
          "steps":["Check project requirements","Review the results"]}
    result=client.post("/api/productivity/missions",headers=h,json=item)
    assert result.status_code==201, result.text
    m=result.json()["mission"]
    assert m["status"]=="draft" and m["execution"]=="no_automatic_actions"
    url="/api/productivity/missions/"+m["id"]+"/transition"
    assert client.post(url,headers=h,json={"status":"completed","expected_revision":1}).status_code==409
    assert client.post(url,json={"status":"approved","expected_revision":1}).status_code==403
    r=client.post(url,headers=h,json={"status":"approved","expected_revision":1})
    assert r.status_code==200
    assert client.post(url,headers=h,json={"status":"in_progress","expected_revision":1}).status_code==409
    r=client.post(url,headers=h,json={"status":"in_progress","expected_revision":2})
    assert r.status_code==200
    assert client.post(url,headers=h,json={"status":"completed","expected_revision":3}).status_code==422
    r=client.post(url,headers=h,json={"status":"completed","expected_revision":3,
                                     "evidence":"Verified the actual output manually"})
    assert r.status_code==200 and r.json()["mission"]["status"]=="completed"
    assert client.post(url,headers=h,json={"status":"in_progress","expected_revision":4}).status_code==409
    assert len(client.get("/api/productivity/missions").json()["missions"])==1
    assert client.get("/api/productivity/missions?project_key=other").json()["missions"]==[]

def test_diagnostics_allowlist_and_authenticated_device(client):
    h=login(client)
    req={"action":"diagnostics.ping"}
    assert client.post("/api/productivity/diagnostics",json=req).status_code==403
    assert client.post("/api/productivity/diagnostics",headers=h,json=req).status_code==409
    assert client.post("/api/productivity/diagnostics",headers=h,json={
        "action":"powershell.exec"}).status_code==403
    dh={"Authorization":"Bearer device-test-token"}
    hb={"device_id":"TRADEVICEPC","hostname":"TRADEVICEPC","platform":"Windows Test","agent_version":"1.4.8",
        "capabilities":["system.status","diagnostics.ping","diagnostics.events"]}
    assert client.post("/api/device/heartbeat",headers=dh,json=hb).status_code==200
    r=client.post("/api/productivity/diagnostics",headers=h,json=req)
    assert r.status_code==202,r.text
    jobid=r.json()["id"]
    job=client.post("/api/device/next",headers=dh,json={}).json()["job"]
    assert job["id"]==jobid and job["action"]=="diagnostics.ping"
    assert client.post("/api/device/result",headers=dh,json={
        "device_id":"TRADEVICEPC","job_id":jobid,"success":True,
        "result":{"kind":"diagnostics.ping","read_only":True,"result":{"reachable":True}}
    }).status_code==200
    data=client.get("/api/device/jobs/"+jobid).json()
    assert data["state"]=="done" and data["result"]["read_only"]
    assert client.post("/api/productivity/diagnostics",headers=h,json={"action":"diagnostics.clock"}).status_code==409

def test_guest_preview_cannot_access_productivity(client,monkeypatch):
    monkeypatch.setenv("SONIC_OPEN_PREVIEW","true")
    monkeypatch.setenv("SONIC_PREVIEW_PAID_ACTIONS","true")
    guest=client.get("/api/session")
    assert guest.json().get("preview") is True
    assert client.get("/api/productivity/missions").status_code==401
    assert client.get("/api/productivity/capabilities").status_code==401
    assert client.post("/api/productivity/facts",json={
        "project_key":"sonic","title":"Attack","content":"Do not save this"
    },headers={"X-Sonic-Preview-CSRF":guest.json()["preview_csrf"]}).status_code==401

def test_daily_brief_and_cloud_search_are_grounded(client):
    from uuid import uuid4
    h=login(client)
    assert client.get("/api/productivity/briefing").status_code==200
    assert client.get("/api/productivity/search?q=project").status_code==200
    assert client.get("/api/productivity/search?q=x").status_code==422
    fact=client.post("/api/productivity/facts",headers=h,json={
        "project_key":"sonic","title":"Audit Falcon",
        "content":"Project Falcon privacy requirements"}).json()["fact"]
    note=client.post("/api/workspace/items",headers=h,json={
        "id":str(uuid4()),"name":"Falcon Checklist.md",
        "kind":"text","parent_id":"root","content":"Falcon internal checklist"})
    assert note.status_code==200
    brief=client.get("/api/productivity/briefing").json()
    assert brief["scope"]=="sonic_internal_only"
    assert brief["workspace_active_items"]>=1
    assert "email" in brief["not_connected"]
    assert brief["latest_project_facts"][0]["title"]=="Audit Falcon"
    result=client.get("/api/productivity/search?q=Falcon").json()
    assert {x["source"] for x in result["results"]}=={
        "project_memory","sonic_cloud_workspace"}
    assert all("content" not in x for x in result["results"])
    assert len(client.get("/api/productivity/search?q=unknownphrase").json()["results"])==0
