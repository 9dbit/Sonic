"""Real HTTP / Chromium desktop+mobile checks with isolated synthetic owner/DB."""
import json
import re
import shutil
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
from qa_server import local_server

ARTIFACT=Path('/mnt/data/sonic-v06-browser-qa') if Path('/mnt/data').exists() else Path('artifacts/v06')
ARTIFACT.mkdir(parents=True, exist_ok=True)

with local_server() as (url,token),sync_playwright() as p:
    browser=p.chromium.launch(executable_path=shutil.which('chromium') or None,headless=True,args=['--no-sandbox','--enable-unsafe-swiftshader'])
    results=[]
    for label,view in [('desktop',{'width':1440,'height':900}),('mobile',{'width':390,'height':844})]:
        page=browser.new_page(viewport=view,device_scale_factor=1,is_mobile=label=='mobile',has_touch=label=='mobile')
        errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(url,wait_until='networkidle')
        page.locator('#ownerToken').fill(token)
        page.locator('#loginForm button[type=submit]').click()
        expect(page.locator('#loginOverlay')).to_have_class(re.compile('.*hidden.*'))
        page.locator('.nav[data-tab="setup"]').click()
        expect(page.locator('#personaStudio h3')).to_have_text('Persona Studio')
        expect(page.locator('input[name="sonicVoice"]')).to_have_count(10)
        page.locator('input[name="sonicVoice"][value="female_03"]').check(force=True)
        page.locator('#sonicPersonaStyle').select_option('poetic')
        page.locator('#sonicPersonaIntensity').select_option('expressive')
        # Intercept only browser previews. The request must include the *draft*
        # selected voice + style + intensity, without persisting on Play.
        preview=[]
        def mock_preview(route):
            preview.append(route.request.post_data_json)
            route.fulfill(status=503,content_type='application/json',body='{"detail":"Synthetic TTS test provider"}')
        page.route('**/api/voice/speak',mock_preview)
        page.locator('[data-action="preview-style"]').click()
        expect(page.locator('#personaStatus')).to_contain_text('Synthetic TTS test provider')
        assert preview[-1]['preview_voice_id']=='female_03'
        assert preview[-1]['preview_style']=='poetic'
        assert preview[-1]['preview_intensity']=='expressive'
        assert preview[-1]['text'].startswith('Selamat datang kembali')
        page.locator('[data-action="save"]').click()
        expect(page.locator('#personaStatus')).to_contain_text('Applied:')
        stored=page.evaluate('async()=> (await fetch("/api/persona")).json()')
        assert stored['active']=={'voice_id':'female_03','style':'poetic','intensity':'expressive'},stored
        # Force re-login and verify persisted preferences survive a fresh browser page.
        page.reload(wait_until='networkidle')
        page.locator('.nav[data-tab="setup"]').click()
        expect(page.locator('input[name="sonicVoice"][value="female_03"]')).to_be_checked()
        page.locator('.nav[data-tab="brain"]').click()
        expect(page.locator('#sonicMotionFloat')).to_be_visible()
        motion=page.locator('#sonicMotionFloat')
        page.wait_for_timeout(350)
        visible=page.evaluate('''()=>{
            const core=window.sonicMotion;
            const c=core.canvas,ctx=c.getContext('2d');
            const pixels=ctx.getImageData(0,0,c.width,c.height).data;
            let particles=0;
            for(let i=3;i<pixels.length;i+=4)if(pixels[i]>24)particles++;
            return {particles,width:c.width,height:c.height,renderer:!!core.ctx};
        }''')
        assert visible['renderer'] and visible['particles']>150,visible
        motion.click(force=True)
        expect(motion).to_have_class(re.compile('.*preview.*'))
        page.wait_for_timeout(50)
        motion.click(force=True)
        expect(motion).to_have_class(re.compile('.*focused.*'))
        assert page.evaluate('window.sonicMotion.focused') is True
        # Voice return command should restore without issuing an unsafe API request.
        page.evaluate('window.sonicMotion.handleCommand("SONIC, kembali ke tempat semula")')
        assert page.evaluate('window.sonicMotion.focused') is False
        page.screenshot(path=str(ARTIFACT/f'sonic-v06-{label}.png'),full_page=False)
        assert not errors,errors
        info=page.evaluate('''()=>({canvas:document.querySelector("#sonicMotionFloat canvas").width,
            renderer:!!window.sonicMotion.ctx,motionState:window.sonicMotion.state,
            selected:document.querySelector("#sonicPersonaStyle").value})''')
        results.append({'viewport':label,'motion':info,'particles_visible':visible['particles'],'preview_style_voice_synced':True,'errors':errors,'persona_saved':True,'double_tap':True})
        page.close()
    browser.close()
    (ARTIFACT/'report.json').write_text(json.dumps(results,indent=2))
    print(json.dumps(results,indent=2))
