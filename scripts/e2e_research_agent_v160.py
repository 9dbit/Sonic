"""Read-only owner Research Agent Chromium QA, synthetic source fixtures only.

No real web search, PC commands, API keys, trading or physical iPhone access.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import shutil

from playwright.sync_api import sync_playwright, expect
from qa_server import local_server

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "research-agent-v160"
OUT.mkdir(parents=True, exist_ok=True)

settings = {
    "SONIC_OPEN_PREVIEW": "true",
    "SONIC_OWNER_ENTRY_ENABLED": "true",
    "SONIC_RESEARCH_AGENT_ENABLED": "true",
    "SONIC_LOCAL_AI_ENABLED": "false",
    "SONIC_PASSWORDLESS_LOGIN": "false",
    "PYTHONPATH": str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""),
}
fake = {
    "reply": "Berdasarkan sumber [1], OpenAI menerbitkan informasi riset. Sumber [2] berisi dokumentasi API.",
    "mode": "sources_only", "purpose": "references", "local_ai_used": False, "read_only": True,
    "sources": [
        {"id": 1, "title": "OpenAI Research", "url": "https://openai.com/research",
         "date": "2026-11-12", "read": True, "excerpt": "Official research material."},
        {"id": 2, "title": "OpenAI Platform Docs", "url": "https://platform.openai.com/docs",
         "date": None, "read": False, "snippet": "Official API documentation."},
        {"id": 3, "title": "Untrusted script URL", "url": "javascript:alert(1)",
         "date": None, "read": False, "snippet": "Must never render as a link."},
    ],
    "steps": [{"tool": "web.search", "status": "ok"},
              {"tool": "web.open", "status": "ok"},
              {"tool": "local.summarize", "status": "skipped"}],
    "notice": "Reader can have partial availability."
}

with local_server(settings=settings) as (base, owner_token), sync_playwright() as pw:
    executable = shutil.which("chromium") or shutil.which("chrome")
    if not executable:
        executable = next((str(p) for p in (
            Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
            Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
        ) if p.exists()), None)
    browser = pw.chromium.launch(executable_path=executable or None,
                                 headless=True, args=["--no-sandbox", "--enable-unsafe-swiftshader"])
    reports = []
    for name, width, height, mobile in (("iphone-390",390,844,True),
                                         ("compact-360",360,740,True),
                                         ("desktop",1440,900,False)):
        guest = browser.new_page(viewport={"width":width,"height":height},
                                 is_mobile=mobile,has_touch=mobile)
        guest.goto(base+"/",wait_until="domcontentloaded")
        expect(guest.locator("#agentResearchToolbar")).to_be_hidden()
        assert guest.request.get(base+"/api/agent/capabilities").status==401
        guest.close()
        page = browser.new_page(viewport={"width":width,"height":height},
                                is_mobile=mobile,has_touch=mobile)
        errors = []
        page.on("pageerror",lambda e:errors.append(str(e)))
        calls=[]
        def intercept(route):
            body=json.loads(route.request.post_data or "{}")
            calls.append(body)
            route.fulfill(status=200,content_type="application/json",body=json.dumps(fake))
        page.route("**/api/agent/research",intercept)
        page.goto(base+"/owner",wait_until="networkidle")
        page.locator("#ownerToken").fill(owner_token)
        page.locator('#loginForm button[type="submit"]').click()
        expect(page.locator("#loginOverlay")).to_be_hidden(timeout=14000)
        page.locator('.nav[data-tab="chat"]').click()
        expect(page.locator("#agentResearchToolbar")).to_be_visible()
        expect(page.locator("#agentModeResearch")).to_be_enabled(timeout=18000)
        page.locator("#agentModeResearch").click()
        expect(page.locator("#agentModeResearch")).to_have_attribute("aria-pressed","true")
        page.locator("#agentPurpose").select_option("references")
        page.locator("#message").fill("OpenAI research")
        page.locator("#send").click()
        expect(page.locator(".agent-research-results")).to_be_visible(timeout=11000)
        assert calls==[{"query":"OpenAI research","purpose":"references","save_to_memory":True,"project":"General"}], calls
        assert page.locator(".agent-source a").count()==2
        anchors=page.locator(".agent-source a").all()
        assert all(a.get_attribute("href").startswith("https://") for a in anchors)
        assert all(a.get_attribute("rel")=="noopener noreferrer" for a in anchors)
        assert "OpenAI" in page.locator(".message.assistant .body").last.inner_text()
        assert page.locator(".agent-steps").count()==1
        viewport=page.evaluate("""() => ({
            width:document.documentElement.clientWidth,
            scroll:document.documentElement.scrollWidth,
            accent:getComputedStyle(document.documentElement).getPropertyValue('--accent').trim()
        })""")
        assert viewport["scroll"]<=viewport["width"]+1, viewport
        assert viewport["accent"]=="#3d95ff"
        page.locator("#agentModeChat").click()
        expect(page.locator("#agentModeChat")).to_have_attribute("aria-pressed","true")
        assert not errors, errors
        page.screenshot(path=str(OUT/(name+".png")),full_page=False)
        reports.append({"viewport":name,"login":"pass","agent_mode":"pass",
                        "sources":2,"no_overflow":True,"js_errors":0})
        page.close()
    browser.close()
    (OUT/"report.json").write_text(json.dumps(reports,indent=2),encoding="utf-8")
    print(json.dumps(reports,indent=2))
print("SONIC_RESEARCH_BROWSER_QA_PASS")