"""V0.8.9 real-browser QA with mocked Windows operator, never live PC file reads.

Confirms desktop/mobile UI, explicit owner confirmation, receipt binding,
no auto Windows scan, XSS-safe preview, and browser cleanup on logout.
"""
import json
import re
import shutil
from pathlib import Path
from uuid import uuid4
from urllib.parse import urlparse
from playwright.sync_api import sync_playwright, expect
from qa_server import local_server

OUT=Path('artifacts/pc-workspace-v089')
OUT.mkdir(parents=True,exist_ok=True)

with local_server() as (url,token),sync_playwright() as p:
    chrome=shutil.which('chromium') or shutil.which('chrome')
    browser=p.chromium.launch(executable_path=chrome or None,headless=True,
        args=['--no-sandbox','--enable-unsafe-swiftshader'])
    reports=[]
    for name,viewport in [('desktop',{'width':1440,'height':900}),
                          ('mobile',{'width':390,'height':844})]:
        page=browser.new_page(viewport=viewport,is_mobile=name=='mobile',has_touch=name=='mobile')
        errors=[]
        operations=[]
        requests={}

        def integrations(route):
            route.fulfill(json={'adapters':[{'id':'windows-native','state':'online',
                'connected':True,'current_capabilities':['file.list','file.read']}],
                'generated_at':'synthetic-test-data'})

        def proposal(route):
            payload=route.request.post_data_json
            assert payload['action'] in ('file.list','file.read')
            assert set(payload['payload'])=={'path'}
            rid=str(uuid4());requests[rid]=payload;operations.append(payload)
            route.fulfill(json={'id':rid,'action':payload['action'],
                'payload':payload['payload'],'state':'pending','digest':'a'*64})

        def operator(route):
            req=route.request
            route_path=urlparse(req.url).path
            rid=route_path.removeprefix('/api/operator/requests/').split('/')[0]
            if rid not in requests:
                route.fulfill(status=404,json={'detail':'Missing mock job'});return
            payload=requests[rid]
            if req.method=='POST' and route_path.endswith('/confirm'):
                assert req.post_data_json=={'confirm':True,'digest':'a'*64}
                route.fulfill(json={'id':rid,'state':'queued'});return
            if req.method=='DELETE':
                route.fulfill(json={'state':'cancelled'});return
            assert req.method=='GET'
            if payload['action']=='file.list':
                result={'directory':'D:\\Sonic\\work','truncated':False,
                    'items':[{'name':'Readme.md','kind':'file','bytes':100},
                             {'name':'Proyek','kind':'directory','bytes':None},
                             {'name':'CON','kind':'file','bytes':1}]}
            else:
                result={'path':'D:\\Sonic\\work\\Readme.md',
                    'content':'Hello from mock Windows\n<img src=x onerror="window.PC_INJECTED=true">'}
            route.fulfill(json={'id':rid,'action':payload['action'],'payload':payload['payload'],
                'state':'done','result':result})

        page.on('pageerror',lambda e:errors.append(str(e)))
        page.route('**/api/integrations',integrations)
        page.route('**/api/operator/requests',proposal)
        page.route('**/api/operator/requests/**',operator)
        page.goto(url,wait_until='networkidle')
        page.locator('#ownerToken').fill(token)
        page.locator('#loginForm button[type=submit]').click()
        expect(page.locator('#loginOverlay')).to_have_class(re.compile('.*hidden.*'))
        page.locator('.nav[data-tab=workspace]').click()
        expect(page.locator('#wsStatus')).to_contain_text('SONIC Cloud')
        page.locator('#wsPcDeviceTab').click()
        expect(page.locator('#wsPcArea')).to_be_visible()
        expect(page.locator('#wsPcStatus')).to_contain_text('online')
        assert operations==[], 'PC must not read automatically on tab selection'
        page.screenshot(path=str(OUT/f'{name}-optin.png'))

        page.once('dialog',lambda d:d.accept())
        page.locator('#wsPcRoot').click()
        expect(page.locator('#wsPcList')).to_contain_text('Readme.md')
        expect(page.locator('#wsPcStatus')).to_contain_text('agent-reported')
        assert len(operations)==1 and operations[0]=={'action':'file.list','payload':{'path':'.'}}
        assert page.get_by_role('button',name='CON',exact=True).is_disabled()
        page.once('dialog',lambda d:d.accept())
        page.get_by_role('button',name='Readme.md',exact=True).click()
        expect(page.locator('#wsPcPreview')).to_be_visible()
        expect(page.locator('#wsPcText')).to_contain_text('<img src=x onerror=')
        assert len(operations)==2 and operations[1]=={'action':'file.read','payload':{'path':'Readme.md'}}
        assert page.evaluate('window.PC_INJECTED') is None, 'preview must remain literal text'
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        page.screenshot(path=str(OUT/f'{name}-preview.png'))
        page.locator('#wsPcCloudTab').click()
        expect(page.locator('#wsPcArea')).not_to_be_visible()
        expect(page.locator('#wsPcText')).to_have_text('')
        expect(page.locator('#wsStatus')).to_contain_text('SONIC Cloud')
        page.locator('#wsPcDeviceTab').click()
        expect(page.locator('#wsPcList')).to_have_text('')
        assert len(operations)==2, 'switching back must not silently refetch PC files'
        page.locator('#logout').click()
        expect(page.locator('#loginOverlay')).to_be_visible()
        expect(page.locator('#wsPcText')).to_have_text('')
        assert not errors, errors
        reports.append({'viewport':name,'explicitOwnerConsent':True,
            'noAutoPCRead':True,'readOnlyQueueReceipt':True,
            'literalTextPreview':True,'logoutClearsPCFiles':True,'pageErrors':errors})
        page.close()
    browser.close()
    (OUT/'report.json').write_text(json.dumps(reports,indent=2))
    print(json.dumps(reports,indent=2))
