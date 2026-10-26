"""Real local HTTP engine + browser, synthetic authenticated Windows companion.

Exercises a lost HTTP response after the job commits, refresh recovery, result
verification and stale approval buttons. No provider call or real PC changes.
"""
import hashlib
import json
from pathlib import Path
import re
import shutil

from playwright.sync_api import sync_playwright, expect
from qa_server import local_server


OUT=Path('artifacts/execution-v087')
OUT.mkdir(parents=True,exist_ok=True)
DEVICE={'Authorization':'Bearer synthetic-device-v087'}
SETTINGS={'SONIC_DEVICE_TOKEN_SHA256':hashlib.sha256(b'synthetic-device-v087').hexdigest(),
          'SONIC_ENABLE_POWERSHELL_EXEC':'true'}


def run():
    results=[]
    with local_server(settings=SETTINGS) as (url,owner),sync_playwright() as pw:
        system_chrome=Path('/Applications/Google Chrome.app/Contents/MacOS/Google Chrome')
        executable=shutil.which('chromium') or (str(system_chrome) if system_chrome.is_file() else None)
        browser=pw.chromium.launch(executable_path=executable,headless=True,
            args=['--no-sandbox','--enable-unsafe-swiftshader'])
        try:
            for name,viewport in [('desktop',{'width':1440,'height':1000}),('mobile',{'width':390,'height':844})]:
                context=browser.new_context(viewport=viewport,is_mobile=name=='mobile',has_touch=name=='mobile')
                page=context.new_page();page.set_default_timeout(15000)
                errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
                heartbeat=page.request.post(url+'/api/device/heartbeat',headers=DEVICE,data={
                    'device_id':'TRADEVICEPC','hostname':'QA Windows','platform':'Windows',
                    'agent_version':'0.8.3','capabilities':['desktop.mkdir','file.mkdir','powershell.exec'],
                    'metrics':{},'gui_targets':[]})
                assert heartbeat.ok
                requests=[]
                lose_response=[True]
                def intercept(route):
                    data=route.request.post_data_json;requests.append(data)
                    response=route.fetch()
                    if lose_response[0]:
                        lose_response[0]=False;assert response.ok;route.abort('failed')
                    else:route.fulfill(response=response)
                page.route('**/api/chat',intercept)
                try:
                    page.goto(url)
                    page.locator('#ownerToken').fill(owner);page.locator('#loginForm button').click()
                    expect(page.locator('#loginOverlay')).to_have_class(re.compile('hidden'))
                    page.locator('[data-tab=chat]').click()
                    previous_completions=page.locator('#chatFeed').inner_text().count('Folder Desktop berhasil dibuat')
                    def send(text):
                        page.locator('#message').fill(text);page.locator('#send').click()
                    def tasks():
                        return page.request.get(url+'/api/engine/tasks').json()['tasks']
                    def next_job():
                        return page.request.post(url+'/api/device/operator/next',headers=DEVICE,data={}).json()['job']
                    def finish(job,result):
                        return page.request.post(url+'/api/device/operator/result',headers=DEVICE,data={
                            'request_id':job['id'],'lease':job['lease'],'success':True,'result':result}).json()
                    send('Buat folder “Engine '+name+'” di Desktop TRADEVICEPC')
                    page.get_by_role('button',name='Periksa / coba kembali',exact=True).click()
                    expect(page.locator('#chatFeed')).to_contain_text('Menunggu Windows')
                    assert requests[0]['request_id']==requests[1]['request_id']
                    active=[t for t in tasks() if t['state']=='queued']
                    assert len(active)==1
                    job=next_job();assert job['payload']=={'name':'Engine '+name}
                    assert next_job() is None
                    assert page.locator('#chatFeed').inner_text().count('Folder Desktop berhasil dibuat')==previous_completions
                    assert finish(job,{'created':True,'exists':True,'name':'wrong',
                        'path':'C:/Users/Owner/Desktop/wrong','scope':'owner_desktop'})['state']=='failed'
                    expect(page.locator('#chatFeed')).to_contain_text('belum dapat diverifikasi')

                    with page.expect_response(lambda r:r.url.endswith('/api/chat') and r.status==200):
                        send('Buat folder Resume '+name+' di Desktop TRADEVICEPC')
                    expect(page.locator('#chatFeed')).to_contain_text('Menunggu Windows')
                    job=next_job();assert job and job['payload']=={'name':'Resume '+name}
                    page.reload();expect(page.locator('#loginOverlay')).to_have_class(re.compile('hidden'))
                    page.locator('[data-tab=chat]').click()
                    expect(page.locator('#chatFeed')).to_contain_text('TRADEVICEPC: Menunggu Windows')
                    assert finish(job,{'created':True,'exists':True,'name':'Resume '+name,
                        'path':'C:/Users/Owner/Desktop/Resume '+name,'scope':'owner_desktop'})['state']=='done'
                    expect(page.locator('#chatFeed')).to_contain_text('Folder Desktop berhasil dibuat')
                    expect(page.locator('#chatFeed')).to_contain_text('Folder diperiksa oleh Windows companion')

                    send('PowerShell: Get-Date')
                    expect(page.locator('#chatFeed .chat-approve-button')).to_have_count(1)
                    old=[t for t in tasks() if t['state']=='pending'][0]['id']
                    page.locator('[data-tab=setup]').click()
                    page.get_by_role('button',name='Hentikan semua tugas PC',exact=True).click()
                    expect(page.locator('#executionTasks')).to_contain_text('Dibatalkan')
                    page.locator('[data-tab=chat]').click()
                    send('PowerShell: Get-Service')
                    expect(page.locator('#chatFeed .chat-approve-button')).to_have_count(2)
                    page.locator('#chatFeed .chat-approve-button').first.click()
                    expect(page.locator('#chatFeed')).to_contain_text('Perintah lain tidak disetujui')
                    assert requests[-1]['approval_request_id']==old
                    assert next_job() is None
                    assert len([t for t in tasks() if t['state']=='pending'])==1
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    assert not errors,errors
                    page.screenshot(path=str(OUT/(name+'.png')))
                    results.append({'viewport':name,'lost_response_replay':'PASS','one_job':'PASS',
                        'wrong_target_rejected':'PASS','refresh_resumes_task':'PASS',
                        'agent_evidence':'PASS','stale_approval_rejected':'PASS','javascript_errors':0})
                    # This fixture is one owner database; cancel the remaining
                    # synthetic proposal before the next fresh browser login.
                    page.locator('[data-tab=setup]').click()
                    page.get_by_role('button',name='Hentikan semua tugas PC',exact=True).click()
                except Exception:
                    page.screenshot(path=str(OUT/(name+'-failure.png')))
                    raise
                finally:context.close()
        finally:browser.close()
    report={'results':results,'http_and_database':'real disposable local server',
            'windows_companion':'synthetic authenticated receipts','microphone_tested':False,
            'physical_iphone_tested':False,'external_provider_calls':False}
    (OUT/'report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report))


if __name__=='__main__':run()
