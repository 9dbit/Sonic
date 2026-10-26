"""Real local storage + desktop/mobile UI; synthetic microphone/WebRTC only.

No paid provider, real microphone, deployed database, or Windows operations.
"""
import json
import re
import shutil
from datetime import datetime, timedelta, timezone
from pathlib import Path

from playwright.sync_api import sync_playwright, expect
from qa_server import local_server

OUT = Path('artifacts/workspace-v088')
OUT.mkdir(parents=True, exist_ok=True)
MIC = r"""(() => {
 window.__mic={calls:0,stops:0,deny:false};
 Object.defineProperty(navigator.mediaDevices,'getUserMedia',{value:async()=>{
  window.__mic.calls++;
  if(window.__mic.deny)throw new DOMException('Denied','NotAllowedError');
  const track={enabled:true,onended:null,stop(){window.__mic.stops++;}};
  return {getTracks:()=>[track],getAudioTracks:()=>[track]};
 }});
 window.RTCPeerConnection=class {
  constructor(){this.iceGatheringState='complete';this.connectionState='new';}
  addTrack(){} createDataChannel(){return this.dc={readyState:'open',send(){},close(){}};}
  async createOffer(){return {type:'offer',sdp:'synthetic-local-only'};}
  async setLocalDescription(o){this.localDescription=o;}
  async setRemoteDescription(){this.connectionState='connected';this.dc.onopen?.();}
  close(){this.connectionState='closed';}
 };
 Object.defineProperty(window,'SonicVoice',{configurable:true,set(C){this.__VC=class extends C{constructor(o){super(o);window.__voice=this;window.__voiceOptions=o;}};},get(){return this.__VC;}});
})();"""

with local_server() as (url, token), sync_playwright() as p:
    chrome = shutil.which('chromium') or shutil.which('chrome')
    browser = p.chromium.launch(executable_path=chrome or None, headless=True,
        args=['--no-sandbox','--enable-unsafe-swiftshader'])
    reports = []
    for label, viewport in [('desktop',{'width':1440,'height':900}),
                             ('mobile',{'width':390,'height':844})]:
        page = browser.new_page(viewport=viewport,is_mobile=label=='mobile',has_touch=label=='mobile')
        errors = []
        page.on('pageerror',lambda e: errors.append(str(e)))
        page.add_init_script(MIC)
        sessions = []
        def voice_session(route):
            sessions.append(route.request.post_data_json)
            route.fulfill(json={'sdp':'synthetic-answer','model':'synthetic-qa',
                'expires_at':(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat()})
        page.route('**/api/voice/sessions',voice_session)
        page.route('**/api/voice/sessions/*/stop',lambda r:r.fulfill(json={'provider_close_confirmed':True}))
        page.goto(url,wait_until='networkidle')
        page.locator('#ownerToken').fill(token)
        page.locator('#loginForm button[type=submit]').click()
        expect(page.locator('#loginOverlay')).to_have_class(re.compile('.*hidden.*'))
        page.wait_for_function('window.sonicWorkspace && window.sonicMotion')
        csrf = page.request.get(url+'/api/session').json()['csrf']
        headers = {'X-Sonic-CSRF':csrf}
        for i in range(4):
            page.request.post(url+'/api/memories',headers=headers,data={'text':f'Proyek QA {label} {i} memakai SONIC workspace dan catatan rapat.'})
        page.locator('.nav[data-tab=workspace]').click()
        expect(page.locator('#wsStatus')).to_contain_text('SONIC Cloud')
        page.locator('#wsNewFolder').click();page.locator('#wsName').fill('Project '+label)
        page.locator('#wsDialogSubmit').click()
        page.get_by_role('button',name='Project '+label,exact=True).click()
        page.locator('#wsNewNote').click();page.locator('#wsName').fill('Meeting '+label+'.md')
        page.locator('#wsDialogSubmit').click()
        expect(page.locator('#wsPreview')).to_be_visible()
        page.locator('#wsEditor').fill('Agenda\n<script>window.BAD=true</script>')
        page.locator('#wsSave').click();expect(page.locator('#wsSaveState')).to_contain_text('Tersimpan')
        assert page.evaluate('window.BAD') is None
        page.screenshot(path=str(OUT/f'{label}-notes.png'))
        # Real backend conflict: editor draft remains intact after another tab wins.
        chosen = page.evaluate('({id:window.sonicWorkspace.selected.id,revision:window.sonicWorkspace.selected.revision})')
        page.request.patch(url+'/api/workspace/items/'+chosen['id'],headers=headers,data={
            'revision':chosen['revision'],'content':'Other tab version'})
        page.locator('#wsEditor').fill('My unsaved version')
        page.locator('#wsSave').click();expect(page.locator('#notice')).to_contain_text('Versi berubah')
        expect(page.locator('#wsEditor')).to_have_value('My unsaved version')
        page.once('dialog',lambda d:d.accept());page.locator('#wsReload').click()
        expect(page.locator('#wsEditor')).to_have_value('Other tab version')
        # Voice edits the visible draft, then explicitly saves through the same API.
        result = page.evaluate("window.sonicWorkspace.handleVoice('tambahkan ke catatan Agenda besok')")
        assert result['handled']
        expect(page.locator('#wsSaveState')).to_contain_text('belum disimpan')
        page.evaluate("window.sonicWorkspace.handleVoice('simpan catatan')")
        expect(page.locator('#wsSaveState')).to_contain_text('Tersimpan')
        page.locator('#wsRename').click();page.locator('#wsName').fill('Renamed '+label+'.md');page.locator('#wsDialogSubmit').click()
        expect(page.locator('#wsPreviewName')).to_have_text('Renamed '+label+'.md')
        page.locator('#wsMove').click();page.locator('#wsMoveTarget').select_option('root');page.locator('#wsDialogSubmit').click()
        page.locator('#wsClosePreview').click()
        page.locator('#wsCloud').click();page.locator('#wsSearch').fill('Renamed '+label)
        expect(page.locator('#wsList')).to_contain_text('Renamed '+label+'.md')
        page.get_by_role('button',name='Renamed '+label+'.md',exact=True).click()
        expect(page.locator('#wsPreview')).to_be_visible()
        expect(page.locator('#wsPreviewName')).to_have_text('Renamed '+label+'.md')
        page.evaluate("window.sonicWorkspace.handleVoice('hapus catatan ini')")
        expect(page.locator('#wsDialog')).to_be_visible()
        page.evaluate("window.sonicWorkspace.handleVoice('setuju')")
        expect(page.locator('#wsDialog')).not_to_be_visible()
        page.locator('#wsTrash').click();page.get_by_role('button',name='Renamed '+label+'.md',exact=True).click()
        page.locator('#wsRestore').click();expect(page.locator('#wsPreview')).not_to_be_visible()
        page.locator('#wsCloud').click()
        expect(page.locator('#wsList')).to_contain_text('Renamed '+label+'.md')
        # Refresh persistence, no secrets or notes in localStorage.
        page.reload(wait_until='networkidle');page.locator('.nav[data-tab=workspace]').click()
        expect(page.locator('#wsList')).to_contain_text('Renamed '+label+'.md')
        assert not page.evaluate('Object.keys(localStorage).some(k=>/token|workspace|note/i.test(k))')
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        page.locator('.nav[data-tab=brain]').click();page.locator('#refreshGraph').click()
        expect(page.locator('#graphStage')).to_have_attribute('data-layout','category-groups')
        page.screenshot(path=str(OUT/f'{label}-groups.png'))
        orb = page.locator('#sonicMotionFloat')
        orb.click(force=True)
        assert page.evaluate('window.__mic.calls') == 0
        page.wait_for_timeout(60);orb.click(force=True)
        expect(page.locator('#voiceStateText')).to_have_text('Listening')
        expect(page.locator('#voiceConsent')).not_to_be_visible()
        assert page.evaluate('window.__mic.calls') == 1
        assert len(sessions) == 1 and sessions[0]['consent'] is True
        page.wait_for_timeout(900)
        shade = page.evaluate("({opacity:+getComputedStyle(document.querySelector('#sonicFocusShade')).opacity,z:+getComputedStyle(document.querySelector('#sonicFocusShade')).zIndex,core:+getComputedStyle(document.querySelector('#sonicMotionFloat')).zIndex})")
        assert shade['opacity'] >= .95 and shade['core'] > shade['z']
        page.screenshot(path=str(OUT/f'{label}-listening.png'))
        orb.click(force=True);page.wait_for_timeout(60);orb.click(force=True)
        assert page.evaluate('window.__mic.calls') == 1
        page.locator('#voiceMute').click();expect(page.locator('#voiceStateText')).to_have_text('Mic muted')
        page.locator('#voiceMute').click();page.keyboard.press('Escape')
        assert not page.evaluate('window.sonicMotion.focused')
        page.locator('.nav[data-tab=workspace]').click()
        # Real SonicVoice event -> app routing -> cloud storage, with context
        # captured when speech starts rather than when transcription arrives.
        page.evaluate("""label => {
          const v=window.__voice;
          v.event({type:'input_audio_buffer.speech_started',item_id:'workspace_create'},v.generation);
          v.event({type:'conversation.item.input_audio_transcription.completed',item_id:'workspace_create',transcript:'buat catatan Voice roundtrip '+label},v.generation);
        }""",label)
        expect(page.locator('#wsPreviewName')).to_have_text('Voice roundtrip '+label+'.md')
        page.evaluate("window.__voice.event({type:'input_audio_buffer.speech_started',item_id:'stale_workspace'},window.__voice.generation)")
        page.locator('#wsClosePreview').click()
        page.get_by_role('button',name='Renamed '+label+'.md',exact=True).click()
        expect(page.locator('#wsPreviewName')).to_have_text('Renamed '+label+'.md')
        page.evaluate("window.__voice.event({type:'conversation.item.input_audio_transcription.completed',item_id:'stale_workspace',transcript:'hapus catatan ini'},window.__voice.generation)")
        page.wait_for_function("document.querySelector('#chatFeed').textContent.includes('Pilihan workspace berubah')")
        expect(page.locator('#wsDialog')).not_to_be_visible()
        page.locator('.nav[data-tab=brain]').click()
        expect(page.locator('#voiceStop')).to_be_visible();page.locator('#voiceStop').click()
        expect(page.locator('#voiceSessionBar')).not_to_be_visible()
        assert page.evaluate('window.__mic.stops') == 1
        # New explicit gesture with browser-denied permission: no provider session.
        page.evaluate('window.__mic.deny=true');page.wait_for_timeout(1100)
        orb.click(force=True);page.wait_for_timeout(60);orb.click(force=True)
        expect(page.locator('#notice')).to_contain_text('Izin mikrofon ditolak')
        assert len(sessions) == 1 and not page.evaluate('window.__voice.active')
        page.keyboard.press('Escape')
        assert not errors, errors
        reports.append({'viewport':label,'workspaceCRUD':True,'conflictDraftPreserved':True,
            'voiceDraftAndExplicitSave':True,'staleVoiceSelectionRejected':True,'groupedNodes':True,'doubleTapOneSession':True,
            'permissionDeniedNoSession':True,'muteStopAccessible':True,'pageErrors':errors})
        page.close()
    browser.close()
    (OUT/'report.json').write_text(json.dumps(reports,indent=2))
    print(json.dumps(reports,indent=2))
