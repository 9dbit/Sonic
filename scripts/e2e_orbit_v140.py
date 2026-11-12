"""Orbit UI: real Chromium, synthetic local DB and blocked external provider calls.

No live credentials, actual microphone, Railway changes or PC commands.
"""
from __future__ import annotations
import json
import re
from pathlib import Path
from playwright.sync_api import expect, sync_playwright
from qa_server import local_server

OUT = Path('artifacts/sonic-orbit-v140')
OUT.mkdir(parents=True, exist_ok=True)

def layout(page, label):
    result=page.evaluate('''() => ({width:innerWidth,scroll:document.documentElement.scrollWidth,
      panel:[...document.querySelectorAll('.content>.panel')].filter(x=>!x.classList.contains('hidden')).map(x=>{const r=x.getBoundingClientRect();return {left:r.left,right:r.right,width:r.width}})})''')
    assert result['scroll']<=result['width']+2,(label,result)
    for p in result['panel']:
        assert p['width']>=240 and p['left']>=-1 and p['right']<=result['width']+1,(label,result)

with local_server(settings={'DEEPSEEK_API_KEY':'LOCAL-FAKE-DO-NOT-SEND','SONIC_BRAIN_PROVIDER':'deepseek','SONIC_DEEPSEEK_MODEL':'deepseek-flash'}) as (url,token), sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True,args=['--no-sandbox','--enable-unsafe-swiftshader'])
    report=[]
    for label,size in [('desktop',{'width':1440,'height':960}),('tablet',{'width':820,'height':1000}),('mobile',{'width':390,'height':844}),('small-mobile',{'width':360,'height':740})]:
        page=browser.new_page(viewport=size,device_scale_factor=1,is_mobile='mobile' in label,has_touch='mobile' in label)
        errors=[]; starts=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.route('https://**',lambda route:route.abort())
        # Even an unintended provider test cannot spend tokens.
        for path in ['/api/setup/test-provider','/api/chat','/api/voice/sessions']:
            page.route('**'+path,lambda route:route.fulfill(status=503,json={'detail':'Blocked by isolated visual QA'}))
        page.goto(url,wait_until='networkidle')
        expect(page.locator('#loginOverlay')).to_be_visible()
        page.locator('#ownerToken').fill(token);page.locator('#loginForm button[type=submit]').click()
        expect(page.locator('#loginOverlay')).to_have_class(re.compile('hidden'),timeout=15000)
        page.locator('.nav[data-tab="brain"]').click()
        expect(page.locator('#orbitOverview')).to_be_visible()
        expect(page.locator('#orbitMemory')).to_have_text('0')
        expect(page.locator('#orbitDevice')).to_have_text('Offline')
        expect(page.locator('#orbitModel')).to_have_text('deepseek-flash')
        expect(page.locator('#sonicHeaderOrb img')).to_be_visible()
        page.wait_for_timeout(900)
        layout(page,label)
        page.screenshot(path=str(OUT/f'{label}-brain.png'))
        pixels=page.evaluate('''()=>{const m=sonicMotion,c=m.canvas,p=m.ctx.getImageData(0,0,c.width,c.height).data;let visible=0,white=0,blue=0,purple=0;for(let i=0;i<p.length;i+=4){if(p[i+3]<25)continue;visible++;if(p[i]>180&&p[i+1]>180&&p[i+2]>180)white++;if(p[i+2]>p[i+1]&&p[i+1]>p[i])blue++;if(p[i]>p[i+1]&&p[i+2]>p[i+1])purple++;}return {renderer:m.renderer,visible,white,blue,purple,width:c.width,height:c.height}}''')
        assert pixels['renderer']=='orb-v140' and pixels['visible']>500 and pixels['white']>20 and pixels['blue']>30 and pixels['purple']>30,pixels
        # Exercise real app routing; only the transport start is replaced. No mic access.
        page.evaluate('''()=>{window.__voiceStarts=0;window.__realStart=SonicVoice.prototype.start;SonicVoice.prototype.start=async function(){window.__voiceStarts++;this.setState('listening');};window.__invokes=0;window.addEventListener('sonic:invoke',()=>window.__invokes++);}''')
        page.locator('#sonicHeaderOrb').click()
        assert page.evaluate('window.__voiceStarts')==0
        page.wait_for_timeout(60);page.locator('#sonicHeaderOrb').click()
        assert page.evaluate('window.__voiceStarts')==1
        assert page.evaluate('sonicMotion.focused') is True
        expect(page.locator('#orbitVoiceState')).to_have_text('Listening')
        page.wait_for_timeout(1000)
        layers=page.evaluate('''()=>({aura:+getComputedStyle(document.querySelector('#sonicWaveAura')).opacity,auraZ:+getComputedStyle(document.querySelector('#sonicWaveAura')).zIndex,shadeZ:+getComputedStyle(document.querySelector('#sonicFocusShade')).zIndex,orbZ:+getComputedStyle(document.querySelector('#sonicMotionFloat')).zIndex,pointer:getComputedStyle(document.querySelector('#sonicWaveAura')).pointerEvents,inert:document.querySelector('#orbitOverview').inert})''')
        assert layers['aura']>.95 and layers['pointer']=='none' and layers['inert'] and layers['shadeZ']<layers['auraZ']<layers['orbZ'],layers
        expect(page.locator('#voiceStop')).to_be_visible()
        # Voice Stop must win the real hit test over the aura and focus shade.
        assert page.locator('#voiceStop').evaluate('el=>{const r=el.getBoundingClientRect();return el.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2));}')
        page.screenshot(path=str(OUT/f'{label}-voice.png'))
        page.locator('#voiceStop').click()
        assert page.evaluate('sonicMotion.focused') is False
        expect(page.locator('#orbitVoiceCaption')).to_be_hidden()
        assert page.evaluate('document.querySelector("#orbitOverview").inert') is False
        page.locator('[data-orbit-tab="memory"]').click()
        expect(page.locator('#memoryPanel')).to_be_visible()
        expect(page.locator('#orbitOverview')).to_be_hidden()
        for tab in ['chat','workspace','devices','setup','brain']:
            page.locator('.nav[data-tab="'+tab+'"]').click();layout(page,label+'-'+tab)
            if tab in ('chat','setup'):page.screenshot(path=str(OUT/f'{label}-{tab}.png'))
        # Expired sessions cannot retain or repopulate private overview values.
        page.evaluate("document.querySelector('#loginOverlay').classList.remove('hidden')")
        expect(page.locator('#orbitMemory')).to_have_text('Locked')
        page.evaluate("window.dispatchEvent(new CustomEvent('sonic:overview',{detail:{kind:'memory',count:999}}))")
        expect(page.locator('#orbitMemory')).to_have_text('Locked')
        page.evaluate("document.querySelector('#loginOverlay').classList.add('hidden')")
        # The aura respects reduced motion and the renderer stays visually useful.
        page.emulate_media(reduced_motion='reduce')
        page.wait_for_timeout(100)
        assert page.evaluate('sonicMotion.reduced') is True
        assert page.locator('.orbit-aura-ribbon').first.evaluate('e=>getComputedStyle(e).animationName')=='none'
        assert not errors,(label,errors)
        report.append({'viewport':label,'layout':True,'orbPixels':pixels,'layers':layers,'voiceStarts':page.evaluate('__voiceStarts'),'reducedMotion':True,'errors':errors})
        page.close()
    # Passwordless login screen with actual production render path, no registration.
    browser.close()
with local_server(settings={'SONIC_PASSWORDLESS_LOGIN':'true'}) as (url,_),sync_playwright() as pw:
    browser=pw.chromium.launch(headless=True,args=['--no-sandbox'])
    for label,size in [('desktop',{'width':1440,'height':960}),('mobile',{'width':390,'height':844})]:
        page=browser.new_page(viewport=size)
        page.goto(url,wait_until='networkidle')
        expect(page.locator('#ownerToken')).to_be_hidden()
        expect(page.locator('.login-card')).to_be_visible()
        page.screenshot(path=str(OUT/f'{label}-passkey.png'))
        assert page.request.post(url+'/api/login',data={'token':'not-an-owner'}).status!=200
        page.close()
    browser.close()
(OUT/'report.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
