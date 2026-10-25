import asyncio
from datetime import timedelta
import json
from uuid import uuid4
import pytest
import httpx
from sqlalchemy import select
from sonic.db import session_factory, VoiceSession, utcnow
from tests.test_engine_v04 import login, note

SDP='v=0\r\no=- 1 1 IN IP4 127.0.0.1\r\nm=audio 9 UDP/TLS/RTP/SAVPF 111\r\n'

@pytest.fixture
def provider(client,monkeypatch):
    import sonic.voice as voice
    monkeypatch.setenv('SONIC_REALTIME_ENABLED','true')
    monkeypatch.setenv('OPENAI_API_KEY','synthetic-test-key-not-for-network')
    requests=[]
    class MockClient:
        def __init__(self,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*args):pass
        async def post(self,url,**kwargs):
            requests.append((url,kwargs))
            if url.endswith('/hangup'):return httpx.Response(200)
            return httpx.Response(201,text=SDP,headers={'Location':'/v1/realtime/calls/rtc_synthetic_123'})
    monkeypatch.setattr(voice.httpx,'AsyncClient',MockClient)
    return requests


def start(client,h):
    sid=str(uuid4())
    response=client.post('/api/voice/sessions',json={'session_id':sid,'sdp':SDP,'consent':True},headers=h)
    assert response.status_code==200,response.text
    assert 'synthetic-test-key' not in response.text
    return sid


def call(client,h,sid,name,args,cid='call1'):
    return client.post(f'/api/voice/sessions/{sid}/tools',json={'call_id':cid,'name':name,'arguments':args},headers=h)


def test_disabled_no_provider_request(client):
    h=login(client)
    assert not client.get('/api/voice/status').json()['enabled']
    r=client.post('/api/voice/sessions',json={'session_id':str(uuid4()),'sdp':SDP,'consent':True},headers=h)
    assert r.status_code==503


def test_auth_consent_and_csrf(client,provider):
    data={'session_id':str(uuid4()),'sdp':SDP,'consent':True}
    assert client.get('/api/voice/status').status_code==401
    assert client.post('/api/voice/sessions',json=data).status_code==401
    h=login(client)
    assert client.post('/api/voice/sessions',json=data).status_code==403
    data['consent']=False
    assert client.post('/api/voice/sessions',json=data,headers=h).status_code==422
    assert not provider


def test_fixed_provider_session_contract(client,provider):
    h=login(client);sid=start(client,h)
    url,payload=provider[0]
    assert url=='https://api.openai.com/v1/realtime/calls'
    config=json.loads(payload['files']['session'][1])
    assert config['model']=='gpt-realtime'
    assert config['audio']['input']['turn_detection']['interrupt_response'] is True
    names={t['name'] for t in config['tools']}
    assert names=={'graph_search','graph_focus','graph_neighbors','graph_reset','memory_search','memory_prepare','device_metrics'}
    assert 'memory_save' not in names
    assert client.get('/api/voice/status').json()['active_session']['id']==sid
    status=client.post(f'/api/voice/sessions/{sid}/stop',json={},headers=h).json()
    assert status['closed'] and status['provider_close_confirmed']
    assert provider[-1][0].endswith('/rtc_synthetic_123/hangup')


def test_memory_proposal_is_not_a_save(client,provider):
    h=login(client);sid=start(client,h)
    r=call(client,h,sid,'memory_prepare',{'fact':'Saya suka makanan pedas'})
    assert r.status_code==200,r.text
    p=r.json()['output']; assert p['saved'] is False
    assert client.get('/api/memories').json()['total']==0
    same=call(client,h,sid,'memory_prepare',{'fact':'Saya suka makanan pedas'})
    assert same.json()==r.json()
    conflict=call(client,h,sid,'memory_prepare',{'fact':'Saya suka kopi'})
    assert conflict.status_code==409
    route=f"/api/voice/sessions/{sid}/memories/{p['proposal_id']}/confirm"
    assert client.post(route,json={'confirm':True}).status_code==403
    assert client.post(route,json={'confirm':False},headers=h).status_code==422
    receipt=client.post(route,json={'confirm':True},headers=h)
    assert receipt.json()['saved'] and receipt.json()['source']=='voice_confirmed'
    again=client.post(route,json={'confirm':True},headers=h)
    assert again.status_code==200 and again.json()['created'] is False
    assert client.get('/api/memories').json()['total']==1
    assert any(n['id']==receipt.json()['node_id'] for n in client.get('/api/knowledge/graph').json()['nodes'])


def test_readonly_tools_shared_memory_graph(client,provider):
    h=login(client);mid=note(client,h);sid=start(client,h)
    r=call(client,h,sid,'memory_search',{'query':'bakso'})
    assert r.json()['output']['results'][0]['id']==mid
    graph=call(client,h,sid,'graph_focus',{'node_id':f'memory:{mid}'},'call2')
    assert graph.json()['ui_actions'][0]['node_id']==f'memory:{mid}'
    for name in ['shell.exec','memory_save','pc_request_snapshot','files.delete','trade','graph_connect']:
        assert call(client,h,sid,name,{},'forbidden_'+name.replace('.','_')).status_code==403


def test_session_scoped_to_login_and_expiry(client,provider):
    h=login(client);sid=start(client,h)
    old=client.cookies.get('sonic_session')
    other=login(client)
    assert call(client,other,sid,'graph_reset',{}).status_code==404
    client.cookies.set('sonic_session',old)
    with session_factory()() as db:
        row=db.get(VoiceSession,sid);row.expires_at=utcnow()-timedelta(seconds=1);db.commit()
    assert call(client,h,sid,'graph_reset',{}).status_code==409
    import sonic.voice as voice
    asyncio.run(voice.sweep_expired())
    with session_factory()() as db:assert db.get(VoiceSession,sid).state=='closed'


def test_single_session_and_daily_limit_survive_restart(client,provider,monkeypatch):
    monkeypatch.setenv('SONIC_VOICE_DAILY_SESSIONS','1')
    h=login(client);sid=start(client,h)
    data={'session_id':str(uuid4()),'sdp':SDP,'consent':True}
    assert client.post('/api/voice/sessions',json=data,headers=h).status_code==409
    client.post(f'/api/voice/sessions/{sid}/stop',json={},headers=h)
    import sonic.db as storage
    storage._engine.dispose();storage._engine=None;storage._Session=None
    assert client.post('/api/voice/sessions',json=data,headers=h).status_code==429


def test_reject_secrets_and_expired_confirm(client,provider):
    h=login(client);sid=start(client,h)
    assert call(client,h,sid,'memory_prepare',{'fact':'my password is abcdef'}).status_code==422
    r=call(client,h,sid,'memory_prepare',{'fact':'Saya suka bakso'},'valid')
    pid=r.json()['output']['proposal_id']
    client.post(f'/api/voice/sessions/{sid}/stop',json={},headers=h)
    assert client.post(f'/api/voice/sessions/{sid}/memories/{pid}/confirm',json={'confirm':True},headers=h).status_code==409
    assert client.get('/api/memories').json()['total']==0


def test_reject_proposal_and_no_restore_deleted_memory(client,provider):
    h=login(client);sid=start(client,h)
    p=call(client,h,sid,'memory_prepare',{'fact':'Saya suka bakso'}).json()['output']['proposal_id']
    client.post(f'/api/voice/sessions/{sid}/memories/{p}/reject',json={},headers=h)
    assert client.post(f'/api/voice/sessions/{sid}/memories/{p}/confirm',json={'confirm':True},headers=h).status_code==409
    p=call(client,h,sid,'memory_prepare',{'fact':'Saya suka kopi'},'call2').json()['output']['proposal_id']
    route=f'/api/voice/sessions/{sid}/memories/{p}/confirm'
    mid=client.post(route,json={'confirm':True},headers=h).json()['memory_id']
    client.delete(f'/api/memories/{mid}',headers=h)
    assert client.post(route,json={'confirm':True},headers=h).status_code==409
    assert client.get('/api/memories').json()['total']==0


def test_provider_failure_does_not_leak_details(client,provider,monkeypatch):
    import sonic.voice as voice
    async def rejected(self,url,**kwargs):return httpx.Response(401,text='SECRET_PROVIDER_ERROR')
    monkeypatch.setattr(voice.httpx.AsyncClient,'post',rejected)
    h=login(client)
    r=client.post('/api/voice/sessions',json={'session_id':str(uuid4()),'sdp':SDP,'consent':True},headers=h)
    assert r.status_code==502 and 'SECRET_PROVIDER_ERROR' not in r.text


def test_bad_sdp_and_extra_body_fields(client,provider):
    h=login(client)
    data={'session_id':str(uuid4()),'sdp':SDP+'m=video 9\r\n','consent':True}
    assert client.post('/api/voice/sessions',json=data,headers=h).status_code==422
    data['sdp']=SDP;data['provider_url']='https://evil.invalid'
    assert client.post('/api/voice/sessions',json=data,headers=h).status_code==422
    assert not provider


def test_logout_hangup_and_tool_revocation(client,provider):
    h=login(client);sid=start(client,h)
    assert client.post('/api/logout',headers=h).status_code==200
    assert call(client,h,sid,'graph_reset',{}).status_code==401
    assert provider[-1][0].endswith('/hangup')


def test_voice_can_read_real_pc_metrics_but_not_execute(client,provider):
    h=login(client);sid=start(client,h)
    missing=call(client,h,sid,'device_metrics',{},'metric_before')
    assert missing.status_code==200
    assert missing.json()['output']['metrics_available'] is False
    assert missing.json()['ui_actions'][0]['type']=='device.metrics'
    ok=client.post('/api/device/heartbeat',json={
        'device_id':'TRADEVICEPC','hostname':'TRADEVICEPC','platform':'Windows',
        'agent_version':'0.5.0','capabilities':['system.metrics'],
        'metrics':{'ram_total_bytes':16*2**30,'ram_available_bytes':7*2**30,'ram_used_percent':56},
        'gui_targets':[]},headers={'Authorization':'Bearer device-test-token'})
    assert ok.status_code==200
    observed=call(client,h,sid,'device_metrics',{},'metric_live')
    assert observed.status_code==200
    assert observed.json()['output']['metrics_available'] is True
    assert observed.json()['output']['metrics']['ram_available_bytes']==7*2**30
    assert observed.json()['ui_actions'][0]['type']=='device.metrics'
    assert call(client,h,sid,'device_metrics',{'script':'taskkill'},'metric_bad').json()['output']=={'error':'INVALID_TOOL_ARGUMENTS'}
    assert call(client,h,sid,'shell.run',{'recipe':'clock'},'shell_forbidden').status_code==403
