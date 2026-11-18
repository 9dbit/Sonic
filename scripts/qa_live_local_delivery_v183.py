"""Opt-in smoke of existing localhost GGUF with a disposable SONIC server.

Does not start/stop a model, touch MT5, read production chat, use owner secrets,
or execute any OS/software action. Requires --allow-local-inference explicitly.
"""
import argparse,hashlib,json,time,sys
from pathlib import Path
import httpx
from qa_server import local_server
from windows_local_ai_v152 import LocalAIBroker,server_ready

if not argparse.ArgumentParser().parse_known_args()[1] == ['--allow-local-inference']:
    raise SystemExit('Pass --allow-local-inference to test the already running model')
if not server_ready():raise SystemExit('Local engine not running; no automatic start')
slots=httpx.get('http://127.0.0.1:11435/slots',timeout=5).json()
if any(row.get('is_processing') for row in slots):raise SystemExit('Model is busy; not adding work')
settings={'SONIC_LOCAL_AI_ENABLED':'true','SONIC_BRAIN_PROVIDER':'local',
          'SONIC_DEVICE_TOKEN_SHA256':hashlib.sha256(b'synthetic-local-delivery-qa').hexdigest()}
with local_server(settings=settings) as (base,owner_token):
    with httpx.Client(base_url=base,timeout=15) as owner,httpx.Client(base_url=base,timeout=15,
            headers={'Authorization':'Bearer synthetic-local-delivery-qa'}) as device:
        login=owner.post('/api/login',json={'token':owner_token});login.raise_for_status()
        csrf=login.json()['csrf']
        device.post('/api/device/heartbeat',json={'device_id':'TRADEVICEPC','hostname':'QA-ISOLATED','platform':'Windows'}).raise_for_status()
        device.post('/api/device/local-ai/heartbeat',json={'device_id':'TRADEVICEPC','state':'running','ram_free_mb':7000}).raise_for_status()
        started=time.perf_counter()
        initial=owner.post('/api/chat',headers={'X-Sonic-CSRF':csrf,'X-Sonic-Async':'1'},
            json={'message':'Berapa 7 ditambah 5? Jawab dengan satu angka saja.','request_id':'real-llama-smoke-183'})
        submit_ms=round((time.perf_counter()-started)*1000)
        assert initial.status_code==202,initial.text
        item=device.post('/api/device/local-ai/next',json={}).json()['job']
        assert item and item['action']=='chat'
        result=LocalAIBroker().chat(item['payload'])
        inference_ms=round((time.perf_counter()-started)*1000)-submit_ms
        assert '12' in result['text'],result['text'][:80]
        receipt=device.post('/api/device/local-ai/result',json={'device_id':'TRADEVICEPC',
            'job_id':item['id'],'success':True,'result':result});receipt.raise_for_status()
        final=owner.get('/api/chat/delivery/real-llama-smoke-183');final.raise_for_status()
        assert final.json()['delivery']['state']=='done'
        assert final.json()['answer_origin']['provider']=='local'
        print(json.dumps({'test':'existing GGUF loopback + disposable SONIC delivery',
             'submit_status':initial.status_code,'submit_ms':submit_ms,'inference_ms':inference_ms,
             'answer':result['text'],'verified_origin':final.json()['answer_origin'],
             'production_credentials_used':False,'PC_actions_executed':False}),flush=True)
print('LIVE_LOCAL_DELIVERY_PASS')
