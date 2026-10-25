"""Authenticated device metrics and per-action approvals for a narrow PC adapter."""
from __future__ import annotations
from datetime import timedelta
import hashlib
import hmac
import json
import re
import secrets
from typing import Literal
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session
from . import auth
from .config import setting
from .db import Device, DeviceTelemetry, OperatorRequest, OperatorOutput, OwnerSession, get_db, utcnow
from .device_contract import ACTIONS, RECIPES, clean_metrics, clean_request

router=APIRouter()


def device_metrics(db:Session) -> dict:
    did=setting('SONIC_DEVICE_ID','TRADEVICEPC')
    d=db.get(Device,did); row=db.get(DeviceTelemetry,did)
    age=max(0,int((utcnow()-d.last_seen).total_seconds())) if d else None
    fresh=bool(d and age<120)
    metric_age=max(0,int((utcnow()-row.updated_at).total_seconds())) if row else None
    available=bool(fresh and row and metric_age<120)
    return {'device_id':did,'node_id':'device:'+did,'connected':fresh,'heartbeat_age_seconds':age,
            'metrics_available':available,'metrics_age_seconds':metric_age,
            'metrics':json.loads(row.metrics_json) if available else {},
            'agent_version':row.agent_version if row else '',
            'capabilities':json.loads(row.capabilities_json) if fresh and row else [],
            'gui_targets':json.loads(row.targets_json) if fresh and row else [],
            'source':'authenticated_companion_heartbeat','read_at':utcnow().isoformat()+'Z',
            'notice':('Fresh authenticated Windows Task Manager telemetry' if available else 'No fresh Windows telemetry; no values are estimated.')}


def metrics_reply(data:dict) -> str:
    m=data.get('metrics') or {}
    if not data.get('metrics_available') or 'ram_available_bytes' not in m:
        return 'Data RAM TRADEVICEPC belum tersedia atau sudah kedaluwarsa. Saya tidak akan menebak angkanya.'
    return (f"Memori RAM tersedia di TRADEVICEPC {m['ram_available_bytes']/2**30:.2f} GiB "
            f"dari {m.get('ram_total_bytes',0)/2**30:.2f} GiB. Diperbarui {data['metrics_age_seconds']} detik lalu.")


def direct_device_command(text:str) -> bool:
    s=text.lower()
    return bool(re.search(r'\b(?:tradevice(?:pc)?|komputer|computer|pc)\b',s) and
                re.search(r'\b(?:ram|memory|memori|disk|storage|ruang|tersisa|kapasitas|status|koneksi|terhubung)\b',s) and
                not re.search(r'\b(?:jangan|simpan|ingat|save|remember)\b',s))


@router.get('/api/device/metrics')
def metrics(_:dict=Depends(auth.require_owner),db:Session=Depends(get_db)):
    return device_metrics(db)


def store_telemetry(db:Session,data):
    if not data.agent_version:return
    row=db.get(DeviceTelemetry,data.device_id)
    if row is None:row=DeviceTelemetry(device_id=data.device_id);db.add(row)
    row.agent_version=data.agent_version
    row.capabilities_json=json.dumps(sorted(set(data.capabilities)&(ACTIONS|{'system.status','system.metrics'})))
    row.metrics_json=json.dumps(clean_metrics(data.metrics))
    targets=[]
    for target in data.gui_targets[:5]:
        if isinstance(target,dict) and str(target.get('window','')).isdecimal() and target.get('application')=='notepad.exe':
            targets.append({'window':str(target['window'])[:20], 'application':'notepad.exe','title':str(target.get('title',''))[:120]})
    row.targets_json=json.dumps(targets)
    row.updated_at=utcnow()


class Strict(BaseModel):model_config=ConfigDict(extra='forbid',strict=True)
class Proposal(Strict):
    action:str=Field(min_length=1,max_length=40)
    payload:dict
class Approval(Strict):
    confirm:Literal[True]
    digest:str=Field(min_length=64,max_length=64)
class Lease(Strict):
    request_id:str=Field(min_length=36,max_length=36)
    lease:str=Field(min_length=32,max_length=128)
class Result(Lease):
    success:bool
    result:dict
class OutputEvent(Lease):
    sequence:int=Field(ge=1,le=48)
    channel:Literal['stdout','stderr','system']
    text:str=Field(min_length=1,max_length=1024)


def owner_row(db,request_id,owner):
    row=db.get(OperatorRequest,request_id)
    if not row or row.owner_sid!=auth.sha256(owner['sid']):raise HTTPException(404,'Request not found in this session')
    return row


def ensure_capability(db,action):
    if action=='powershell.exec' and setting('SONIC_ENABLE_POWERSHELL_EXEC','false').lower() not in ('1','true','yes'):
        raise HTTPException(403,'PowerShell command broker is disabled in this environment')
    if action not in device_metrics(db)['capabilities']:
        raise HTTPException(409,'Updated Windows companion and local opt-in required. No action queued.')


def receipt(row):
    return {'id':row.id,'action':row.action,'payload':json.loads(row.payload_json),'digest':row.digest,
            'state':row.state,'expires_at':row.expires_at.isoformat()+'Z',
            'result':json.loads(row.result_json) if row.result_json else None}


@router.get('/api/operator/capabilities')
def capabilities(_:dict=Depends(auth.require_owner),db:Session=Depends(get_db)):
    return {**device_metrics(db),'shell_recipes':RECIPES, 'shell_inspection_examples':['Get-Process','Get-Service','Get-NetAdapter','Get-CimInstance Win32_Processor'],
            'powershell_enabled':setting('SONIC_ENABLE_POWERSHELL_EXEC','false').lower() in ('1','true','yes'),
            'policy':'Each command requires exact preview and owner approval. PowerShell is unrestricted inside the Limited Windows user account, not an OS sandbox. Avoid secrets; no elevation or inbound ports.'}


@router.post('/api/operator/requests')
def propose(p:Proposal,owner:dict=Depends(auth.require_owner_write),db:Session=Depends(get_db)):
    try:payload=clean_request(p.action,p.payload)
    except (ValueError,TypeError) as e:raise HTTPException(422,str(e)) from None
    ensure_capability(db,p.action)
    sid=auth.sha256(owner['sid'])
    count=db.scalar(select(func.count()).select_from(OperatorRequest).where(OperatorRequest.owner_sid==sid,
        OperatorRequest.state.in_(['pending','queued','leased']),OperatorRequest.expires_at>utcnow())) or 0
    if count>=4:raise HTTPException(429,'Finish or cancel pending actions before requesting more')
    rid=str(uuid4());raw=json.dumps(payload,sort_keys=True,separators=(',',':'))
    digest=hashlib.sha256((rid+p.action+raw).encode()).hexdigest()
    row=OperatorRequest(id=rid,owner_sid=sid,device_id=setting('SONIC_DEVICE_ID','TRADEVICEPC'),action=p.action,
        payload_json=raw,digest=digest,expires_at=utcnow()+timedelta(seconds=90))
    db.add(row);db.commit();return receipt(row)


@router.post('/api/operator/requests/{request_id}/confirm')
def confirm(request_id:str,p:Approval,owner:dict=Depends(auth.require_owner_write),db:Session=Depends(get_db)):
    row=owner_row(db,request_id,owner)
    if not hmac.compare_digest(p.digest,row.digest):raise HTTPException(409,'Action changed; review before confirming')
    if row.state!='pending' or row.expires_at<=utcnow():raise HTTPException(409,'Approval expired or no longer pending')
    ensure_capability(db,row.action)
    lease_deadline=utcnow()+timedelta(seconds=180 if row.action=='powershell.exec' else 90)
    db.execute(update(OperatorRequest).where(OperatorRequest.id==row.id,OperatorRequest.state=='pending').values(state='queued',expires_at=lease_deadline))
    db.commit();db.refresh(row);return receipt(row)


@router.get('/api/operator/requests/{request_id}')
def status(request_id:str,owner:dict=Depends(auth.require_owner),db:Session=Depends(get_db)):
    row=owner_row(db,request_id,owner)
    if row.state in ('pending','queued','leased') and row.expires_at<=utcnow():
        row.state='expired';db.commit()
    return receipt(row)


@router.get('/api/operator/history')
def history(limit:int=20,_:dict=Depends(auth.require_owner),db:Session=Depends(get_db)):
    # SONIC has exactly one authenticated owner. Previous session receipts
    # remain visible, but never to unauthenticated or device-token clients.
    cap=max(1,min(limit,40))
    rows=db.scalars(select(OperatorRequest).order_by(OperatorRequest.created_at.desc()).limit(cap)).all()
    return {'requests':[receipt(row) for row in rows]}


@router.get('/api/operator/requests/{request_id}/stream')
def stream(request_id:str,after:int=0,owner:dict=Depends(auth.require_owner),db:Session=Depends(get_db)):
    owner_row(db,request_id,owner)
    if not 0 <= after <= 48:raise HTTPException(422,'Invalid stream offset')
    rows=db.scalars(select(OperatorOutput).where(OperatorOutput.request_id==request_id,OperatorOutput.sequence>after)
                    .order_by(OperatorOutput.sequence.asc()).limit(48)).all()
    return {'events':[{'sequence':r.sequence,'channel':r.channel,'text':r.content,'created_at':r.created_at.isoformat()+'Z'} for r in rows],
            'next_sequence':rows[-1].sequence if rows else after}


@router.delete('/api/operator/requests/{request_id}')
def cancel(request_id:str,owner:dict=Depends(auth.require_owner_write),db:Session=Depends(get_db)):
    row=owner_row(db,request_id,owner)
    if row.state in ('pending','queued','leased'):row.state='cancelled';db.commit()
    return {'state':row.state,'notice':'Cancellation may not undo an action already underway'}


@router.post('/api/device/operator/next')
def next_action(request:Request,db:Session=Depends(get_db)):
    auth.require_device(request)
    rows=db.scalars(select(OperatorRequest).where(OperatorRequest.device_id==setting('SONIC_DEVICE_ID','TRADEVICEPC'),
        OperatorRequest.state=='queued',OperatorRequest.expires_at>utcnow()).order_by(OperatorRequest.created_at).limit(4)).all()
    for row in rows:
        session=db.get(OwnerSession,row.owner_sid)
        if not session or session.expires_at<=utcnow():
            row.state='cancelled';db.commit();continue
        token=secrets.token_urlsafe(32)
        result=db.execute(update(OperatorRequest).where(OperatorRequest.id==row.id,OperatorRequest.state=='queued').values(state='leased',lease_hash=auth.sha256(token)))
        db.commit()
        if result.rowcount:return {'job':{'id':row.id,'action':row.action,'payload':json.loads(row.payload_json),'lease':token,'expires_at':row.expires_at.isoformat()+'Z'}}
    return {'job':None}


def valid_lease(db,p):
    row=db.get(OperatorRequest,p.request_id)
    if not row or row.device_id!=setting('SONIC_DEVICE_ID','TRADEVICEPC') or not row.lease_hash or not hmac.compare_digest(auth.sha256(p.lease),row.lease_hash):
        raise HTTPException(403,'Invalid device lease')
    return row


@router.post('/api/device/operator/check')
def check(p:Lease,request:Request,db:Session=Depends(get_db)):
    auth.require_device(request);row=valid_lease(db,p)
    session=db.get(OwnerSession,row.owner_sid)
    return {'execute':bool(row.state=='leased' and row.expires_at>utcnow() and session and session.expires_at>utcnow())}


@router.post('/api/device/operator/stream')
def device_stream(event:OutputEvent,request:Request,db:Session=Depends(get_db)):
    auth.require_device(request)
    row=valid_lease(db,event)
    if row.action!='powershell.exec' or row.state!='leased' or row.expires_at<=utcnow():
        raise HTTPException(409,'Command stream no longer active')
    if any(ord(ch)<32 and ch not in '\\n\\r\\t' for ch in event.text):
        raise HTTPException(422,'Invalid output control characters')
    existing=db.scalar(select(OperatorOutput).where(OperatorOutput.request_id==row.id,OperatorOutput.sequence==event.sequence))
    if existing:
        if existing.channel==event.channel and existing.content==event.text:return {'accepted':True,'duplicate':True}
        raise HTTPException(409,'Stream sequence conflict')
    last=db.scalar(select(func.max(OperatorOutput.sequence)).where(OperatorOutput.request_id==row.id)) or 0
    if event.sequence!=last+1:raise HTTPException(409,'Stream sequence gap')
    db.add(OperatorOutput(request_id=row.id,sequence=event.sequence,channel=event.channel,content=event.text))
    db.commit()
    return {'accepted':True,'sequence':event.sequence}


@router.post('/api/device/operator/result')
def result(p:Result,request:Request,db:Session=Depends(get_db)):
    auth.require_device(request);row=valid_lease(db,p)
    if row.state in ('done','failed'):return {'accepted':True,'duplicate':True}
    if row.state not in ('leased','cancelled','expired'):raise HTTPException(409,'Request no longer leased')
    raw=json.dumps(p.result,ensure_ascii=False)
    if len(raw.encode())>32768:raise HTTPException(413,'Result exceeds 32KB limit')
    row.result_json=raw
    if row.state=='leased':row.state='done' if p.success else 'failed'
    db.commit();return {'accepted':True,'state':row.state}
