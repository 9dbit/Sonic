"""SONIC v2.3.1: public preview, owner entry and static focus at iPhone widths."""
import os
import re
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from qa_server import local_server

BROWSER=os.getenv("SONIC_QA_BROWSER","chromium")
OUT=Path("artifacts/ux-v231")
OUT.mkdir(parents=True,exist_ok=True)
SETTINGS={"SONIC_OWNER_ENTRY_ENABLED":"true","SONIC_PASSWORDLESS_LOGIN":"false",
          "SONIC_OPEN_PREVIEW":"true","SONIC_PREVIEW_PAID_ACTIONS":"false",
          "SONIC_LOCAL_AI_ENABLED":"false"}

def assert_fits(page):
    d=page.evaluate("""() => {
      const r=s=>{const e=document.querySelector(s);if(!e)return null;const b=e.getBoundingClientRect();
        return {left:b.left,right:b.right,top:b.top,bottom:b.bottom,width:b.width};};
      return {vw:innerWidth,scroll:document.documentElement.scrollWidth,
        header:r('.topbar'),buttons:r('.topbar .top-right'),
        owner:r('#sonicOwnerAccess')};
    }""")
    assert d["scroll"]<=d["vw"]+2,d
    for key in ["header","buttons","owner"]:
        assert d[key] is not None,d
        assert d[key]["left"]>=-1 and d[key]["right"]<=d["vw"]+1,d

with local_server(settings=SETTINGS) as (base,token),sync_playwright() as pw:
    browser=getattr(pw,BROWSER).launch(headless=True,
        **({"args":["--no-sandbox","--enable-unsafe-swiftshader"]} if BROWSER=="chromium" else {}))
    for name,width,height in [("iphone",390,844),("compact",360,740)]:
        page=browser.new_page(viewport={"width":width,"height":height},
            is_mobile=True,has_touch=True)
        errors=[]
        page.on("pageerror",lambda error:errors.append(str(error)))
        page.goto(base+"/",wait_until="domcontentloaded")
        expect(page.locator("body")).to_have_class(re.compile("sonic-open-preview"),timeout=18000)
        expect(page.locator("#sonicOwnerAccess")).to_be_visible(timeout=10000)
        assert_fits(page)
        page.locator('.sidebar .nav[data-tab="chat"]').click()
        expect(page.locator("#previewModelPicker select")).to_be_visible()
        expect(page.locator("#v22ModelControl .runtime-widget")).to_be_hidden()
        expect(page.locator("#v22PCOnline")).to_contain_text("Private")
        page.screenshot(path=str(OUT/f"{BROWSER}-{name}-preview-chat.png"))
        page.locator('.sidebar .nav[data-tab="studio"]').click()
        expect(page.locator("#v231OwnerGate")).to_be_visible()
        expect(page.locator("#v231StudioOwnerLogin")).to_have_attribute("href","/owner")
        expect(page.locator("#asGenerate")).to_be_hidden()
        page.screenshot(path=str(OUT/f"{BROWSER}-{name}-preview-studio.png"))
        # No external microphone or provider call: validate the focus layout
        # directly through the existing in-browser motion controller.
        page.evaluate("() => window.sonicMotion.setFocus(true)")
        expect(page.locator("body")).to_have_class(re.compile("sonic-focused"))
        expect(page.locator(".sidebar")).to_be_hidden()
        focused=page.evaluate("""() => {
          const style=getComputedStyle(document.querySelector('#sonicFocusShade'),'::after');
          const caption=document.getElementById('orbitVoiceCaption').getBoundingClientRect();
          return {icon:style.backgroundImage,iconContent:style.content,
                  captionTop:caption.top,captionBottom:caption.bottom,vh:innerHeight};
        }""")
        assert "sonic-mark.svg" in focused["icon"],focused
        assert focused["captionTop"]>0 and focused["captionBottom"]<focused["vh"],focused
        page.screenshot(path=str(OUT/f"{BROWSER}-{name}-voice-focus.png"))
        page.locator(".sonic-focus-controls button").last.click()
        expect(page.locator("body")).not_to_have_class(re.compile("sonic-focused"))
        # The real owner login is available and the restricted Studio becomes
        # a usable authoring workspace only after owner authentication.
        page.locator("#sonicOwnerAccess").click()
        expect(page.locator("#loginOverlay")).to_be_visible()
        page.wait_for_url(re.compile(r".*/owner$"),timeout=12000)
        page.locator("#ownerToken").fill(token)
        login_responses=[]
        page.on("response",lambda response:login_responses.append((response.status,response.url.split("/")[-1]))
            if "/api/owner/login" in response.url else None)
        page.locator('#loginForm button[type="submit"]').click()
        try:
            expect(page.locator("#loginOverlay")).to_be_hidden(timeout=18000)
        except AssertionError:
            print("SONIC_OWNER_LOGIN_DIAGNOSTICS",
                {"viewport":name,"url":page.url,
                 "error":page.locator("#loginError").text_content(),
                 "responses":login_responses,
                 "preview":page.locator("body").get_attribute("class")},flush=True)
            page.screenshot(path=str(OUT/f"{BROWSER}-{name}-owner-login-failed.png"))
            raise
        page.locator('.sidebar .nav[data-tab="studio"]').click()
        expect(page.locator("#studioPanel")).to_be_visible()
        expect(page.locator("#v231OwnerGate")).to_have_count(0)
        expect(page.locator("#asGenerate")).to_be_enabled(timeout=8000)
        assert not errors,errors
        page.screenshot(path=str(OUT/f"{BROWSER}-{name}-owner-studio.png"))
        page.close()
    browser.close()
print("SONIC_V231_"+BROWSER.upper()+"_PASS")
