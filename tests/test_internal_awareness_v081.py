"""Regression for SONIC device self-awareness and stale prompt repair."""
from tests.test_engine_v04 import login
from tests.test_presence_v05 import heartbeat
from sonic.operator import direct_capability_question, capability_reply
from sonic.brain import SYSTEM, TOOLS
from sonic.engine import execute_chat
from sonic.db import session_factory
import asyncio

def test_internal_capability_intents():
    for phrase in ['Apa yang kita bisa lakukan terhadap tradevicepc?',
                   'SONIC, kemampuan PC kita apa?',
                   'What can SONIC do on tradevicepc?']:
        assert direct_capability_question(phrase),phrase
    for phrase in ['tolong simpan memory saya','berapa RAM PC','halo SONIC','Get-Date']:
        assert not direct_capability_question(phrase),phrase

def test_brain_knows_own_pc():
    assert 'V0.8' in SYSTEM
    assert 'You have no shell access' not in SYSTEM
    assert 'pc_capabilities' in {x['name'] for x in TOOLS}
    assert 'high-impact PC actions require approval' in SYSTEM

def test_chat_capability_reply_uses_actual_heartbeat(client):
    h=login(client)
    r=client.post('/api/chat',headers=h,json={'message':'Apa yang kita bisa lakukan terhadap tradevicepc?'})
    assert r.status_code==200,r.text
    assert r.json()['engine']['route']=='device_capabilities'
    assert 'offline' in r.json()['reply']
    assert heartbeat(client).status_code==200
    r=client.post('/api/chat',headers=h,json={'message':'Apa yang kita bisa lakukan terhadap tradevicepc?'})
    assert r.status_code==200,r.text
    assert 'TRADEVICEPC' in r.json()['reply']
    assert 'online' in r.json()['reply']
    assert 'persetujuan' in r.json()['reply']
    assert r.json()['engine']['route']=='device_capabilities'
