"""Disposable PostgreSQL concurrency proof; never uses the app DATABASE_URL."""
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import nullcontext
from threading import Barrier
from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import create_engine, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session
from starlette.requests import Request

from sonic import auth
from sonic.chat_delivery import ChatDelivery
from sonic.db import Base, BrainUsage, ChatMessage, EngineRun, LocalAIJob
from sonic.local_ai import Receipt, device_result


@pytest.fixture
def delivery_pg(monkeypatch):
    raw=os.environ.get('SONIC_DELIVERY_TEST_POSTGRES_URL','')
    if not raw:
        pytest.skip('Dedicated disposable delivery PostgreSQL URL not configured')
    url=make_url(raw)
    if (url.drivername!='postgresql+psycopg' or
        url.host not in ('localhost','127.0.0.1') or url.database!='sonic_delivery_ci'):
        raise RuntimeError('Only explicit local sonic_delivery_ci PostgreSQL is permitted')
    schema='delivery_ci_'+uuid4().hex
    admin=create_engine(raw)
    engine=None
    try:
        with admin.begin() as connection:
            connection.execute(text('CREATE SCHEMA "'+schema+'"'))
        engine=create_engine(raw,connect_args={'options':'-csearch_path='+schema},pool_pre_ping=True)
        Base.metadata.create_all(engine)
        monkeypatch.setenv('SONIC_DEVICE_ID','TRADEVICEPC')
        monkeypatch.setenv('SONIC_DEVICE_TOKEN_SHA256',auth.sha256('delivery-ci-device'))
        yield engine
    finally:
        if engine is not None:
            engine.dispose()
        with admin.begin() as connection:
            connection.execute(text('DROP SCHEMA IF EXISTS "'+schema+'" CASCADE'))
        admin.dispose()


def test_postgres_concurrent_settlement_retains_one_answer_and_usage(delivery_pg,monkeypatch):
    import sonic.chat_delivery as delivery
    import sonic.providers as providers
    # Cross-worker correctness must come from PostgreSQL, not a process RLock.
    monkeypatch.setattr(delivery,'_lock',nullcontext())
    original_usage=providers.record_usage
    def delayed_usage(*args,**kwargs):
        time.sleep(.05)  # Keep the winning transaction open while peers contend.
        return original_usage(*args,**kwargs)
    monkeypatch.setattr(providers,'record_usage',delayed_usage)
    run_id,job_id,turn_id=(str(uuid4()) for _ in range(3))
    envelope={'reply':'pending','engine':{'run_id':run_id,'status':'queued','route':'model_conversation'}}
    with Session(delivery_pg) as db:
        db.add(EngineRun(id=run_id,channel='chat',route='model_conversation',status='queued',
                         steps_json='[]',duration_ms=0))
        db.add(LocalAIJob(id=job_id,device_id='TRADEVICEPC',owner_sid='a'*64,
                         action='chat',state='done',payload_json='',
                         result_json=json.dumps({'text':'One retained answer',
                                                 'usage':{'input_tokens':8,'output_tokens':4}})))
        db.add(ChatDelivery(id=turn_id,owner_sid='a'*64,fingerprint='b'*64,state='queued',
                            local_job_id=job_id,response_json=json.dumps(envelope)))
        db.commit()
    barrier=Barrier(8)
    def poll(_):
        with Session(delivery_pg,expire_on_commit=False) as db:
            barrier.wait(timeout=10)
            return delivery.settle(db,turn_id).state
    with ThreadPoolExecutor(max_workers=8) as executor:
        assert list(executor.map(poll,range(8)))==['done']*8
    with Session(delivery_pg) as db:
        assert db.scalar(select(func.count()).select_from(ChatMessage))==1
        assert db.scalar(select(func.count()).select_from(BrainUsage))==1
        assert db.get(EngineRun,run_id).status=='completed'
        assert json.loads(db.get(ChatDelivery,turn_id).response_json)['reply']=='One retained answer'


def test_postgres_conflicting_receipts_have_one_terminal_winner(delivery_pg):
    job_id=str(uuid4())
    with Session(delivery_pg) as db:
        db.add(LocalAIJob(id=job_id,device_id='TRADEVICEPC',owner_sid='a'*64,
                         action='chat',state='leased',payload_json='',result_json=''))
        db.commit()
    barrier=Barrier(2)
    def receipt(index):
        answer='Authenticated receipt '+str(index)
        request=Request({'type':'http','headers':[(b'authorization',b'Bearer delivery-ci-device')]})
        body=Receipt(device_id='TRADEVICEPC',job_id=job_id,success=True,result={'text':answer})
        with Session(delivery_pg,expire_on_commit=False) as db:
            stale=db.get(LocalAIJob,job_id)
            assert stale.state=='leased'
            barrier.wait(timeout=10)
            try:
                result=device_result(body,request,db)
                return (200,answer,result)
            except HTTPException as exc:
                return (exc.status_code,answer,{})
    with ThreadPoolExecutor(max_workers=2) as executor:
        results=list(executor.map(receipt,range(2)))
    assert sorted(row[0] for row in results)==[200,409],results
    winner=next(row[1] for row in results if row[0]==200)
    with Session(delivery_pg) as db:
        job=db.get(LocalAIJob,job_id)
        assert job.state=='done'
        assert json.loads(job.result_json)['text']==winner
        duplicate=device_result(Receipt(device_id='TRADEVICEPC',job_id=job_id,success=True,
            result={'text':winner}),Request({'type':'http','headers':[
                (b'authorization',b'Bearer delivery-ci-device')]}),db)
        assert duplicate['duplicate'] is True
