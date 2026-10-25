"""SONIC V0.8 real Chromium E2E against disposable owner and fake Windows agent.

No production tokens or Windows command execution are used in this test.
"""
from __future__ import annotations
import hashlib
import json
from pathlib import Path
import re
import shutil
import time
import httpx
from playwright.sync_api import sync_playwright, expect
from qa_server import local_server

OUT = Path('artifacts/pc-v08')
OUT.mkdir(parents=True,exist_ok=True)

def launch_browser(p):
    binary=shutil.which('chromium') or shutil.which('chrome')
    if not binary:
        for path in [Path('C:/Program Files/Google/Chrome/Application/chrome.exe'),
                     Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe')]:
            if path.is_file():
                binary=str(path);break
    return p.chromium.launch(executable_path=binary or None,headless=True,
                             args=['--no-sandbox','--enable-unsafe-swiftshader'])

device_token='synthetic-device-token-v08'
settings={'SONIC_ENABLE_POWERSHELL_EXEC':'true',
          'SONIC_DEVICE_TOKEN_SHA256':hashlib.sha256(device_token.encode()).hexdigest()}
with local_server(settings=settings) as (url,owner), sync_playwright() as p:
    agent_headers={'Authorization':'Bearer '+device_token}
    def agent(route,data):
        response=httpx.post(url+route,headers=agent_headers,json=data,timeout=12)
        assert response.status_code==200,(route,response.status_code,response.text)
        return response.json()
    heartbeat={
        'device_id':'TRADEVICEPC','hostname':'TRADEVICEPC','platform':'Windows',
        'agent_version':'0.8.0',
        'capabilities':['system.metrics','system.status','powershell.exec',
                        'process.terminate','shell.inspect'],
        'metrics':{
            'cpu_usage_percent':34.4,'ram_total_bytes':16*2**30,
            'ram_available_bytes':8*2**30,'ram_used_percent':50,
            'process_count':203,'network_rx_bytes_per_second':1200,
            'processes':[
                {'pid':234,'name':'notepad.exe','ram_bytes':16000000,
                 'cpu_percent':2.0,'status':'running'},
                {'pid':500,'name':'lsass.exe','ram_bytes':9000000,
                 'cpu_percent':.1,'status':'running'}],
            'gpus':[{'name':'Mock GPU'}],
            'disks':[{'drive':'C:','free_bytes':12000000000,
                      'total_bytes':50000000000}],
        },'gui_targets':[]
    }
    agent('/api/device/heartbeat',heartbeat)
    browser=launch_browser(p)
    result=[]
    for label,viewport in [('desktop',{'width':1440,'height':900}),
                           ('mobile',{'width':390,'height':844})]:
        page=browser.new_page(viewport=viewport,device_scale_factor=1,
                              has_touch=label=='mobile',is_mobile=label=='mobile')
        errors=[]
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(url,wait_until='networkidle')
        page.locator('#ownerToken').fill(owner)
        page.locator('#loginForm button[type=submit]').click()
        expect(page.locator('#loginOverlay')).to_have_class(re.compile('.*hidden.*'))
        page.locator('.nav[data-tab="devices"]').click()
        expect(page.locator('#pcCommandCenter')).to_be_visible()
        expect(page.locator('#pcBrokerStatus')).to_have_text('PowerShell ready',timeout=12000)
        expect(page.locator('#pcProcessList')).to_contain_text('notepad.exe')
        expect(page.locator('#pcProcessList')).to_contain_text('lsass.exe')
        assert page.locator('#pcProcessList button').count()==2
        assert page.locator('#pcProcessList button').nth(1).is_disabled()
        page.locator('[data-pc-example]').first.click()
        expect(page.locator('#pcScript')).to_have_value(re.compile('Get-Process'))
        page.locator('#pcScript').fill('Get-Date')
        page.locator('#pcReview').click()
        expect(page.locator('#pcApproval')).to_be_visible()
        expect(page.locator('#pcApprovalText')).to_contain_text('Get-Date')
        assert agent('/api/device/operator/next',{})['job'] is None
        page.locator('#pcApprovalConfirm').click()
        job=None
        for _ in range(32):
            job=agent('/api/device/operator/next',{}).get('job')
            if job:break
            page.wait_for_timeout(180)
        assert job and job['action']=='powershell.exec',job
        lease={'request_id':job['id'],'lease':job['lease']}
        assert agent('/api/device/operator/check',lease)['execute']
        agent('/api/device/operator/stream',{**lease,'sequence':1,
              'channel':'stdout','text':'2026-10-26T04:00:00\n'})
        agent('/api/device/operator/stream',{**lease,'sequence':2,
              'channel':'stderr','text':'synthetic warning\n'})
        agent('/api/device/operator/result',{**lease,'success':True,
              'result':{'exit_code':0,'events_sent':2}})
        expect(page.locator('#pcOutput')).to_contain_text('2026-10-26T04:00:00',timeout=12000)
        expect(page.locator('#pcExecState')).to_have_text('State: done',timeout=12000)
        expect(page.locator('#pcOutput')).to_contain_text('[stderr] synthetic warning')
        page.locator('#pcRefreshHistory').click()
        expect(page.locator('#pcHistory')).to_contain_text('Get-Date')
        page.screenshot(path=str(OUT/f'pc-command-{label}.png'),full_page=False)

        # Simulate a long in-flight command; cancellation is cloud-mediated,
        # not a fake success state in the UI.
        page.locator('#pcScript').fill('Start-Sleep -Seconds 30')
        page.locator('#pcReview').click()
        page.locator('#pcApprovalConfirm').click()
        active=None
        for _ in range(32):
            active=agent('/api/device/operator/next',{}).get('job')
            if active:break
            page.wait_for_timeout(200)
        assert active and active['action']=='powershell.exec'
        wait_lease={'request_id':active['id'],'lease':active['lease']}
        page.locator('#pcStop').click()
        for _ in range(40):
            if agent('/api/device/operator/check',wait_lease)['execute'] is False:break
            page.wait_for_timeout(150)
        assert agent('/api/device/operator/check',wait_lease)['execute'] is False
        agent('/api/device/operator/result',{**wait_lease,'success':False,
              'result':{'cancelled':True}})
        expect(page.locator('#pcExecState')).to_have_text('State: cancelled',timeout=12000)

        # End Task must never skip the exact PID/name approval dialog.
        end=page.locator('#pcProcessList button').first
        end.click()
        expect(page.locator('#pcApproval')).to_be_visible()
        expect(page.locator('#pcApprovalText')).to_contain_text('notepad.exe')
        page.locator('#pcApprovalCancel').click()
        page.wait_for_timeout(150)
        assert agent('/api/device/operator/next',{})['job'] is None

        assert not errors,errors
        result.append({'viewport':label,'readiness':True,'approval':True,
                       'streamed':True,'cancelled':True,'end_task_rejected':True,
                       'browser_errors':errors})
        page.close()
    browser.close()
    (OUT/'report.json').write_text(json.dumps(result,indent=2))
    print(json.dumps(result,indent=2))
