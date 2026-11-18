"""Chat PC acceptance with synthetic authenticated device receipts only.
No live owner credentials, Windows commands, installers, or model calls.
"""
from __future__ import annotations
import hashlib
import json
import os
import time
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright, expect
from qa_server import local_server

OUT=Path(__file__).resolve().parents[1]/'artifacts'/'pc-agent-v183'
OUT.mkdir(parents=True,exist_ok=True)
TOKEN='qa-pc-agent-v183-only'
SETTINGS={'SONIC_DEVICE_TOKEN_SHA256':hashlib.sha256(TOKEN.encode()).hexdigest(),
 'SONIC_ENABLE_SOFTWARE_DISCOVERY':'true','SONIC_ENABLE_SOFTWARE_INSTALL':'true',
 'SONIC_OPEN_PREVIEW':'true','SONIC_OWNER_ENTRY_ENABLED':'true','SONIC_PASSWORDLESS_LOGIN':'false',
 'SONIC_PREVIEW_PAID_ACTIONS':'false'}
ENGINE=os.environ.get('SONIC_QA_BROWSER','chromium')
def digest(plan):
 return hashlib.sha256(json.dumps(plan,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
reports=[]
with local_server(settings=SETTINGS) as (base,owner),sync_playwright() as p:
 browser=getattr(p,ENGINE).launch(headless=True,**({'args':['--no-sandbox','--enable-unsafe-swiftshader']} if ENGINE=='chromium' else {}))
 device=httpx.Client(base_url=base,headers={'Authorization':'Bearer '+TOKEN},timeout=15)
 def agent(path,payload):
  response=device.post(path,json=payload);assert response.status_code==200,response.text
  return response.json()
 def next_job(page,action):
  for _ in range(40):
   job=agent('/api/device/operator/next',{}).get('job')
   if job:
    assert job['action']==action,job
    return job
   page.wait_for_timeout(150)
  raise AssertionError('No queued '+action)
 def complete(job,result):
  return agent('/api/device/operator/result',{'request_id':job['id'],'lease':job['lease'],'success':True,'result':result})
 def inspected(job,metadata):
  plan={**job['payload'],'source':'winget','scope':'user','allow_reboot':False}
  complete(job,{'ok':True,'status':'inspected','plan':plan,'plan_sha256':digest(plan),
   'evidence':{'kind':'winget_show_raw','exit_code':0,'stdout':metadata,'stderr':''}})
  return plan
 for label,w,h,version in [('iphone',390,690,'1.2.3'),('desktop',1440,900,'2.3.4')]:
  agent('/api/device/heartbeat',{'device_id':'TRADEVICEPC','hostname':'Synthetic-PC','platform':'Windows',
   'agent_version':'0.10.0','capabilities':['system.status','software.search','software.inspect','software.inventory','software.install'],
   'metrics':{'ram_total_bytes':16*2**30,'ram_available_bytes':8*2**30}})
  page=browser.new_page(viewport={'width':w,'height':h},is_mobile=w<721,has_touch=w<721)
  errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.route('**/api/huggingface/**',lambda r:r.fulfill(status=200,json={'results':[],'count':0,'files':[]}))
  page.goto(base+'/owner',wait_until='domcontentloaded')
  page.locator('#ownerToken').fill(owner);page.locator('#loginForm button[type=submit]').click()
  expect(page.locator('#loginOverlay')).to_be_hidden(timeout=15000)
  page.locator('.nav[data-tab=chat]').click()
  expect(page.locator('#pcTools')).to_be_visible(timeout=12000)
  page.locator('#pcTools > summary').click()
  expect(page.locator('#pcTools [data-pc-action="window.open"]').first).to_be_disabled()
  page.locator('.pc-inspect-form > summary').click()
  page.locator('#pcPackage').fill('Example.Editor');page.locator('#pcVersion').fill(version)
  assert not page.locator('#pcSourceConsent').is_checked()
  assert not page.locator('#pcPackageConsent').is_checked()
  page.locator('#pcInspect').click()
  first=next_job(page,'software.inspect')
  assert first['payload']=={'package_id':'Example.Editor','version':version,
    'accept_source_agreements':False,'accept_package_agreements':False}
  metadata=('Publisher: Example Publisher\nVersion: '+version+
    '\nLicense: Synthetic test license\nLicense URL: https://example.invalid/license\n'+
    '<img src=x onerror="window.pcCatalogXss=true">')
  inspected(first,metadata)
  expect(page.locator('.pc-inspection').last).to_contain_text('Example.Editor',timeout=12000)
  expect(page.locator('.pc-inspection').last).to_contain_text(version)
  expect(page.locator('.pc-inspection').last).to_contain_text('winget')
  expect(page.locator('.pc-inspection').last).to_contain_text('Akun Windows saat ini')
  expect(page.locator('.pc-inspection-metadata pre').last).to_contain_text('Synthetic test license')
  expect(page.locator('.pc-inspection-metadata pre').last).to_contain_text('<img src=x')
  assert page.locator('.pc-inspection img').count()==0
  assert page.evaluate('window.pcCatalogXss === undefined')
  assert page.get_by_role('button',name='Tinjau instalasi',exact=True).count()==0
  page.screenshot(path=str(OUT/f'{ENGINE}-{label}-inspection.png'))
  page.get_by_role('button',name='Tinjau paket & lisensi',exact=True).last.click()
  expect(page.locator('#pcPackage')).to_have_value('Example.Editor')
  expect(page.locator('#pcVersion')).to_have_value(version)
  assert not page.locator('#pcSourceConsent').is_checked()
  assert not page.locator('#pcPackageConsent').is_checked()
  page.locator('#pcSourceConsent').check();page.locator('#pcPackageConsent').check()
  page.locator('#pcInspect').click()
  second=next_job(page,'software.inspect')
  assert second['payload']['accept_source_agreements'] is True
  assert second['payload']['accept_package_agreements'] is True
  plan=inspected(second,metadata)
  review=page.get_by_role('button',name='Tinjau instalasi',exact=True).last
  expect(review).to_be_visible(timeout=12000);review.click()
  expect(page.locator('.chat-inline-approval').last).to_be_visible(timeout=12000)
  assert agent('/api/device/operator/next',{})['job'] is None
  approval=page.locator('.message.assistant').filter(has=page.locator('.chat-inline-approval')).last
  expect(approval).to_contain_text('Example.Editor');expect(approval).to_contain_text(version)
  expect(approval).to_contain_text('winget')
  page.locator('.chat-reject-button').last.click()
  expect(page.locator('#chatFeed')).to_contain_text('Perintah software.install dibatalkan',timeout=12000)
  assert agent('/api/device/operator/next',{})['job'] is None
  review.click()
  expect(page.locator('.chat-approve-button').last).to_be_enabled(timeout=12000)
  page.screenshot(path=str(OUT/f'{ENGINE}-{label}-approval.png'))
  page.locator('.chat-approve-button').last.click()
  install=next_job(page,'software.install')
  assert install['payload']=={'plan':plan,'plan_sha256':digest(plan)}
  assert agent('/api/device/operator/next',{})['job'] is None
  installed={key:plan[key] for key in ('package_id','version','source')}
  complete(install,{'ok':True,'status':'succeeded','plan_sha256':digest(plan),'installed':installed,
    'evidence':{'kind':'winget_export_json','packages':[installed]}})
  expect(page.locator('#chatFeed')).to_contain_text('Instalasi software terverifikasi',timeout=12000)
  expect(page.locator('#send')).to_be_enabled(timeout=12000)
  # A paused older delivery must not be replaced by a new message or clear its draft.
  posts=[];page.on('request',lambda req:posts.append(req.url) if req.method=='POST' and req.url.endswith('/api/chat') else None)
  page.route('**/api/chat/delivery/paused-prior',lambda r:r.fulfill(status=200,json={
   'reply':'Jawaban lama dipulihkan.','delivery':{'id':'paused-prior','state':'done'},
   'answer_origin':{'kind':'system_status','inference_performed':False}}))
  page.evaluate("sessionStorage.setItem('sonic.pending-chat.v183', JSON.stringify({id:'paused-prior',at:Date.now()}))")
  page.locator('#message').fill('Simpan draft baru ini')
  page.locator('#send').click()
  expect(page.locator('#chatFeed')).to_contain_text('Jawaban lama dipulihkan.',timeout=12000)
  expect(page.locator('#message')).to_have_value('Simpan draft baru ini')
  assert posts==[],posts
  assert page.evaluate("sessionStorage.getItem('sonic.pending-chat.v183')") is None
  # A reply already in persisted history must retain recovered approval controls.
  agent('/api/device/heartbeat',{'device_id':'TRADEVICEPC','hostname':'Synthetic-PC','platform':'Windows',
   'agent_version':'0.10.0','capabilities':['system.status','window.open'],
   'metrics':{'ram_total_bytes':16*2**30,'ram_available_bytes':8*2**30}})
  restored=page.evaluate("""async rid=>{
   const session=await (await fetch('/api/session')).json();
   const response=await fetch('/api/chat',{method:'POST',headers:{'Content-Type':'application/json','X-Sonic-CSRF':session.csrf,'X-Sonic-Async':'1'},
     body:JSON.stringify({message:'buka notepad',request_id:rid})});
   if(!response.ok)throw Error('Synthetic proposal submission failed');
   const data=await response.json();
   if(!data.operator_proposals?.length)throw Error('Synthetic proposal missing');
   sessionStorage.setItem('sonic.pending-chat.v183',JSON.stringify({id:rid,at:Date.now()}));
   const history=await (await fetch('/api/history')).json();
   return {reply:data.reply,id:data.operator_proposals[0].id,
     historyCount:history.messages.filter(m=>m.role==='assistant'&&m.content===data.reply).length};
  }""",'recover-approval-'+label)
  assert agent('/api/device/operator/next',{})['job'] is None
  page.reload(wait_until='domcontentloaded')
  recovered_row=page.locator('.chat-inline-approval[data-approval-id="'+restored['id']+'"]')
  expect(recovered_row).to_be_visible(timeout=15000)
  assert page.locator('#chatFeed .message.assistant .body').evaluate_all('(nodes,reply)=>nodes.filter(n=>n.textContent===reply).length',restored['reply'])==restored['historyCount'],restored
  recovered_row.locator('.chat-reject-button').click()
  expect(page.locator('#chatFeed')).to_contain_text('Perintah window.open dibatalkan',timeout=12000)
  assert agent('/api/device/operator/next',{})['job'] is None
  assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
  assert not errors,errors
  reports.append({'browser':ENGINE,'viewport':label,'metadata_visible_before_consent':True,
    'metadata_html_inert':True,'exact_inspection_plan':True,'cancel_prevents_install':True,
    'final_approval_required':True,'verified_version_receipt':True,'draft_preserved_during_recovery':True,
    'approval_recovered_in_existing_history':True,'synthetic_device_only':True})
  page.close()
 device.close();browser.close()
(OUT/f'{ENGINE}-report.json').write_text(json.dumps(reports,indent=2),encoding='utf-8')
print(json.dumps(reports));print('PC_AGENT_'+ENGINE.upper()+'_PASS')
