"""Durable execution identities, native adapter routing and result evidence.

The operator queue remains the sole execution authority. A dispatch response is
not completion. Unknown adapters cannot inherit native or ChatGPT permissions.
"""
from __future__ import annotations

import json
from pathlib import PureWindowsPath
from fastapi import HTTPException
from sqlalchemy import select, update

from . import auth
from .db import EngineRun, ExecutionTask, OperatorRequest, utcnow
from .device_contract import clean_request

ACTIVE = frozenset({'pending', 'queued', 'leased'})
PHASES = {'pending': 'awaiting_approval', 'queued': 'queued', 'leased': 'running',
          'done': 'completed', 'failed': 'failed', 'expired': 'expired', 'cancelled': 'cancelled'}


def input_identity(owner: dict, channel: str, request_id: str, text: str) -> dict:
    return {'request_key': auth.sha256(auth.sha256(owner['sid'])+':'+channel+':'+request_id),
            'request_hash': auth.sha256(text), 'owner_sid': auth.sha256(owner['sid']),
            'channel': channel}


def find_replay(db, identity: dict) -> ExecutionTask | None:
    task = db.scalar(select(ExecutionTask).where(ExecutionTask.request_key == identity['request_key']))
    if task and task.request_hash != identity['request_hash']:
        raise HTTPException(409, 'REQUEST_ID_REUSED_WITH_DIFFERENT_COMMAND')
    return task


class NativeWindowsAdapter:
    id = 'windows-native'

    def prepare(self, db, action: str, payload: dict) -> dict:
        from .integrations import integration_snapshot
        from .config import setting
        native = next(a for a in integration_snapshot(db)['adapters'] if a['id'] == self.id)
        if not native['connected'] or action not in native['current_capabilities']:
            raise HTTPException(409, 'WINDOWS_CAPABILITY_NOT_READY: No action queued')
        if action == 'powershell.exec' and setting('SONIC_ENABLE_POWERSHELL_EXEC', 'false').lower() not in ('1', 'true', 'yes'):
            raise HTTPException(403, 'PowerShell command broker is disabled in this environment')
        return clean_request(action, payload)

    def verify(self, action: str, payload: dict, result: dict, success: bool) -> dict:
        if not success:
            return {'status': 'failed', 'code': 'DEVICE_ACTION_FAILED'}
        if action in ('window.open','window.close','window.focus'):
            expected={'window.open':('opened','FIND_OR_LAUNCH'),
                      'window.close':('closed','WM_CLOSE'),
                      'window.focus':('focused','SET_FOREGROUND')}[action]
            if (result.get('app') != payload['app']
                    or result.get(expected[0]) is not True
                    or result.get('method') != expected[1]):
                return {'status':'unverified','code':'WINDOW_RESULT_TARGET_OR_METHOD_MISMATCH'}
            return {'status':'agent_reported','code':'WINDOW_ACTION_DEVICE_RECEIPT',
                    'app':payload['app'],'method':expected[1],
                    'independent_readback':False}
        if action not in ('desktop.mkdir', 'file.mkdir'):
            # A successful process exit is not independent proof of arbitrary
            # PowerShell side effects. Preserve that distinction in the UI.
            return {'status': 'agent_reported', 'code': 'AUTHENTICATED_DEVICE_RECEIPT'}
        if result.get('exists') is not True or type(result.get('created')) is not bool:
            return {'status': 'unverified', 'code': 'FOLDER_EXISTENCE_EVIDENCE_MISSING'}
        raw_path = result.get('path')
        if not isinstance(raw_path, str) or not 1 <= len(raw_path) <= 500 or any(ord(c) < 32 for c in raw_path):
            return {'status': 'unverified', 'code': 'FOLDER_PATH_EVIDENCE_MISSING'}
        path = PureWindowsPath(raw_path)
        if not path.is_absolute() or path.drive.startswith('\\\\') or '..' in path.parts:
            return {'status': 'unverified', 'code': 'FOLDER_PATH_EVIDENCE_INVALID'}
        if action == 'desktop.mkdir':
            expected = payload['name']
            valid = (result.get('scope') == 'owner_desktop' and result.get('name') == expected
                     and path.name.casefold() == expected.casefold())
        else:
            expected = PureWindowsPath('D:/Sonic/work') / payload['path']
            # Legacy compatible companion already supplies this exact path and
            # relative path; it enforces reparse-point and root checks locally.
            valid = (path == expected and result.get('relative_path') == payload['path'])
        if not valid:
            return {'status': 'unverified', 'code': 'FOLDER_TARGET_MISMATCH'}
        return {'status': 'agent_verified', 'code': 'EXPECTED_FOLDER_EXISTS', 'path': raw_path,
                'source': 'authenticated_windows_companion', 'independent_readback': False}


NATIVE = NativeWindowsAdapter()


def choose_adapter(db, action: str, payload: dict, adapter_id: str = 'windows-native'):
    if adapter_id != NATIVE.id:
        raise HTTPException(409, 'EXECUTOR_NOT_CONNECTED: Separate SONIC authorization required')
    return NATIVE, NATIVE.prepare(db, action, payload)


def phase(db, row: OperatorRequest) -> str:
    if row.state in ACTIVE and row.expires_at <= utcnow():
        db.execute(update(OperatorRequest).where(OperatorRequest.id == row.id,
            OperatorRequest.state.in_(ACTIVE), OperatorRequest.expires_at <= utcnow()).values(state='expired'))
        db.commit()
        db.refresh(row)
    return PHASES.get(row.state, 'unknown')


def task_snapshot(db, task: ExecutionTask) -> dict:
    row = db.get(OperatorRequest, task.id)
    if row is None:
        raise HTTPException(409, 'EXECUTION_RECEIPT_UNAVAILABLE')
    status = phase(db, row)
    verification = json.loads(task.verification_json)
    return {'id': task.id, 'run_id': task.run_id, 'channel': task.channel,
            'adapter': task.adapter_id, 'action': row.action, 'state': row.state, 'status': status,
            'verification': verification or {'status': 'pending'},
            'created_at': task.created_at.isoformat()+'Z',
            'expires_at': row.expires_at.isoformat()+'Z', 'cancellable': row.state in ACTIVE}


def replay_response(db, task: ExecutionTask) -> dict:
    snapshot = task_snapshot(db, task)
    if task.response_json:
        response = json.loads(task.response_json)
    else:
        # A process may have stopped after atomically queueing the operation,
        # but before saving its HTTP response. Recover its ID; never requeue.
        pending = snapshot['state'] == 'pending'
        item = {'id': task.id, 'action': snapshot['action']}
        response = {'reply': 'Perintah sudah diterima. Status perangkat: '+snapshot['state']+'.',
                    'operator_jobs': [] if pending else [item],
                    'operator_proposals': [item] if pending else [],
                    'memory_events': [], 'ui_actions': [], 'memory_references': [],
                    'engine': {'run_id': task.run_id, 'route': 'chat_pc_action'}}
    response['engine'].update(status=snapshot['status'], task_id=task.id, adapter=task.adapter_id)
    response['task'] = snapshot
    if snapshot['state'] in ('done', 'failed'):
        from .operator import chat_result_text, chat_output_excerpt
        row = db.get(OperatorRequest, task.id)
        response['reply'] = chat_result_text(row, json.loads(row.result_json or '{}'), row.state == 'done',
            chat_output_excerpt(db, row.id) if row.action == 'powershell.exec' else '')
    elif snapshot['state'] in ('cancelled', 'expired'):
        response['reply'] = 'Perintah '+snapshot['action']+' '+snapshot['state']+'. Tidak dijalankan ulang.'
        response['operator_jobs'] = []
        response['operator_proposals'] = []
    return response


def update_run(db, row: OperatorRequest):
    task = db.get(ExecutionTask, row.id)
    if task:
        db.execute(update(EngineRun).where(EngineRun.id == task.run_id).values(status=PHASES[row.state]))


def owned_task(db, task_id: str, owner: dict):
    task = db.get(ExecutionTask, task_id)
    if task is None or task.owner_sid != auth.sha256(owner['sid']):
        raise HTTPException(404, 'Task not found in this login')
    return task
