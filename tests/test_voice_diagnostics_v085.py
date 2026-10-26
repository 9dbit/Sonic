"""Test private aggregated diagnostics cannot reveal chat text or device credentials."""
from tests.test_engine_v04 import login
from tests.test_voice_v04 import provider,start
from tests.test_voice_command_v084 import connect,dispatch,next_job,DEVICE

def test_owner_history_diagnostics_available_only_to_authenticated_device(client,provider):
    h=login(client);connect(client);sid=start(client,h)
    p=dispatch(client,h,sid,'trace_item','Buatkan di desktop dengan nama foldernya Today.')
    assert p.status_code==200,p.text
    assert p.json()['operator_jobs'][0]['action']=='desktop.mkdir'
    assert client.post('/api/device/diagnostics/recent').status_code==401
    result=client.post('/api/device/diagnostics/recent',headers=DEVICE)
    assert result.status_code==200,result.text
    data=result.json()
    assert data['voice_action_dispatches_recent']>=1
    assert any('desktop.mkdir' in x['actions_queued'] for x in data['voice_dispatch_recent'])
    assert data['chat_history_last_150']['user_folder_mentions']>=1
    assert data['operator_last_100']['actions']['desktop.mkdir']>=1
    raw=result.text
    assert 'Buatkan di desktop dengan nama foldernya Today' not in raw
    assert 'synthetic-test-key-not-for-network' not in raw
    assert 'trace_item' not in raw
