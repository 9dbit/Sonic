"""SONIC Integration particle browser acceptance: real authenticated local server.

Uses a disposable user and a fake Windows heartbeat. No credentials copied,
no real RDC/Google OAuth, no Windows commands, no microphone and no production writes.
"""
from __future__ import annotations
import hashlib
import json
import re
import shutil
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright, expect
from qa_server import local_server

OUT=Path('artifacts/integrations-v086')
OUT.mkdir(parents=True,exist_ok=True)
device_token='synthetic-v086-device-token'
settings={'SONIC_DEVICE_TOKEN_SHA256':hashlib.sha256(device_token.encode()).hexdigest()}

def device_heartbeat(url,capabilities):
    payload={
        'device_id':'TRADEVICEPC','hostname':'TRADEVICEPC','platform':'Windows',
        'agent_version':'0.8.3','capabilities':capabilities,
        'metrics':{'ram_total_bytes':16*2**30,'ram_available_bytes':8*2**30},
        'gui_targets':[]
    }
    response=httpx.post(url+'/api/device/heartbeat',json=payload,
                        headers={'Authorization':'Bearer '+device_token},timeout=15)
    assert response.status_code==200,response.text

with local_server(settings=settings) as (url,owner),sync_playwright() as p:
    device_heartbeat(url,['system.status','system.metrics','desktop.mkdir','file.mkdir','process.list'])
    executable=shutil.which('chromium') or shutil.which('chrome')
    if not executable:
        executable=next((str(x) for x in (
            Path('C:/Program Files/Google/Chrome/Application/chrome.exe'),
            Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'))
                         if x.is_file()),None)
    browser=p.chromium.launch(executable_path=executable or None,headless=True,
                              args=['--no-sandbox','--enable-unsafe-swiftshader'])
    report=[]
    for viewport,dimensions in [('desktop',{'width':1440,'height':900}),
                                ('mobile',{'width':390,'height':844})]:
        page=browser.new_page(viewport=dimensions,device_scale_factor=1,
                              has_touch=viewport=='mobile',is_mobile=viewport=='mobile')
        errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(url,wait_until='networkidle')
        page.locator('#ownerToken').fill(owner)
        page.locator('#loginForm button[type=submit]').click()
        expect(page.locator('#loginOverlay')).to_have_class(re.compile('hidden'))
        page.locator('.nav[data-tab="brain"]').click()
        page.locator('#focusIntegration').click()
        expect(page.locator('#graphStage')).to_have_attribute('data-selected','integration:hub')
        expect(page.locator('#nodeInspector h3')).to_have_text('Integration')
        expect(page.locator('.integration-entry')).to_have_count(4)
        for ident in ('windows-native','rdc','google-drive','notepad'):
            expect(page.locator('.integration-entry[data-integration="'+ident+'"]')).to_be_visible()
        assert page.locator('.integration-entry[data-integration="windows-native"]').get_attribute('data-state')=='online'
        assert page.locator('.integration-entry[data-integration="rdc"]').get_attribute('data-state')=='not_connected'
        assert page.locator('.integration-entry[data-integration="google-drive"]').get_attribute('data-state')=='not_connected'
        assert page.locator('.integration-entry[data-integration="notepad"]').get_attribute('data-state')=='not_ready'
        assert page.locator('.integration-entry[data-integration="rdc"]').inner_text().find('Belum terhubung')>=0
        details=page.locator('.integration-entry[data-integration="windows-native"] details')
        details.locator('summary').click()
        expect(details).to_contain_text('desktop.mkdir')
        assert page.evaluate("window.sonicGraph.nodes.filter(n=>n.category==='integration').length")==1
        # Toggle the real device advertisement on the test backend. The UI
        # must update and must never claim success when actions are unavailable.
        device_heartbeat(url,[])
        page.locator('#nodeInspector .integration-refresh').click()
        expect(page.locator('.integration-entry[data-integration="windows-native"]')).to_have_attribute(
            'data-state','not_ready')
        device_heartbeat(url,['system.metrics','desktop.mkdir'])
        page.locator('#nodeInspector .integration-refresh').click()
        expect(page.locator('.integration-entry[data-integration="windows-native"]')).to_have_attribute(
            'data-state','online')
        summary=page.evaluate("""() => ({
            integrationNodes:window.sonicGraph.nodes.filter(n=>n.category==='integration').length,
            selected:window.sonicGraph.selected,
            statusCount:document.querySelectorAll('.integration-entry').length,
            extraWidth:document.documentElement.scrollWidth-innerWidth,
            inspectorVisible:getComputedStyle(document.getElementById('graphInspector')).display!=='none',
            bg:getComputedStyle(document.getElementById('brainPanel')).backgroundColor,
            controls:document.querySelector('#focusIntegration').getAttribute('aria-label')
        })""")
        assert summary['integrationNodes']==1,summary
        assert summary['selected']=='integration:hub',summary
        assert summary['inspectorVisible'],summary
        assert summary['extraWidth']<=5,summary
        assert summary['bg']=='rgb(0, 0, 0)',summary
        assert not errors,errors
        page.screenshot(path=str(OUT/('integration-'+viewport+'.png')),full_page=False)
        report.append({'viewport':viewport,**summary,'pageErrors':errors})
        page.close()
    browser.close()
    (OUT/'report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2))
