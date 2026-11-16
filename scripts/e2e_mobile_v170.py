"""SONIC v1.7 mobile QA including header, composer, navigation, neural list and research memory."""
import json, os, shutil
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from qa_server import local_server

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"artifacts"/"mobile-v170";OUT.mkdir(parents=True,exist_ok=True)
settings={"SONIC_OPEN_PREVIEW":"true","SONIC_OWNER_ENTRY_ENABLED":"true",
          "SONIC_RESEARCH_AGENT_ENABLED":"true",
          "SONIC_LOCAL_AI_ENABLED":"false","SONIC_PASSWORDLESS_LOGIN":"false",
          "PYTHONPATH":str(ROOT)+os.pathsep+os.environ.get("PYTHONPATH","")}
with local_server(settings=settings) as (base,token),sync_playwright() as p:
    executable=next((str(path) for path in (
        Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
        Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
    ) if path.is_file()),None)
    browser=p.chromium.launch(executable_path=executable,headless=True,
                              args=["--no-sandbox","--enable-unsafe-swiftshader"])
    for name,w,h in [("iphone-390",390,844),("compact-360",360,740),("desktop",1440,900)]:
        page=browser.new_page(viewport={"width":w,"height":h},device_scale_factor=1,
                              is_mobile=w<721,has_touch=w<721)
        errors=[];page.on("pageerror",lambda e:errors.append(str(e)))
        page.goto(base+"/owner",wait_until="domcontentloaded")
        page.locator("#ownerToken").fill(token)
        page.locator('#loginForm button[type="submit"]').click()
        expect(page.locator("#loginOverlay")).to_be_hidden(timeout=14000)
        page.locator('.nav[data-tab="chat"]').click()
        expect(page.locator("#chatPanel")).to_be_visible()
        page.locator("#agentModeResearch").click()
        expect(page.locator("#agentResearchPreferences")).to_be_visible(timeout=5000)
        expect(page.locator("#agentSaveMemory")).to_be_checked()
        boxes=page.evaluate("""() => {
           function box(s){const n=document.querySelector(s);if(!n)return null;
             const r=n.getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height,right:r.right};}
           return {vw:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth,
                   topbar:box('.topbar'),topright:box('.topbar .top-right'),
                   mic:box('#talkSonic'),headerOrb:box('#sonicHeaderOrb'),
                   topStyle:{headerPosition:getComputedStyle(document.querySelector('.topbar')).position,
                             position:getComputedStyle(document.querySelector('.topbar .top-right')).position,
                             top:getComputedStyle(document.querySelector('.topbar .top-right')).top,
                             offsetParent:document.querySelector('.topbar .top-right').offsetParent?.className},
                   prefs:box('#agentResearchPreferences'),chat:box('#chatPanel'),
                   composer:box('#chatForm'),nav:box('.sidebar')};
        }""")
        print("BOUNDS",name,json.dumps(boxes),flush=True)
        assert boxes["scroll"]<=boxes["vw"]+1,boxes
        if w<721:
            assert boxes["topbar"]["h"]<=75,boxes
            assert boxes["mic"]["y"]<=boxes["topbar"]["y"]+65,boxes
            page.locator("#mobileMoreNav").click()
            expect(page.locator("#mobileMoreMenu")).to_be_visible()
            page.locator('[data-mobile-go="workspace"]').click()
            expect(page.locator("#workspacePanel")).to_be_visible()
            page.locator('.nav[data-tab="chat"]').click()
            page.locator("#chatExtras").click()
            expect(page.locator("#camera")).to_be_visible()
            page.locator("#chatExtras").click()
            page.locator('.nav[data-tab="brain"]').click()
            expect(page.locator("#neuralKnowledgeList")).to_be_visible()
            page.screenshot(path=str(OUT/(name+"-neural.png")))
            page.locator("#neuralGraphBtn").click()
            expect(page.locator("#neuralKnowledgeList")).to_be_hidden()
            print("GRAPH_HIT",page.evaluate("""() => {let e=document.querySelector("#neuralKnowledgeBtn"),r=e.getBoundingClientRect();let hit=document.elementFromPoint(r.x+r.width/2,r.y+r.height/2);return {rect:{x:r.x,y:r.y,w:r.width,h:r.height},hit:hit?.id||hit?.className,scrollY:window.scrollY}}"""),flush=True)
            page.locator("#neuralKnowledgeBtn").click(timeout=6000)
            expect(page.locator("#neuralKnowledgeList")).to_be_visible()
            page.locator('.nav[data-tab="chat"]').click()
        active_nav=page.evaluate("""() => [...document.querySelectorAll('.sidebar .nav.active')].map(e=>e.dataset.tab||e.id)""")
        print('ACTIVE_NAV',name,active_nav,flush=True)
        assert active_nav==['chat'],active_nav
        page.screenshot(path=str(OUT/(name+"-chat.png")))
        assert not errors,errors
        page.close()
    browser.close()
print("SONIC_V170_MOBILE_QA_PASS")
