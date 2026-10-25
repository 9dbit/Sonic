"""Real local HTTP + browser + fake microphone; provider and WebRTC peer simulated.

Tests shared real database and UI. Does NOT verify actual OpenAI audio or iPhone.
"""
import contextlib
import json
from pathlib import Path
import shutil
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from playwright.sync_api import sync_playwright, expect
from scripts.qa_server import local_server

ARTIFACTS=Path(__file__).resolve().parents[1]/'artifacts'
FAKE_PEER='''(() => {
 const get=navigator.mediaDevices.getUserMedia.bind(navigator.mediaDevices);
 navigator.mediaDevices.getUserMedia=async o=>{const stream=await get(o);window.qaMedia=stream;return stream;};
 class Peer {
  constructor(){this.iceGatheringState='complete';this.connectionState='new';}
  createDataChannel(){const dc={readyState:'connecting',sent:[],send(x){this.sent.push(JSON.parse(x));},close(){this.readyState='closed';}};window.qaDC=this.dc=dc;return dc;}
  addTrack(){} async createOffer(){return {sdp:'v=0\\r\\nm=audio 9 UDP/TLS/RTP/SAVPF 111\\r\\n'};}
  async setLocalDescription(x){this.localDescription=x;}
  async setRemoteDescription(x){this.dc.readyState='open';setTimeout(()=>this.dc.onopen?.(),5);}
  close(){this.connectionState='closed';} addEventListener(){} removeEventListener(){}
 }
 window.RTCPeerConnection=Peer;
 window.qaEvent=e=>window.qaDC.onmessage?.({data:JSON.stringify(e)});
})();'''


def run():
    ARTIFACTS.mkdir(exist_ok=True)
    results=[]
    settings={'SONIC_QA_VOICE':'synthetic-only','SONIC_REALTIME_ENABLED':'true','OPENAI_API_KEY':'synthetic-provider-no-network'}
    with local_server('tests.voice_qa_app:app',settings) as (base,owner),sync_playwright() as pw:
        opts={'headless':True,'args':['--no-sandbox','--enable-unsafe-swiftshader','--use-fake-ui-for-media-stream','--use-fake-device-for-media-stream']}
        if shutil.which('chromium'):opts['executable_path']=shutil.which('chromium')
        browser=pw.chromium.launch(**opts)
        try:
            for name,size in [('desktop',{'width':1440,'height':1000}),('mobile',{'width':390,'height':844})]:
                context=browser.new_context(viewport=size,is_mobile=name=='mobile',has_touch=name=='mobile',permissions=['microphone'])
                page=context.new_page();page.set_default_timeout(15000);errors=[]
                page.on('pageerror',lambda e:errors.append(str(e)))
                try:
                    page.add_init_script(FAKE_PEER)
                    page.goto(base);page.locator('#ownerToken').fill(owner);page.locator('#loginForm button').click()
                    expect(page.locator('#brainPanel')).to_be_visible()
                    page.locator('#brainMessage').fill('SONIC, simpan ke memoriku bahwa saya suka bakso')
                    page.locator('#brainSend').click();expect(page.locator('#brainReceipt .receipt')).to_be_visible()
                    page.locator('#brainMessage').fill('Tampilkan memory tentang bakso');page.locator('#brainSend').click()
                    expect(page.locator('#brainAnswerText')).to_contain_text('Ditemukan')
                    expect(page.locator('#searchResults')).to_contain_text('bakso')
                    if name=='mobile':page.locator('#closeInspector').click()
                    page.locator('#talkSonic').click();expect(page.locator('#voiceConsent')).to_be_visible()
                    assert page.evaluate('!window.qaMedia')
                    page.screenshot(path=str(ARTIFACTS/f'sonic-v04-{name}-consent.png'))
                    page.locator('#voiceAgree').check();page.locator('#startVoice').click()
                    expect(page.locator('#voiceStateText')).to_have_text('Listening')
                    assert page.evaluate('window.qaMedia.getAudioTracks()[0].readyState')=='live'
                    page.locator('#voiceMute').click();expect(page.locator('#voiceStateText')).to_have_text('Mic muted')
                    assert page.evaluate('window.qaMedia.getAudioTracks()[0].enabled') is False
                    page.locator('#voiceMute').click()
                    proposal={'type':'response.function_call_arguments.done','call_id':'qa-memory-'+name,'name':'memory_prepare','arguments':json.dumps({'fact':'Catatan suara uji '+name})}
                    page.evaluate('e=>{qaEvent({type:"response.created"});qaEvent(e);qaEvent({type:"response.done"});}',proposal)
                    expect(page.locator('#voiceProposalHost')).to_contain_text('Belum tersimpan')
                    before=page.request.get(base+'/api/memories').json()['total']
                    page.screenshot(path=str(ARTIFACTS/f'sonic-v04-{name}-memory-confirm.png'))
                    page.get_by_role('button',name='Confirm memory',exact=True).click()
                    expect(page.locator('#voiceProposalHost')).to_contain_text('Tersimpan di Memory Vault')
                    assert page.request.get(base+'/api/memories').json()['total']==before+1
                    notes=page.request.get(base+'/api/memories').json()['memories']
                    assert any(n['source']=='voice_confirmed' for n in notes)
                    page.locator('#voiceStop').click();expect(page.locator('#voiceSessionBar')).to_be_hidden()
                    assert page.evaluate('window.qaMedia.getTracks().every(t=>t.readyState==="ended")')
                    assert page.evaluate('document.documentElement.scrollWidth<=innerWidth')
                    page.locator('[data-tab=setup]').click();page.locator('#refreshRuns').click()
                    expect(page.locator('#engineRuns')).to_contain_text('graph_command')
                    assert not errors, errors
                    page.locator('#setupLogout').click();expect(page.locator('#loginOverlay')).to_be_visible()
                    results.append({'viewport':name,'graph_commands':'PASS','http_voice_tool_confirm':'PASS','microphone_start_stop':'PASS (fake media)','javascript_errors':0})
                except Exception:
                    with contextlib.suppress(Exception):page.screenshot(path=str(ARTIFACTS/f'sonic-v04-{name}-failure.png'))
                    raise
                finally:context.close()
        finally:browser.close()
    report={'results':results,'provider':'synthetic (no external API)','webrtc_peer':'simulated','media':'Chromium fake microphone',
            'database_and_http':'real disposable local server','live_openai_verified':False,'physical_iphone_tested':False,'private_user_data_used':False}
    (ARTIFACTS/'engine-v04-browser-report.json').write_text(json.dumps(report,indent=2))
    print(json.dumps(report))

if __name__=='__main__':run()
