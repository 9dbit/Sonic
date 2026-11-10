"""Software broker authorization, inspection binding and device evidence contracts."""
from datetime import timedelta
import json

import pytest

from sonic import software
from sonic.db import OperatorRequest, session_factory, utcnow
from sonic.device_contract import clean_request
from tests.test_engine_v04 import login
from tests.test_command_center_v08 import heartbeat, approve, next_job, DEVICE_HEADERS


INSPECT = {'package_id': 'Example.Editor', 'version': '1.2.3',
           'accept_source_agreements': True, 'accept_package_agreements': True}


def prepare(client, monkeypatch):
    monkeypatch.setenv('SONIC_ENABLE_SOFTWARE_DISCOVERY', 'true')
    monkeypatch.setenv('SONIC_ENABLE_SOFTWARE_INSTALL', 'true')
    headers = login(client)
    assert heartbeat(client, list(software.ACTIONS)).status_code == 200
    return headers


def propose(client, headers, action, payload):
    return client.post('/api/operator/requests', headers=headers, json={'action': action, 'payload': payload})


def finish(client, job, result, success=True):
    return client.post('/api/device/operator/result', headers=DEVICE_HEADERS, json={
        'request_id': job['id'], 'lease': job['lease'], 'success': success, 'result': result})


def inspection_result(args=None):
    plan = software.inspection_plan(args or INSPECT)
    return {'ok': True, 'status': 'inspected', 'plan': plan, 'plan_sha256': software.plan_digest(plan),
            'evidence': {'kind': 'winget_show_raw', 'stdout': 'Publisher: Example\nVersion: 1.2.3',
                         'stderr': '', 'exit_code': 0, 'truncated': False}, 'metadata_parsed': False}


def inspect(client, headers, args=None):
    response = propose(client, headers, 'software.inspect', args or INSPECT)
    assert response.status_code == 200, response.text
    row = response.json()
    assert approve(client, headers, row).status_code == 200
    job = next_job(client)
    result = inspection_result(args)
    assert finish(client, job, result).json()['state'] == 'done'
    return row, {'plan': result['plan'], 'plan_sha256': result['plan_sha256']}


def success_result(payload):
    installed = {key: payload['plan'][key] for key in ('package_id', 'version', 'source')}
    return {'ok': True, 'status': 'succeeded', 'plan_sha256': payload['plan_sha256'],
            'installed': {**installed, 'scope': 'user', 'scope_verified': False},
            'evidence': {'kind': 'winget_export_json', 'packages': [installed]}}


def test_software_needs_server_gates_and_current_companion(client, monkeypatch):
    headers = login(client)
    heartbeat(client, list(software.ACTIONS))
    query = {'query': 'editor', 'accept_source_agreements': False}
    monkeypatch.delenv('SONIC_ENABLE_SOFTWARE_DISCOVERY', raising=False)
    assert propose(client, headers, 'software.search', query).status_code == 403
    monkeypatch.setenv('SONIC_ENABLE_SOFTWARE_INSTALL', 'true')
    assert client.get('/api/operator/capabilities').json()['software']['installation_enabled'] is False
    monkeypatch.setenv('SONIC_ENABLE_SOFTWARE_DISCOVERY', 'true')
    heartbeat(client, ['file.list'])
    assert propose(client, headers, 'software.search', query).status_code == 409
    heartbeat(client, list(software.ACTIONS))
    assert propose(client, headers, 'software.search', query).status_code == 200


@pytest.mark.parametrize('action,payload', [
    ('software.search', {'query': '--source evil', 'accept_source_agreements': False}),
    ('software.search', {'query': 'editor; whoami', 'accept_source_agreements': False}),
    ('software.search', {'query': 'editor', 'accept_source_agreements': 'true'}),
    ('software.inventory', {'command': 'winget list'}),
    ('software.inspect', {**INSPECT, 'package_id': 'Example.Editor;evil'}),
    ('software.inspect', {**INSPECT, 'version': '--latest'}),
    ('software.inspect', {**INSPECT, 'version': 'latest'}),
    ('software.inspect', {**INSPECT, 'version': '1.2.3 && evil'}),
    ('software.inspect', {**INSPECT, 'source': 'other'}),
    ('software.inspect', {**INSPECT, 'scope': 'machine'}),
])
def test_software_args_cannot_be_raw_shell_or_unpinned(action, payload):
    with pytest.raises(ValueError):
        clean_request(action, payload)


def test_plan_digest_reboot_scope_and_agreement_flags_are_bound():
    plan = software.inspection_plan(INSPECT)
    payload = {'plan': plan, 'plan_sha256': software.plan_digest(plan)}
    assert clean_request('software.install', payload) == payload
    for change in ({'allow_reboot': True}, {'scope': 'machine'}, {'source': 'other'},
                   {'accept_package_agreements': False}, {'accept_source_agreements': False},
                   {'accept_package_agreements': 1}, {'command': 'evil'}):
        changed = {**plan, **change}
        with pytest.raises(ValueError):
            clean_request('software.install', {'plan': changed, 'plan_sha256': software.plan_digest(changed)})
    with pytest.raises(ValueError):
        clean_request('software.install', {**payload, 'plan_sha256': '0' * 64})


def test_client_cannot_invent_an_inspection_or_change_its_agreements(client, monkeypatch):
    headers = prepare(client, monkeypatch)
    valid = inspection_result()
    payload = {'plan': valid['plan'], 'plan_sha256': valid['plan_sha256']}
    assert propose(client, headers, 'software.install', payload).status_code == 409
    inspect(client, headers, {**INSPECT, 'accept_package_agreements': False})
    # A new valid hash is still not a device-authenticated inspection.
    assert propose(client, headers, 'software.install', payload).status_code == 409


def test_inspection_success_is_verified_even_without_execution_task(client, monkeypatch):
    headers = prepare(client, monkeypatch)
    row = propose(client, headers, 'software.inspect', INSPECT).json()
    approve(client, headers, row)
    job = next_job(client)
    result = inspection_result()
    result['plan']['version'] = '9.9.9'
    result['plan_sha256'] = software.plan_digest(result['plan'])
    assert finish(client, job, result).json()['state'] == 'failed'
    assert client.get('/api/operator/requests/' + row['id']).json()['operation_status'] == 'unverified'


def test_install_waits_for_exact_approval_and_checks_version_evidence(client, monkeypatch):
    headers = prepare(client, monkeypatch)
    _, payload = inspect(client, headers)
    response = propose(client, headers, 'software.install', payload)
    assert response.status_code == 200, response.text
    row = response.json()
    assert row['state'] == 'pending' and next_job(client) is None
    assert approve(client, headers, {**row, 'digest': '0' * 64}).status_code == 409
    assert approve(client, headers, row).status_code == 200
    job = next_job(client)
    assert job['action'] == 'software.install'
    with session_factory()() as db:
        active = db.get(OperatorRequest, row['id'])
        assert (active.expires_at - utcnow()).total_seconds() > software.INSTALL_SECONDS
    base = {'request_id': job['id'], 'lease': job['lease']}
    assert client.post('/api/device/operator/stream', headers=DEVICE_HEADERS, json={
        **base, 'sequence': 1, 'channel': 'system', 'text': 'verifying_installation'}).status_code == 200
    result = success_result(payload)
    result['evidence']['packages'][0]['version'] = '9.9.9'
    assert finish(client, job, result).json()['state'] == 'failed'
    assert propose(client, headers, 'software.install', payload).status_code == 409


def test_matching_installed_version_is_completed_and_no_second_attempt(client, monkeypatch):
    headers = prepare(client, monkeypatch)
    _, payload = inspect(client, headers)
    row = propose(client, headers, 'software.install', payload).json()
    approve(client, headers, row)
    job = next_job(client)
    result = success_result(payload)
    assert finish(client, job, result).json()['state'] == 'done'
    receipt = client.get('/api/operator/requests/' + row['id']).json()
    assert receipt['operation_status'] == 'succeeded' and receipt['automatic_retry'] is False
    assert propose(client, headers, 'software.install', payload).status_code == 409
    verified = software.verify_result('software.install', payload, result, True)
    assert verified['status'] == 'agent_verified' and verified['scope_verified'] is False
    assert verified['independent_readback'] is False


def test_inspection_is_session_bound_and_expires(client, monkeypatch):
    headers = prepare(client, monkeypatch)
    row, payload = inspect(client, headers)
    client.post('/api/logout', headers=headers)
    headers = login(client)
    assert propose(client, headers, 'software.install', payload).status_code == 409
    row, payload = inspect(client, headers)
    with session_factory()() as db:
        db.get(OperatorRequest, row['id']).created_at = utcnow() - timedelta(seconds=software.PLAN_MAX_AGE_SECONDS + 1)
        db.commit()
    assert propose(client, headers, 'software.install', payload).status_code == 409


def test_disabled_gate_cancels_a_queued_software_action(client, monkeypatch):
    headers = prepare(client, monkeypatch)
    row = propose(client, headers, 'software.inventory', {}).json()
    approve(client, headers, row)
    monkeypatch.setenv('SONIC_ENABLE_SOFTWARE_DISCOVERY', 'false')
    assert next_job(client) is None
    receipt = client.get('/api/operator/requests/' + row['id']).json()
    assert receipt['state'] == 'cancelled' and receipt['operation_status'] == 'blocked'


def test_inspection_is_rechecked_before_device_can_lease_install(client, monkeypatch):
    headers = prepare(client, monkeypatch)
    inspection, payload = inspect(client, headers)
    row = propose(client, headers, 'software.install', payload).json()
    assert approve(client, headers, row).status_code == 200
    with session_factory()() as db:
        db.get(OperatorRequest, inspection['id']).created_at = utcnow() - timedelta(seconds=software.PLAN_MAX_AGE_SECONDS + 1)
        db.commit()
    assert next_job(client) is None
    receipt = client.get('/api/operator/requests/' + row['id']).json()
    assert receipt['state'] == 'cancelled' and receipt['operation_status'] == 'blocked'


def test_cancelled_install_keeps_late_receipt_and_refuses_blind_retry(client, monkeypatch):
    headers = prepare(client, monkeypatch)
    _, payload = inspect(client, headers)
    row = propose(client, headers, 'software.install', payload).json()
    approve(client, headers, row)
    job = next_job(client)
    cancelled = client.delete('/api/operator/requests/' + row['id'], headers=headers).json()
    assert cancelled['state'] == 'cancelled' and 'does not roll back' in cancelled['notice']
    assert finish(client, job, success_result(payload)).json()['state'] == 'cancelled'
    receipt = client.get('/api/operator/requests/' + row['id']).json()
    assert receipt['operation_status'] == 'succeeded'
    assert receipt['state'] == 'cancelled'
    assert propose(client, headers, 'software.install', payload).status_code == 409


@pytest.mark.parametrize('status', ['requires_user_action', 'reconciliation_required', 'reboot_required'])
def test_nonterminal_or_uncertain_installer_status_never_means_installed(status):
    inspected = inspection_result()
    payload = {'plan': inspected['plan'], 'plan_sha256': inspected['plan_sha256']}
    result = success_result(payload)
    result['status'] = status
    assert software.verify_result('software.install', payload, result, True)['status'] == 'unverified'
    text = software.result_text('software.install', {**result, 'ok': False}, False)
    assert 'Instalasi software terverifikasi' not in text
