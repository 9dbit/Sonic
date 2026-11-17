"""Owner login isolation regression. Synthetic sessions, no PC or AI calls.
Run SONIC_QA_BROWSER=webkit for WebKit, default Chromium. Artifacts distinguish
local synthetic screenshots from separately verified live staging screenshots.
"""
import json
import os
from pathlib import Path
from playwright.sync_api import sync_playwright, expect
from qa_server import local_server

OUT=Path('artifacts/auth-isolation'); OUT.mkdir(parents=True,exist_ok=True)
SETTINGS={'SONIC_OPEN_PREVIEW':'true','SONIC_OWNER_ENTRY_ENABLED':'true',
          'SONIC_PASSWORDLESS_LOGIN':'false','SONIC_LOCAL_AI_ENABLED':'false',
          'SONIC_RESEARCH_AGENT_ENABLED':'false','SONIC_PREVIEW_PAID_ACTIONS':'false'}


def assert_locked(page, *, js=True):
    expect(page.locator('#loginOverlay')).to_be_visible()
    for selector in ('.app','.sidebar','#neuralMobileSwitcher','#mobileMoreNav',
                     '#sonicMotionFloat','#orbitVoiceCaption'):
        loc=page.locator(selector)
        if loc.count(): expect(loc).to_be_hidden()
    form=page.locator('#loginOverlay .login-card')
    expect(form).to_be_visible()
    if js: expect(page.locator('.app')).to_have_attribute('inert','')
    metrics=page.evaluate('''() => {
      const overlay=document.getElementById('loginOverlay');
      const card=overlay.querySelector('.login-card').getBoundingClientRect();
      return {width:innerWidth,scrollWidth:document.documentElement.scrollWidth,
        card:{left:card.left,right:card.right},
        inert:document.querySelector('.app').inert};
    }''')
    assert metrics['scrollWidth']<=metrics['width']+1,metrics
    assert metrics['card']['left']>=0 and metrics['card']['right']<=metrics['width']+1,metrics
    if js: assert metrics['inert'] is True,metrics
    # Real hit testing, not just "form is visible". Check logo, field, button.
    for selector in ('#loginOverlay .login-orb img','#ownerToken',
                     '#loginForm button[type="submit"]'):
        loc=page.locator(selector)
        if not loc.is_visible(): continue
        loc.scroll_into_view_if_needed()
        hit=loc.evaluate('''el => {
          const r=el.getBoundingClientRect();
          return [[.5,.5],[.15,.5],[.85,.5]].every(([x,y])=>{
            const n=document.elementFromPoint(r.x+r.width*x,r.y+r.height*y);
            return !!n && (el===n||el.contains(n));
          });
        }''')
        assert hit, 'Login control obscured: '+selector


def main():
    engine=os.environ.get('SONIC_QA_BROWSER','chromium')
    reports=[]
    with local_server(settings=SETTINGS) as (base,token),sync_playwright() as p:
        browser=getattr(p,engine).launch(headless=True,**({'args':['--no-sandbox','--enable-unsafe-swiftshader']} if engine=='chromium' else {}))
        for name,w,h in [('iphone',390,690),('small',360,640),('landscape',844,390),('desktop',1440,900)]:
            page=browser.new_page(viewport={'width':w,'height':h},is_mobile=w<=844,has_touch=w<=844)
            errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
            # No vendor API can be called by this visual QA.
            page.route('https://**',lambda route:route.abort())
            page.goto(base+'/owner',wait_until='domcontentloaded')
            expect(page.locator('#loginOverlay')).to_have_attribute('aria-modal','true')
            assert_locked(page)
            page.locator('#loginOverlay').evaluate('el=>el.scrollTop=0')
            page.screenshot(path=str(OUT/f'{engine}-{name}-first-load.png'))
            if name=='iphone':
                page.locator('#ownerToken').fill('synthetic-invalid-token')
                page.locator('#loginForm button[type=submit]').click()
                expect(page.locator('#loginError')).not_to_be_empty()
                assert_locked(page)
                page.locator('#ownerToken').fill('')
            # Tab cannot move focus into application controls under the login.
            page.locator('#ownerToken').focus()
            for _ in range(8):
                page.keyboard.press('Tab')
                assert page.evaluate("document.getElementById('loginOverlay').contains(document.activeElement)")
            page.locator('#loginOverlay').evaluate('el=>el.scrollTop=0')
            page.locator('#ownerToken').blur()
            page.screenshot(path=str(OUT/f'{engine}-{name}-logged-out.png'))
            page.locator('#ownerToken').fill(token)
            page.locator('#loginForm button[type=submit]').click()
            expect(page.locator('#loginOverlay')).to_be_hidden(timeout=15000)
            expect(page.locator('.app')).to_be_visible()
            assert page.evaluate("document.querySelector('.app').inert") is False
            page.locator('.nav[data-tab=brain]').click()
            if w<=720: expect(page.locator('#neuralKnowledgeList')).to_be_visible()
            # Trigger an actual protected API request after the session expires.
            page.locator('.nav[data-tab=devices]').click()
            expect(page.locator('#refreshDevice')).to_be_visible()
            page.context.clear_cookies()
            page.locator('#refreshDevice').click()
            expect(page.locator('#loginOverlay')).to_be_visible(timeout=12000)
            assert_locked(page)
            # Login and use the real logout flow, then verify isolation again.
            page.locator('#ownerToken').fill(token)
            page.locator('#loginForm button[type=submit]').click()
            expect(page.locator('#loginOverlay')).to_be_hidden(timeout=15000)
            if w<=720:
                page.locator('#mobileMoreNav').click()
                page.locator('[data-mobile-go=setup]').click()
            else: page.locator('.nav[data-tab=setup]').click()
            page.locator('#setupLogout').click()
            assert_locked(page)
            if name=='iphone':
                # Reduced visible height is a keyboard-layout simulation, not a physical iPhone claim.
                page.set_viewport_size({'width':390,'height':320})
                page.locator('#ownerToken').focus()
                assert_locked(page)
                page.screenshot(path=str(OUT/f'{engine}-keyboard-height.png'))
            assert not errors, errors
            reports.append({'browser':engine,'viewport':name,'first_load':'pass','invalid_or_expired':'pass','logout':'pass','hit_tests':'pass','focus_isolated':'pass'})
            page.close()
        # Fail-closed styling works with scripts disabled too.
        nojs=browser.new_page(viewport={'width':390,'height':690},java_script_enabled=False)
        nojs.goto(base+'/owner',wait_until='domcontentloaded')
        assert_locked(nojs,js=False)
        nojs.close()
        failed=browser.new_page(viewport={'width':390,'height':690},is_mobile=True,has_touch=True)
        failed.route('**/api/session',lambda route:route.fulfill(status=503,json={'detail':'Synthetic session failure'}))
        failed.goto(base+'/owner',wait_until='domcontentloaded')
        assert_locked(failed)
        failed.close()
        public=browser.new_page(viewport={'width':390,'height':690},is_mobile=True,has_touch=True)
        public.goto(base+'/',wait_until='domcontentloaded')
        expect(public.locator('#loginOverlay')).to_be_hidden()
        expect(public.locator('.app')).to_be_visible()
        assert public.request.get(base+'/api/agent/memory').status==401
        public.close();browser.close()
    # Passwordless login uses a different server-rendered card; it must also isolate.
    with local_server(settings={**SETTINGS,'SONIC_PASSWORDLESS_LOGIN':'true'}) as (base,_),sync_playwright() as p:
        browser=getattr(p,engine).launch(headless=True)
        page=browser.new_page(viewport={'width':390,'height':690},is_mobile=True,has_touch=True)
        page.goto(base+'/owner',wait_until='domcontentloaded')
        expect(page.locator('#passkeyLogin')).to_be_visible()
        assert_locked(page)
        page.screenshot(path=str(OUT/f'{engine}-passkey-logged-out.png'))
        browser.close()
    (OUT/f'{engine}-report.json').write_text(json.dumps(reports,indent=2),encoding='utf-8')
    print(json.dumps(reports),flush=True)
    print('AUTH_ISOLATION_'+engine.upper()+'_PASS',flush=True)

if __name__=='__main__': main()
