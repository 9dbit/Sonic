"""Chromium/WebKit: lose submit response, reload, recover same local job.
Synthetic owner/device data. No live owner auth, PC command or external model.
"""
import hashlib,json,os,time
from pathlib import Path
import httpx
from playwright.sync_api import sync_playwright,expect
from qa_server import local_server

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts'/'chat-delivery-v183';OUT.mkdir(parents=True,exist_ok=True)
MODEL='DeepSeek-V4-Pro-Qwen3.5-9B-UNCENSORED-heretic.Q4_K_M'
settings={'SONIC_OPEN_PREVIEW':'true','SONIC_OWNER_ENTRY_ENABLED':'true',
 'SONIC_BRAIN_PROVIDER':'local','SONIC_LOCAL_AI_ENABLED':'true','SONIC_PASSWORDLESS_LOGIN':'false',
 'SONIC_PREVIEW_PAID_ACTIONS':'false','SONIC_ENABLE_SOFTWARE_DISCOVERY':'true',
 'SONIC_ENABLE_SOFTWARE_INSTALL':'true',
 'SONIC_DEVICE_TOKEN_SHA256':hashlib.sha256(b'qa-device-only').hexdigest()}
engine=os.environ.get('SONIC_QA_BROWSER','chromium');reports=[]
with local_server(settings=settings) as (base,token),sync_playwright() as p:
 browser=getattr(p,engine).launch(headless=True,**({'args':['--no-sandbox','--enable-unsafe-swiftshader']} if engine=='chromium' else {}))
 device=httpx.Client(base_url=base,headers={'Authorization':'Bearer qa-device-only'},timeout=15)
 for name,w,h in [('iphone',390,690),('small',360,640),('desktop',1440,900)]:
  device.post('/api/device/heartbeat',json={'device_id':'TRADEVICEPC','hostname':'QA-PC','platform':'Windows',
      'agent_version':'0.10.0','capabilities':['system.status','software.search','software.inspect','software.install','software.inventory','window.open'],
      'metrics':{'cpu_usage_percent':15,'memory_total_mb':16000,'memory_available_mb':7000}}).raise_for_status()
  device.post('/api/device/local-ai/heartbeat',json={'device_id':'TRADEVICEPC','state':'running','ram_free_mb':7000,'gpu_free_mb':3100}).raise_for_status()
  page=browser.new_page(viewport={'width':w,'height':h},is_mobile=w<721,has_touch=w<721)
  errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.route('**/api/huggingface/**',lambda r:r.fulfill(status=200,json={'results':[],'count':0,'files':[]}))
  page.goto(base+'/owner',wait_until='domcontentloaded')
  expect(page.locator('.app')).to_be_hidden()
  page.locator('#ownerToken').fill(token);page.locator('#loginForm button[type=submit]').click()
  expect(page.locator('#loginOverlay')).to_be_hidden(timeout=15000)
  page.locator('.nav[data-tab=chat]').click()
  expect(page.locator('#pcTools')).to_be_visible(timeout=12000)
  count=[]
  failure={'iphone':'network','small':502,'desktop':504}[name]
  def drop_response(route):
   count.append(route.request.post_data_json)
   received=route.fetch()
   assert received.status==202,received.text()
   # Server has queued it, but Safari receives only a failed network fetch.
   if failure=='network':route.abort('failed')
   else:route.fulfill(status=failure,json={'detail':'Synthetic proxy error after acceptance'})
  page.route('**/api/chat',drop_response)
  page.locator('#message').fill('Jawab singkat: tes pemulihan '+name)
  page.locator('#send').click()
  expect(page.locator('#chatFeed')).to_contain_text('memproses jawaban',timeout=12000)
  assert len(count)==1
  request_id=count[0]['request_id']
  job=device.post('/api/device/local-ai/next',json={}).json()['job'];assert job and job['action']=='chat'
  page.screenshot(path=str(OUT/f'{engine}-{name}-waiting.png'))
  page.reload(wait_until='domcontentloaded')
  expect(page.locator('#loginOverlay')).to_be_hidden(timeout=12000)
  # The original worker finishes after the browser was reloaded.
  answer='Jawaban lokal pulih tanpa pengiriman ulang: '+name
  receipt=device.post('/api/device/local-ai/result',json={'device_id':'TRADEVICEPC','job_id':job['id'],
       'success':True,'result':{'text':answer,'usage':{'input_tokens':23,'output_tokens':9}}})
  assert receipt.status_code==200,receipt.text
  expect(page.locator('#chatFeed')).to_contain_text(answer,timeout=15000)
  expect(page.locator('#send')).to_be_enabled(timeout=12000)
  assert len(count)==1,'Reload must not resubmit inference'
  assert page.locator('#chatFeed .message.assistant .body').filter(has_text=answer).count()==1
  assert device.post('/api/device/local-ai/next',json={}).json()['job'] is None
  assert page.evaluate("sessionStorage.getItem('sonic.pending-chat.v183')") is None
  closed_composer=page.locator('#chatForm').bounding_box()
  page.locator('#pcTools > summary').click()
  expect(page.locator('#pcSoftwareQuery')).to_be_visible()
  def open_layout():
   layout=page.evaluate('''()=>{const rect=s=>document.querySelector(s).getBoundingClientRect();
    const hit=s=>{const e=document.querySelector(s),r=e.getBoundingClientRect();return e.contains(document.elementFromPoint(r.x+r.width/2,r.y+r.height/2))};
    const c=rect('#chatForm'),p=rect('#pcTools'),n=rect('.sidebar'),t=rect('#chatPanel .runtime-widget');
    return {composerTop:c.top,composerBottom:c.bottom,panelTop:p.top,panelBottom:p.bottom,runtimeBottom:t.bottom,navTop:n.top,
      composerHit:hit('#message'),sendHit:hit('#send'),summaryHit:hit('#pcTools > summary'),vw:innerWidth,sw:document.documentElement.scrollWidth};}''')
   assert abs(layout['composerTop']-closed_composer['y'])<=1,layout
   assert layout['panelBottom']<=layout['composerTop'],layout
   assert layout['panelTop']>=layout['runtimeBottom']-1,layout
   assert layout['sw']<=layout['vw']+1,layout
   assert all(layout[k] for k in ['composerHit','sendHit','summaryHit']),layout
   if w<721:assert layout['composerBottom']<=layout['navTop'],layout
   return layout
  opened=open_layout()
  page.screenshot(path=str(OUT/f'{engine}-{name}-pc-tools.png'))
  page.locator('.pc-inspect-form > summary').click()
  page.locator('#pcPackage').fill('Git.Git')
  page.locator('#pcVersion').fill('2.0.0')
  expanded=open_layout()
  page.screenshot(path=str(OUT/f'{engine}-{name}-pc-tools-expanded.png'))
  page.locator('#pcVersion').press('Escape')
  expect(page.locator('#pcTools')).not_to_have_attribute('open','')
  expect(page.locator('#pcTools > summary')).to_be_focused()
  page.locator('#pcTools > summary').click()
  page.locator('#message').click()
  expect(page.locator('#pcTools')).not_to_have_attribute('open','')
  metrics=page.evaluate("""()=>{const c=document.querySelector('#chatForm').getBoundingClientRect(),n=document.querySelector('.sidebar').getBoundingClientRect();return{vw:innerWidth,sw:document.documentElement.scrollWidth,composerBottom:c.bottom,navTop:n.top};}""")
  assert metrics['sw']<=metrics['vw']+1,metrics
  if w<721:assert metrics['composerBottom']<=metrics['navTop'],metrics
  page.screenshot(path=str(OUT/f'{engine}-{name}-recovered.png'))
  assert not errors,errors
  reports.append({'browser':engine,'viewport':name,'lost_post_response':'recovered','reload':'same_job',
       'submit_failure':failure,'submitted':len(count),'history_answer_count':1,'layout':metrics,'open_layout':opened,'expanded_layout':expanded})
  page.close()
 device.close();browser.close()
(OUT/f'{engine}-report.json').write_text(json.dumps(reports,indent=2),encoding='utf-8')
print(json.dumps(reports));print('DELIVERY_'+engine.upper()+'_PASS')
