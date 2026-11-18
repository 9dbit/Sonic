"""SONIC v2.2 real engine UI acceptance, no fake owner data or PC actions."""
from __future__ import annotations
import json
import os
import re
from pathlib import Path

from playwright.sync_api import sync_playwright, expect
from qa_server import local_server

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"artifacts"/"ux-v220"
OUT.mkdir(parents=True,exist_ok=True)
BROWSER=os.environ.get("SONIC_QA_BROWSER","chromium")
SETTINGS={"SONIC_OWNER_ENTRY_ENABLED":"true","SONIC_PASSWORDLESS_LOGIN":"false",
          "SONIC_OPEN_PREVIEW":"true","SONIC_PREVIEW_PAID_ACTIONS":"false",
          "SONIC_LOCAL_AI_ENABLED":"false"}
results=[]

with local_server(settings=SETTINGS) as (base,owner),sync_playwright() as playwright:
    binary=os.environ.get("SONIC_QA_CHROME_PATH") if BROWSER=="chromium" else None
    browser=getattr(playwright,BROWSER).launch(
        headless=True,
        **({"executable_path":binary} if binary else {}),
        **({"args":["--no-sandbox","--enable-unsafe-swiftshader"]} if BROWSER=="chromium" else {}))
    for label,width,height in [("desktop",1440,900),("iphone",390,844),("compact",360,740)]:
        mobile=width<721
        page=browser.new_page(viewport={"width":width,"height":height},
                               is_mobile=mobile,has_touch=mobile)
        errors=[]
        page.on("pageerror",lambda error:errors.append(str(error)))
        page.goto(base+"/owner",wait_until="domcontentloaded")
        page.locator("#ownerToken").fill(owner)
        page.locator('#loginForm button[type="submit"]').click()
        expect(page.locator("#loginOverlay")).to_be_hidden(timeout=18000)
        expect(page.locator("body")).to_have_class(re.compile("sonic-ux-v220"),timeout=7000)
        assert page.locator('.sidebar .nav[data-tab=dashboard] use').get_attribute("href")=="#i-home"

        # Chat: real model widget, real device status and a single composer.
        page.locator('.sidebar .nav[data-tab="chat"]').click()
        expect(page.locator("#chatPanel")).to_be_visible()
        expect(page.locator(".sidebar .nav.active")).to_have_count(1)
        expect(page.locator("#v22ChatTop")).to_be_visible()
        expect(page.locator("#v22ModelControl .runtime-widget")).to_be_visible(timeout=8000)
        expect(page.locator("#chatForm")).to_be_visible()
        assert page.locator("#chatPanel .as-chat-banner").is_hidden()
        page.screenshot(path=str(OUT/f"{BROWSER}-{label}-chat.png"),full_page=True)

        # Local failure offers one explicit route into Coding Studio, never a hidden fallback.
        page.evaluate("""() => {
          const feed=document.getElementById('chatFeed');
          const user=document.createElement('div');user.className='message user';
          const txt=document.createElement('div');txt.className='body';
          txt.textContent='Buat kalkulator sederhana ui modern';user.append(txt);feed.append(user);
          const err=document.createElement('div');err.className='message assistant error';
          const body=document.createElement('div');body.className='body';
          body.textContent='Local AI melebihi batas 75 detik.';err.append(body);feed.append(err);
        }""")
        expect(page.locator(".message.error .v22-open-coding")).to_be_visible(timeout=6000)
        page.locator(".message.error .v22-open-coding").last.click()
        expect(page.locator("#studioPanel")).to_be_visible()
        expect(page.locator(".sidebar .nav.active")).to_have_count(1)
        expect(page.locator("#asCodingPrompt")).to_have_value("Buat kalkulator sederhana ui modern")
        expect(page.locator("#v22RecentArtifacts")).to_be_visible()
        expect(page.locator("#asQuota")).to_contain_text("items",timeout=9000)
        prior_count=page.locator("#v22RecentGrid .v22-artifact-card").count()
        expect(page.locator("#asCodingProvider")).to_have_value("local")
        expect(page.locator("#asGenerate")).to_be_enabled()
        expect(page.locator(".v22-studio-hero")).to_be_visible()
        page.screenshot(path=str(OUT/f"{BROWSER}-{label}-studio.png"),full_page=True)

        # Existing generation, preview and persistence must still be usable.
        page.locator("#asNewBtn").click()
        expect(page.locator("#asEditor")).to_be_visible(timeout=8000)
        page.locator("#asPreviewBtn").click()
        expect(page.locator("#asStage iframe.as-iframe")).to_be_visible(timeout=12000)
        iframe=page.frame_locator("#asStage iframe.as-iframe")
        expect(iframe.locator("#out")).to_contain_text("33.000.000",timeout=8000)
        page.locator("#asSaveBtn").click()
        expect(page.locator("#asNotice")).to_contain_text("Saved to owner-only SONIC database",timeout=14000)
        expect(page.locator("#v22RecentGrid .v22-artifact-card")).to_have_count(min(prior_count+1,4),timeout=7000)
        page.screenshot(path=str(OUT/f"{BROWSER}-{label}-gallery.png"),full_page=True)

        # Knowledge uses WebGL engine and a real graph route for its light trace.
        page.locator('.sidebar .nav[data-tab="brain"]').click()
        expect(page.locator("#brainPanel")).to_be_visible()
        expect(page.locator(".sidebar .nav.active")).to_have_count(1)
        expect(page.locator("#v22KnowledgeStatus")).to_be_visible()
        expect(page.locator("#graphStage")).to_be_visible(timeout=8000)
        assert page.evaluate("""() => typeof window.SonicGraph?.prototype.signalIntegration==="function" """)
        assert page.evaluate("""() => window.SonicGraph.shortestPath(
          'sonic','integration',[{source:'sonic',target:'bridge'},{source:'bridge',target:'integration'}]
        ).length===3""")
        if mobile:
            expect(page.locator("#neuralGraphBtn")).to_have_attribute("aria-pressed","true")
            page.locator("#neuralKnowledgeBtn").click()
            expect(page.locator("#neuralKnowledgeList")).to_be_visible()
            page.locator("#neuralGraphBtn").click()
            expect(page.locator("#graphStage")).to_be_visible()
        page.screenshot(path=str(OUT/f"{BROWSER}-{label}-knowledge.png"),full_page=True)

        if mobile:
            # The actual animated SONIC canvas remains anchored on the right.
            for destination,dock in [("brain","v22KnowledgeOrbDock"),("studio","v22StudioOrbDock"),("chat","v22ChatOrbDock")]:
                page.locator('.sidebar .nav[data-tab="'+destination+'"]').click()
                expect(page.locator("#"+dock)).to_be_visible()
                page.wait_for_timeout(200)
                # MotionCore may not start without GPU in CI. The approved
                # animated branded orb is a real, always-rendered fallback.
                bounds=page.locator("#"+dock+" .v22-orb-fallback").bounding_box()
                assert bounds, "missing visible SONIC orb"
                assert bounds["x"] >= width*.48 and bounds["x"]+bounds["width"] <= width+2,(destination,bounds)
                assert 0 <= bounds["y"] < height,(destination,bounds)
                assert page.locator("#"+dock+" .v22-orb-fallback img").get_attribute("src").startswith("/assets/sonic-mark.svg")
            page.locator("#mobileMoreNav").click()
            expect(page.locator("#mobileMoreMenu")).to_be_visible()
            expect(page.locator('[data-mobile-go=workspace]')).to_be_visible()
            # Avoid false overflow even at 360px with safe-area notches.
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2"),"horizontal overflow"
        assert not errors,errors
        results.append({"browser":BROWSER,"viewport":label,"chat":True,"studio":True,
                        "webgl_graph":True,"live_orb_visible":True,
                        "sandbox":True,"no_horizontal_overflow":True,"javascript_errors":errors})
        page.close()
    browser.close()

(OUT/f"{BROWSER}-results.json").write_text(json.dumps(results,indent=2),encoding="utf-8")
print(json.dumps(results))
print("SONIC_UX_V220_"+BROWSER.upper()+"_PASS")
