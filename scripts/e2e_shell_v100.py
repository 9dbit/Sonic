"""SONIC Command Deck R1: responsive UI acceptance without private or remote actions.

Checks actual FastAPI + Chromium desktop/tablet/mobile while protecting the
existing WebGL graph and procedural particle canvas. Uses disposable localhost
SQLite and a synthetic owner token, never Railway or TRADEVICEPC.
"""
from __future__ import annotations
import json
import re
import shutil
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright, expect
from qa_server import local_server

OUT=Path('artifacts/sonic-command-deck-r1')
OUT.mkdir(parents=True,exist_ok=True)

def check_layout(page,label,phase):
    details=page.evaluate("""() => {
      const title=document.getElementById('pageTitle');
      const bar=document.querySelector('.topbar').getBoundingClientRect();
      const nav=document.querySelector('.sidebar').getBoundingClientRect();
      const panel=[...document.querySelectorAll('.content>.panel')]
        .find(el=>!el.classList.contains('hidden'));
      const rect=panel?.getBoundingClientRect();
      return {viewport:innerWidth,documentWidth:document.documentElement.scrollWidth,
        nav:{left:nav.left,bottom:nav.bottom,width:nav.width},headerHeight:bar.height,
        panel:{left:rect?.left,right:rect?.right,width:rect?.width},
        page:title?.textContent,background:getComputedStyle(document.body).backgroundColor};
    }""")
    assert details['documentWidth']<=details['viewport']+2,(label,phase,details)
    assert details['panel']['width']>=240,(label,phase,details)
    assert details['panel']['left']>=-1,(label,phase,details)
    assert details['panel']['right']<=details['viewport']+1,(label,phase,details)
    return details

with local_server() as (url,token),sync_playwright() as p:
    app=httpx.get(url+'/assets/sonic-mark.svg',timeout=10)
    assert app.status_code==200 and '<svg' in app.text and '<script' not in app.text
    css=httpx.get(url+'/assets/sonic-shell-v100.css',timeout=10)
    assert css.status_code==200 and 'sonic-motion-float.focused' not in css.text
    assert '#sonicMotionAnchor' in css.text
    browser=p.chromium.launch(executable_path=shutil.which('chromium') or shutil.which('chrome') or None,
                              headless=True,args=['--no-sandbox','--enable-unsafe-swiftshader'])
    summary=[]
    for label,size in [
        ('wide',{'width':1600,'height':950}),
        ('desktop',{'width':1366,'height':850}),
        ('tablet',{'width':820,'height':1000}),
        ('mobile',{'width':390,'height':844}),
        ('small-mobile',{'width':360,'height':740}),
    ]:
        page=browser.new_page(viewport=size,device_scale_factor=1,
                              is_mobile=label.endswith('mobile'),has_touch=label.endswith('mobile'))
        errors=[]
        page.on('pageerror',lambda e: errors.append(str(e)))
        page.goto(url,wait_until='networkidle')
        expect(page.locator('#loginOverlay')).to_be_visible()
        expect(page.locator('.login-card img[alt="SONIC logo"]')).to_be_visible()
        page.screenshot(path=str(OUT/f'{label}-login.png'),full_page=False)

        page.locator('#ownerToken').fill(token)
        page.locator('#loginForm button[type=submit]').click()
        expect(page.locator('#loginOverlay')).to_have_class(re.compile('hidden'),timeout=12000)
        expect(page.locator('#brainPanel')).to_be_visible()
        expect(page.locator('#graphStage canvas').first).to_be_visible(timeout=12000)
        expect(page.locator('#sonicMotionFloat canvas')).to_be_visible(timeout=12000)
        assert page.locator('#graphStage canvas').count()>=2,'Missing existing knowledge graph renderers'
        dimensions=page.locator('#sonicMotionFloat canvas').evaluate(
            '(c)=>({width:c.width,height:c.height,clientWidth:c.clientWidth,clientHeight:c.clientHeight})')
        assert dimensions['width']>=25 and dimensions['height']>=25,dimensions
        assert dimensions['clientWidth']>=25 and dimensions['clientHeight']>=25
        expect(page.locator('#sonicMotionAnchor')).to_be_attached()
        expect(page.locator('#neuralField')).to_have_count(0)
        expect(page.locator('.neural-field-label')).to_be_visible()
        check_layout(page,label,'neural')
        if label.endswith('mobile'):
            expect(page.locator('#graphInspector')).to_be_hidden()
            page.locator('#toggleInspector').click()
            expect(page.locator('#graphInspector')).to_be_visible()
            page.locator('#closeInspector').click()
            expect(page.locator('#graphInspector')).to_be_hidden()
            page.locator('#toggleFilters').click()
            expect(page.locator('#graphFilters')).to_be_visible()
            page.locator('#closeFilters').click()
            expect(page.locator('#graphFilters')).to_be_hidden()
        else:
            expect(page.locator('#graphInspector')).to_be_visible()
            expect(page.locator('.brand-symbol')).to_be_visible()
        page.screenshot(path=str(OUT/f'{label}-neural.png'),full_page=False)
        page.locator('.nav[data-tab="chat"]').click()
        expect(page.locator('#chatPanel')).to_be_visible()
        expect(page.locator('#hero')).to_be_visible()
        expect(page.locator('#pageSubtitle')).to_contain_text('conversation')
        expect(page.locator('#hero img')).to_be_visible()
        assert page.locator('#message').is_enabled()
        check_layout(page,label,'chat')
        page.screenshot(path=str(OUT/f'{label}-chat.png'),full_page=False)

        # Hero shortcuts invoke the original nav handlers (no parallel router).
        page.locator('#goToWorkspace').click()
        expect(page.locator('#workspacePanel')).to_be_visible()
        expect(page.locator('.nav[data-tab="workspace"]')).to_have_class(re.compile('active'))
        expect(page.locator('#wsPcCloudTab')).to_be_visible()
        check_layout(page,label,'workspace')
        if label in ('desktop','mobile'):
            page.screenshot(path=str(OUT/f'{label}-workspace.png'),full_page=False)

        page.locator('.nav[data-tab="memory"]').click()
        expect(page.locator('#memoryPanel')).to_be_visible()
        expect(page.locator('#memoryInput')).to_be_visible()
        check_layout(page,label,'memory')

        page.locator('.nav[data-tab="devices"]').click()
        expect(page.locator('#devicesPanel')).to_be_visible()
        expect(page.locator('#pcWindowControl')).to_be_visible()
        expect(page.locator('#pcCommandCenter')).to_be_visible()
        check_layout(page,label,'devices')
        if label in ('desktop','mobile'):
            page.screenshot(path=str(OUT/f'{label}-devices.png'),full_page=False)

        page.locator('.nav[data-tab="setup"]').click()
        expect(page.locator('#setupPanel')).to_be_visible()
        check_layout(page,label,'settings')
        assert not errors,(label,errors)
        summary.append({'viewport':label,'width':size['width'],
                        'preserved_graph_canvases':True,'preserved_sonic_particle_canvas':True,
                        'new_brand_logo':True,'responsive_no_horizontal_page_overflow':True,
                        'nav_and_hero_shortcuts':True,'device_controls_preserved':True,
                        'page_errors':errors})
        page.close()
    browser.close()
    (OUT/'report.json').write_text(json.dumps(summary,indent=2))
    print(json.dumps(summary,indent=2))
