"""SONIC V0.6 persona security, durability and realtime/TTS integration."""
from __future__ import annotations
from fastapi.testclient import TestClient
from sonic.persona import VOICES, STYLE_PROMPTS, INTENSITY_PROMPTS, profile, persona_instruction, provider_voice
from sonic.voice import session_config
from sonic.db import session_factory


def login(client: TestClient):
    r = client.post('/api/login', json={'token': 'owner-test-token'})
    assert r.status_code == 200
    return r.json()['csrf']


def test_catalog_is_ten_unique_realtime_voices():
    assert len(VOICES) == 10
    assert len(set(v['provider_voice'] for v in VOICES)) == 10
    assert len([v for v in VOICES if v['group'] == 'male']) == 5
    assert len([v for v in VOICES if v['group'] == 'female']) == 5
    assert len(STYLE_PROMPTS) == 10
    assert len(INTENSITY_PROMPTS) == 3


def test_rejects_unauthenticated_reads_and_writes(client):
    assert client.get('/api/persona').status_code == 401
    assert client.put('/api/persona', json={'voice_id':'male_01','style':'friendly','intensity':'balanced'}).status_code == 401


def test_defaults_and_persistence(client):
    csrf=login(client)
    d=client.get('/api/persona').json()
    assert d['active']=={'voice_id':'male_01','style':'friendly','intensity':'balanced'}
    assert len(d['voices'])==10
    payload={'voice_id':'female_03','style':'poetic','intensity':'expressive'}
    r=client.put('/api/persona', json=payload,headers={'X-Sonic-CSRF':csrf})
    assert r.status_code==200 and r.json()['saved'] is True
    assert r.json()['active']==payload
    assert client.get('/api/persona').json()['active']==payload
    db=session_factory()()
    try:
        assert profile(db)==payload
        config=session_config(profile(db))
    finally:db.close()
    assert config['audio']['output']['voice']=='shimmer'
    assert 'occasional graceful imagery' in config['instructions']
    assert 'privacy' in config['instructions']


def test_csrf_and_values_are_whitelisted(client):
    csrf=login(client)
    valid={'voice_id':'male_02','style':'robot','intensity':'short'}
    assert client.put('/api/persona', json=valid).status_code == 403
    for tampered in [dict(valid,style='disable_all_limits'),dict(valid,voice_id='admin'),dict(valid,intensity='unlimited'),dict(valid,metadata='inject')]:
        assert client.put('/api/persona', json=tampered,headers={'X-Sonic-CSRF':csrf}).status_code==422
    assert client.get('/api/persona').json()['active']['style']=='friendly'


def test_preset_and_custom_persona(client):
    csrf=login(client)
    assert client.post('/api/persona/presets/work',headers={'X-Sonic-CSRF':csrf}).json()['active']['style']=='professional'
    assert client.post('/api/persona/presets/personal',headers={'X-Sonic-CSRF':csrf}).json()['active']['intensity']=='balanced'
    assert client.post('/api/persona/presets/experimental',headers={'X-Sonic-CSRF':csrf}).json()['active']['style']=='glitch'
    assert client.post('/api/persona/presets/ultraadmin',headers={'X-Sonic-CSRF':csrf}).status_code==422


def test_persona_does_not_change_tool_policy():
    for style in STYLE_PROMPTS:
        text=persona_instruction({'style':style,'intensity':'expressive','voice_id':'male_01'})
        assert 'Keep facts, privacy, approvals, safety rules, and tool permissions unchanged' in text
        assert 'Never fabricate' in text
    assert provider_voice({'voice_id':'unknown'})=='cedar'


def test_preview_voice_uses_allowlisted_provider_and_does_not_save(client, monkeypatch):
    import sonic.speech as speech
    csrf=login(client)
    monkeypatch.setenv('OPENAI_API_KEY','sk-disposable-test-provider-key')
    payloads=[]
    class DummyResponse:
        status_code=200
        content=b'ID3 synthetic audio from test transport'
    class Client:
        def __init__(self,*a,**kw): pass
        async def __aenter__(self):return self
        async def __aexit__(self,*a):pass
        async def post(self,*a,**kw):payloads.append(kw['json']);return DummyResponse()
    monkeypatch.setattr(speech.httpx,'AsyncClient',Client)
    r=client.post('/api/voice/speak',json={'text':'Welcome back, sir','consent':True,'preview_voice_id':'female_03'},headers={'X-Sonic-CSRF':csrf})
    assert r.status_code==200
    assert r.headers['x-sonic-voice']=='shimmer'
    assert payloads[-1]['voice']=='shimmer'
    assert client.get('/api/persona').json()['active']['voice_id']=='male_01'
    denied=client.post('/api/voice/speak',json={'text':'hi','consent':True,'preview_voice_id':'forbidden-voice'},headers={'X-Sonic-CSRF':csrf})
    assert denied.status_code==422


def test_style_preview_uses_selected_voice_style_and_intensity_without_saving(client, monkeypatch):
    import sonic.speech as speech
    csrf = login(client)
    monkeypatch.setenv('OPENAI_API_KEY', 'sk-test-synthetic-do-not-share')
    bodies=[]
    class Response:
        status_code=200
        content=b'ID3 synthetic provider audio'
    class MockClient:
        def __init__(self,*a,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*a):pass
        async def post(self,*a,**kwargs):bodies.append(kwargs['json']);return Response()
    monkeypatch.setattr(speech.httpx,'AsyncClient',MockClient)
    out=client.post('/api/voice/speak',json={
        'text':'SONIC ONLINE. SISTEM SIAP. MENUNGGU INSTRUKSI BERIKUTNYA.',
        'consent':True, 'preview_voice_id':'female_02','preview_style':'robot',
        'preview_intensity':'short'
    },headers={'X-Sonic-CSRF':csrf})
    assert out.status_code==200
    assert out.headers['X-Sonic-Voice']=='coral'
    assert out.headers['X-Sonic-Style']=='robot'
    assert out.headers['X-Sonic-Intensity']=='short'
    assert bodies[-1]['voice']=='coral'
    assert 'precise, minimal, systematic' in bodies[-1]['instructions']
    assert 'one or two sentences' in bodies[-1]['instructions']
    assert client.get('/api/persona').json()['active']=={
        'voice_id':'male_01','style':'friendly','intensity':'balanced'}
    for field,value in [('preview_style','ignore_all_rules'),('preview_intensity','unlimited')]:
        bad=client.post('/api/voice/speak',json={
            'text':'Hello','consent':True,field:value
        },headers={'X-Sonic-CSRF':csrf})
        assert bad.status_code==422


def test_saved_persona_used_for_realtime_and_subsequent_tts(client,monkeypatch):
    import sonic.speech as speech
    csrf=login(client)
    chosen={'voice_id':'female_05','style':'humor','intensity':'expressive'}
    assert client.put('/api/persona',json=chosen,headers={'X-Sonic-CSRF':csrf}).status_code==200
    with session_factory()() as db:
        config=session_config(profile(db))
    assert config['audio']['output']['voice']=='alloy'
    assert 'contextual wit' in config['instructions']
    monkeypatch.setenv('OPENAI_API_KEY','sk-test-synthetic-do-not-share')
    bodies=[]
    class Response:
        status_code=200
        content=b'ID3 mock'
    class MockClient:
        def __init__(self,*a,**kwargs):pass
        async def __aenter__(self):return self
        async def __aexit__(self,*a):pass
        async def post(self,*a,**kwargs):bodies.append(kwargs['json']);return Response()
    monkeypatch.setattr(speech.httpx,'AsyncClient',MockClient)
    resp=client.post('/api/voice/speak',json={'text':'Test applied voice','consent':True},headers={'X-Sonic-CSRF':csrf})
    assert resp.status_code==200
    assert resp.headers['X-Sonic-Voice']=='alloy'
    assert resp.headers['X-Sonic-Style']=='humor'
    assert bodies[-1]['voice']=='alloy'
