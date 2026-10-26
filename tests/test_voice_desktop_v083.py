"""Voice/desktop action acceptance, replay defenses and local Windows path guards."""
from datetime import timedelta
from pathlib import Path

import pytest

from sonic.chat_actions import classify
from sonic.device_contract import clean_request
from sonic.voice import session_config
from sonic.db import VoiceSession, VoiceActionDispatch, session_factory, utcnow
from scripts.windows_workspace_v082 import create_desktop_folder
from tests.test_engine_v04 import login
from tests.test_voice_v04 import provider, start


DEVICE_HEADERS={'Authorization':'Bearer device-test-token'}


def heartbeat(client):
    response=client.post('/api/device/heartbeat',headers=DEVICE_HEADERS,json={
        'device_id':'TRADEVICEPC','hostname':'TRADEVICEPC','platform':'Windows',
        'agent_version':'0.8.3','capabilities':['system.status','system.metrics','file.mkdir',
        'desktop.mkdir','file.read','file.list','powershell.exec','process.list'],
        'metrics':{'ram_total_bytes':16*2**30,'ram_available_bytes':8*2**30},
        'gui_targets':[]
    })
    assert response.status_code==200,response.text


def utter(client,h,sid,item,text):
    return client.post(f'/api/voice/sessions/{sid}/dispatch',headers=h,
                       json={'item_id':item,'transcript':text})


def next_job(client):
    response=client.post('/api/device/operator/next',headers=DEVICE_HEADERS,json={})
    assert response.status_code==200,response.text
    return response.json()['job']


@pytest.mark.parametrize('phrase',[
    'Tolong buatkan folder bernama Today di desktop Threadvice PC.',
    'SONIC, buat folder Today di desktop TRADEVICEPC',
    'Buatkan folder bernama Sonic di desktop.',
    'tolong bikin folder baru bernama Renders di dekstop komputer saya',
])
def test_natural_speech_desktop_target(phrase):
    action=classify(phrase)
    assert action is not None,phrase
    assert action.kind=='automatic'
    assert action.action=='desktop.mkdir'
    assert action.payload.get('name') in ('Today','Sonic','Renders')


def test_desktop_does_not_fall_back_to_workspace():
    action=classify('buat folder Today di TRADEVICEPC')
    assert action.action=='file.mkdir'
    assert action.payload=={'path':'Today'}
    # An uncertain Desktop request must never silently create in the workspace.
    assert classify('buat folder Today di desktop laptop orang lain') is None
    assert classify('Sebelumnya, coba kamu cek di log history itu kamu membuat folder Sonic di desktop. Itu bisa.') is None


@pytest.mark.parametrize('unsafe',[
    '../Windows','C:\\Windows','folder/child','secrets','NUL','bad:folder','folder?','%APPDATA%'
])
def test_desktop_payload_confined(unsafe):
    with pytest.raises(ValueError):
        clean_request('desktop.mkdir',{'name':unsafe})


def test_desktop_helper_stays_in_test_folder_and_is_idempotent(tmp_path):
    first=create_desktop_folder('Today',tmp_path)
    second=create_desktop_folder('Today',tmp_path)
    assert first['scope']=='owner_desktop'
    assert first['created'] is True
    assert second['created'] is False
    assert (tmp_path/'Today').is_dir()
    (tmp_path/'Collision').write_text('a')
    with pytest.raises(PermissionError):
        create_desktop_folder('Collision',tmp_path)
    with pytest.raises(PermissionError):
        create_desktop_folder('../escape',tmp_path)


def test_realtime_response_waits_until_owner_transcript_is_checked():
    cfg=session_config()
    assert cfg['audio']['input']['turn_detection']['create_response'] is False
    assert 'owner Desktop' in cfg['instructions']
    assert 'You cannot control a PC' not in cfg['instructions']
    assert 'VERIFIED_SONIC_ACTION_ROUTE' in cfg['instructions']


def test_voice_desktop_creation_and_replay(client,provider):
    h=login(client);heartbeat(client);sid=start(client,h)
    prompt='Tolong buatkan folder bernama Today di desktop Threadvice PC.'
    response=utter(client,h,sid,'item_desktop_today',prompt)
    assert response.status_code==200,response.text
    data=response.json()
    assert data['handled'] is True
    assert data['route']=='chat_pc_action'
    assert data['operator_jobs'][0]['action']=='desktop.mkdir'
    assert 'Desktop' in data['reply']
    dup=utter(client,h,sid,'item_desktop_today',prompt)
    assert dup.status_code==200 and dup.json()['operator_jobs']==data['operator_jobs']
    assert utter(client,h,sid,'item_desktop_today','Tolong buat folder Another di desktop').status_code==409
    job=next_job(client)
    assert job['action']=='desktop.mkdir' and job['payload']=={'name':'Today'}
    assert next_job(client) is None
    complete=client.post('/api/device/operator/result',headers=DEVICE_HEADERS,json={
        'request_id':job['id'],'lease':job['lease'],'success':True,
        'result':{'created':True,'name':'Today','exists':True,
                  'path':'C:\\Users\\Owner\\Desktop\\Today','scope':'owner_desktop'}})
    assert complete.status_code==200,complete.text
    history=client.get('/api/history').json()['messages']
    assert any('Folder Desktop berhasil dibuat' in m['content'] for m in history)
    with session_factory()() as db:
        events=db.query(VoiceActionDispatch).filter(VoiceActionDispatch.session_id==sid).all()
        assert len(events)==1 and events[0].state=='done'


def test_general_voice_transcript_never_queues_pc_command(client,provider):
    h=login(client);heartbeat(client);sid=start(client,h)
    r=utter(client,h,sid,'item_general_1','Ceritakan bagaimana cara membuat folder.')
    assert r.status_code==200 and r.json()['handled'] is False
    assert next_job(client) is None
    with session_factory()() as db:
        assert not db.query(VoiceActionDispatch).all()


def test_voice_confirmation_in_same_session(client,provider,monkeypatch):
    monkeypatch.setenv('SONIC_ENABLE_POWERSHELL_EXEC','true')
    h=login(client);heartbeat(client);sid=start(client,h)
    preview=utter(client,h,sid,'item_ps1','PowerShell: Get-Date')
    assert preview.status_code==200
    assert preview.json()['operator_proposals'][0]['action']=='powershell.exec'
    assert next_job(client) is None
    yes=utter(client,h,sid,'item_yes','setuju')
    assert yes.status_code==200
    assert yes.json()['operator_jobs'][0]['action']=='powershell.exec'
    job=next_job(client)
    assert job['action']=='powershell.exec'
    assert utter(client,h,sid,'item_yes','setuju').json()['operator_jobs']==yes.json()['operator_jobs']


def test_unowned_or_expired_voice_cannot_enqueue_desktop(client,provider):
    h=login(client);heartbeat(client);sid=start(client,h)
    url=f'/api/voice/sessions/{sid}/dispatch'
    body={'item_id':'item_1','transcript':'buat folder Today di desktop'}
    assert client.post(url,json=body).status_code in (401,403)
    h_other=login(client)
    assert client.post(url,json=body,headers=h_other).status_code==404
    with session_factory()() as db:
        row=db.get(VoiceSession,sid);row.expires_at=utcnow()-timedelta(seconds=1);db.commit()
    assert client.post(url,json=body,headers=h).status_code in (403,404,409)
    assert next_job(client) is None


def test_expired_active_owner_voice_session_rejected(client,provider):
    h=login(client);heartbeat(client);sid=start(client,h)
    with session_factory()() as db:
        row=db.get(VoiceSession,sid)
        row.expires_at=utcnow()-timedelta(seconds=1)
        db.commit()
    r=utter(client,h,sid,'item_expired','buat folder Today di desktop')
    assert r.status_code==409
    assert next_job(client) is None
