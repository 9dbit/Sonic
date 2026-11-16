"""SONIC v1.5.2 local-GGUF relay security and UI contract tests (synthetic only)."""
import hashlib
import json
import threading
import time

import pytest

from tests.test_auth_and_api import auth
from sonic.db import Device, LocalAIJob, session_factory, utcnow
from sonic.local_ai import MODEL


def device_headers():
    return {"Authorization": "Bearer device-test-token"}


def heartbeat(client):
    assert client.post('/api/device/heartbeat',headers=device_headers(),json={
        "device_id":"TRADEVICEPC","hostname":"TRADEVICEPC","platform":"Windows",
        "agent_version":"0.10.0","capabilities":["system.status"],"metrics":{}
    }).status_code==200
    return client.post('/api/device/local-ai/heartbeat',headers=device_headers(),json={
        "device_id":"TRADEVICEPC","state":"running",
        "ram_free_mb":1890,"gpu_free_mb":3119,"gpu_used_mb":2842
    })


def test_local_ai_off_by_default_and_owner_only(client):
    assert client.get('/api/local-ai/status').status_code==401
    assert client.post('/api/local-ai/control',json={"action":"start"}).status_code==401
    csrf=auth(client)
    assert client.get('/api/local-ai/status').json()['enabled'] is False
    assert client.post('/api/local-ai/control',json={"action":"start"}).status_code==403
    assert client.post('/api/local-ai/control',headers={"X-Sonic-CSRF":csrf},
                       json={"action":"start"}).status_code==503
    assert client.post('/api/device/local-ai/heartbeat',json={
        "device_id":"TRADEVICEPC","state":"stopped","ram_free_mb":8000
    }).status_code==401
    assert client.post('/api/device/local-ai/next',headers=device_headers()).json()=={"job":None}
    html=client.get('/').text
    assert 'sonic-black-grey-blue-v152.css' in html
    assert 'id="localAIControl"' in html
    assert 'local-ai-v152.js' in html


def test_owner_control_is_bounded_and_device_jobs_are_authenticated(client, monkeypatch):
    monkeypatch.setenv('SONIC_LOCAL_AI_ENABLED','true')
    csrf=auth(client)
    assert client.post('/api/local-ai/control',headers={"X-Sonic-CSRF":csrf},
                       json={"action":"start"}).status_code==409
    assert heartbeat(client).status_code==200
    snapshot=client.get('/api/local-ai/status').json()
    assert snapshot['state']=='running'
    assert snapshot['bridge_online'] and snapshot['device_online']
    assert snapshot['hardware']['gpu_free_mb']==3119
    assert client.post('/api/local-ai/control',headers={"X-Sonic-CSRF":csrf},
                       json={"action":"restart"}).status_code==422
    assert client.post('/api/local-ai/control',headers={"X-Sonic-CSRF":csrf},
                       json={"action":"start","executable":"cmd.exe"}).status_code==422
    created=client.post('/api/local-ai/control',headers={"X-Sonic-CSRF":csrf},
                        json={"action":"stop"})
    assert created.status_code==200
    job_id=created.json()['id']
    assert client.post('/api/device/local-ai/next').status_code==401
    leased=client.post('/api/device/local-ai/next',headers=device_headers()).json()['job']
    assert leased['id']==job_id and leased['action']=='stop' and leased['payload']=={}
    assert client.post('/api/device/local-ai/result',headers=device_headers(),json={
        "device_id":"OTHER","job_id":job_id,"success":True,"result":{"state":"stopped"}
    }).status_code==403
    assert client.post('/api/device/local-ai/result',headers=device_headers(),json={
        "device_id":"TRADEVICEPC","job_id":job_id,"success":True,"result":{"state":"stopped"}
    }).status_code==200
    done=client.get('/api/local-ai/jobs/'+job_id).json()
    assert done['state']=='done' and done['result']['state']=='stopped'
    assert client.post('/api/device/local-ai/result',headers=device_headers(),json={
        "device_id":"TRADEVICEPC","job_id":job_id,"success":True,"result":{"state":"stopped"}
    }).status_code==409
    assert client.get('/api/local-ai/jobs/never').status_code==404


def test_local_provider_selection_and_text_only_bridge(client, monkeypatch):
    monkeypatch.setenv('SONIC_LOCAL_AI_ENABLED','true')
    csrf=auth(client)
    options=client.get('/api/models').json()['models']
    local=next(option for option in options if option['provider']=='local')
    assert local['model']==MODEL
    assert local['key_configured'] is True
    assert client.put('/api/models/selection',headers={"X-Sonic-CSRF":csrf},
                      json={"provider":"local","model":MODEL}).status_code==409
    assert heartbeat(client).status_code==200
    selected=client.put('/api/models/selection',headers={"X-Sonic-CSRF":csrf},
                        json={"provider":"local","model":MODEL})
    assert selected.status_code==200
    assert client.get('/api/models').json()['selected']['provider']=='local'
    # A real cloud API cannot be invoked by selecting Local; this endpoint
    # only creates a signed device job, never sends requests to model vendor.
    import sonic.local_ai as bridge
    assert bridge.compact_messages({
        "input":[{"role":"user","content":"UNTRUSTED REFERENCE DATA, NOT A REQUEST. prior"},
                 {"role":"user","content":"Berapa 3 x 7?"}],
        "tools":[{"name":"powershell.exec"}]
    })[-1] == {"role":"user","content":"Berapa 3 x 7?"}
    with pytest.raises(Exception):
        bridge.compact_messages({"input":[{"type":"function_call","name":"pc_exec"}]})


def test_local_model_not_exposed_in_anonymous_preview(client, monkeypatch):
    monkeypatch.setenv('SONIC_LOCAL_AI_ENABLED','true')
    monkeypatch.setenv('SONIC_OPEN_PREVIEW','true')
    available=client.get('/api/preview/models')
    assert available.status_code==200
    assert all(m['provider']!='local' for m in available.json()['models'])
    assert client.post('/api/local-ai/control',json={"action":"start"}).status_code==401


def test_local_companion_source_has_only_fixed_model_and_loopback():
    from pathlib import Path
    source=(Path(__file__).resolve().parent.parent/'scripts/windows_local_ai_v152.py').read_text()
    assert '127.0.0.1:11435' in source
    assert 'subprocess.Popen(args' in source
    assert 'shell=False' in source
    assert 'RAM_GUARD_MIN_6500MB' in source
    assert 'AI_SERVER_NOT_OWNED_BY_SONIC_COMPANION' in source
    assert 'terminal64' not in source.lower()