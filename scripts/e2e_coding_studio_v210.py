"""Browser acceptance for explicit Coding Studio choices and sandbox handoff."""
import json
import os
from pathlib import Path
from playwright.sync_api import expect, sync_playwright
from qa_server import local_server

OUT=Path("artifacts/coding-studio-v210")
OUT.mkdir(parents=True,exist_ok=True)
BROWSER=os.environ.get("SONIC_QA_BROWSER","chromium")
HTML='''<!doctype html><html lang="id"><head><style>body{font:16px system-ui;padding:25px}</style></head>
<body><main><h1>RAB Calculator</h1><label>Volume<input type="number" id="v" value="3"></label>
<label>Price<input type="number" id="p" value="500"></label><output id="out"></output>
<script>const v=document.getElementById('v'),p=document.getElementById('p'),o=document.getElementById('out');
function calc(){o.textContent=String(Number(v.value)*Number(p.value))}v.oninput=p.oninput=calc;calc();</script>
</main></body></html>'''
settings={"SONIC_OPEN_PREVIEW":"true","SONIC_OWNER_ENTRY_ENABLED":"true",
          "SONIC_PASSWORDLESS_LOGIN":"false","SONIC_PREVIEW_PAID_ACTIONS":"false"}
results=[]
with local_server(settings=settings) as (base,token),sync_playwright() as p:
    browser=getattr(p,BROWSER).launch(headless=True,**(
       {"args":["--no-sandbox","--enable-unsafe-swiftshader"]} if BROWSER=="chromium" else {}))
    for device,width,height in [("desktop",1440,900),("iphone",390,844)]:
        page=browser.new_page(viewport={"width":width,"height":height},
                              is_mobile=device=="iphone",has_touch=device=="iphone")
        errors=[]
        page.on("pageerror",lambda e:errors.append(str(e)))
        page.on("dialog",lambda dialog:dialog.accept())
        page.goto(base+"/owner",wait_until="domcontentloaded")
        page.locator("#ownerToken").fill(token)
        page.locator("#loginForm button[type=submit]").click()
        expect(page.locator("#loginOverlay")).to_be_hidden(timeout=16000)
        page.locator('.sidebar .nav[data-tab="chat"]').click()
        expect(page.locator(".as-chat-banner .as-button").first).to_be_visible()
        page.locator(".as-chat-banner .as-button").first.click()
        expect(page.locator("#studioPanel")).to_be_visible(timeout=10000)
        expect(page.locator("#asGenerate")).to_be_disabled()
        expect(page.locator("#asCodingProvider")).to_have_value("")
        page.screenshot(path=str(OUT/f"{BROWSER}-{device}-coding-empty.png"),full_page=True)
        page.route("**/api/coding/generate",lambda route:route.fulfill(
            status=200,content_type="application/json",
            body=json.dumps({"state":"done","provider":"deepseek",
                             "model":"deepseek-flash","html":HTML,
                             "saved":False,"previewed":False})))
        page.locator("#asCodingProvider").select_option("deepseek")
        page.locator("#asCodingPrompt").fill("Create a small RAB calculator for interior construction.")
        expect(page.locator("#asGenerate")).to_be_enabled()
        page.locator("#asGenerate").click()
        expect(page.locator("#asCodingStatus")).to_contain_text("Source lengkap",timeout=12000)
        assert "RAB Calculator" in page.locator("#asCode").input_value()
        expect(page.locator("#asEditor")).to_be_visible()
        page.screenshot(path=str(OUT/f"{BROWSER}-{device}-generated-code.png"),full_page=True)
        page.locator("#asPreviewBtn").click()
        expect(page.locator("#asStage iframe.as-iframe")).to_be_visible(timeout=9000)
        frame=page.frame_locator("#asStage iframe.as-iframe")
        expect(frame.locator("#out")).to_contain_text("1500",timeout=9000)
        page.screenshot(path=str(OUT/f"{BROWSER}-{device}-sandbox-preview.png"),full_page=True)
        page.locator("#asSaveBtn").click()
        expect(page.locator("#asNotice")).to_contain_text("Saved to owner-only SONIC database",timeout=12000)
        saved_id=page.locator("#asLibrary .as-entry").first.get_attribute("data-id")
        page.locator("#asCodeRevise").check()
        page.locator("#asCodingProvider").select_option("deepseek")
        page.locator("#asGenerate").click()
        expect(page.locator("#asCodingStatus")).to_contain_text("Source lengkap",timeout=12000)
        page.locator("#asSaveBtn").click()
        expect(page.locator("#asSubtitle")).to_contain_text("v2",timeout=12000)
        assert page.locator("#asLibrary .as-entry").first.get_attribute("data-id")==saved_id
        page.locator("#asCodeRevise").uncheck()
        page.locator("#asCodingProvider").select_option("local")
        page.locator("#asCodingPrompt").fill("Create one small local HTML stopwatch UI.")
        page.unroute("**/api/coding/generate")
        page.route("**/api/coding/generate",lambda route:route.fulfill(
          status=200,content_type="application/json",
          body=json.dumps({"state":"queued","provider":"local","job_id":"00000000-0000-0000-0000-000000000001"})))
        page.route("**/api/coding/local/*",lambda route:route.fulfill(
          status=200,content_type="application/json",
          body=json.dumps({"state":"failed","error":"Local AI output terpotong. Pilih DeepSeek Cloud secara eksplisit."})))
        page.locator("#asGenerate").click()
        expect(page.locator("#asCodingStatus")).to_contain_text("terpotong",timeout=14000)
        expect(page.locator("#asCodingProvider")).to_have_value("local")
        assert page.locator("#asLibrary .as-entry").count()>=1
        if device=="iphone":
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2"),"horizontal overflow"
        assert not errors,errors
        results.append({"browser":BROWSER,"device":device,"cloud_choice":True,
                        "local_no_fallback":True,"sandbox":True,"js_errors":errors})
        page.close()
    browser.close()
(OUT/f"{BROWSER}-report.json").write_text(json.dumps(results,indent=2),encoding="utf-8")
print(json.dumps(results))
print("SONIC_CODING_V210_"+BROWSER.upper()+"_PASS")
