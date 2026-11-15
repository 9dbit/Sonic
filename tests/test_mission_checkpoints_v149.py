"""SONIC v1.4.9 mission checkpoints: durable, reviewed, append-only audit."""
import hashlib


def owner(client):
    r=client.post("/api/login",json={"token":"owner-test-token"})
    assert r.status_code==200
    return {"X-Sonic-CSRF":r.json()["csrf"]}


def start(client,h,steps=None):
    data={"project_key":"sonic","goal":"Test accountable mission checkpoints",
          "steps":steps or ["Inspect system state","Verify the documented result"]}
    r=client.post("/api/productivity/missions",headers=h,json=data)
    assert r.status_code==201,r.text
    mid=r.json()["mission"]["id"]
    u="/api/productivity/missions/"+mid+"/transition"
    assert client.post(u,headers=h,json={"status":"approved","expected_revision":1}).status_code==200
    assert client.post(u,headers=h,json={"status":"in_progress","expected_revision":2}).status_code==200
    return mid


def test_owner_csrf_guest_and_data_isolation(client,monkeypatch):
    h=owner(client)
    mid=start(client,h)
    base="/api/productivity/missions/"+mid
    assert client.get(base+"/steps").status_code==200
    assert client.get(base+"/audit").status_code==200
    assert client.post(base+"/steps/0/complete",json={
        "expected_revision":3,"evidence":"Evidence for this step"}).status_code==403
    assert client.post(base+"/steps/0/complete",headers=h,json={
        "expected_revision":3,"evidence":"secret password 12345"}).status_code==422
    assert client.get("/api/productivity/missions/invalid/steps").status_code==404
    assert client.get("/api/productivity/missions/invalid/audit").status_code==404
    client.post("/api/logout",headers=h)
    assert client.get(base+"/steps").status_code==401
    assert client.get(base+"/audit").status_code==401
    assert client.post(base+"/steps/0/complete",headers=h,json={
        "expected_revision":3,"evidence":"Evidence for this step"}).status_code==401


def test_sequential_checkpoints_revision_and_audit(client):
    h=owner(client)
    mid=start(client,h)
    base="/api/productivity/missions/"+mid
    def check(i,rev,evidence):
        return client.post(base+"/steps/"+str(i)+"/complete",headers=h,
                           json={"expected_revision":rev,"evidence":evidence})
    assert check(1,3,"Evidence on step two").status_code==409
    assert check(0,2,"Evidence on first step").status_code==409
    assert check(0,3,"Evidence on first step").status_code==200
    assert check(0,4,"Evidence on first step").status_code==409
    assert check(1,3,"Evidence on step two").status_code==409
    assert check(1,4,"Evidence on step two").status_code==200
    checkpoint=client.get(base+"/steps").json()
    assert checkpoint["revision"]==5
    assert [step["done"] for step in checkpoint["steps"]]==[True,True]
    assert checkpoint["steps"][0]["evidence"]=="Evidence on first step"
    assert checkpoint["steps"][1]["evidence"]=="Evidence on step two"
    listing=client.get("/api/productivity/missions").json()["missions"][0]
    assert listing["step_progress"]["total"]==2
    assert listing["step_progress"]["completed"]==2
    assert [c["done"] for c in listing["step_progress"]["checkpoints"]]==[True,True]
    audit=client.get(base+"/audit").json()
    assert len(audit["audit"])==4
    assert all("Evidence on" not in str(entry) for entry in audit["audit"])
    first=next(x for x in audit["audit"] if x["action"]=="step.completed" and x["step_index"]==0)
    assert first["evidence_sha256"]==hashlib.sha256(b"Evidence on first step").hexdigest()
    assert audit["raw_evidence_in_audit"] is False


def test_reopen_last_checkpoint_then_close_mission(client):
    h=owner(client)
    mid=start(client,h)
    base="/api/productivity/missions/"+mid
    step=lambda i,a,r,e: client.post(base+"/steps/"+str(i)+"/"+a,headers=h,
        json={"expected_revision":r,"evidence":e})
    assert step(0,"complete",3,"Verified first checkpoint").status_code==200
    assert step(1,"complete",4,"Verified second checkpoint").status_code==200
    assert step(0,"reopen",5,"Need another inspection").status_code==409
    assert step(1,"reopen",4,"Need another inspection").status_code==409
    reopened=step(1,"reopen",5,"Re-review second checkpoint")
    assert reopened.status_code==200 and reopened.json()["revision"]==6
    assert client.get(base+"/steps").json()["steps"][1]["done"] is False
    assert client.post(base+"/transition",headers=h,json={"status":"completed",
        "expected_revision":6,"evidence":"Review complete and verified"}).status_code==409
    assert step(1,"complete",6,"Retested the second checkpoint").status_code==200
    completed=client.post(base+"/transition",headers=h,json={
        "status":"completed","expected_revision":7,
        "evidence":"All steps reviewed by human operator"})
    assert completed.status_code==200, completed.text
    assert completed.json()["mission"]["status"]=="completed"
    assert step(1,"reopen",8,"Reopen after mission closed").status_code==409
    assert client.get(base+"/audit").json()["audit"][0]["action"]=="mission.completed"


def test_invalid_steps_and_unverified_complete_denied(client):
    h=owner(client)
    mid=start(client,h,steps=["Only one mission checkpoint"])
    base="/api/productivity/missions/"+mid
    attempt=lambda idx,rev,e: client.post(base+"/steps/"+str(idx)+"/complete",
        headers=h,json={"expected_revision":rev,"evidence":e})
    assert attempt(-1,3,"Verified checkpoint") .status_code==404
    assert attempt(5,3,"Verified checkpoint").status_code==404
    assert attempt(0,3,"too short").status_code==422
    assert attempt(0,3,"This includes api_key access") .status_code==422
    assert client.post(base+"/transition",headers=h,json={
        "status":"completed","expected_revision":3,
        "evidence":"Human verified the job"}).status_code==409
    assert client.get(base+"/audit").json()["audit"][-1]["action"]=="mission.approved"
