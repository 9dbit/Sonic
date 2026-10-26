"""SONIC V0.8.2 chat-first PC commands: scoped autonomy, in-chat approval and receipts."""
import pytest
from tests.test_engine_v04 import login
from sonic.chat_actions import classify,confirmation_intent
from sonic.device_contract import clean_workspace_folder
from sonic.db import session_factory, OperatorRequest,ChatOperation,ChatMessage
from sqlalchemy import select

DEVICE={'Authorization':'Bearer device-test-token'}


def connect(client):
    r=client.post('/api/device/heartbeat',headers=DEVICE,json={
        'device_id':'TRADEVICEPC','hostname':'TRADEVICEPC','platform':'Windows',
        'agent_version':'0.8.2',
        'capabilities':['system.status','system.metrics','file.mkdir','file.list',
                        'file.read','process.list','window.list','powershell.exec',
                        'process.terminate'],
        'metrics':{'ram_total_bytes':16000000,'ram_available_bytes':8000000},
        'gui_targets':[]
    })
    assert r.status_code==200,r.text


def chat(client,h,message):
    return client.post('/api/chat',headers=h,json={'message':message})


def next_job(client):
    r=client.post('/api/device/operator/next',headers=DEVICE,json={})
    assert r.status_code==200,r.text
    return r.json()['job']


def finish(client,job,result,success=True):
    r=client.post('/api/device/operator/result',headers=DEVICE,json={
        'request_id':job['id'],'lease':job['lease'],
        'success':success,'result':result
    })
    assert r.status_code==200,r.text
    return r.json()


def test_folder_creation_chat_no_approval_and_result_persists(client):
    h=login(client);connect(client)
    r=chat(client,h,'Sonic, buat folder QA Sonic di TRADEVICEPC')
    assert r.status_code==200,r.text
    body=r.json()
    assert body['engine']['route']=='chat_pc_action'
    assert body['operator_jobs'][0]['action']=='file.mkdir'
    assert body['operator_proposals']==[]
    rid=body['operator_jobs'][0]['id']
    with session_factory()() as db:
        row=db.get(OperatorRequest,rid)
        assert row.state=='queued'
        assert db.get(ChatOperation,rid) is not None
    job=next_job(client)
    assert job['action']=='file.mkdir' and job['payload']=={'path':'QA Sonic'}
    assert finish(client,job,{'created':True,'exists':True,'path':r'D:\Sonic\work\QA Sonic',
                             'relative_path':'QA Sonic'})['state']=='done'
    history=client.get('/api/history').json()['messages']
    assert any('Folder berhasil dibuat' in m['content'] and 'QA Sonic' in m['content'] for m in history)
    # A duplicate device report is idempotent, never writes two chat receipts.
    finish(client,job,{'created':True,'exists':True,'path':r'D:\Sonic\work\QA Sonic'})
    history=client.get('/api/history').json()['messages']
    assert sum('Folder berhasil dibuat' in m['content'] for m in history)==1


def test_sensitive_powershell_approved_from_same_chat(client,monkeypatch):
    monkeypatch.setenv('SONIC_ENABLE_POWERSHELL_EXEC','true')
    h=login(client);connect(client)
    r=chat(client,h,'PowerShell: Get-Date')
    assert r.status_code==200,r.text
    assert 'Balas SETUJU' in r.json()['reply']
    assert len(r.json()['operator_proposals'])==1
    assert next_job(client) is None
    req_id=r.json()['operator_proposals'][0]['id']
    unauthorized=client.post('/api/chat',json={'message':'setuju'})
    assert unauthorized.status_code==403
    yes=chat(client,h,'setuju')
    assert yes.status_code==200,yes.text
    assert yes.json()['operator_jobs'][0]['id']==req_id
    job=next_job(client)
    assert job and job['action']=='powershell.exec'
    finish(client,job,{'exit_code':0,'events_sent':0})
    history=client.get('/api/history').json()['messages']
    assert any('PowerShell selesai' in m['content'] for m in history)


def test_sensitive_chat_can_cancel_without_page_change(client,monkeypatch):
    monkeypatch.setenv('SONIC_ENABLE_POWERSHELL_EXEC','true')
    h=login(client);connect(client)
    r=chat(client,h,'jalankan powershell: Get-Service')
    assert r.json()['operator_proposals']
    canceled=chat(client,h,'batal')
    assert 'dibatalkan' in canceled.json()['reply']
    assert next_job(client) is None
    assert 'Tidak ada' in chat(client,h,'setuju').json()['reply']


def test_safe_read_actions_autoqueue(client):
    h=login(client);connect(client)
    requests=[('lihat folder QA', 'file.list',{'path':'QA'}),
              ('baca file data.txt','file.read',{'path':'data.txt'}),
              ('cek proses','process.list',{}),
              ('lihat windows','window.list',{})]
    for prompt,action,payload in requests:
        res=chat(client,h,prompt)
        assert res.status_code==200,res.text
        assert res.json()['operator_jobs'][0]['action']==action
        job=next_job(client)
        assert job['action']==action and job['payload']==payload
        finish(client,job,{'items':[],'processes':[],'windows':[],'directory':'D:/Sonic/work',
                           'path':'D:/Sonic/work/data.txt','content':'sample'})


@pytest.mark.parametrize('path',[
    '../escape',r'C:\Windows\System32',r'\\server\share',
    'folder/../../escape','secrets','CON',r'..\Windows',
    '.git/private', 'folder//bad','folder.','folder/$env:APPDATA',
    'folder/with?','foo:bar',
])
def test_folder_path_rejects_escape(path):
    with pytest.raises(ValueError):
        clean_workspace_folder(path)


@pytest.mark.parametrize('prompt',[
    'jangan buat folder X',
    'contoh buat folder X',
    'bagaimana cara buat folder X',
    'apakah sonic bisa buat folder X?',
    'bisakah SONIC buat folder baru?',
    'kalau buat folder X nanti apa terjadi?',
    'hapus semua folder',
])
def test_no_automatic_action_without_owner_intent(prompt):
    assert classify(prompt) is None


def test_read_only_no_autoapproval_for_powerful_commands(client,monkeypatch):
    monkeypatch.setenv('SONIC_ENABLE_POWERSHELL_EXEC','true')
    h=login(client);connect(client)
    cmd=chat(client,h,'hentikan proses notepad.exe PID 1820')
    assert cmd.status_code==200,cmd.text
    assert cmd.json()['operator_proposals'][0]['action']=='process.terminate'
    assert next_job(client) is None
    assert chat(client,h,'setuju').json()['operator_jobs']
    job=next_job(client)
    assert job['action']=='process.terminate'
    finish(client,job,{'pid':1820,'name':'notepad.exe','terminated':True})


def test_consent_bound_to_owner_session(client,monkeypatch):
    monkeypatch.setenv('SONIC_ENABLE_POWERSHELL_EXEC','true')
    h=login(client);connect(client)
    assert chat(client,h,'PowerShell: Get-Date').json()['operator_proposals']
    assert client.post('/api/logout',headers=h).status_code==200
    h2=login(client)
    r=chat(client,h2,'setuju')
    assert 'Tidak ada' in r.json()['reply']
    assert next_job(client) is None
