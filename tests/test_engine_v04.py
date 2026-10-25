import json
import pytest
from sonic.graph_commands import direct_graph_command, run_graph_tool
from sonic.db import session_factory
from sonic.api import VERSION


def login(client):
    r=client.post('/api/login',json={'token':'owner-test-token'})
    assert r.status_code == 200
    return {'X-Sonic-CSRF':r.json()['csrf']}


def note(client,h,text='Saya suka bakso Bandung'):
    r=client.post('/api/memories',json={'text':text},headers=h)
    assert r.status_code==200
    return r.json()['id']


@pytest.mark.parametrize('text,name',[
    ('SONIC, tampilkan memory tentang bakso','graph_search'),
    ('Tolong buka memory #25','graph_focus'),
    ('Perlihatkan hubungannya depth 2','graph_neighbors'),
    ('Kembali ke seluruh brain','graph_reset'),
    ('show notes about SONIC','graph_search'),
    ('open memory 8','graph_focus'),
])
def test_narrow_navigation_intent(text,name):
    assert direct_graph_command(text,'memory:1')[0]==name


@pytest.mark.parametrize('text',[
    'Jangan buka memory #1','Apa itu knowledge graph?',
    'Contoh perintah: tampilkan memory tentang bakso',
    '"tampilkan memory tentang bakso"','Hapus semua memory',
])
def test_no_unrequested_navigation(text):
    assert direct_graph_command(text) is None


def test_real_graph_chat_actions_and_audit(client):
    h=login(client);mid=note(client,h)
    r=client.post('/api/chat',json={'message':'SONIC, tampilkan memory tentang bakso'},headers=h)
    assert r.status_code==200, r.text
    body=r.json()
    assert body['engine']['route']=='graph_command'
    assert f'memory:{mid}' in body['ui_actions'][0]['node_ids']
    r=client.post('/api/chat',json={'message':f'Buka memory #{mid}'},headers=h)
    assert r.json()['ui_actions']==[{'type':'graph.focus','node_id':f'memory:{mid}'}]
    r=client.post('/api/chat',json={'message':'Perlihatkan hubungannya depth 2','selected_node_id':f'memory:{mid}'},headers=h)
    assert r.json()['ui_actions'][0]['depth']==2
    reset=client.post('/api/chat',json={'message':'Kembali ke seluruh brain'},headers=h)
    assert reset.json()['ui_actions']==[{'type':'graph.reset'}]
    runs=client.get('/api/engine/runs').json()['runs']
    assert len(runs)==4
    assert 'bakso' not in json.dumps(runs)
    assert client.get('/api/memories').json()['total']==1


def test_invalid_or_deleted_node_never_applied(client):
    h=login(client);mid=note(client,h)
    client.delete(f'/api/memories/{mid}',headers=h)
    r=client.post('/api/chat',json={'message':f'Buka memory #{mid}'},headers=h)
    assert r.status_code==200 and not r.json()['ui_actions']
    with session_factory()() as db:
        assert run_graph_tool(db,'graph_focus',{'node_id':'missing'})['error']=='GRAPH_NODE_NOT_FOUND'
        assert run_graph_tool(db,'graph_focus',{'node_id':'system:sonic','eval':'alert(1)'})['error']=='INVALID_TOOL_ARGUMENTS'
        assert run_graph_tool(db,'graph_neighbors',{'node_id':'system:sonic','depth':99})['error']=='INVALID_TOOL_ARGUMENTS'


def test_engine_auth_and_csrf(client):
    assert client.get('/api/engine/runs').status_code==401
    login(client)
    assert client.post('/api/chat',json={'message':'Kembali ke seluruh brain'}).status_code==403


def test_failed_run_no_fake_success(client):
    h=login(client)
    assert client.post('/api/chat',json={'message':'Halo SONIC'},headers=h).status_code==503
    r=client.get('/api/engine/runs').json()['runs'][0]
    assert r['status']=='failed' and r['route']=='model_conversation'


def test_version_and_lifespan(client):
    assert client.get('/api/health').json()['version']==VERSION
    login(client)
    assert client.get('/api/setup/status').json()['version']==VERSION
