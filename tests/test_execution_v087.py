"""Execution engine contracts: durable identity, actual targets and terminal state."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
import json
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.orm import Session

from sonic import auth
from sonic.db import (Base, ChatMessage, ChatOperation, Device, DeviceTelemetry, EngineRun, ExecutionTask,
                      OperatorRequest, OwnerSession, VoiceActionDispatch, session_factory, utcnow)
from sonic.execution import choose_adapter, input_identity, NATIVE
from tests.test_engine_v04 import login
from tests.test_voice_command_v084 import connect, dispatch, next_job, DEVICE
from tests.test_chat_first_v082 import finish
from tests.test_voice_v04 import provider, start


def chat(client, h, text='buat folder Engine QA di Desktop TRADEVICEPC', key='request_1', **extra):
    return client.post('/api/chat', headers=h, json={'message':text,'request_id':key,**extra})


def good_result(name='Engine QA'):
    return {'exists':True,'created':True,'name':name,'scope':'owner_desktop',
            'path':'C:/Users/Owner/OneDrive/Desktop/'+name}


def test_chat_input_replay_keeps_one_durable_job_and_tracks_actual_phase(client):
    h=login(client);connect(client)
    first=chat(client,h).json()
    task=first['task']
    assert task['status']=='queued' and task['verification']=={'status':'pending'}
    assert first['engine']['status']=='queued'
    assert chat(client,h).json()['task']['id']==task['id']
    with session_factory()() as db:
        assert db.scalar(select(func.count()).select_from(ExecutionTask))==1
        assert db.scalar(select(func.count()).select_from(OperatorRequest))==1
        assert db.scalar(select(func.count()).select_from(ChatOperation))==1
        assert db.scalar(select(func.count()).select_from(ChatMessage).where(ChatMessage.role=='user'))==1
    assert chat(client,h,'buat folder Different di Desktop TRADEVICEPC').status_code==409
    job=next_job(client)
    assert client.get('/api/engine/tasks/'+task['id']).json()['status']=='running'
    assert next_job(client) is None
    finish(client,job,good_result())
    done=client.get('/api/engine/tasks/'+task['id']).json()
    assert done['status']=='completed'
    assert done['verification']['status']=='agent_verified'
    assert done['verification']['independent_readback'] is False
    replay=chat(client,h).json()
    assert replay['engine']['status']=='completed'
    assert 'Folder Desktop berhasil dibuat' in replay['reply']
    assert next_job(client) is None
    assert client.get('/api/engine/runs').json()['runs'][0]['status']=='completed'


@pytest.mark.parametrize('change',[
    {'exists':False},{'exists':'true'},{'created':'yes'},{'name':'Other'},
    {'path':'C:/Users/Owner/Desktop/Other'},{'path':'relative/Engine QA'},
    {'scope':'sonic_workspace'}, {'path':'C:/Users/Owner/Desktop/../Engine QA'},
])
def test_success_flag_without_matching_folder_evidence_is_failure(client,change):
    h=login(client);connect(client)
    task=chat(client,h).json()['task']
    job=next_job(client)
    assert finish(client,job,{**good_result(),**change})['state']=='failed'
    snapshot=client.get('/api/engine/tasks/'+task['id']).json()
    assert snapshot['verification']['status']=='unverified'
    history=client.get('/api/history').json()['messages']
    assert not any('Folder Desktop berhasil dibuat' in x['content'] for x in history)
    assert any('belum dapat diverifikasi' in x['content'] for x in history)


def test_workspace_receipt_cannot_silently_change_destination(client):
    h=login(client);connect(client)
    chat(client,h,'buat folder Engine QA di TRADEVICEPC')
    job=next_job(client)
    assert finish(client,job,{'exists':True,'created':True,'relative_path':'Engine QA',
        'path':'C:/Users/Owner/Desktop/Engine QA'})['state']=='failed'


def test_powerful_command_is_reported_without_claiming_verified_side_effects(client,monkeypatch):
    monkeypatch.setenv('SONIC_ENABLE_POWERSHELL_EXEC','true')
    h=login(client);connect(client)
    task=chat(client,h,'PowerShell: Get-Date').json()['task']
    assert task['status']=='awaiting_approval'
    assert next_job(client) is None
    approved=chat(client,h,'setuju',key='approval',approval_request_id=task['id'])
    assert approved.status_code==200
    job=next_job(client);finish(client,job,{'exit_code':0})
    assert client.get('/api/engine/tasks/'+task['id']).json()['verification']['status']=='agent_reported'


def test_old_approval_button_never_approves_a_new_proposal(client,monkeypatch):
    monkeypatch.setenv('SONIC_ENABLE_POWERSHELL_EXEC','true')
    h=login(client);connect(client)
    old=chat(client,h,'PowerShell: Get-Date').json()['task']['id']
    client.delete('/api/operator/requests/'+old,headers=h)
    current=chat(client,h,'PowerShell: Get-Service',key='new_proposal').json()['task']['id']
    response=chat(client,h,'setuju',key='stale_button',approval_request_id=old)
    assert 'Perintah lain tidak disetujui' in response.json()['reply']
    assert client.get('/api/engine/tasks/'+current).json()['status']=='awaiting_approval'
    assert next_job(client) is None


def test_stop_cancels_queued_and_leased_jobs_without_reviving_on_late_results(client):
    h=login(client);connect(client)
    first=chat(client,h).json()['task']['id']
    job=next_job(client)
    second=chat(client,h,'buat folder Another di Desktop TRADEVICEPC',key='second').json()['task']['id']
    assert client.post('/api/engine/stop',json={}).status_code==403
    assert client.post('/api/engine/stop',headers=h,json={}).json()['cancelled']==2
    assert client.post('/api/device/operator/check',headers=DEVICE,
        json={'request_id':job['id'],'lease':job['lease']}).json()['execute'] is False
    assert next_job(client) is None
    assert finish(client,job,good_result())['state']=='cancelled'
    assert all(client.get('/api/engine/tasks/'+key).json()['status']=='cancelled' for key in (first,second))
    assert chat(client,h).json()['operator_jobs']==[]


def test_late_success_does_not_complete_expired_job(client):
    h=login(client);connect(client)
    rid=chat(client,h).json()['task']['id'];job=next_job(client)
    with session_factory()() as db:
        db.get(OperatorRequest,rid).expires_at=utcnow()-timedelta(seconds=1);db.commit()
    assert finish(client,job,good_result())['state']=='expired'
    assert client.get('/api/engine/tasks/'+rid).json()['status']=='expired'


def test_tasks_require_owner_session_and_are_not_revealed_to_next_login(client):
    assert client.get('/api/engine/tasks').status_code==401
    h=login(client);connect(client)
    rid=chat(client,h).json()['task']['id']
    client.post('/api/logout',headers=h)
    login(client)
    assert client.get('/api/engine/tasks').json()['tasks']==[]
    assert client.get('/api/engine/tasks/'+rid).status_code==404


def test_router_requires_fresh_capabilities_and_never_uses_unconnected_adapters(client):
    h=login(client);connect(client)
    with session_factory()() as db:
        for adapter in ('rdc','google-drive','notepad','unknown'):
            with pytest.raises(Exception) as error:
                choose_adapter(db,'desktop.mkdir',{'name':'QA'},adapter)
            assert error.value.status_code==409
        db.get(DeviceTelemetry,'TRADEVICEPC').updated_at=utcnow()-timedelta(seconds=121)
        db.commit()
    response=chat(client,h).json()
    assert not response['operator_jobs'] and response['engine']['status']=='rejected'
    assert next_job(client) is None


@pytest.mark.parametrize('phrase',[
    'Buat folder “Sonic Project” di Desktop TRADEVICEPC.',
    'Tolong buatkan folder bernama Sonic Project di desktop.',
])
def test_voice_preserves_structured_target_and_original_owner_transcript(client,provider,phrase):
    h=login(client);connect(client);sid=start(client,h)
    data=dispatch(client,h,sid,'quoted_item',phrase).json()
    assert data['task']['channel']=='voice' and data['engine']['status']=='queued'
    job=next_job(client)
    assert job['action']=='desktop.mkdir' and job['payload']=={'name':'Sonic Project'}
    history=client.get('/api/history').json()['messages']
    assert any(x['role']=='user' and x['content']==phrase for x in history)


def test_voice_recovers_queued_task_when_worker_lost_dispatch_response(client,provider):
    h=login(client);connect(client);sid=start(client,h)
    phrase='Buat folder Today di Desktop'
    first=dispatch(client,h,sid,'crash_after_queue',phrase).json()
    with session_factory()() as db:
        row=db.scalar(select(VoiceActionDispatch));row.state='processing';row.result_json='{}'
        db.get(ExecutionTask,first['task']['id']).response_json=''
        db.commit()
    replay=dispatch(client,h,sid,'crash_after_queue',phrase).json()
    assert replay['task']['id']==first['task']['id']
    assert replay['operator_jobs'][0]['id']==first['task']['id']
    assert next_job(client) and next_job(client) is None


def test_failed_voice_dispatch_has_explicit_unconfirmed_state(client,provider):
    h=login(client);connect(client);sid=start(client,h)
    phrase='Buat folder Today di Desktop'
    key=auth.sha256(sid+':failed_item')
    with session_factory()() as db:
        db.add(VoiceActionDispatch(id=key,session_id=sid,transcript_hash=auth.sha256(phrase),state='failed'))
        db.commit()
    response=dispatch(client,h,sid,'failed_item',phrase).json()
    assert response['route']=='voice_dispatch_unconfirmed'
    assert not response.get('processing') and not response['operator_jobs']


def test_concurrent_retries_commit_one_operation(client):
    h=login(client);connect(client)
    with ThreadPoolExecutor(max_workers=4) as pool:
        responses=list(pool.map(lambda _:chat(client,h),range(4)))
    assert all(r.status_code==200 for r in responses),[r.text for r in responses]
    ids={r.json()['task']['id'] for r in responses}
    assert len(ids)==1
    with session_factory()() as db:
        assert db.scalar(select(func.count()).select_from(OperatorRequest))==1
        assert db.scalar(select(func.count()).select_from(ChatOperation))==1


def test_text_status_query_and_unparsed_pc_request_do_not_call_model(client):
    h=login(client);connect(client)
    chat(client,h)
    response=chat(client,h,'Sudah jadi?',key='status').json()
    assert response['engine']['route']=='task_status'
    assert 'belum selesai' in response['reply'] and not response['operator_jobs']
    unclear=chat(client,h,'buat folder Today di desktop laptop orang lain',key='unclear').json()
    assert unclear['engine']['route']=='chat_pc_clarification'
    assert unclear['engine']['status']=='needs_clarification'
    assert next_job(client) and next_job(client) is None


def test_stop_clears_unfinished_voice_folder_slot(client,provider):
    from sonic.db import VoicePendingFolder
    h=login(client);connect(client);sid=start(client,h)
    assert dispatch(client,h,sid,'prepare_slot','Buat folder di Desktop').json()['route']=='voice_folder_slot'
    client.post('/api/engine/stop',headers=h,json={})
    with session_factory()() as db:
        assert db.get(VoicePendingFolder,sid) is None
    assert dispatch(client,h,sid,'after_stop','Today').json()['handled'] is False
    assert next_job(client) is None


@pytest.mark.skipif(not os.environ.get('SONIC_TEST_POSTGRES_URL'),reason='Disposable PostgreSQL not configured')
def test_postgres_queue_and_input_identity_commit_atomically():
    """Run in the existing isolated PostgreSQL CI service, never staging DB."""
    from sonic.operator import chat_queue
    url=os.environ['SONIC_TEST_POSTGRES_URL']
    assert url.startswith('postgresql+psycopg://') and 'localhost' in url and '/sonic_test' in url
    admin=create_engine(url)
    schema='sonic_engine_qa_'+uuid4().hex
    with admin.begin() as connection:
        connection.execute(text('CREATE SCHEMA '+schema))
    engine=admin.execution_options(schema_translate_map={None:schema})
    owner={'sid':'synthetic-owner-session'}
    identity=input_identity(owner,'chat','retry_id','buat folder QA di Desktop')
    try:
        Base.metadata.create_all(engine)
        with Session(engine,expire_on_commit=False) as db:
            db.add(Device(id='TRADEVICEPC'))
            db.add(DeviceTelemetry(device_id='TRADEVICEPC',capabilities_json='["desktop.mkdir"]'))
            message=ChatMessage(role='user',content='synthetic QA')
            db.add(message);db.commit();mid=message.id
        def queue(_):
            with Session(engine,expire_on_commit=False) as db:
                db.info.update(execution_identity=identity,execution_run_id=str(uuid4()))
                return chat_queue(db,owner,'desktop.mkdir',{'name':'QA'},mid,True)
        with ThreadPoolExecutor(max_workers=4) as pool:
            receipts=list(pool.map(queue,range(8)))
        assert len({r['id'] for r in receipts})==1
        with Session(engine) as db:
            assert db.scalar(select(func.count()).select_from(ExecutionTask))==1
            assert db.scalar(select(func.count()).select_from(OperatorRequest))==1
            assert db.scalar(select(func.count()).select_from(ChatOperation))==1
    finally:
        with admin.begin() as connection:
            connection.execute(text('DROP SCHEMA '+schema+' CASCADE'))
        admin.dispose()
