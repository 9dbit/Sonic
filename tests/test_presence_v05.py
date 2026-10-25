import hashlib
from uuid import uuid4
from datetime import timedelta
from sqlalchemy import select
from sonic.db import session_factory, DeviceTelemetry, Device, OperatorRequest, utcnow
from sonic.device_contract import clean_request,clean_metrics
from sonic.operator import direct_device_command
from tests.test_engine_v04 import login
import pytest


def heartbeat(client):
    return client.post('/api/device/heartbeat',json={
        'device_id':'TRADEVICEPC','hostname':'TRADEVICEPC','platform':'Windows',
        'agent_version':'0.5.0','capabilities':['system.metrics','system.status','shell.run','file.read','mouse.click','keyboard.type','keyboard.key','trade.execute'],
        'metrics':{'ram_total_bytes':16*2**30,'ram_available_bytes':7*2**30,'ram_used_percent':56,'disks':[{'drive':'C:','total_bytes':100,'free_bytes':42}]},
        'gui_targets':[]},headers={'Authorization':'Bearer device-test-token'})


def test_readonly_metrics_live_source_and_auth(client):
    assert client.get('/api/device/metrics').status_code==401
    h=login(client)
    assert client.get('/api/device/metrics').json()['metrics_available'] is False
    assert heartbeat(client).status_code==200
    state=client.get('/api/device/metrics').json()
    assert state['connected'] and state['metrics_available']
    assert state['metrics']['ram_available_bytes']==7*2**30
    assert 'trade.execute' not in state['capabilities']
    result=client.post('/api/chat',json={'message':'SONIC, cek TRADEVICEPC berapa memory yang tersisa'},headers=h)
    assert result.status_code==200 and '7.00 GiB' in result.json()['reply']
    assert result.json()['ui_actions'][0]['type']=='device.metrics'


def test_fail_closed_and_approved_queue(client):
    h=login(client)
    r=client.post('/api/operator/requests',json={'action':'shell.run','payload':{'recipe':'clock'}},headers=h)
    assert r.status_code==409
    heartbeat(client)
    assert client.post('/api/operator/requests',json={'action':'shell.run','payload':{'command':'cmd /c dir'}},headers=h).status_code==422
    assert client.post('/api/operator/requests',json={'action':'shell.run','payload':{'recipe':'powershell'}},headers=h).status_code==422
    assert client.post('/api/operator/requests',json={'action':'keyboard.key','payload':{'window':'123','key':'CTRL+ALT+DEL'}},headers=h).status_code==422
    r=client.post('/api/operator/requests',json={'action':'shell.run','payload':{'recipe':'clock'}},headers=h)
    assert r.status_code==200,r.text
    receipt=r.json()
    assert receipt['state']=='pending'
    device_headers={'Authorization':'Bearer device-test-token'}
    assert client.post('/api/device/operator/next',json={},headers=device_headers).json()['job'] is None
    assert client.post(f"/api/operator/requests/{receipt['id']}/confirm",json={'confirm':True,'digest':receipt['digest']}).status_code==403
    assert client.post(f"/api/operator/requests/{receipt['id']}/confirm",json={'confirm':True,'digest':'0'*64},headers=h).status_code==409
    confirmed=client.post(f"/api/operator/requests/{receipt['id']}/confirm",json={'confirm':True,'digest':receipt['digest']},headers=h)
    assert confirmed.status_code==200
    job=client.post('/api/device/operator/next',json={},headers=device_headers).json()['job']
    assert job['id']==receipt['id']
    assert client.post('/api/device/operator/check',json={'request_id':job['id'],'lease':job['lease']},headers=device_headers).json()['execute']
    assert client.post('/api/device/operator/result',json={'request_id':job['id'],'lease':job['lease'],'success':True,'result':{'output':'2026-01-01T00:00:00Z'}},headers=device_headers).status_code==200
    assert client.post('/api/device/operator/check',json={'request_id':job['id'],'lease':job['lease']},headers=device_headers).json()['execute'] is False
    assert client.get(f"/api/operator/requests/{receipt['id']}").json()['state']=='done'


def test_logout_rejects_queued_operator_actions(client):
    h=login(client);heartbeat(client)
    r=client.post('/api/operator/requests',json={'action':'file.read','payload':{'path':'D:\\Sonic\\work\\notes.txt'}},headers=h).json()
    assert client.post(f"/api/operator/requests/{r['id']}/confirm",json={'confirm':True,'digest':r['digest']},headers=h).status_code==200
    assert client.post('/api/logout',headers=h).status_code==200
    job=client.post('/api/device/operator/next',json={},headers={'Authorization':'Bearer device-test-token'}).json()['job']
    assert job is None


def test_contract_guards():
    for action,payload in [
        ('file.read',{'path':'\\\\server\\share'}),
        ('shell.run',{'recipe':'taskkill'}),
        ('keyboard.type',{'window':'1','text':'a\nb'}),
        ('mouse.click',{'window':'1','x':True,'y':1}),
        ('keyboard.key',{'window':'1','key':'WIN+R'})]:
        with pytest.raises(ValueError):clean_request(action,payload)
    assert clean_request('keyboard.key',{'window':'123','key':'enter'})['key']=='ENTER'
    assert clean_metrics({'ram_used_percent':200,'ram_total_bytes':100,'ram_available_bytes':110,'disks':[]}).get('ram_available_bytes') is None


def test_reference_transcript_requires_auth(client):
    assert client.post('/api/voice/reference/transcribe',json={}).status_code==401
    h=login(client)
    assert client.post('/api/voice/reference/transcribe',json={'mime_type':'audio/mpeg','audio_base64':'AAAA'*10,'consent':True},headers=h).status_code==422
