"""Browser acceptance of SONIC owner-only productivity UI."""
import json
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from qa_server import local_server

OUT=Path("artifacts/productivity-v148")
OUT.mkdir(parents=True,exist_ok=True)
report=[]
with local_server(settings={"DEEPSEEK_API_KEY":"FAKE-DO-NOT-CALL","SONIC_BRAIN_PROVIDER":"deepseek"}) as (url,token), sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True,args=["--no-sandbox","--enable-unsafe-swiftshader"])
    for name,viewport in [("desktop",{"width":1440,"height":900}),("mobile",{"width":390,"height":844}),("small-mobile",{"width":360,"height":740})]:
        page=browser.new_page(viewport=viewport)
        errors=[]
        page.on("pageerror",lambda e:errors.append(str(e)))
        page.route("https://**",lambda r:r.abort())
        page.goto(url,wait_until="networkidle")
        expect(page.locator("#loginOverlay")).to_be_visible()
        expect(page.locator("#productivityHub")).to_be_hidden()
        page.locator("#ownerToken").fill(token)
        page.locator("#loginForm button[type=submit]").click()
        expect(page.locator("#loginOverlay")).to_have_class("login-overlay hidden",timeout=15000)
        page.locator('.nav[data-tab="devices"]').click()
        expect(page.locator("#productivityHub")).to_be_visible(timeout=15000)
        expect(page.locator("#prodUptimePct")).to_have_text("COLLECTING",timeout=15000)
        assert page.locator("#prodUptimeTimeline .prod-uptime-bar").count()==48
        expect(page.locator("#prodUptimeCoverage")).to_have_text("0.00%")
        page.locator("#prodFactTitle").fill("Project checkpoint")
        page.locator("#prodFactText").fill("Browser QA checkpoint with synthetic data only.")
        page.locator("#productivityHub button:has-text('Save to project')").click()
        expect(page.locator("#prodFacts")).to_contain_text("Project checkpoint")
        page.locator("#prodGoal").fill("Review project requirements safely")
        page.locator("#prodSteps").fill("Prepare baseline checklist\nReview approved steps")
        page.locator("#productivityHub button:has-text('Create draft mission')").click()
        expect(page.locator("#prodMissions")).to_contain_text("Review project requirements safely")
        expect(page.locator("#prodMissions")).to_contain_text("draft")
        page.locator("#prodMissions button:has-text('Approve plan')").click()
        expect(page.locator("#prodMissions")).to_contain_text("approved")
        page.locator("#prodMissions button:has-text('Start manual work')").click()
        expect(page.locator("#prodMissions")).to_contain_text("in_progress")
        expect(page.locator("#prodMissions button:has-text('Mark completed')")).to_be_disabled()
        for i in range(2):
            page.once("dialog",lambda dialog:dialog.accept("Synthetic browser checkpoint verified"))
            page.locator("#prodMissions button:has-text('Complete step')").click()
            expect(page.locator("#prodMissions")).to_contain_text("checkpoints "+str(i+1)+"/2")
        expect(page.locator("#prodMissions button:has-text('Mark completed')")).to_be_enabled()
        page.once("dialog",lambda dialog:dialog.accept("Synthetic final evidence for QA"))
        page.locator("#prodMissions button:has-text('Mark completed')").click()
        expect(page.locator("#prodMissions")).to_contain_text("completed")
        page.locator("#prodMissions button:has-text('Audit log')").first.click()
        expect(page.locator("#prodMissions")).to_contain_text("mission.completed")
        assert page.locator("#prodDiagButtons button").count()==4
        assert all(page.locator("#prodDiagButtons button").nth(i).is_disabled() for i in range(4))
        width=page.evaluate("({viewport:innerWidth,document:document.documentElement.scrollWidth})")
        assert width["document"]<=width["viewport"]+4,(name,width)
        assert not errors,(name,errors)
        page.screenshot(path=str(OUT/(name+"-devices.png")),full_page=True)
        report.append({"viewport":name,"errors":errors,"ui_visible":True,"memory_saved":True,"mission_checkpoint_evidence_flow":True,"no_device_execution":True,"width":width})
        page.close()
    browser.close()
(OUT/"report.json").write_text(json.dumps(report,indent=2),encoding="utf-8")
print(json.dumps(report,indent=2))
