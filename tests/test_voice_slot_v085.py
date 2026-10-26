"""Regression for real two-turn voice intent completion without invented actions."""
from tests.test_voice_v04 import provider,start
from tests.test_engine_v04 import login
from tests.test_voice_command_v084 import connect,dispatch,next_job,DEVICE
from sonic.db import VoicePendingFolder,session_factory

def test_voice_name_slot_creates_a_single_real_desktop_job(client,provider):
    h=login(client);connect(client);sid=start(client,h)
    first=dispatch(client,h,sid,'item_missing_name','Tolong buatkan folder di Desktop.')
    assert first.status_code==200,first.text
    assert first.json()['route']=='voice_folder_slot'
    assert first.json()['operator_jobs']==[]
    assert next_job(client) is None
    with session_factory()() as db:
        pending=db.get(VoicePendingFolder,sid)
        assert pending and pending.scope=='desktop'
    second=dispatch(client,h,sid,'item_name_only','namanya Today.')
    assert second.status_code==200,second.text
    assert second.json()['route']=='chat_pc_action'
    assert second.json()['operator_jobs'][0]['action']=='desktop.mkdir'
    assert dispatch(client,h,sid,'item_name_only','namanya Today.').json()==second.json()
    job=next_job(client)
    assert job['action']=='desktop.mkdir' and job['payload']=={'name':'Today'}
    assert next_job(client) is None
    with session_factory()() as db:
        assert db.get(VoicePendingFolder,sid) is None


def test_voice_location_slot_retains_folder_name_until_location_is_clear(client,provider):
    h=login(client);connect(client);sid=start(client,h)
    first=dispatch(client,h,sid,'item_where','Buat folder Today')
    assert first.status_code==200,first.text
    assert first.json()['route']=='voice_folder_slot'
    assert 'Desktop atau workspace' in first.json()['reply']
    assert next_job(client) is None
    last=dispatch(client,h,sid,'item_desktop','di desktop')
    assert last.status_code==200,last.text
    assert last.json()['operator_jobs'][0]['action']=='desktop.mkdir'
    job=next_job(client)
    assert job['payload']=={'name':'Today'}


def test_voice_workspace_location_slot_is_distinct_from_desktop(client,provider):
    h=login(client);connect(client);sid=start(client,h)
    assert dispatch(client,h,sid,'which_dir','Buat folder Today').json()['route']=='voice_folder_slot'
    result=dispatch(client,h,sid,'set_workspace','workspace')
    assert result.status_code==200
    assert result.json()['operator_jobs'][0]['action']=='file.mkdir'
    job=next_job(client)
    assert job['payload']=={'path':'Today'}


def test_vague_references_never_create_a_folder(client,provider):
    h=login(client);connect(client);sid=start(client,h)
    r=dispatch(client,h,sid,'vague','Buatkan di desktop dong, folder yang kemarin itu.')
    assert r.status_code==200,r.text
    assert r.json()['route']=='voice_pc_clarification'
    assert r.json()['operator_jobs']==[]
    assert next_job(client) is None


def test_cancel_slot_does_not_cancel_unrelated_or_create(client,provider):
    h=login(client);connect(client);sid=start(client,h)
    dispatch(client,h,sid,'prepare','Buatkan folder di Desktop')
    cancel=dispatch(client,h,sid,'cancel','Batal')
    assert cancel.status_code==200
    assert cancel.json()['route']=='voice_folder_cancelled'
    assert next_job(client) is None
    with session_factory()() as db:
        assert db.get(VoicePendingFolder,sid) is None


def test_unsafe_folder_name_does_not_escape_slot(client,provider):
    h=login(client);connect(client);sid=start(client,h)
    dispatch(client,h,sid,'prepare','Buat folder di desktop')
    unsafe=dispatch(client,h,sid,'bad_name','../Windows')
    assert unsafe.status_code==200
    assert unsafe.json()['operator_jobs']==[]
    assert next_job(client) is None
