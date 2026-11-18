"""SONIC 1.9 dashboard-first UI acceptance, synthetic owner only.
No real device commands, model calls, or credentials.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
from qa_server import local_server

OUT=Path(__file__).resolve().parents[1]/"artifacts"/"sonic-ia-v190"
OUT.mkdir(parents=True,exist_ok=True)
BROWSER=os.environ.get("SONIC_QA_BROWSER","chromium")
SETTINGS={
 "SONIC_OWNER_ENTRY_ENABLED":"true",
 "SONIC_PASSWORDLESS_LOGIN":"false",
 "SONIC_OPEN_PREVIEW":"true",
 "SONIC_PREVIEW_PAID_ACTIONS":"false",
}
results=[]
with local_server(settings=SETTINGS) as (base,owner),sync_playwright() as p:
 browser=getattr(p,BROWSER).launch(
   headless=True,
   **({"args":["--no-sandbox","--enable-unsafe-swiftshader"]}
      if BROWSER=="chromium" else {})
 )
 for label,w,h in [("desktop",1440,900),("iphone",390,844)]:
  page=browser.new_page(viewport={"width":w,"height":h},is_mobile=w<721,has_touch=w<721)
  errors=[]
  page.on("pageerror",lambda error: errors.append(str(error)))
  page.goto(base+"/owner",wait_until="domcontentloaded")
  page.locator("#ownerToken").fill(owner)
  page.locator("#loginForm button[type=submit]").click()
  expect(page.locator("#loginOverlay")).to_be_hidden(timeout=16000)
  expect(page.locator("#dashboardPanel")).to_be_visible(timeout=16000)
  expect(page.locator("#pageTitle")).to_have_text("Dashboard")
  expect(page.locator("#dashAskForm")).to_be_visible()
  expect(page.locator(".sidebar [data-tab=dashboard]")).to_have_attribute("aria-current","page",timeout=16000)
  assert page.locator(".sonic-dash-quick [data-sonic-open=pc]").count()==1
  page.screenshot(path=str(OUT/f"{BROWSER}-{label}-dashboard.png"),full_page=True)
  page.locator(".sidebar .nav[data-tab=brain]").click()
  expect(page.locator("#brainPanel")).to_be_visible()
  expect(page.locator("#knowledgeViews")).to_be_visible()
  expect(page.locator("#pageTitle")).to_have_text("Knowledge")
  page.locator('#knowledgeViews [data-sonic-knowledge=memory]').click()
  expect(page.locator("#memoryPanel")).to_be_visible()
  assert page.locator("#knowledgeViews").get_attribute("hidden") is None
  page.screenshot(path=str(OUT/f"{BROWSER}-{label}-knowledge.png"),full_page=True)
  if label=="iphone":
   page.locator("#mobileMoreNav").click()
   expect(page.locator("#mobileMoreMenu")).to_be_visible()
   page.locator('[data-mobile-go=devices]').click()
  else:
   page.locator(".sidebar .nav[data-tab=devices]").click()
  expect(page.locator("#devicesPanel")).to_be_visible()
  expect(page.locator("#devicesPanel .sonic-ia-tabs")).to_be_visible()
  expect(page.locator('#devicesPanel [data-ia-group=overview]')).to_be_visible()
  page.locator('#devicesPanel .sonic-ia-tabs [data-ia-target=control]').click()
  expect(page.locator("#pcCommandCenter")).to_be_visible()
  expect(page.locator("#operatorPanel")).to_be_visible()
  page.locator('#devicesPanel .sonic-ia-tabs [data-ia-target=applications]').click()
  expect(page.locator("#softwareManager")).to_be_visible()
  page.screenshot(path=str(OUT/f"{BROWSER}-{label}-devices.png"),full_page=True)
  if label=="iphone":
   page.locator("#mobileMoreNav").click()
   page.locator('[data-mobile-go=setup]').click()
  else:
   page.locator(".sidebar .nav[data-tab=setup]").click()
  expect(page.locator("#setupPanel")).to_be_visible()
  expect(page.locator("#setupPanel .sonic-ia-tabs")).to_be_visible()
  expect(page.locator("#brainModelControl")).to_be_visible()
  expect(page.locator("#huggingFaceHub")).to_be_visible()
  page.locator('#setupPanel .sonic-ia-tabs [data-ia-target=voice]').click()
  expect(page.locator('#setupPanel [data-ia-group=voice]')).to_be_visible()
  expect(page.locator("#personaStudio")).to_be_visible()
  page.screenshot(path=str(OUT/f"{BROWSER}-{label}-settings.png"),full_page=True)
  assert not errors,errors
  if label=="iphone":
   assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 1"),"horizontal overflow"
  results.append({"browser":BROWSER,"viewport":label,"dashboard":True,
    "knowledge_tabs":True,"device_segmentation":True,"settings_segmentation":True,
    "no_window_commands":True,"page_errors":errors})
  page.close()
 browser.close()
(OUT/f"{BROWSER}-report.json").write_text(json.dumps(results,indent=2),encoding="utf-8")
print(json.dumps(results))
print("SONIC_IA_"+BROWSER.upper()+"_PASS")
