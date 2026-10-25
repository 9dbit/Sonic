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
        page.locator('[data-action="save"]').click()
        expect(page.locator('#personaStatus')).to_contain_text('Saved.')
        stored=page.evaluate('async()=> (await fetch("/api/persona")).json()')
        assert stored['active']=={'voice_id':'female_03','style':'poetic','intensity':'expressive'},stored
        # Force re-login and verify persisted preferences survive a fresh browser page.
        page.reload(wait_until='networkidle')
        page.locator('.nav[data-tab="setup"]').click()
        expect(page.locator('input[name="sonicVoice"][value="female_03"]')).to_be_checked()
        page.locator('.nav[data-tab="brain"]').click()
        expect(page.locator('#sonicMotionFloat')).to_be_visible()
        motion=page.locator('#sonicMotionFloat')
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
            webgl:!!window.sonicMotion.gl,videoLoaded:window.sonicMotion.video.readyState,
            selected:document.querySelector("#sonicPersonaStyle").value})''')
        results.append({'viewport':label,'motion':info,'errors':errors,'persona_saved':True,'double_tap':True})
        page.close()
    browser.close()
    (ARTIFACT/'report.json').write_text(json.dumps(results,indent=2))
    print(json.dumps(results,indent=2))
