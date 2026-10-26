"""SONIC V0.8.6 Integration particle inventory and authorization gates."""
from datetime import timedelta

from sonic.db import session_factory, Device, DeviceTelemetry, utcnow
from sonic.integrations import integration_snapshot, CATALOG
from tests.test_engine_v04 import login
from tests.test_voice_command_v084 import connect, DEVICE

def test_integrations_endpoints_require_real_owner_login(client):
    assert client.get('/api/integrations').status_code==401
    assert client.get('/api/knowledge/graph').status_code==401
    h=login(client)
    r=client.get('/api/integrations')
    assert r.status_code==200,r.text
    assert r.json()['schema']=='sonic.integrations.v1'
    assert client.post('/api/integrations',json={},headers=h).status_code==405


def test_exactly_one_integration_particle_and_its_registered_adapter_list(client):
    login(client)
    graph=client.get('/api/knowledge/graph')
    assert graph.status_code==200,graph.text
    payload=graph.json()
    nodes=[n for n in payload['nodes'] if n['id']=='integration:hub']
    assert len(nodes)==1
    hub=nodes[0]
    assert hub['category']=='integration'
    assert hub['label']=='Integration'
    assert hub['source']=='sonic.integration_registry'
    assert hub['integration_counts']['total']==4
    assert hub['integration_counts']['connected']==0
    assert {item['id'] for item in hub['adapters']}=={
        'windows-native','rdc','google-drive','notepad'}
    assert payload['counts']['categories']['integration']==1
    assert any(e['source']=='system:sonic' and
               e['target']=='integration:hub' for e in payload['edges'])
    assert not any(n['id'].startswith('integration:rdc:') for n in payload['nodes'])


def test_only_live_sonic_device_advertises_connected_executor(client):
    login(client)
    connect(client)
    result=client.get('/api/integrations')
    assert result.status_code==200,result.text
    data=result.json()
    assert data['counts']['total']==4
    assert data['counts']['connected']==1
    by_id={a['id']:a for a in data['adapters']}
    native=by_id['windows-native']
    assert native['state']=='online' and native['connected'] is True
    assert native['verification']=='live_device_heartbeat_and_capabilities'
    assert 'desktop.mkdir' in native['current_capabilities']
    assert native['last_verified_at'] is not None
    assert native['recent_completed_jobs']==0
    for key in ('rdc','google-drive','notepad'):
        assert by_id[key]['connected'] is False
        assert by_id[key]['verification']=='none'
        assert by_id[key]['current_capabilities']==[]
    assert by_id['rdc']['state']=='not_connected'
    assert by_id['google-drive']['state']=='not_connected'
    assert by_id['notepad']['state']=='not_ready'
    graph=client.get('/api/knowledge/graph').json()
    hub=next(n for n in graph['nodes'] if n['id']=='integration:hub')
    assert hub['integration_counts']['connected']==1
    assert any(e['source']=='integration:hub' and
               e['target']=='device:TRADEVICEPC' for e in graph['edges'])


def test_stale_heartbeat_never_displays_a_connected_executor(client):
    login(client);connect(client)
    with session_factory()() as db:
        device=db.get(Device,'TRADEVICEPC')
        device.last_seen=utcnow()-timedelta(minutes=4)
        db.commit()
    native=client.get('/api/integrations').json()['adapters'][0]
    assert native['state']=='offline'
    assert native['connected'] is False
    assert native['current_capabilities']==[]


def test_online_companion_without_advertised_actions_is_not_ready(client):
    login(client);connect(client)
    data={
      'device_id':'TRADEVICEPC','hostname':'TRADEVICEPC','platform':'Windows',
      'agent_version':'0.8.3','capabilities':[],
      'metrics':{'ram_total_bytes':16*2**30,'ram_available_bytes':8*2**30},
      'gui_targets':[]
    }
    r=client.post('/api/device/heartbeat',json=data,headers=DEVICE)
    assert r.status_code==200,r.text
    native=client.get('/api/integrations').json()['adapters'][0]
    assert native['state']=='not_ready'
    assert native['connected'] is False
    assert native['verification']=='none'


def test_private_registry_does_not_leak_secrets_or_claim_chatgpt_oauth(client):
    login(client);connect(client)
    body=client.get('/api/integrations').text
    assert 'owner-test-token' not in body
    assert 'device-test-token' not in body
    assert 'z'*64 not in body
    assert '"connected":true' in body
    assert '"id":"rdc"' in body and '"id":"google-drive"' in body
    assert '"not_connected"' in body
    assert 'ChatGPT' in body


def test_open_integration_from_chat_uses_real_graph_node(client):
    h=login(client)
    r=client.post('/api/chat',json={'message':'SONIC, buka Integration'},headers=h)
    assert r.status_code==200,r.text
    data=r.json()
    assert data['engine']['route']=='graph_command'
    assert data['ui_actions']==[{'type':'graph.focus','node_id':'integration:hub'}]
    assert not data['operator_jobs']


def test_realtime_context_sees_state_but_cannot_execute_integrations():
    from sonic.voice import session_config
    snapshot={'device_id':'TRADEVICEPC','connected':True,
              'integration_status':[
                  {'id':'windows-native','connected':True,'state':'online'},
                  {'id':'rdc','connected':False,'state':'not_connected'}]}
    config=session_config(device_context=snapshot)
    text=config['instructions']
    assert 'integration_adapters' in text
    assert '"rdc"' in text
    assert '"not_connected"' in text
    assert 'do NOT grant SONIC access' in text
    assert not any(tool.get('name') in ('rdc.execute','google_drive.write','notepad.type')
                   for tool in config['tools'])
