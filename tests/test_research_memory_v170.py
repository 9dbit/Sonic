"""SONIC v1.7 Search expansion, research memory and privacy regressions."""
import pytest

from tests.test_auth_and_api import auth
from sonic import research_agent as agent
from sonic import research_web as web
from sonic.research_memory import ResearchMemory, tokens


def data():
    return {"sources":[
        {"id":1,"title":"Man-in-the-middle attack explained","url":"https://owasp.org/example",
         "publisher":"owasp.org","date":None,"snippet":"An attacker intercepts traffic between two parties.",
         "excerpt":"A man-in-the-middle attack allows intercepting communications between two parties.","read":True}
    ],"trace":[{"tool":"web.search","status":"ok","found":1},
              {"tool":"web.open","status":"ok","source_id":1}],
            "queries":["man-in-the-middle attack explained"],"reason":None,
            "notice":"Verify with original."}


def test_mitm_alias_search_expands_without_provider_guesswork():
    queries=web.expand_queries("Bagaimana cara kerja MITM?","references")
    assert len(queries)==2
    assert all("man-in-the-middle" in q for q in queries)
    candidates=[{"url":"https://owasp.org/example","title":"Man-in-the-middle attack explained",
                 "publisher":"owasp.org","snippet":"Security intercepts traffic.","date":None}]
    assert web.pick_sources("Bagaimana cara kerja MITM?",candidates)[0]["id"]==1
    assert "man-in-the-middle" in tokens("MITM network interception")


def test_research_memory_persists_requires_opt_in_and_owner(client,monkeypatch):
    monkeypatch.setenv("SONIC_RESEARCH_AGENT_ENABLED","true")
    monkeypatch.setattr(agent,"search_and_read",lambda *a,**kw: data())
    csrf=auth(client)
    headers={"X-Sonic-CSRF":csrf}
    # Legacy requests do not auto-save silently.
    basic=client.post("/api/agent/research",headers=headers,
                      json={"query":"How does MITM work?","purpose":"references"})
    assert basic.status_code==200
    assert basic.json()["memory_saved"] is False
    assert client.get("/api/agent/memory").json()["total"]==0
    result=client.post("/api/agent/research",headers=headers,json={
        "query":"How does MITM work?","purpose":"references",
        "save_to_memory":True,"project":"Cybersecurity"})
    assert result.status_code==200,result.text
    memory_id=result.json()["research_id"]
    assert memory_id
    item=client.get("/api/agent/memory/"+memory_id)
    assert item.status_code==200 and item.json()["project"]=="Cybersecurity"
    assert item.json()["sources"][0]["url"]=="https://owasp.org/example"
    assert item.json()["sources"][0]["read"] is True
    searched=client.get("/api/agent/memory?search=man-in-the-middle").json()
    assert searched["total"]==1
    assert searched["results"][0]["id"]==memory_id
    assert client.delete("/api/agent/memory/"+memory_id).status_code==403
    deleted=client.delete("/api/agent/memory/"+memory_id,headers=headers)
    assert deleted.status_code==200
    assert client.get("/api/agent/memory").json()["total"]==0


def test_memory_search_cross_risks_saved_with_citations(client,monkeypatch):
    monkeypatch.setenv("SONIC_RESEARCH_AGENT_ENABLED","true")
    monkeypatch.setattr(agent,"search_and_read",lambda *a,**kw:data())
    csrf=auth(client)
    headers={"X-Sonic-CSRF":csrf}
    first=client.post("/api/agent/research",headers=headers,json={
        "query":"Man in the middle attack mitigation","purpose":"references",
        "save_to_memory":True,"project":"Security"})
    assert first.status_code==200
    next=client.post("/api/agent/research",headers=headers,json={
        "query":"Compare MITM attack defenses","purpose":"references"})
    assert next.status_code==200
    assert len(next.json()["memory_matches"])>=1
    assert next.json()["memory_matches"][0]["id"]==first.json()["research_id"]


def test_cloud_general_explanation_with_no_sources_is_clearly_unverified(client,monkeypatch):
    monkeypatch.setenv("SONIC_RESEARCH_AGENT_ENABLED","true")
    monkeypatch.setenv("SONIC_RESEARCH_CLOUD_SUMMARY_ENABLED","true")
    empty={"sources":[],"trace":[{"tool":"web.search","status":"ok","found":0}],
           "queries":["MITM"],"reason":"no_relevant_sources","notice":"no relevant"}
    monkeypatch.setattr(agent,"search_and_read",lambda *a,**kw:empty)
    async def fake_cloud(*a,**kw):
        return ("Penjelasan umum (belum terverifikasi sumber): MITM menyisipkan perantara pada komunikasi.", "deepseek")
    monkeypatch.setattr(agent,"_cloud_summarize",fake_cloud)
    csrf=auth(client)
    r=client.post("/api/agent/research",headers={"X-Sonic-CSRF":csrf},
                  json={"query":"Bagaimana cara kerja MITM?","purpose":"references","save_to_memory":True})
    assert r.status_code==200
    d=r.json()
    assert d["mode"]=="general_explanation_unverified"
    assert d["memory_saved"] is False
    assert d["sources"]==[]
    assert d["model_provider"]=="deepseek"


def test_guest_cannot_list_or_remove_research_memories(client,monkeypatch):
    monkeypatch.setenv("SONIC_OPEN_PREVIEW","true")
    client.get("/api/session")
    assert client.get("/api/agent/memory").status_code==401
    assert client.get("/api/agent/memory/aaa").status_code==401
    assert client.delete("/api/agent/memory/aaa").status_code==401


def test_mitm_research_uses_wikimedia_fallback_and_rejects_man_trucks(monkeypatch):
    irrelevant=[
        {"title":"MAN Trucks, Buses and Vans","url":"https://www.man.eu/global/",
         "publisher":"www.man.eu","snippet":"MAN commercial vehicles","date":None},
        {"title":"Man - Wikipedia","url":"https://en.wikipedia.org/wiki/Man",
         "publisher":"en.wikipedia.org","snippet":"The human adult male","date":None}
    ]
    trusted=[{"title":"Man-in-the-middle attack",
              "url":"https://en.wikipedia.org/wiki/Man-in-the-middle_attack",
              "publisher":"en.wikipedia.org",
              "snippet":"In cybersecurity a man-in-the-middle attack intercepts messages",
              "date":None}]
    monkeypatch.setattr(web,"search_rss",lambda query:irrelevant)
    monkeypatch.setattr(web,"wiki_search",lambda query:trusted)
    monkeypatch.setattr(web,"read_public_page",lambda url,query:"In a man-in-the-middle attack messages can be intercepted in transit.")
    result=web.search_and_read("Bagaimana cara kerja MITM?","references")
    assert result["sources"]
    assert len(result["sources"])==1
    assert result["sources"][0]["title"]=="Man-in-the-middle attack"
    assert "man.eu" not in result["sources"][0]["url"]
    assert any(step["tool"]=="web.search.wikipedia" and step["status"]=="ok" for step in result["trace"])

def test_source_free_cloud_summary_is_always_marked_unverified(client,monkeypatch):
    monkeypatch.setenv("SONIC_RESEARCH_AGENT_ENABLED","true")
    monkeypatch.setenv("SONIC_RESEARCH_CLOUD_SUMMARY_ENABLED","true")
    monkeypatch.setattr(agent,"search_and_read",lambda *a,**kw:{
        "sources":[],"trace":[{"tool":"web.search","status":"ok","found":0}],
        "queries":["mitm"],"reason":"no_relevant_sources","notice":"none"})
    async def mock(*a,**kw):
        return ("MITM adalah metode intersepsi dalam komunikasi komputer.","deepseek")
    monkeypatch.setattr(agent,"_cloud_summarize",mock)
    csrf=auth(client)
    result=client.post("/api/agent/research",headers={"X-Sonic-CSRF":csrf},
                       json={"query":"Bagaimana cara kerja MITM?","purpose":"references"})
    assert result.status_code==200
    data=result.json()
    assert data["mode"]=="general_explanation_unverified"
    assert data["reply"].startswith("Penjelasan umum (belum terverifikasi sumber):")
    assert data["sources"]==[]
