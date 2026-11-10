"""Software chat and companion integration; no installer is executed."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace
import pytest

from sonic.chat_actions import classify
from sonic.voice_intent import parse_voice_intent


@pytest.mark.parametrize('text,action', [
    ('Sonic cari software Visual Studio Code di TRADEVICE PC', 'software.search'),
    ('Tolong install Visual Studio Code', 'software.search'),
    ('Periksa software Microsoft.VisualStudioCode versi 1.143.1', 'software.inspect'),
    ('Install Microsoft.VisualStudioCode versi 1.143.1 di PC', 'software.inspect'),
    ('Tampilkan software terpasang di TRADEVICEPC', 'software.inventory'),
])
def test_owner_software_intent_only_prepares_discovery(text, action):
    request=classify(text)
    assert request.action == action
    assert request.kind == 'automatic'
    assert request.action != 'software.install'
    assert not request.payload.get('accept_source_agreements',False)
    assert not request.payload.get('accept_package_agreements',False)
    voice=parse_voice_intent(text)
    assert voice.kind == 'action' and voice.action == request


@pytest.mark.parametrize('text', [
    'Jangan install Visual Studio Code',
    'Bagaimana cara install Visual Studio Code?',
    'Misalnya install Visual Studio Code',
    'The website says install Visual Studio Code',
])
def test_narrative_or_negated_software_is_not_an_action(text):
    assert classify(text) is None


@pytest.fixture
def companion(monkeypatch):
    scripts=Path(__file__).resolve().parents[1]/'scripts'
    monkeypatch.syspath_prepend(str(scripts))
    spec=importlib.util.spec_from_file_location('sonic_software_companion_test',scripts/'windows_agent_v05.py')
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module,'extended_stats',lambda:{'cpu_usage_percent':1})
    return module


def test_discovery_requires_local_gate_and_verified_preflight(companion,monkeypatch):
    monkeypatch.delenv('SONIC_SOFTWARE_DISCOVERY_ENABLED',raising=False)
    calls=[]
    fake=SimpleNamespace(preflight=lambda:calls.append('probe') or {
        'ok':True,'discovery_enabled':True,'install_enabled':False})
    companion._SOFTWARE_BROKER=fake
    assert companion.software_capabilities()==[] and not calls
    monkeypatch.setenv('SONIC_SOFTWARE_DISCOVERY_ENABLED','1')
    assert set(companion.software_capabilities())=={'software.search','software.inspect','software.inventory'}
    assert calls==['probe']
    companion.software_capabilities()
    assert calls==['probe']


def test_failed_preflight_does_not_advertise_software(companion,monkeypatch):
    monkeypatch.setenv('SONIC_SOFTWARE_DISCOVERY_ENABLED','1')
    companion._SOFTWARE_BROKER=SimpleNamespace(preflight=lambda:{'ok':False,'code':'LIMITED_USER_REQUIRED'})
    assert companion.software_capabilities()==[]


def test_upgrade_preflight_does_not_advertise_candidate_software(companion,monkeypatch):
    calls=[]
    monkeypatch.setattr(companion,'software_capabilities',lambda:['software.install'])
    monkeypatch.setattr(companion,'api',lambda route,payload:calls.append((route,payload)) or {'ok':True})
    companion.run_once(only_heartbeat=True)
    assert len(calls)==1
    assert 'software.install' not in calls[0][1]['capabilities']


def test_pending_receipt_delivery_never_reexecutes_installer(companion,monkeypatch):
    receipt={'request_id':'receipt-id','lease':'lease','success':True,'result':{'ok':True}}
    companion._SOFTWARE_PENDING_RESULT=receipt
    monkeypatch.setattr(companion,'software_capabilities',lambda:[])
    calls=[]
    def api(route,payload):
        calls.append((route,payload))
        if route.endswith('/next'):return {'job':None}
        return {'ok':True}
    monkeypatch.setattr(companion,'api',api)
    monkeypatch.setattr(companion,'execute_software',lambda *args:pytest.fail('Installer must not replay'))
    companion.run_once()
    assert companion._SOFTWARE_PENDING_RESULT is None
    assert calls[1]==('/api/device/operator/result',receipt)


def test_failed_receipt_delivery_blocks_further_dispatch(companion,monkeypatch):
    receipt={'request_id':'receipt-id','lease':'lease','success':False,'result':{'ok':False}}
    companion._SOFTWARE_PENDING_RESULT=receipt
    monkeypatch.setattr(companion,'software_capabilities',lambda:[])
    calls=[]
    def api(route,payload):
        calls.append(route)
        if route.endswith('/result'):raise TimeoutError('offline')
        return {'ok':True}
    monkeypatch.setattr(companion,'api',api)
    with pytest.raises(TimeoutError):companion.run_once()
    assert companion._SOFTWARE_PENDING_RESULT is receipt
    assert not any(route.endswith('/next') for route in calls)


def test_software_execution_checks_lease_and_streams_only_bounded_progress(companion,monkeypatch):
    calls=[]
    def api(route,payload):
        calls.append((route,payload))
        return {'execute':True,'accepted':True}
    def handle(action,payload,**kwargs):
        assert action=='software.search'
        assert kwargs['task_id']=='task-id'
        assert kwargs['cancel_requested']() is False
        kwargs['on_progress']({'phase':'discovering','elapsed_seconds':0,'untrusted':'not-forwarded'})
        kwargs['on_progress']({'phase':'discovering','elapsed_seconds':1})
        return {'ok':True,'status':'searched'}
    monkeypatch.setattr(companion,'api',api)
    companion._SOFTWARE_BROKER=SimpleNamespace(handle=handle)
    result=companion.execute_software({'id':'task-id','action':'software.search','payload':{}},
        {'request_id':'task-id','lease':'test-lease'},['software.search'])
    assert result['ok']
    streams=[p for route,p in calls if route.endswith('/stream')]
    assert len(streams)==1 and streams[0]['sequence']==1
    assert 'untrusted' not in streams[0]['text']


def test_lost_progress_ack_retries_identical_event(companion,monkeypatch):
    streams=[]
    def api(route,payload):
        if route.endswith('/stream'):
            streams.append(dict(payload))
            if len(streams)==1:raise TimeoutError('ack lost after server accepted')
        return {'execute':True,'accepted':True}
    def handle(action,payload,**kwargs):
        kwargs['on_progress']({'phase':'discovering','elapsed_seconds':0})
        kwargs['on_progress']({'phase':'verifying_inventory','elapsed_seconds':5})
        return {'ok':True,'status':'searched'}
    monkeypatch.setattr(companion,'api',api)
    companion._SOFTWARE_BROKER=SimpleNamespace(handle=handle)
    companion.execute_software({'id':'task-id','action':'software.search','payload':{}},
        {'request_id':'task-id','lease':'test-lease'},['software.search'])
    assert streams[0]==streams[1]
    assert streams[2]['sequence']==2
    assert streams[2]['text']!=streams[0]['text']
