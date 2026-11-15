"""Real-browser personal preview pairing QA, synthetic DB and device credentials."""
from __future__ import annotations
import hashlib, json
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
import httpx
from qa_server import local_server

settings={"SONIC_OPEN_PREVIEW":"true","SONIC_PREVIEW_PAID_ACTIONS":"true",
          "SONIC_PASSWORDLESS_LOGIN":"false","DEEPSEEK_API_KEY":"synthetic-no-network",
          "OPENAI_API_KEY":"synthetic-no-network","SONIC_REALTIME_ENABLED":"true",
          "SONIC_DEVICE_TOKEN_SHA256":hashlib.sha256(b"synthetic-device-v151").hexdigest()}
out=Path("artifacts/trusted-preview-v151");out.mkdir(parents=True,exist_ok=True)
with local_server(settings=settings) as (base,_owner),sync_playwright() as pw:
 browser=pw.chromium.launch(headless=True,args=["--no-sandbox"])
 results=[]
 for name,viewport in [("iphone",{"width":390,"height":844}),("small-iphone",{"width":360,"height":740}),("desktop",{"width":1440,"height":900})]:
    context=browser.new_context(viewport=viewport)
    page=context.new_page()
    errors=[]
    page.on("pageerror",lambda err:errors.append(str(err)))
    page.goto(base,wait_until="networkidle")
    expect(page.locator("#loginOverlay")).to_have_class("login-overlay hidden")
    page.locator('.nav[data-tab="devices"]').click()
    expect(page.locator("#productivityHub")).to_be_hidden()
    data=httpx.post(base+"/api/preview/trusted/issue",headers={
        "Authorization":"Bearer synthetic-device-v151"},json={}).json()
    assert data["one_time"] is True
    pair_url=data["pair_url"]
    page.goto(pair_url,wait_until="networkidle")
    page.wait_for_timeout(1800)
    print("PAIR_DIAG",name,"banner",page.locator("#sonicTrustedPairStatus").all_text_contents(),
          "session",{k:v for k,v in page.request.get(base+"/api/session").json().items()
                     if k in ("preview","trusted_uptime","authenticated")},
          "js_errors",errors,flush=True)
    expect(page.locator("#devicesPanel")).to_be_visible(timeout=15000)
    expect(page.locator("#productivityHub")).to_be_visible(timeout=15000)
    expect(page.locator("#productivityHub")).to_have_class("prod-hub preview-uptime-only")
    expect(page.locator("#prodUptimePct")).to_have_text("COLLECTING",timeout=15000)
    expect(page.locator("#prodUptimeTimeline .prod-uptime-bar")).to_have_count(48)
    assert page.locator("#prodUptimeCoverage").inner_text()=="0.00%"
    assert page.locator("#prodUnpairIphone").is_visible()
    assert not page.locator("#prodFacts").is_visible()
    assert page.request.get(base+"/api/history").status==401
    assert page.request.get(base+"/api/uptime/summary").status==401
    assert not errors,(name,errors)
    size=page.evaluate("({viewport:innerWidth,document:document.documentElement.scrollWidth})")
    assert size["document"]<=size["viewport"]+4,(name,size)
    page.screenshot(path=str(out/(name+"-paired.png")),full_page=True)
    page.once("dialog",lambda dialog:dialog.accept())
    page.locator("#prodUnpairIphone").click()
    expect(page.locator("#productivityHub")).to_be_hidden(timeout=15000)
    # Unpair revokes the capability without changing the owner-access policy.
    results.append({"viewport":name,"paired_uptime":True,"private_owner_blocked":True,"errors":errors,"width":size})
    context.close()
 browser.close()
 print(json.dumps(results,indent=2))
