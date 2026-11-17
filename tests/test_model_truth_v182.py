"""Model truth regressions. Synthetic owner, DB, web results and inference only."""
import pytest
from fastapi import HTTPException
from tests.test_auth_and_api import auth
from sonic import research_agent as agent
from sonic import model_runtime as rt
from sonic import local_ai
from sonic.providers import Selection

LOCAL=Selection('local',local_ai.MODEL)
CLOUD=Selection('deepseek','deepseek-flash')

def web_result(*a,**kw):
    return {'sources':[{'id':1,'title':'Verified test source','url':'https://example.org/reference',
        'publisher':'example.org','snippet':'Synthetic relevant test material.',
        'excerpt':'Synthetic relevant test material.','read':True}],
        'trace':[], 'queries':['synthetic'], 'reason':None, 'notice':'Test fixture'}

def configure(monkeypatch,selected,ready):
    monkeypatch.setenv('SONIC_RESEARCH_AGENT_ENABLED','true')
    monkeypatch.setenv('SONIC_RESEARCH_CLOUD_SUMMARY_ENABLED','true')
    monkeypatch.setattr('sonic.providers.selected_model',lambda db:selected)
    monkeypatch.setattr(rt,'selected_model',lambda db:selected)
    monkeypatch.setattr(rt,'configured',lambda provider:True)
    monkeypatch.setattr(rt,'runtime_snapshot',lambda db:{'enabled':True,'device_online':True,
        'bridge_online':True,'state':'running' if ready else 'stopped','checked_seconds_ago':1})
    monkeypatch.setattr(agent,'_local_running',lambda db:ready)
    monkeypatch.setattr(agent,'search_and_read',web_result)

@pytest.mark.parametrize('text',[
    'Model aktif apa yang sonic gunakan sekarang?', 'Model apa yang kamu pakai?',
    'What model are you using?', 'Apakah local AI sedang running?',
    'SONIC menggunakan model apa sekarang?'])
def test_first_party_model_intents(text):
    assert rt.is_model_status_question(text)

@pytest.mark.parametrize('text',[
    'Cari model terbaru di Hugging Face', 'Bagaimana cara kerja MITM?',
    'Bandingkan model lokal dengan DeepSeek', 'Apa itu model 3D?',
    'Find active model research papers',
    'Jelaskan model regresi yang digunakan perusahaan',
    'Model apa yang digunakan perusahaan di Jepang?'])
def test_not_every_model_question_is_status(text):
    assert not rt.is_model_status_question(text)

@pytest.mark.parametrize('endpoint,body',[
    ('/api/chat',{'message':'Model aktif apa yang sonic gunakan sekarang?'}),
    ('/api/agent/research',{'query':'Model aktif apa yang sonic gunakan sekarang?','save_to_memory':True})])
def test_status_uses_no_search_no_model_no_research_memory(client,monkeypatch,endpoint,body):
    configure(monkeypatch,LOCAL,False)
    def forbidden(*a,**kw):raise AssertionError('No external request allowed')
    monkeypatch.setattr(agent,'search_and_read',forbidden)
    monkeypatch.setattr(local_ai,'infer',forbidden)
    csrf=auth(client)
    result=client.post(endpoint,headers={'X-Sonic-CSRF':csrf},json=body)
    assert result.status_code==200,result.text
    data=result.json()
    assert data['mode']=='system_status'
    assert data['sources']==[] and not data['memory_saved']
    assert data['answer_origin']['inference_performed'] is False
    assert 'belum berjalan' in data['reply']
    assert client.get('/api/agent/memory').json()['total']==0

def test_cloud_selected_local_running_still_calls_cloud_only(client,monkeypatch):
    configure(monkeypatch,CLOUD,True)
    calls=[]
    async def cloud(q,s,m,db,selection=None):
        assert selection==CLOUD
        calls.append('cloud');return ('Jawaban sumber [1].','deepseek')
    async def local(*a,**kw):
        calls.append('unexpected-local');raise AssertionError('Wrong model: selected cloud')
    monkeypatch.setattr(agent,'_cloud_summarize',cloud)
    monkeypatch.setattr(local_ai,'infer',local)
    csrf=auth(client)
    r=client.post('/api/agent/research',headers={'X-Sonic-CSRF':csrf},json={'query':'Synthetic public research'})
    assert r.status_code==200,r.text
    d=r.json();assert calls==['cloud'] and d['mode']=='cloud_summary'
    assert d['answer_origin']['model']=='deepseek-flash'
    assert d['answer_origin']['provider']=='deepseek' and d['answer_origin']['inference_performed']

def test_local_stopped_is_not_cloud_available_and_makes_no_search(client,monkeypatch):
    configure(monkeypatch,LOCAL,False)
    def forbidden(*a,**kw):raise AssertionError('No search or cloud fallback')
    monkeypatch.setattr(agent,'search_and_read',forbidden)
    monkeypatch.setattr(agent,'_cloud_summarize',forbidden)
    csrf=auth(client)
    r=client.post('/api/agent/research',headers={'X-Sonic-CSRF':csrf},json={'query':'Synthetic research','save_to_memory':True})
    d=r.json();assert d['mode']=='model_unavailable'
    assert not d['answer_origin']['inference_performed']
    caps=client.get('/api/agent/capabilities').json()['runtime']
    assert caps['selected']['provider']=='local' and caps['selected']['state']=='stopped'
    assert not caps['cloud_synthesis_eligible'] and not caps['research_synthesis_eligible']

def test_local_running_uses_local_only_and_failed_local_never_falls_back(client,monkeypatch):
    configure(monkeypatch,LOCAL,True)
    calls=[]
    async def local(request):
        calls.append('local')
        return {'output':[{'content':[{'text':'Penjelasan dari local [1].'}]}]}
    async def cloud(*a,**kw):
        calls.append('unexpected-cloud');raise AssertionError('No fallback allowed')
    monkeypatch.setattr(local_ai,'infer',local)
    monkeypatch.setattr(agent,'_cloud_summarize',cloud)
    csrf=auth(client);headers={'X-Sonic-CSRF':csrf}
    r=client.post('/api/agent/research',headers=headers,json={'query':'Synthetic public research'})
    d=r.json();assert d['mode']=='local_summary' and calls==['local']
    assert d['answer_origin']['model']==local_ai.MODEL
    async def fail(request):raise HTTPException(504,'Synthetic model timeout')
    monkeypatch.setattr(local_ai,'infer',fail)
    r=client.post('/api/agent/research',headers=headers,json={'query':'Synthetic research again'})
    d=r.json();assert d['mode']=='sources_only'
    assert not d['answer_origin']['inference_performed'] and d['answer_origin']['provider'] is None
    assert 'unexpected-cloud' not in calls

def test_cloud_config_is_not_inference_proof(client,monkeypatch):
    configure(monkeypatch,CLOUD,False)
    auth(client)
    data=client.get('/api/intelligence/status').json()
    assert data['selected']['state']=='configured_not_probed'
    assert data['inference_verified'] is False

def test_runtime_status_owner_only(client,monkeypatch):
    monkeypatch.setenv('SONIC_OPEN_PREVIEW','true')
    client.get('/api/session')
    assert client.get('/api/intelligence/status').status_code==401
