"""SONIC V0.9.0 Window Control: precise owner intent, review, device receipts."""
from __future__ import annotations

from types import SimpleNamespace
from pathlib import Path
import pytest

from sonic.chat_actions import classify
from sonic.device_contract import clean_request
from sonic.window_policy_v090 import parse_window_command, looks_like_window_command
from tests.test_engine_v04 import login
from tests.test_voice_v04 import provider, start
from tests.test_chat_first_v082 import next_job, finish

DEVICE={'Authorization':'Bearer device-test-token'}


def connect(client, caps=True):
    capabilities=['system.status','system.metrics','window.list']
    if caps:
        capabilities += ['window.open','window.focus','window.close']
    r=client.post('/api/device/heartbeat', headers=DEVICE,json={
        'device_id':'TRADEVICEPC','hostname':'TRADEVICEPC','platform':'Windows',
        'agent_version':'0.9.0','capabilities':capabilities,
        'metrics':{'ram_total_bytes':16*2**30,'ram_available_bytes':8*2**30},
        'gui_targets':[]
    })
    assert r.status_code==200,r.text


def chat(client,headers,spoken,request_id):
    return client.post('/api/chat',headers=headers,json={
        'message':spoken,'request_id':request_id
    })


@pytest.mark.parametrize('phrase,action,app,kind',[
    ('SONIC, tutup MetaTrader 5','window.close','metatrader5','review'),
    ('Matiin kamu close MetaTrader 5 ya.','window.close','metatrader5','review'),
    ('Tolong close window MT5 di TRADEVICEPC','window.close','metatrader5','review'),
    ('Buka Notepad','window.open','notepad','review'),
    ('Please open Microsoft Paint','window.open','paint','review'),
    ('Fokuskan Notepad','window.focus','notepad','automatic'),
    ('Fokus MetaTrader 5','window.focus','metatrader5','review'),
])
def test_explicit_chat_and_voice_commands(phrase,action,app,kind):
    assert parse_window_command(phrase)==(action,app)
    parsed=classify(phrase)
    assert parsed is not None
    assert (parsed.action,parsed.payload,parsed.kind)==(action,{'app':app},kind)


@pytest.mark.parametrize('phrase',[
    'Hola', 'Jangan tutup MetaTrader 5', 'Contoh cara close MetaTrader 5',
    'Apakah bisa tutup MetaTrader 5?', 'Tutup posisi MetaTrader 5',
    'Close all MT5 orders', 'Tutup window yang tadi',
    'Close Chrome', 'Open cmd.exe', 'Close powershell.exe',
    'Tutup MT5 lalu buka Paint', 'Matiin semua aplikasi',
])
def test_no_guess_or_unapproved_app(phrase):
    assert parse_window_command(phrase) is None
    assert classify(phrase) is None


@pytest.mark.parametrize('payload',[
    {'app':'chrome'}, {'app':'../terminal64.exe'}, {'app':'metatrader5','path':'C:/bad'},
    {'app':'MetaTrader 5'},{'app':'metatrader5','force':True},
    {'app':''}, {'app':7}, {},
])
def test_server_rejects_non_allowlisted_payload(payload):
    with pytest.raises(ValueError):
        clean_request('window.close',payload)


def test_without_new_agent_capability_no_job_or_false_confirmation(client):
    h=login(client);connect(client,caps=False)
    result=chat(client,h,'Tutup MetaTrader 5','no_window_agent').json()
    assert result['operator_jobs']==[] and result['operator_proposals']==[]
    assert result['engine']['status']=='rejected'
    assert next_job(client) is None


def test_trading_window_close_requires_approval_and_agent_receipt(client):
    h=login(client);connect(client)
    first=chat(client,h,'Matiin kamu close MetaTrader 5 ya.','close_mt5').json()
    assert first['engine']['status']=='awaiting_approval'
    assert first['operator_jobs']==[]
    assert first['operator_proposals'][0]['action']=='window.close'
    assert 'EA' in first['reply'] and 'WM_CLOSE' in first['reply']
    task=first['task']
    assert next_job(client) is None
    before=client.get('/api/engine/tasks/'+task['id']).json()
    assert before['verification']=={'status':'pending'}
    approval=chat(client,h,'setuju','approve_mt5').json()
    assert approval['operator_jobs'][0]['id']==task['id']
    job=next_job(client)
    assert job['action']=='window.close' and job['payload']=={'app':'metatrader5'}
    receipt={'app':'metatrader5','method':'WM_CLOSE','closed':True,'close_requested':True}
    assert finish(client,job,receipt)['state']=='done'
    after=client.get('/api/engine/tasks/'+task['id']).json()
    assert after['verification']['status']=='agent_reported'
    assert after['verification']['independent_readback'] is False
    messages=client.get('/api/history').json()['messages']
    assert any('dilaporkan tertutup' in m['content'] for m in messages if m['role']=='assistant')
    assert next_job(client) is None


def test_no_false_close_when_save_dialog_keeps_window_visible(client):
    h=login(client);connect(client)
    jobinfo=chat(client,h,'Tutup Notepad','close_notepad').json()
    chat(client,h,'setuju','approve_notepad')
    job=next_job(client)
    state=finish(client,job,{'app':'notepad','method':'WM_CLOSE',
                             'close_requested':True,'closed':False},False)
    assert state['state']=='failed'
    messages=client.get('/api/history').json()['messages']
    assert any('belum terkonfirmasi tertutup' in m['content'] for m in messages if m['role']=='assistant')
    assert all('dilaporkan tertutup' not in m['content'] for m in messages)


def test_false_success_payload_cannot_turn_into_verified_window_close(client):
    h=login(client);connect(client)
    data=chat(client,h,'Tutup MetaTrader 5','target_mismatch').json()
    chat(client,h,'setuju','approve_target_mismatch')
    job=next_job(client)
    bad={'app':'notepad','method':'WM_CLOSE','closed':True}
    assert finish(client,job,bad)['state']=='failed'
    evidence=client.get('/api/engine/tasks/'+data['task']['id']).json()['verification']
    assert evidence['status']=='unverified' and evidence['code']=='WINDOW_RESULT_TARGET_OR_METHOD_MISMATCH'


def test_foreground_notepad_can_queue_without_extra_review(client):
    h=login(client);connect(client)
    data=chat(client,h,'Fokuskan Notepad','focus_notepad').json()
    assert data['operator_proposals']==[]
    assert data['operator_jobs'][0]['action']=='window.focus'
    job=next_job(client)
    assert job['payload']=={'app':'notepad'}
    assert finish(client,job,{'app':'notepad','method':'SET_FOREGROUND','focused':True})['state']=='done'


def test_voice_close_proposes_only_and_hola_does_not_approve(client,provider):
    h=login(client);connect(client);sid=start(client,h)
    def dispatch(item,text,origin='transcript',approval=None):
        return client.post(f'/api/voice/sessions/{sid}/dispatch',headers=h,json={
            'item_id':item,'transcript':text,'origin':origin,
            **({'approval_request_id':approval} if approval else {})
        })
    proposed=dispatch('mt5_voice','SONIC, close MetaTrader 5').json()
    assert proposed['operator_proposals'][0]['action']=='window.close'
    request_id=proposed['operator_proposals'][0]['id']
    assert next_job(client) is None
    hola=dispatch('hola_after_mt5','Hola').json()
    assert hola['route']=='voice_window_pending'
    assert 'Belum ada aksi' in hola['reply']
    yes_speech=dispatch('spoken_yes','setuju').json()
    assert yes_speech['route']=='voice_approval_review'
    assert next_job(client) is None
    yes_button=dispatch('click_yes','setuju','approval_button',request_id).json()
    assert yes_button['operator_jobs'][0]['id']==request_id
    assert next_job(client)['action']=='window.close'
