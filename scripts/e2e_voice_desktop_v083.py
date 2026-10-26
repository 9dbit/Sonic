"""Chrome UI QA for Realtime transcript -> Chat PC action -> inline consent.

Uses a disposable local SONIC owner and synthetic voice dispatch responses.
No microphone/provider access and no actual Windows write occurs in this test.
"""
import json
import re
import shutil
from pathlib import Path

from playwright.sync_api import sync_playwright,expect
from qa_server import local_server

OUT=Path('artifacts/voice-desktop-v083')
OUT.mkdir(parents=True,exist_ok=True)

with local_server() as (url,owner),sync_playwright() as p:
    chrome=shutil.which('chromium') or shutil.which('chrome')
    if not chrome:
        chrome=next((str(x) for x in (
            Path('C:/Program Files/Google/Chrome/Application/chrome.exe'),
            Path('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe'))
            if x.is_file()),None)
    browser=p.chromium.launch(executable_path=chrome or None,headless=True,
        args=['--no-sandbox','--enable-unsafe-swiftshader'])
    results=[]
    for name,viewport in [('desktop',{'width':1440,'height':900}),
                          ('mobile',{'width':390,'height':844})]:
        page=browser.new_page(viewport=viewport,is_mobile=name=='mobile',
                              has_touch=name=='mobile')
        errors=[]
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.add_init_script("""(() => {
          Object.defineProperty(window,'SonicVoice',{
            configurable:true,
            set(C){
              this.__VoiceProxy=class extends C{
                constructor(options){
                  super(options);
                  window.__voiceOptions=options;
                  window.__voiceInstance=this;
                }
              };
            },
            get(){return this.__VoiceProxy;}
          });
        })();""")
        seen=[]
        def route_dispatch(route):
            data=route.request.post_data_json
            seen.append(data)
            phrase=data['transcript']
            if phrase=='setuju':
                response={'handled':True,'reply':'Disetujui melalui voice. Menunggu hasil PC.',
                          'operator_jobs':[{'id':'job_voice_ps','action':'powershell.exec'}],
                          'operator_proposals':[]}
            elif phrase.startswith('PowerShell:'):
                response={'handled':True,'reply':'Perintah sensitif. Balas SETUJU atau BATAL.',
                          'operator_jobs':[],
                          'operator_proposals':[{'id':'job_voice_review','action':'powershell.exec'}]}
            else:
                response={'handled':True,
                          'reply':'Saya jalankan folder Today di Desktop TRADEVICEPC tanpa konfirmasi.',
                          'operator_jobs':[{'id':'job_voice_desktop','action':'desktop.mkdir'}],
                          'operator_proposals':[]}
            route.fulfill(status=200,content_type='application/json',body=json.dumps(response))
        page.route('**/api/voice/sessions/**/dispatch',route_dispatch)
        def route_job(route):
            path=route.request.url
            completion='PowerShell selesai: Get-Date' if 'job_voice_ps' in path else \
                       'Folder Desktop berhasil dibuat di TRADEVICEPC: Desktop/Today'
            route.fulfill(status=200,content_type='application/json',
                          body=json.dumps({'state':'done','chat_completion':completion,
                                           'result':{'created':True}}))
        page.route('**/api/operator/requests/job_voice_*',route_job)
        page.goto(url,wait_until='networkidle')
        page.locator('#ownerToken').fill(owner)
        page.locator('#loginForm button[type=submit]').click()
        expect(page.locator('#loginOverlay')).to_have_class(re.compile('hidden'))
        page.locator('.nav[data-tab=chat]').click()
        assert page.evaluate("typeof window.__voiceOptions?.onTranscript")== 'function'
        page.evaluate("window.__voiceInstance.setState('listening');window.__voiceInstance.sessionId='synthetic_v083'")
        state=page.evaluate("""async () => await window.__voiceOptions.onTranscript('user',
           'Tolong buatkan folder bernama Today di desktop Threadvice PC.',
           {sessionId:'synthetic_v083',itemId:'item_voice_desktop'})""")
        assert state['handled'] is True
        expect(page.locator('#chatFeed')).to_contain_text('Saya jalankan folder Today',timeout=10000)
        expect(page.locator('#chatFeed')).to_contain_text('Folder Desktop berhasil dibuat',timeout=12000)
        assert page.locator('#devicesPanel').is_hidden()
        page.evaluate("""async () => await window.__voiceOptions.onTranscript('user',
           'PowerShell: Get-Date',{sessionId:'synthetic_v083',itemId:'item_voice_ps'})""")
        expect(page.locator('#chatFeed .chat-inline-approval')).to_have_count(1)
        page.locator('#chatFeed .chat-inline-approval .chat-approve-button').click()
        expect(page.locator('#chatFeed')).to_contain_text('Disetujui melalui voice',timeout=10000)
        expect(page.locator('#chatFeed')).to_contain_text('PowerShell selesai',timeout=12000)
        assert page.locator('#devicesPanel').is_hidden()
        assert [x['transcript'] for x in seen]==[
            'Tolong buatkan folder bernama Today di desktop Threadvice PC.',
            'PowerShell: Get-Date','setuju']
        assert not errors,errors
        page.screenshot(path=str(OUT/('voice-desktop-'+name+'.png')),full_page=False)
        results.append({'viewport':name,'desktop_action_without_confirmation':True,
                        'sensitive_inline_consent':True,'same_chat':True,
                        'errors':errors})
        page.close()
    browser.close()
    (OUT/'report.json').write_text(json.dumps(results,indent=2),encoding='utf-8')
    print(json.dumps(results,indent=2))
