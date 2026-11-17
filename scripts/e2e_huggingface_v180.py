"""SONIC v1.8 Hugging Face browser QA: owner discovery and guest isolation."""
import os
import re
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
from qa_server import local_server

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/"artifacts"/"huggingface-v180"
OUT.mkdir(parents=True,exist_ok=True)
PIN="mradermacher/DeepSeek-V4-Pro-Qwen3.5-9B-UNCENSORED-heretic-GGUF"
SAMPLE=[
 {"id":PIN,"title":"DeepSeek-V4-Pro-Qwen3.5-9B-UNCENSORED-heretic-GGUF",
  "author":"mradermacher","downloads":15200,"likes":104,"gated":False,
  "url":"https://huggingface.co/"+PIN,"installed_in_sonic":True},
 {"id":"unsloth/Qwen3.5-9B-GGUF","title":"Qwen3.5-9B-GGUF",
  "author":"unsloth","downloads":812000,"likes":422,"gated":False,
  "url":"https://huggingface.co/unsloth/Qwen3.5-9B-GGUF","installed_in_sonic":False}
]
def item(id):
    return {**next(i for i in SAMPLE if i["id"]==id),
        "license":"apache-2.0","files":[
            {"filename":"model.Q4_K_M.gguf","bytes":5780092768},
            {"filename":"model.Q8_0.gguf","bytes":9780000000}
        ],"gguf_count":2}

SETTINGS={"SONIC_OPEN_PREVIEW":"true","SONIC_OWNER_ENTRY_ENABLED":"true",
          "SONIC_LOCAL_AI_ENABLED":"true","SONIC_PASSWORDLESS_LOGIN":"false"}
with local_server(settings=SETTINGS) as (base,token),sync_playwright() as p:
    candidates=[Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
                Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")]
    binary=next((str(v) for v in candidates if v.exists()),None)
    browser=p.chromium.launch(executable_path=binary,headless=True,args=["--no-sandbox","--enable-unsafe-swiftshader"])
    for name,w,h in (("mobile",390,844),("compact",360,740),("desktop",1440,900)):
        page=browser.new_page(viewport={"width":w,"height":h},is_mobile=w<721,has_touch=w<721)
        errors=[]
        page.on("pageerror",lambda e:errors.append(str(e)))
        page.route("**/api/huggingface/search?*",lambda route:route.fulfill(
            status=200,content_type="application/json",json={"results":SAMPLE,"count":2,"read_only":True}))
        page.route(re.compile(r".*/api/huggingface/model/.*"),lambda route:route.fulfill(
            status=200,content_type="application/json",
            json=item(PIN if PIN in route.request.url else "unsloth/Qwen3.5-9B-GGUF")))
        # Guest must not load private hub metadata or enable device controls.
        page.goto(base+"/",wait_until="domcontentloaded")
        expect(page.locator("#huggingFaceHub")).to_have_count(1)
        expect(page.locator("#hfStartPinned")).to_be_disabled()
        page.goto(base+"/owner",wait_until="domcontentloaded")
        page.locator("#ownerToken").fill(token)
        page.locator('#loginForm button[type=submit]').click()
        expect(page.locator("#loginOverlay")).to_be_hidden(timeout=12000)
        page.locator('.nav[data-tab="devices"]').click()
        expect(page.locator("#huggingFaceHub")).to_be_visible()
        expect(page.locator("#hfConnection")).to_have_text("CONNECTED",timeout=14000)
        expect(page.locator(".hf-result")).to_have_count(2,timeout=14000)
        expect(page.locator("#hfSelectedTitle")).to_contain_text("DeepSeek",timeout=10000)
        expect(page.locator(".hf-file")).to_have_count(2,timeout=10000)
        page.locator(".hf-result").nth(1).click()
        expect(page.locator("#hfSelectedTitle")).to_contain_text("Qwen3.5",timeout=10000)
        expect(page.locator("#hfStartPinned")).to_be_disabled()
        expect(page.locator("#hfUseChatPinned")).to_be_disabled()
        page.locator(".hf-result").first.click()
        expect(page.locator("#hfSelectedTitle")).to_contain_text("DeepSeek",timeout=10000)
        page.locator("#hfSearchInput").fill("DeepSeek GGUF")
        page.locator("#hfSearchButton").click()
        expect(page.locator(".hf-result")).to_have_count(2,timeout=10000)
        page.locator("#hfJump").click()
        page.locator("#huggingFaceHub").scroll_into_view_if_needed()
        page.wait_for_timeout(250)
        page.screenshot(path=str(OUT/f"{name}.png"))
        dims=page.evaluate("""()=>({
            documentWidth:document.documentElement.scrollWidth,
            width:innerWidth,
            hub:(()=>{let r=document.getElementById('huggingFaceHub').getBoundingClientRect();return{x:r.x,right:r.right,width:r.width}})()
        })""")
        assert dims["documentWidth"]<=dims["width"]+1,dims
        assert dims["hub"]["x"]>=-1 and dims["hub"]["right"]<=dims["width"]+1,dims
        assert not errors,errors
        print(name,"HF_HUB_PASS",dims,flush=True)
        page.close()
    browser.close()
print("SONIC_HF_HUB_V180_E2E_PASS")
