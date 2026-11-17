"""Source-of-answer and compact UI acceptance, synthetic owner only.
No vendor inference, PC command, cloud secrets, live chat history or real files.
"""
import json,os
from pathlib import Path
from playwright.sync_api import sync_playwright,expect
from qa_server import local_server
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts'/'model-truth-v182';OUT.mkdir(parents=True,exist_ok=True)
settings={'SONIC_OPEN_PREVIEW':'true','SONIC_OWNER_ENTRY_ENABLED':'true',
          'SONIC_RESEARCH_AGENT_ENABLED':'true','SONIC_RESEARCH_CLOUD_SUMMARY_ENABLED':'true',
          'SONIC_BRAIN_PROVIDER':'local','SONIC_LOCAL_AI_ENABLED':'true',
          'SONIC_PASSWORDLESS_LOGIN':'false','SONIC_PREVIEW_PAID_ACTIONS':'false'}
engine=os.environ.get('SONIC_QA_BROWSER','chromium')
reports=[]
with local_server(settings=settings) as (base,token),sync_playwright() as p:
    browser=getattr(p,engine).launch(headless=True,**({'args':['--no-sandbox','--enable-unsafe-swiftshader']} if engine=='chromium' else {}))
    for label,w,h in [('iphone',390,690),('small',360,640),('desktop',1440,900)]:
        page=browser.new_page(viewport={'width':w,'height':h},is_mobile=w<721,has_touch=w<721)
        errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.route('**/api/huggingface/**',lambda r:r.fulfill(status=200,json={'results':[],'count':0,'files':[]}))
        page.goto(base+'/owner',wait_until='domcontentloaded')
        expect(page.locator('.app')).to_be_hidden()
        page.locator('#ownerToken').fill(token)
        page.locator('#loginForm button[type=submit]').click()
        expect(page.locator('#loginOverlay')).to_be_hidden(timeout=15000)
        page.locator('.nav[data-tab=chat]').click()
        expect(page.locator('#chatPanel .runtime-title')).to_contain_text('Local Qwen 9B',timeout=10000)
        expect(page.locator('#chatPanel .runtime-state')).to_have_text('BELUM BERJALAN')
        expect(page.locator('#agentModeResearch')).to_be_enabled(timeout=10000)
        page.locator('#agentModeResearch').click()
        expect(page.locator('.research-options')).not_to_have_attribute('open','')
        page.locator('#message').fill('Model aktif apa yang sonic gunakan sekarang?')
        page.locator('#send').click()
        expect(page.locator('#chatFeed .message.assistant .body').last).to_contain_text('Model terpilih:',timeout=12000)
        expect(page.locator('#chatFeed .message.assistant .body').last).to_contain_text('belum berjalan')
        expect(page.locator('#chatFeed .answer-origin').last).to_have_text('STATUS SONIC · Tanpa model/web')
        assert page.locator('.agent-source').count()==0
        assert 'Selected cloud AI available' not in page.locator('#chatPanel').inner_text()
        metrics=page.evaluate('''() => {const c=document.querySelector('#chatForm').getBoundingClientRect(),n=document.querySelector('.sidebar').getBoundingClientRect(),f=document.querySelector('#chatFeed').getBoundingClientRect();return {vw:innerWidth,sw:document.documentElement.scrollWidth,composerBottom:c.bottom,navTop:n.top,feedHeight:f.height,micBg:getComputedStyle(document.querySelector('#mic')).backgroundColor};}''')
        assert metrics['sw']<=metrics['vw']+1,metrics
        if w<721:
            assert metrics['composerBottom']<=metrics['navTop'],metrics
            assert metrics['feedHeight']>=150,metrics
            assert metrics['micBg']=='rgb(37, 49, 62)',metrics
        page.screenshot(path=str(OUT/f'{engine}-{label}-chat.png'))
        page.locator('#chatPanel .runtime-widget > summary').click()
        expect(page.locator('#chatPanel .runtime-message')).to_contain_text('belum berjalan')
        page.locator('#chatPanel [data-runtime-action=settings]').click()
        expect(page.locator('#brainModelControl')).to_be_visible()
        expect(page.locator('#brainModelControl .runtime-state')).to_have_text('BELUM BERJALAN')
        page.screenshot(path=str(OUT/f'{engine}-{label}-models.png'))
        page.locator('.nav[data-tab=devices]').click()
        assert page.evaluate("document.getElementById('localAIControl').compareDocumentPosition(document.getElementById('huggingFaceHub')) & Node.DOCUMENT_POSITION_FOLLOWING")
        page.locator('#localAIControl').scroll_into_view_if_needed()
        page.screenshot(path=str(OUT/f'{engine}-{label}-local-controls.png'))
        if w<721:
            page.locator('.nav[data-tab=brain]').click()
            page.locator('#neuralGraphBtn').click()
            expect(page.locator('#neuralGraphBtn')).to_have_attribute('aria-pressed','true')
            expect(page.locator('#neuralKnowledgeBtn')).to_have_attribute('aria-pressed','false')
            page.wait_for_timeout(180)
            page.screenshot(path=str(OUT/f'{engine}-{label}-neural.png'))
        assert not errors,errors
        reports.append({'browser':engine,'viewport':label,'status_route':'no_search_no_inference','local_stopped':'no_cloud_claim','layout':metrics})
        page.close()
    browser.close()
(OUT/f'{engine}-report.json').write_text(json.dumps(reports,indent=2),encoding='utf-8')
print(json.dumps(reports),flush=True)
print('MODEL_TRUTH_'+engine.upper()+'_PASS')
