"""Artifact Studio desktop/mobile browser acceptance with synthetic owner and files.

Never executes Windows commands, external model requests, installer or deployment.
"""
import base64
import json
import os
from pathlib import Path

from playwright.sync_api import sync_playwright, expect
from qa_server import local_server

OUT = Path("artifacts/artifact-studio-v200")
OUT.mkdir(parents=True, exist_ok=True)
BROWSER = os.environ.get("SONIC_QA_BROWSER", "chromium")
settings = {"SONIC_OPEN_PREVIEW":"true", "SONIC_OWNER_ENTRY_ENABLED":"true",
            "SONIC_PASSWORDLESS_LOGIN":"false", "SONIC_PREVIEW_PAID_ACTIONS":"false"}
reports = []

with local_server(settings=settings) as (base,token), sync_playwright() as playwright:
    browser = getattr(playwright, BROWSER).launch(
        headless=True,
        **({"args":["--no-sandbox","--enable-unsafe-swiftshader"]}
           if BROWSER=="chromium" else {}))
    for label,width,height in [("desktop",1440,900),("iphone",390,844)]:
        page=browser.new_page(viewport={"width":width,"height":height},
                              is_mobile=label=="iphone",has_touch=label=="iphone")
        errors=[]
        page.on("pageerror",lambda e: errors.append(str(e)))
        page.goto(base+"/owner",wait_until="domcontentloaded")
        page.locator("#ownerToken").fill(token)
        page.locator("#loginForm button[type=submit]").click()
        expect(page.locator("#loginOverlay")).to_be_hidden(timeout=20000)
        page.locator('.sidebar [data-tab="studio"]').click()
        expect(page.locator("#studioPanel")).to_be_visible(timeout=15000)
        expect(page.locator("#asNewBtn")).to_be_visible()
        expect(page.locator("#asQuota")).to_contain_text("items",timeout=15000)
        page.screenshot(path=str(OUT/(BROWSER+"-"+label+"-studio-empty.png")),full_page=True)
        initial_artifact_count=page.locator("#asLibrary .as-entry").count()

        page.locator("#asNewBtn").click()
        expect(page.locator("#asEditor")).to_be_visible()
        assert "Kalkulator RAB Interior" in page.locator("#asCode").input_value()
        page.locator("#asPreviewBtn").click()
        expect(page.locator("#asStage iframe.as-iframe")).to_be_visible()
        # Preview must be opaque-origin, not privileged SONIC.
        assert page.locator("#asStage iframe.as-iframe").get_attribute("sandbox")=="allow-scripts"
        frame=page.frame_locator("#asStage iframe.as-iframe")
        expect(frame.locator("#vol")).to_be_visible(timeout=7000)
        expect(frame.locator("#out")).to_contain_text("33.000.000",timeout=7000)
        page.screenshot(path=str(OUT/(BROWSER+"-"+label+"-html-preview.png")),full_page=True)

        page.locator("#asSaveBtn").click()
        expect(page.locator("#asNotice")).to_contain_text("Saved to owner-only SONIC database",timeout=14000)
        expect(page.locator("#asLibrary .as-entry")).to_have_count(initial_artifact_count+1)
        page.locator("#asEditBtn").click()
        expect(page.locator("#asEditor")).to_be_visible()
        page.locator("#asDraftName").fill("RAB Calculator v2")
        page.locator("#asSaveBtn").click()
        expect(page.locator("#asSubtitle")).to_contain_text("v2",timeout=14000)
        page.locator('[data-as-tab="versions"]').click()
        expect(page.locator("#asHistory .as-history-btn")).to_have_count(2)
        page.screenshot(path=str(OUT/(BROWSER+"-"+label+"-versions.png")),full_page=True)
        # Assistant replies arrive asynchronously. Studio must detect HTML only
        # after the final message text has been populated.
        page.locator('.sidebar [data-tab="chat"]').click()
        page.evaluate("""() => {
            const node=document.createElement('div');node.id='asSyntheticReply';node.className='message assistant';
            const body=document.createElement('div');body.className='body';body.textContent='Generating tool…';
            node.append(body);document.getElementById('chatFeed').append(node);
        }""")
        page.evaluate("""() => {
            const ticks=String.fromCharCode(96).repeat(3);
            document.querySelector('#asSyntheticReply .body').textContent=
              ticks+'html\\n<!doctype html><html><body><h1>QA generated tool</h1></body></html>\\n'+ticks;
        }""")
        expect(page.locator("#asSyntheticReply .as-chat-action")).to_be_visible(timeout=8000)
        page.locator("#asSyntheticReply .as-chat-action").click()
        expect(page.locator("#studioPanel")).to_be_visible(timeout=8000)
        assert "QA generated tool" in page.locator("#asCode").input_value()
        assert not errors, errors
        if label=="iphone":
            assert page.evaluate("document.documentElement.scrollWidth<=innerWidth+2"),"horizontal overflow"
        reports.append({"browser":BROWSER,"viewport":label,"owner_api":True,
                        "sandbox_executable":True,"version_history":True,"js_errors":errors})
        page.close()
    browser.close()
(OUT/(BROWSER+"-report.json")).write_text(json.dumps(reports,indent=2),encoding="utf-8")
print(json.dumps(reports))
print("SONIC_ARTIFACT_V200_"+BROWSER.upper()+"_PASS")
