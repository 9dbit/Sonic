"""Recoverable local chat and owner PC-agent integration. Synthetic only."""
from datetime import timedelta
import json
import time
from uuid import uuid4
import pytest
from sqlalchemy import select, func
from tests.test_auth_and_api import auth
from tests.test_local_ai_v152 import heartbeat, device_headers
from sonic.db import ChatMessage, LocalAIJob, session_factory, utcnow
from sonic.local_ai import MODEL, compact_messages
from sonic.chat_delivery import ChatDelivery


def setup_local(client,monkeypatch):
    monkeypatch.setenv('SONIC_LOCAL_AI_ENABLED','true')
    csrf=auth(client)
    heartbeat(client)
    headers={'X-Sonic-CSRF':csrf,'X-Sonic-Async':'1'}
    assert client.put('/api/models/selection',headers=headers,json={'provider':'local','model':MODEL}).status_code==200
    return headers


def post(client,headers,request_id=None,message='Berikan tiga ide desain restoran yang ringkas.'):
    request_id=request_id or str(uuid4())
    return request_id,client.post('/api/chat',headers=headers,json={
        'message':message,'request_id':request_id})


def lease(client):
    r=client.post('/api/device/local-ai/next',headers=device_headers())
    assert r.status_code==200,r.text
    return r.json()['job']


def result(client,job,text='Gunakan pencahayaan berlapis dan sirkulasi yang baik.'):
    return client.post('/api/device/local-ai/result',headers=device_headers(),json={
        'device_id':'TRADEVICEPC','job_id':job['id'],'success':True,
        'result':{'text':text,'usage':{'input_tokens':30,'output_tokens':12}}})


def test_local_submit_is_short_and_retry_is_same_job(client,monkeypatch):
    h=setup_local(client,monkeypatch)
    import sonic.brain as brain
    async def forbidden(*a,**kw):raise AssertionError('No synchronous model wait allowed')
    monkeypatch.setattr(brain,'complete',forbidden)
    start=time.monotonic();rid,r=post(client,h)
    assert time.monotonic()-start<3
    assert r.status_code==202,r.text
    assert r.json()['delivery']['state']=='queued'
    assert r.json()['answer_origin']['inference_performed'] is False
    again=post(client,h,rid)[1]
    assert again.json()['delivery']['id']==r.json()['delivery']['id']
    with session_factory()() as db:
        assert db.scalar(select(func.count()).select_from(LocalAIJob))==1
        assert db.scalar(select(func.count()).select_from(ChatMessage).where(ChatMessage.role=='user'))==1
    assert post(client,h,rid,'Different request')[1].status_code==409
    job=lease(client)
    assert job['action']=='chat' and 'tools' not in job['payload']
    assert result(client,job).status_code==200
    done=client.get('/api/chat/delivery/'+rid)
    assert done.status_code==200
    assert done.json()['delivery']['state']=='done'
    assert done.json()['answer_origin']['provider']=='local'
    assert done.json()['answer_origin']['inference_performed'] is True
    assert post(client,h,rid)[1].json()['reply']==done.json()['reply']
    for _ in range(3):client.get('/api/chat/delivery/'+rid)
    with session_factory()() as db:
        assert db.scalar(select(func.count()).select_from(ChatMessage).where(ChatMessage.role=='assistant'))==1
    # A lost upload acknowledgment can be repeated exactly, but not altered.
    assert result(client,job).json()['duplicate'] is True
    assert result(client,job,'Forged changed text').status_code==409


def test_pending_delivery_is_session_bound_and_guest_protected(client,monkeypatch):
    h=setup_local(client,monkeypatch)
    rid,r=post(client,h)
    assert r.status_code==202
    client.post('/api/logout',headers=h)
    assert client.get('/api/chat/delivery/'+rid).status_code==401
    h2={'X-Sonic-CSRF':auth(client),'X-Sonic-Async':'1'}
    assert client.get('/api/chat/delivery/'+rid).status_code==404
    assert client.post('/api/chat',headers={'X-Sonic-Async':'1'},json={
        'message':'not authorized','request_id':'x'}).status_code==403


def test_lease_expiry_does_not_replay_or_wedge_next_turn(client,monkeypatch):
    h=setup_local(client,monkeypatch)
    rid,r=post(client,h);old=lease(client)
    with session_factory()() as db:
        row=db.get(LocalAIJob,old['id']);row.updated_at=utcnow()-timedelta(seconds=200)
        db.commit()
    rid2,nextturn=post(client,h)
    assert nextturn.status_code==202,nextturn.text
    assert result(client,old).json()['ignored'] is True
    assert client.get('/api/chat/delivery/'+rid).json()['delivery']['state']=='failed'
    new=lease(client);assert new['id']!=old['id']
    assert result(client,new).status_code==200
    assert client.get('/api/chat/delivery/'+rid2).json()['delivery']['state']=='done'


def test_old_context_is_budgeted_without_cutting_current_request():
    current='Supaya mudah buatkan dalam format .exe dan .dmg untuk saya test.'
    request={'input':[{'role':'assistant','content':'A'*1500},
                      {'role':'user','content':'B'*1500},
                      {'role':'assistant','content':'C'*1500},
                      {'role':'user','content':current}]}
    compact=compact_messages(request)
    assert compact[-1]['content']==current
    assert sum(len(i['content']) for i in compact[1:])<=2200
    with pytest.raises(Exception):compact_messages({'input':[{'role':'user','content':'X'*1101}]})


def test_stopped_local_fails_without_cloud_or_hidden_retry(client,monkeypatch):
    h=setup_local(client,monkeypatch)
    client.post('/api/device/local-ai/heartbeat',headers=device_headers(),json={
        'device_id':'TRADEVICEPC','state':'stopped','ram_free_mb':6000})
    rid,r=post(client,h)
    assert r.json()['delivery']['state']=='failed'
    assert r.json()['answer_origin']['inference_performed'] is False
    with session_factory()() as db:
        assert db.scalar(select(func.count()).select_from(LocalAIJob))==0


def test_pc_inspection_and_exact_install_stay_in_chat(client,monkeypatch):
    from tests.test_software import prepare,INSPECT,inspection_result,finish,success_result
    from tests.test_command_center_v08 import next_job
    headers=prepare(client,monkeypatch)
    r=client.post('/api/pc-agent/inspect',headers=headers,json={**INSPECT,'request_id':str(uuid4())})
    assert r.status_code==200,r.text
    inspection=next_job(client)
    assert inspection['action']=='software.inspect'
    assert finish(client,inspection,inspection_result()).json()['state']=='done'
    proposal=client.post('/api/pc-agent/install-review',headers=headers,json={
        'inspection_id':inspection['id'],'request_id':str(uuid4())})
    assert proposal.status_code==200,proposal.text
    assert len(proposal.json()['operator_proposals'])==1
    assert next_job(client) is None
    proposal_id=proposal.json()['operator_proposals'][0]['id']
    approved=client.post('/api/chat',headers=headers,json={'message':'setuju',
        'request_id':str(uuid4()),'approval_request_id':proposal_id})
    assert approved.status_code==200
    install=next_job(client)
    assert install['action']=='software.install'
    assert install['payload']['plan']['scope']=='user'
    assert install['payload']['plan']['allow_reboot'] is False
    assert finish(client,install,success_result(install['payload'])).json()['state']=='done'
    receipt=client.get('/api/operator/requests/'+proposal_id).json()
    assert 'terverifikasi' in receipt['chat_completion']


def test_pc_install_cannot_forge_inspection_or_consent(client,monkeypatch):
    from tests.test_software import prepare,INSPECT,inspection_result,finish
    from tests.test_command_center_v08 import next_job
    headers=prepare(client,monkeypatch)
    assert client.post('/api/pc-agent/install-review',headers=headers,json={
        'inspection_id':str(uuid4()),'request_id':str(uuid4())}).status_code==404
    args={**INSPECT,'accept_source_agreements':False,'accept_package_agreements':False}
    assert client.post('/api/pc-agent/inspect',headers=headers,json={**args,'request_id':str(uuid4())}).status_code==200
    job=next_job(client);finish(client,job,inspection_result(args))
    assert client.post('/api/pc-agent/install-review',headers=headers,json={
        'inspection_id':job['id'],'request_id':str(uuid4())}).status_code==409
    assert client.post('/api/pc-agent/inspect',json={**INSPECT,'request_id':'x'}).status_code==403
    assert client.post('/api/pc-agent/inspect',headers=headers,json={**INSPECT,
        'request_id':'x','command':'anything'}).status_code==422


def test_run_is_explicit_allowlisted_owner_intent():
    from sonic.chat_actions import classify
    assert classify('run notepad').action=='window.open'
    assert classify('run notepad').kind=='review'
    assert classify('jangan run notepad') is None
    assert classify('run notepad; whoami') is None


def test_early_receipt_and_poll_wait_for_response_envelope(client,monkeypatch):
    """A receipt arriving before the submit response cannot finalize twice."""
    h=setup_local(client,monkeypatch)
    import sonic.engine as engine
    from sonic.chat_delivery import settle
    from sonic.db import BrainUsage, EngineRun
    original=engine.execute_chat
    async def fast_receipt(*args,**kwargs):
        output=await original(*args,**kwargs)
        with session_factory()() as other:
            turn=other.scalar(select(ChatDelivery))
            job=other.get(LocalAIJob,turn.local_job_id)
            job.state='done'
            job.result_json=json.dumps({'text':'Receipt before response envelope'})
            other.commit()
            pending=settle(other,turn.id)
            assert pending.state=='queued' and not pending.response_json
            assert other.scalar(select(func.count()).select_from(ChatMessage)
                                .where(ChatMessage.role=='assistant'))==0
        return output
    monkeypatch.setattr(engine,'execute_chat',fast_receipt)
    rid,r=post(client,h)
    assert r.status_code==200 and r.json()['delivery']['state']=='done',r.text
    assert r.json()['reply']=='Receipt before response envelope'
    assert client.get('/api/chat/delivery/'+rid).json()['reply']==r.json()['reply']
    with session_factory()() as db:
        assert db.scalar(select(func.count()).select_from(ChatMessage)
                         .where(ChatMessage.role=='assistant'))==1
        assert db.scalar(select(func.count()).select_from(BrainUsage))==1
        run=db.get(EngineRun,r.json()['engine']['run_id'])
        assert run.status=='completed'
        assert {'tool':'local.chat','status':'completed'} in json.loads(run.steps_json)


def test_submit_cannot_revive_delivery_expired_during_preparation(client,monkeypatch):
    h=setup_local(client,monkeypatch)
    import sonic.engine as engine
    from sonic.chat_delivery import settle
    original=engine.execute_chat
    async def delayed(*args,**kwargs):
        output=await original(*args,**kwargs)
        with session_factory()() as other:
            turn=other.scalar(select(ChatDelivery))
            turn.created_at=utcnow()-timedelta(seconds=200)
            other.commit()
            assert settle(other,turn.id).state=='failed'
        return output
    monkeypatch.setattr(engine,'execute_chat',delayed)
    rid,r=post(client,h)
    assert r.json()['delivery']['state']=='failed'
    with session_factory()() as db:
        assert db.scalar(select(LocalAIJob)).state=='expired'
        assert db.scalar(select(func.count()).select_from(ChatMessage)
                         .where(ChatMessage.role=='assistant'))==0


def test_job_creation_and_delivery_link_share_transaction(client,monkeypatch):
    h=setup_local(client,monkeypatch)
    import sonic.local_ai as local
    original=local.create_job
    def crash_after_job_insert(*args,**kwargs):
        original(*args,**kwargs)
        raise RuntimeError('synthetic crash before delivery link commit')
    monkeypatch.setattr(local,'create_job',crash_after_job_insert)
    with pytest.raises(RuntimeError,match='synthetic crash'):
        post(client,h)
    with session_factory()() as db:
        assert db.scalar(select(func.count()).select_from(LocalAIJob))==0
        assert db.scalar(select(ChatDelivery)).state=='failed'


@pytest.mark.parametrize('terminal',['expired','done'])
def test_stale_receipt_session_cannot_overwrite_terminal_job(client,monkeypatch,terminal):
    """Replay an old ORM session after another transaction changes the job."""
    h=setup_local(client,monkeypatch)
    post(client,h)
    job=lease(client)
    import sonic.local_ai as local
    from starlette.requests import Request
    with session_factory()() as stale:
        cached=stale.get(LocalAIJob,job['id'])
        assert cached.state=='leased'
        with session_factory()() as other:
            current=other.get(LocalAIJob,job['id'])
            current.state=terminal
            current.result_json=json.dumps({'text':'First authenticated receipt'}) if terminal=='done' else ''
            other.commit()
        monkeypatch.setattr(local.auth,'require_device',lambda request:None)
        receipt=local.Receipt(device_id='TRADEVICEPC',job_id=job['id'],
                              success=True,result={'text':'Late conflicting receipt'})
        request=Request({'type':'http','headers':[]})
        if terminal=='expired':
            assert local.device_result(receipt,request,stale)['ignored'] is True
        else:
            from fastapi import HTTPException
            with pytest.raises(HTTPException) as conflict:
                local.device_result(receipt,request,stale)
            assert conflict.value.status_code==409
    with session_factory()() as db:
        saved=db.get(LocalAIJob,job['id'])
        assert saved.state==terminal
        if terminal=='done':
            assert json.loads(saved.result_json)['text']=='First authenticated receipt'


@pytest.mark.parametrize('outcome',['failed','timeout'])
def test_engine_status_tracks_local_queue_and_failure(client,monkeypatch,outcome):
    h=setup_local(client,monkeypatch)
    from sonic.db import EngineRun,BrainUsage
    rid,r=post(client,h)
    run_id=r.json()['engine']['run_id']
    assert r.json()['engine']['status']=='queued'
    with session_factory()() as db:
        assert db.get(EngineRun,run_id).status=='queued'
    if outcome=='failed':
        job=lease(client)
        receipt=client.post('/api/device/local-ai/result',headers=device_headers(),json={
            'device_id':'TRADEVICEPC','job_id':job['id'],'success':False,
            'result':{'error':'synthetic inference failure'}})
        assert receipt.status_code==200,receipt.text
    else:
        with session_factory()() as db:
            turn=db.scalar(select(ChatDelivery))
            turn.created_at=utcnow()-timedelta(seconds=200)
            db.commit()
    final=client.get('/api/chat/delivery/'+rid).json()
    assert final['delivery']['state']=='failed'
    assert final['engine']['status']=='failed'
    assert final['answer_origin']['inference_performed'] is False
    with session_factory()() as db:
        run=db.get(EngineRun,run_id)
        assert run.status=='failed'
        assert {'tool':'local.chat','status':'failed'} in json.loads(run.steps_json)
        assert db.scalar(select(func.count()).select_from(ChatMessage)
                         .where(ChatMessage.role=='assistant'))==0
        assert db.scalar(select(func.count()).select_from(BrainUsage))==0
