"""SONIC 0.8.4 actual screenshot regression: speech PC intent and proof-only receipts."""
import pytest
from sonic.chat_actions import classify, confirmation_intent, looks_like_pc_action
from tests.test_voice_v04 import provider, start
from tests.test_engine_v04 import login
from tests.test_chat_first_v082 import connect as connect_v082, next_job, finish

DEVICE={'Authorization':'Bearer device-test-token'}

def connect(client):
    reply=client.post('/api/device/heartbeat',headers=DEVICE,json={
      'device_id':'TRADEVICEPC','hostname':'TRADEVICEPC','platform':'Windows',
      'agent_version':'0.8.4','capabilities':['system.status','system.metrics',
        'desktop.mkdir','file.mkdir','file.list','powershell.exec','process.list'],
      'metrics':{'ram_total_bytes':16*2**30,'ram_available_bytes':8*2**30},
      'gui_targets':[]
    })
    assert reply.status_code==200,reply.text

def dispatch(client,h,sid,item,text,origin='transcript'):
    return client.post(f'/api/voice/sessions/{sid}/dispatch',headers=h,json={
        'item_id':item,'transcript':text,'origin':origin})

@pytest.mark.parametrize('spoken,name,action',[
    ('Buatkan di desktop dengan nama foldernya Today.','Today','desktop.mkdir'),
    ('Tolong buatkan di desktop dengan nama foldernya Today.','Today','desktop.mkdir'),
    ('Buatkan folder di desktop bernama Today.','Today','desktop.mkdir'),
    ('Buat folder bernama Today di desktop TRADEVICEPC.','Today','desktop.mkdir'),
    ('Bikin folder Today di dekstop komputer saya.','Today','desktop.mkdir'),
    ('Di desktop TRADEVICEPC buat folder dengan nama Today.','Today','desktop.mkdir'),
    ('SONIC, buat folder Today di desktop Threadvice PC.','Today','desktop.mkdir'),
    ('Buat folder "Chat QA desktop" di TRADEVICEPC','Chat QA desktop','file.mkdir')
])
def test_exact_spoken_folder_paraphrases(spoken,name,action):
    a=classify(spoken)
    assert a is not None,spoken
    assert a.action==action
    assert a.payload==({'name':name} if action=='desktop.mkdir' else {'path':name})

@pytest.mark.parametrize('phrase',[
    'Sebelumnya, coba kamu cek di log history itu kamu membuat folder bernama Sonic di desktop. Itu bisa.',
    'Bagaimana cara buat folder Today di desktop?',
    'Jangan buat folder Today di desktop',
    'Kalau saya membuat folder Today di desktop, apa akibatnya?',
    'Tolong buatkan di desktop dengan nama foldernya ../Windows',
])
def test_non_commands_or_unsafe_folder_names_not_enqueued(phrase):
    try:
        result=classify(phrase)
    except ValueError:
        result=None
    assert result is None

def test_voice_screenshot_phrase_enqueues_one_real_lease(client,provider):
    h=login(client);connect(client);sid=start(client,h)
    phrase='Buatkan di desktop dengan nama foldernya Today.'
    first=dispatch(client,h,sid,'screenshot_item_1',phrase)
    assert first.status_code==200,first.text
    out=first.json()
    assert out['handled'] and out['route']=='chat_pc_action'
    assert out['operator_jobs'][0]['action']=='desktop.mkdir'
    assert out['operator_proposals']==[]
    assert 'Desktop' in out['reply']
    same=dispatch(client,h,sid,'screenshot_item_1',phrase)
    assert same.status_code==200 and same.json()==out
    job=next_job(client)
    assert job['action']=='desktop.mkdir' and job['payload']=={'name':'Today'}
    assert next_job(client) is None
    finished=finish(client,job,{'created':True,'exists':True,
        'name':'Today','scope':'owner_desktop',
        'path':'C:/Users/Owner/Desktop/Today'})
    assert finished['state']=='done'
    history=client.get('/api/history').json()['messages']
    assert any('Folder Desktop berhasil dibuat' in row['content'] for row in history)
    assert next_job(client) is None

def test_speech_approvals_are_not_sufficient_for_powershell(client,provider,monkeypatch):
    monkeypatch.setenv('SONIC_ENABLE_POWERSHELL_EXEC','true')
    h=login(client);connect(client);sid=start(client,h)
    proposal=dispatch(client,h,sid,'ps_preview','PowerShell: Get-Date').json()
    assert proposal['operator_proposals'][0]['action']=='powershell.exec'
    assert next_job(client) is None
    voice_yes=dispatch(client,h,sid,'ps_speech_yes','Oke, setuju. Jalankan pakai PowerShell.')
    assert voice_yes.status_code==200,voice_yes.text
    assert voice_yes.json()['route']=='voice_approval_review'
    assert voice_yes.json()['operator_jobs']==[]
    assert next_job(client) is None
    click_yes=dispatch(client,h,sid,'pc_button_yes','setuju','approval_button')
    assert click_yes.status_code==200,click_yes.text
    assert click_yes.json()['operator_jobs'][0]['action']=='powershell.exec'
    assert next_job(client)['action']=='powershell.exec'

def test_voice_unparsed_pc_command_is_explained_not_generative(client,provider):
    h=login(client);connect(client);sid=start(client,h)
    phrase='Buatkan di desktop dong, folder yang kemarin itu.'
    assert classify(phrase) is None
    assert looks_like_pc_action(phrase) is True
    response=dispatch(client,h,sid,'pc_ambiguous',phrase)
    assert response.status_code==200,response.text
    data=response.json()
    assert data['handled'] is True
    assert data['route']=='voice_pc_clarification'
    assert data['operator_jobs']==[]
    assert 'Belum ada perintah yang dijalankan' in data['reply']
    assert next_job(client) is None

def test_non_pc_small_talk_still_reaches_realtime(client,provider):
    h=login(client);connect(client);sid=start(client,h)
    reply=dispatch(client,h,sid,'greeting','Selamat pagi SONIC. Bagaimana kabarmu?')
    assert reply.status_code==200 and reply.json()['handled'] is False
    assert next_job(client) is None

def test_button_origin_cannot_submit_arbitrary_pc_command(client,provider):
    h=login(client);connect(client);sid=start(client,h)
    result=dispatch(client,h,sid,'button_invalid',
                    'Buat folder Today di desktop','approval_button')
    assert result.status_code==422
    assert next_job(client) is None

def test_paraphrased_owner_confirmation_only_with_pending_review():
    assert confirmation_intent('Oke, setuju. Jalankan pakai PowerShell.')=='approve'
    assert confirmation_intent('solusi lainnya apa?') is None
