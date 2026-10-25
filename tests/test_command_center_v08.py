"""V0.8 cloud broker isolation, CSRF, lease, output and cancellation regressions."""
import os
import pytest
from sonic.device_contract import clean_request, validate_powershell_command
from tests.test_engine_v04 import login

DEVICE_HEADERS={'Authorization':'Bearer device-test-token'}


def heartbeat(client,capabilities=None):
    return client.post('/api/device/heartbeat',headers=DEVICE_HEADERS,json={
        'device_id':'TRADEVICEPC','hostname':'TRADEVICEPC','platform':'Windows',
        'agent_version':'0.8.0',
        'capabilities':capabilities if capabilities is not None else [
            'system.metrics','system.status','powershell.exec','process.terminate'],
        'metrics':{'cpu_usage_percent':35.5,'ram_total_bytes':16*2**30,
                   'ram_available_bytes':7*2**30,'ram_used_percent':56.25,
                   'processes':[{'pid':501,'name':'notepad.exe','ram_bytes':12000000}],
                   'gpus':[{'name':'Test GPU'}]},
        'gui_targets':[]
    })


def request_exec(client,h,cmd='Get-Date',timeout=15):
    return client.post('/api/operator/requests',headers=h,json={
        'action':'powershell.exec','payload':{
            'command':cmd,'timeout_seconds':timeout
        }
    })


def approve(client,h,receipt):
    return client.post('/api/operator/requests/'+receipt['id']+'/confirm',
                       headers=h,json={'confirm':True,'digest':receipt['digest']})


def next_job(client):
    return client.post('/api/device/operator/next',headers=DEVICE_HEADERS,json={}).json()['job']


def test_gate_needs_host_feature_and_live_device(client,monkeypatch):
    h=login(client)
    assert heartbeat(client).status_code==200
    monkeypatch.delenv('SONIC_ENABLE_POWERSHELL_EXEC',raising=False)
    assert request_exec(client,h).status_code==403
    monkeypatch.setenv('SONIC_ENABLE_POWERSHELL_EXEC','true')
    heartbeat(client,['system.metrics'])
    assert request_exec(client,h).status_code==409
    heartbeat(client)
    result=request_exec(client,h)
    assert result.status_code==200,result.text
    assert result.json()['state']=='pending'
    assert next_job(client) is None
    assert client.get('/api/operator/capabilities').json()['powershell_enabled'] is True


def test_owner_approval_and_stdout_stream_lease(client,monkeypatch):
    monkeypatch.setenv('SONIC_ENABLE_POWERSHELL_EXEC','true')
    h=login(client);heartbeat(client)
    proposal=request_exec(client,h,'Get-Date; Get-Process -Name notepad',20)
    assert proposal.status_code==200,proposal.text
    receipt=proposal.json()
    assert client.post('/api/operator/requests/'+receipt['id']+'/confirm',json={
        'confirm':True,'digest':receipt['digest']}).status_code==403
    assert approve(client,h,{**receipt,'digest':'0'*64}).status_code==409
    assert approve(client,h,receipt).status_code==200
    job=next_job(client)
    assert job and job['id']==receipt['id'] and job['action']=='powershell.exec'
    assert job['payload']['command']=='Get-Date; Get-Process -Name notepad'
    assert client.post('/api/device/operator/check',headers=DEVICE_HEADERS,json={
        'request_id':job['id'],'lease':job['lease']}).json()['execute'] is True
    base={'request_id':job['id'],'lease':job['lease']}
    assert client.post('/api/device/operator/stream',json={
        **base,'sequence':1,'channel':'stdout','text':'line one\n'}).status_code==401
    first={**base,'sequence':1,'channel':'stdout','text':'line one\n'}
    assert client.post('/api/device/operator/stream',headers=DEVICE_HEADERS,json=first).status_code==200
    duplicate=client.post('/api/device/operator/stream',headers=DEVICE_HEADERS,json=first)
    assert duplicate.status_code==200 and duplicate.json()['duplicate'] is True
    assert client.post('/api/device/operator/stream',headers=DEVICE_HEADERS,json={
        **first,'text':'different'}).status_code==409
    assert client.post('/api/device/operator/stream',headers=DEVICE_HEADERS,json={
        **base,'sequence':3,'channel':'stderr','text':'out of order'}).status_code==409
    assert client.post('/api/device/operator/stream',headers=DEVICE_HEADERS,json={
        **base,'sequence':2,'channel':'stderr','text':'warning\n'}).status_code==200
    assert client.get('/api/operator/requests/'+job['id']+'/stream').status_code==200
    chunks=client.get('/api/operator/requests/'+job['id']+'/stream?after=0').json()
    assert [x['text'] for x in chunks['events']]==['line one\n','warning\n']
    assert client.get('/api/operator/requests/'+job['id']+'/stream?after=1').json()['next_sequence']==2
    assert client.post('/api/device/operator/result',headers=DEVICE_HEADERS,json={
        **base,'success':True,'result':{'exit_code':0,'events_sent':2}}).status_code==200
    assert client.get('/api/operator/requests/'+job['id']).json()['state']=='done'
    assert client.post('/api/device/operator/stream',headers=DEVICE_HEADERS,json={
        **base,'sequence':3,'channel':'stdout','text':'late'}).status_code==409


def test_cancel_inflight_and_owner_history(client,monkeypatch):
    monkeypatch.setenv('SONIC_ENABLE_POWERSHELL_EXEC','true')
    h=login(client);heartbeat(client)
    receipt=request_exec(client,h,'Start-Sleep -Seconds 5',10).json()
    approve(client,h,receipt)
    job=next_job(client);base={'request_id':job['id'],'lease':job['lease']}
    assert client.post('/api/device/operator/check',json=base,headers=DEVICE_HEADERS).json()['execute']
    cancel=client.delete('/api/operator/requests/'+receipt['id'],headers=h)
    assert cancel.status_code==200 and cancel.json()['state']=='cancelled'
    assert client.post('/api/device/operator/check',json=base,headers=DEVICE_HEADERS).json()['execute'] is False
    assert client.post('/api/device/operator/stream',json={
        **base,'sequence':1,'channel':'stdout','text':'late'},
        headers=DEVICE_HEADERS).status_code==409
    assert client.post('/api/device/operator/result',json={
        **base,'success':False,'result':{'cancelled':True}},
        headers=DEVICE_HEADERS).status_code==200
    assert client.get('/api/operator/history').status_code==200
    history=client.get('/api/operator/history?limit=3').json()['requests']
    assert history[0]['state']=='cancelled'
    assert 'created_at' in history[0]
    assert client.post('/api/logout',headers=h).status_code==200
    h2=login(client)
    assert client.get('/api/operator/history').json()['requests'][0]['id']==receipt['id']
    assert client.get('/api/operator/requests/'+receipt['id'],headers=h2).status_code==404


@pytest.mark.parametrize('command,seconds',[
    ('',10),
    ('x'*1201,10),
    ('Get-Process',0),
    ('Get-Date',61),
    ('Get-Date',True),
    ('Get-Date\x00',10),
    ('Get-Date\n'*15,10),
    ('Get-Item Env:SONIC_DEVICE_TOKEN',10),
    ('Start-Process powershell -Verb RunAs',10),
    ('powershell -EncodedCommand AAAB',10),
])
def test_untrusted_powershell_rejected(command,seconds):
    with pytest.raises(ValueError):
        clean_request('powershell.exec',{'command':command,'timeout_seconds':seconds})


def test_approved_process_guard_and_unknown_args():
    assert clean_request('process.terminate',{'pid':501,'expected_name':'notepad.exe'})=={
        'pid':501,'expected_name':'notepad.exe'}
    for payload in [
        {'pid':True,'expected_name':'notepad.exe'},
        {'pid':0,'expected_name':'notepad.exe'},
        {'pid':999,'expected_name':'notepad.exe','force':True},
        {'pid':101,'expected_name':'bad; command'},
    ]:
        with pytest.raises(ValueError):
            clean_request('process.terminate',payload)
    assert validate_powershell_command('Get-Date;Get-Process',30)=='Get-Date;Get-Process'
