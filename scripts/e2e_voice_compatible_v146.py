"""Browser contract: Safari-compatible speech fallback after WebRTC failure.
No microphone used; model and speech are stubbed and no paid requests occur.
"""
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
from qa_server import local_server

ROOT=Path(__file__).resolve().parent.parent
OUT=ROOT/"artifacts"/"voice-compatible-v146"
OUT.mkdir(parents=True,exist_ok=True)

BOOTSTRAP="""
window.__compat={};
window.SpeechRecognition=window.webkitSpeechRecognition=class {
  constructor(){this.lang='';this.continuous=false;}
  start(){window.__compat.recognition=this;}
  abort(){window.__compat.aborted=true;}
};
window.SpeechSynthesisUtterance=class {
  constructor(text){this.text=text;}
};
Object.defineProperty(window,'speechSynthesis',{configurable:true,value:{
  getVoices:()=>[{lang:'id-ID',name:'Bahasa Indonesia'}],
  speak:u=>{window.__compat.utterance=u;},
  cancel:()=>{window.__compat.cancelled=true;}
}});
"""

with local_server(settings={
    "SONIC_OPEN_PREVIEW":"true",
    "SONIC_PREVIEW_PAID_ACTIONS":"true",
    "SONIC_BRAIN_PROVIDER":"deepseek",
    "SONIC_DEEPSEEK_MODEL":"deepseek-flash",
    "DEEPSEEK_API_KEY":"SYNTHETIC-ONLY",
    "OPENAI_API_KEY":"SYNTHETIC-ONLY"
}) as (url,_),sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True,args=["--no-sandbox"])
    for label,viewport in [("desktop",{"width":1400,"height":860}),
                           ("mac",{"width":1024,"height":768}),
                           ("iphone",{"width":390,"height":844})]:
        page=browser.new_page(viewport=viewport)
        page.add_init_script(BOOTSTRAP)
        calls=[]
        def fake(route):
            calls.append(route.request.post_data_json)
            route.fulfill(status=200,json={"reply":"SONIC hadir. Ada yang bisa saya bantu?",
                "provider":"deepseek","model":"deepseek-flash"})
        page.route("**/api/preview/chat",fake)
        errs=[]
        page.on("pageerror",lambda e:errs.append(str(e)))
        page.goto(url,wait_until="networkidle")
        expect(page.locator("#loginOverlay")).to_be_hidden()
        page.evaluate("""()=>{sonicMotion.setFocus(true);
          sonicMotion.voiceFeedback('WebRTC disconnected',{retry:true,compat:true});}""")
        expect(page.locator("#sonicVoiceCompatible")).to_be_visible()
        page.screenshot(path=str(OUT/f"{label}-voice-options.png"))
        page.locator("#sonicVoiceCompatible").click()
        expect(page.locator("#sonicVoiceFocusStop")).to_be_visible()
        page.evaluate("""()=>window.__compat.recognition.onresult({
          results:[{isFinal:true,0:{transcript:'Halo SONIC'}}]
        })""")
        for _ in range(70):
            if page.evaluate("()=>Boolean(window.__compat.utterance?.text?.includes('SONIC hadir'))"):
                break
            page.wait_for_timeout(100)
        assert page.evaluate("()=>Boolean(window.__compat.utterance?.text?.includes('SONIC hadir'))"), page.locator('#notice').inner_text()
        assert len(calls)==1,calls
        assert calls[0]["message"]=="Halo SONIC",calls
        assert calls[0]["provider"]=="deepseek",calls
        expect(page.locator("#sonicVoiceFocusHint")).to_contain_text("membacakan")
        page.evaluate("window.__compat.utterance.onend()")
        expect(page.locator("#sonicVoiceCompatible")).to_be_visible()
        assert page.evaluate("window.__compat.aborted") is True
        assert not errs,(label,errs)
        assert page.request.get(url+"/api/history").status==401
        print("PASS",label,"compat transcript, no owner data, response voice and stop")
        page.close()
    browser.close()
