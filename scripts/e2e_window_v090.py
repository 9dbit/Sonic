"""SONIC V0.9.0 desktop/mobile window control acceptance against a fake Windows device.
No real app is opened/closed. No production credentials or provider calls.
"""
import hashlib
import json
import re
import shutil
from pathlib import Path

import httpx
from playwright.sync_api import sync_playwright, expect
from qa_server import local_server

ARTIFACTS=Path('artifacts/window-v090')
ARTIFACTS.mkdir(parents=True,exist_ok=True)
token='synthetic-window-agent-token-only-for-qa'
settings={'SONIC_DEVICE_TOKEN_SHA256':hashlib.sha256(token.encode()).hexdigest()}
with local_server(settings=settings) as (url,owner),sync_playwright() as p:
    def agent(route,payload):
        r=httpx.post(url+route,headers={'Authorization':'Bearer '+token},json=payload,timeout=15)
        assert r.status_code==200,(route,r.status_code,r.text[:400])
        return r.json()

    agent('/api/device/heartbeat',{
        'device_id':'TRADEVICEPC','hostname':'TRADEVICEPC','platform':'Windows',
        'agent_version':'0.9.0',
        'capabilities':['system.status','system.metrics','window.list','window.open','window.focus','window.close'],
        'metrics':{'ram_total_bytes':16*2**30,'ram_available_bytes':8*2**30},
        'gui_targets':[]
    })
    browser=p.chromium.launch(executable_path=shutil.which('chromium') or shutil.which('chrome') or None,
                              headless=True,args=['--no-sandbox','--enable-unsafe-swiftshader'])
    reports=[]
    for device,viewport in [('desktop',{'width':1440,'height':900}),('mobile',{'width':390,'height':844})]:
        page=browser.new_page(viewport=viewport,device_scale_factor=1,
                              has_touch=device=='mobile',is_mobile=device=='mobile')
        errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(url,wait_until='networkidle')
        page.locator('#ownerToken').fill(owner)
        page.locator('#loginForm button[type=submit]').click()
        expect(page.locator('#loginOverlay')).to_have_class(re.compile('.*hidden.*'))
        page.locator('.nav[data-tab=devices]').click()
        expect(page.locator('#pcWindowControl')).to_be_visible()
        expect(page.locator('#pcWindowStatus')).to_contain_text('mendukung Window Control',timeout=12000)
        assert page.locator('[data-window-action=\"window.close\"]').is_enabled()

        # MetaTrader5: exact warning + no job before explicit approval.
        page.locator('#pcWindowApp').select_option('metatrader5')
        page.locator('[data-window-action=\"window.close\"]').click()
        expect(page.locator('#pcApproval')).to_be_visible()
        expect(page.locator('#pcApprovalText')).to_contain_text('WM_CLOSE')
        expect(page.locator('#pcApprovalText')).to_contain_text('MetaTrader')
        assert agent('/api/device/operator/next',{})['job'] is None
        page.screenshot(path=str(ARTIFACTS/f'{device}-mt5-approval.png'))
        page.locator('#pcApprovalCancel').click()
        assert agent('/api/device/operator/next',{})['job'] is None

        # Notepad open: one approved request, synthetic Windows receipt only.
        page.locator('#pcWindowApp').select_option('notepad')
        page.locator('[data-window-action=\"window.open\"]').click()
        expect(page.locator('#pcApproval')).to_be_visible()
        expect(page.locator('#pcApprovalText')).to_contain_text('notepad')
        page.locator('#pcApprovalConfirm').click()
        job=None
        for _ in range(45):
            job=agent('/api/device/operator/next',{}).get('job')
            if job:break
            page.wait_for_timeout(150)
        assert job is not None, 'No queued approved window request'
        assert job['action']=='window.open' and job['payload']=={'app':'notepad'},job
        agent('/api/device/operator/result',{'request_id':job['id'],'lease':job['lease'],
            'success':True,'result':{'app':'notepad','method':'FIND_OR_LAUNCH','opened':True,
                                      'new_process_started':True}})
        expect(page.locator('#pcExecState')).to_have_text('State: done',timeout=12000)
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        assert errors==[],errors
        reports.append({'viewport':device,'trading_warning':True,'approval_gate':True,
                        'auth_window_receipt':True,'no_real_pc_control':True,'browser_errors':errors})
        page.close()
    browser.close()
    (ARTIFACTS/'report.json').write_text(json.dumps(reports,indent=2))
    print(json.dumps(reports,indent=2))
