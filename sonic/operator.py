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
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from . import auth
from .config import setting
from .db import Device, DeviceTelemetry, OperatorRequest, OperatorOutput, OwnerSession, ChatMessage, ChatOperation, ExecutionTask, get_db, utcnow
from .device_contract import ACTIONS, RECIPES, clean_metrics, clean_request

router=APIRouter()


@router.post('/api/device/diagnostics/recent')
def recent_voice_and_chat_diagnostics(request:Request,db:Session=Depends(get_db)):
    """Private, device-authenticated, read-only aggregate diagnosis.

    No user chat text, transcripts, credentials, folder names or session IDs
    leave this endpoint. Used to correlate voice acceptance with real PC jobs.
    """
    auth.require_device(request)
    from collections import Counter
    from .db import VoiceSession, VoiceActionDispatch, EngineRun
    sessions=db.scalars(select(VoiceSession).order_by(
        VoiceSession.created_at.desc()).limit(30)).all()
    attempts=db.scalars(select(VoiceActionDispatch).order_by(
        VoiceActionDispatch.created_at.desc()).limit(120)).all()
    jobs=db.scalars(select(OperatorRequest).order_by(
        OperatorRequest.created_at.desc()).limit(100)).all()
    messages=db.scalars(select(ChatMessage).order_by(
        ChatMessage.id.desc()).limit(150)).all()
    runs=db.scalars(select(EngineRun).order_by(
        EngineRun.created_at.desc()).limit(100)).all()
    attempt_rows=[]
    for attempt in attempts[:40]:
        try:
            receipt=json.loads(attempt.result_json)
            route=str(receipt.get('route','unknown'))[:45]
            jobs_created=[str(v.get('action','unknown'))[:40]
                for v in receipt.get('operator_jobs',[]) if isinstance(v,dict)]
        except (ValueError,TypeError,AttributeError):
            route='not_finalized';jobs_created=[]
        attempt_rows.append({
            'timestamp':attempt.created_at.isoformat()+'Z',
            'dispatch_state':attempt.state,'engine_route':route,
            'actions_queued':jobs_created})
    user=[m for m in messages if m.role=='user']
    responses=[m for m in messages if m.role=='assistant']
    return {
        'window':'latest_rows_not_a_time_filtered_window',
        'voice_sessions_recent':len(sessions),
        'voice_session_states':dict(Counter(s.state for s in sessions)),
        'voice_action_dispatches_recent':len(attempts),
        'voice_dispatch_routes':dict(Counter(x['engine_route'] for x in attempt_rows)),
        'voice_dispatch_recent':attempt_rows[:25],
        'chat_history_last_150':{
            'user_messages':len(user),'assistant_messages':len(responses),
            'user_folder_mentions':sum(bool(re.search(r'\b(?:folder(?:nya)?|direktori|mkdir)\b',m.content,re.I)) for m in user),
            'assistant_device_refusals':sum(bool(re.search(r'(?:tidak bisa|belum bisa|kendala teknis).{0,120}(?:folder|pc|komputer|powershell)',m.content,re.I|re.S)) for m in responses),
            'assistant_verified_folder_receipts':sum('Folder Desktop berhasil dibuat' in m.content for m in responses)
        },
        'operator_last_100':{
            'total':len(jobs),
            'actions':dict(Counter(m.action for m in jobs)),
            'states':dict(Counter(m.state for m in jobs)),
            'recent':[{'at':m.created_at.isoformat()+'Z','action':m.action,
                       'state':m.state} for m in jobs[:20]]
        },
        'engine_run_last_100':{
            'routes':dict(Counter((m.channel,m.route,m.status) for m in runs
                if m.channel in ('chat','voice','voice_tool'))).__str__()[:2800]
        }
    }


def device_metrics(db:Session) -> dict:
    did=setting('SONIC_DEVICE_ID','TRADEVICEPC')
    d=db.get(Device,did); row=db.get(DeviceTelemetry,did)
    age=max(0,int((utcnow()-d.last_seen).total_seconds())) if d else None
    fresh=bool(d and age<120)
    metric_age=max(0,int((utcnow()-row.updated_at).total_seconds())) if row else None
    available=bool(fresh and row and metric_age<120)
    return {'device_id':did,'node_id':'device:'+did,'connected':fresh,'heartbeat_age_seconds':age,
            'metrics_available':available,'metrics_age_seconds':metric_age,
            'sampled_at':row.updated_at.isoformat()+'Z' if row else None,
            'metrics':json.loads(row.metrics_json) if available else {},
            'agent_version':row.agent_version if row else '',
            'capabilities':json.loads(row.capabilities_json) if available else [],
            'gui_targets':json.loads(row.targets_json) if available else [],
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


# Deterministic answers for questions about SONIC's own registered Windows PC.
# Model instructions alone must never be the only way to know our device identity.
def direct_capability_question(text:str) -> bool:
    s=text.casefold()
    device=bool(re.search(r'\b(?:tradevicepc|tradevice|komputer|computer|pc|sonic)\b',s))
    intent=bool(re.search(r'apa yang (?:kita |sonic )?bisa|bisa (?:lakukan|apa)|kemampuan|capabilit|fitur.*(?:pc|komputer)|what can (?:you|sonic|we) do|kontrol.*(?:pc|komputer)',s))
    return device and intent


def capability_reply(data:dict) -> str:
    device_id=data['device_id']
    if not data['connected']:
        return (f"{device_id} adalah komputer Windows yang terdaftar sebagai perangkat SONIC, "
                "tetapi companion sekarang offline atau heartbeat-nya sudah kedaluwarsa. "
                "Saat online, SONIC dapat membaca Task Manager dan menampilkan PC Command Center. "
                "Saya tidak akan mengklaim PowerShell siap sebelum capability perangkat terverifikasi.")
    caps=set(data.get('capabilities') or [])
    abilities=[]
    if data['metrics_available']:
        abilities.append("memantau CPU, RAM, disk, network, proses, services, dan GPU jika driver menyediakannya")
    if 'process.list' in caps:abilities.append("melihat daftar proses berjalan")
    if 'file.mkdir' in caps:abilities.append("membuat folder otomatis di workspace SONIC langsung lewat chat")
    if 'desktop.mkdir' in caps:abilities.append("membuat folder di Desktop Windows langsung dari chat atau suara")
    if 'file.list' in caps:abilities.append("menjelajah folder kerja SONIC yang diizinkan")
    if 'file.read' in caps:abilities.append("membaca file teks dari workspace yang diizinkan")
    if 'powershell.exec' in caps and setting('SONIC_ENABLE_POWERSHELL_EXEC','false').lower() in ('true','1','yes'):
        abilities.append("menjalankan perintah PowerShell setelah persetujuan eksplisit untuk setiap command")
    elif 'shell.inspect' in caps:abilities.append("melakukan inspeksi PowerShell diagnostik yang dibatasi")
    if 'process.terminate' in caps:abilities.append("mengakhiri proses non-kritis melalui End Task dengan persetujuan pemilik")
    if 'window.list' in caps:abilities.append("membaca daftar jendela desktop")
    if 'window.focus' in caps:abilities.append("memfokuskan window aplikasi yang diizinkan")
    if 'window.open' in caps:abilities.append("membuka Notepad, Paint, atau MetaTrader 5 jika konfigurasi lokal mengizinkan")
    if 'window.close' in caps:abilities.append("menutup window secara normal (WM_CLOSE) setelah persetujuan, tanpa force-kill")
    if not abilities:abilities.append("menampilkan status dan heartbeat perangkat")
    return (f"{device_id} adalah PC Windows milik Anda yang terhubung ke SONIC. "
            f"Status: online; companion {data.get('agent_version') or 'versi tidak tersedia'}. "
            "Kemampuan yang terverifikasi saat ini: "+ "; ".join(abilities)+
            ". Untuk operasi aman cukup perintahkan saya langsung di chat. "
            "PowerShell dan End Task memerlukan persetujuan sekali melalui balasan SETUJU/BATAL di chat; "
            "tidak perlu pindah halaman, dan GUI automation tetap dibatasi.")


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
            'state':row.state,'created_at':row.created_at.isoformat()+'Z','expires_at':row.expires_at.isoformat()+'Z',
            'result':json.loads(row.result_json) if row.result_json else None}


# Safe, scoped operations can be queued directly from an authenticated owner chat
# request. Everything else keeps a pending review, resolved IN THE SAME CHAT.
AUTO_SAFE_ACTIONS=frozenset({'desktop.mkdir','file.mkdir','file.list','file.read','process.list','window.list','window.focus'})

def chat_queue(db:Session,owner:dict,action:str,payload:dict,source_message_id:int,auto:bool) -> dict:
    from .execution import choose_adapter, find_replay
    identity=db.info.get('execution_identity')
    if identity:
        replay=find_replay(db,identity)
        if replay:
            db.info['execution_task_id']=replay.id
            return receipt(db.get(OperatorRequest,replay.id))
    try:
        adapter,safe=choose_adapter(db,action,payload)
    except (ValueError,TypeError) as exc:
        raise HTTPException(422,str(exc)) from None
    if auto and action not in AUTO_SAFE_ACTIONS:
        raise HTTPException(403,'OPERATION_REQUIRES_CHAT_APPROVAL')
    if not auto and action not in {'powershell.exec','process.terminate','window.open','window.close','window.focus'}:
        raise HTTPException(403,'CHAT_REVIEW_ACTION_NOT_SUPPORTED')
    sid=auth.sha256(owner['sid'])
    active=db.scalar(select(func.count()).select_from(OperatorRequest).where(
        OperatorRequest.owner_sid==sid,
        OperatorRequest.state.in_(['pending','queued','leased']),
        OperatorRequest.expires_at>utcnow())) or 0
    if active>=4:
        raise HTTPException(429,'Maksimal empat tugas PC aktif. Tunggu hasil atau batalkan tugas sebelumnya.')
    if not auto:
        pending=db.scalars(select(OperatorRequest).join(
            ChatOperation,ChatOperation.request_id==OperatorRequest.id).where(
            OperatorRequest.owner_sid==sid,OperatorRequest.state=='pending',
            OperatorRequest.expires_at>utcnow()).limit(1)).first()
        if pending:
            raise HTTPException(409,'Masih ada perintah sensitif menunggu jawaban setuju/batal di chat.')
    rid=str(uuid4());raw=json.dumps(safe,sort_keys=True,separators=(',',':'))
    digest=hashlib.sha256((rid+action+raw).encode()).hexdigest()
    row=OperatorRequest(id=rid,owner_sid=sid,device_id=setting('SONIC_DEVICE_ID','TRADEVICEPC'),
        action=action,payload_json=raw,digest=digest,
        state='queued' if auto else 'pending',
        expires_at=utcnow()+timedelta(seconds=180 if auto else 120))
    db.add(row)
    db.add(ChatOperation(request_id=rid,source_message_id=source_message_id))
    if identity:
        db.add(ExecutionTask(id=rid,**identity,run_id=db.info['execution_run_id'],adapter_id=adapter.id))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        replay=find_replay(db,identity) if identity else None
        if not replay:
            raise
        db.info['execution_task_id']=replay.id
        return receipt(db.get(OperatorRequest,replay.id))
    db.info['execution_task_id']=rid if identity else None
    return receipt(row)


def chat_decide(db:Session,owner:dict,approved:bool,request_id:str|None=None) -> dict | None:
    sid=auth.sha256(owner['sid'])
    if request_id:
        row=owner_row(db,request_id,owner)
        if db.get(ChatOperation,row.id) is None:
            raise HTTPException(404,'Chat proposal not found')
        if row.state!='pending' or row.expires_at<=utcnow():
            raise HTTPException(409,'Persetujuan ini sudah tidak berlaku. Perintah lain tidak disetujui.')
        pending=[row]
    else:
        pending=db.scalars(select(OperatorRequest).join(
            ChatOperation,ChatOperation.request_id==OperatorRequest.id).where(
            OperatorRequest.owner_sid==sid,OperatorRequest.state=='pending',
            OperatorRequest.expires_at>utcnow()).order_by(
            OperatorRequest.created_at.desc()).limit(2)).all()
    if not pending:return None
    if len(pending)>1:raise HTTPException(409,'Ada beberapa proposal. Batalkan salah satunya dulu.')
    row=pending[0]
    # Compare-and-set prevents a concurrent Stop or another approval from
    # reviving this exact proposal after the owner has cancelled it.
    if approved:
        ensure_capability(db,row.action)
        values={'state':'queued','expires_at':utcnow()+timedelta(seconds=180 if row.action=='powershell.exec' else 90)}
    else:
        values={'state':'cancelled'}
    changed=db.execute(update(OperatorRequest).where(OperatorRequest.id==row.id,
        OperatorRequest.state=='pending',OperatorRequest.expires_at>utcnow()).values(**values))
    if not changed.rowcount:
        db.rollback()
        raise HTTPException(409,'Proposal is no longer awaiting approval')
    db.refresh(row)
    from .execution import update_run
    update_run(db,row)
    db.commit()
    return receipt(row)


def chat_output_excerpt(db:Session,request_id:str) -> str:
    """Only bounded output from the authenticated lease; never server secrets."""
    chunks=db.scalars(select(OperatorOutput).where(OperatorOutput.request_id==request_id)
                     .order_by(OperatorOutput.sequence.asc()).limit(24)).all()
    return ''.join(('[stderr] ' if event.channel=='stderr' else '')+event.content
                   for event in chunks if event.channel in ('stdout','stderr'))[:6000]


def chat_result_text(row:OperatorRequest,result:dict,success:bool,output_text:str='') -> str:
    if not success:
        if result.get('error')=='RESULT_VERIFICATION_FAILED':
            return 'Hasil folder dari TRADEVICEPC belum dapat diverifikasi: nama, lokasi, atau bukti keberadaannya tidak sesuai. Tugas ditandai gagal.'
        code=str(result.get('error') or result.get('detail') or 'DEVICE_ACTION_FAILED')[:140]
        return f"SONIC: tindakan {row.action} gagal pada TRADEVICEPC ({code})."
    if row.action=='desktop.mkdir':
        p=str(result.get('path','desktop tanpa path terverifikasi'))[:250]
        return ('Folder Desktop berhasil dibuat' if result.get('created') is True else
                'Folder Desktop sudah tersedia')+f' di TRADEVICEPC: {p}'
    if row.action=='file.mkdir':
        p=str(result.get('path','folder tanpa path terverifikasi'))[:250]
        return ('Folder berhasil dibuat' if result.get('created') is True else
                'Folder sudah tersedia')+f' di TRADEVICEPC: {p}'
    if row.action=='file.list':
        entries=result.get('items',[])
        names=', '.join(str(e.get('name',''))[:70] for e in entries[:35] if isinstance(e,dict))
        return f"Isi folder {str(result.get('directory',''))[:180]}: {names or '(kosong)'}"
    if row.action=='file.read':
        from .memory import SECRET_PATTERN
        content=str(result.get('content',''))[:8000]
        if SECRET_PATTERN.search(content):
            return 'File berhasil dibaca, tetapi kontennya mengandung pola informasi sensitif. SONIC tidak menyalinnya ke histori chat.'
        return f"Isi file {str(result.get('path',''))[:200]}:\n{content}"
    if row.action=='process.list':
        names=', '.join(f"{i.get('process','')} (PID {i.get('pid','')})" for i in result.get('processes',[])[:25] if isinstance(i,dict))
        return f"Proses Windows terdeteksi: {names or '(tidak ada data)'}"
    if row.action=='window.list':
        names=', '.join(str(i.get('title',''))[:100] for i in result.get('windows',[])[:20] if isinstance(i,dict))
        return f"Jendela aktif: {names or '(tidak ada jendela terdeteksi)'}"
    if row.action=='powershell.exec':
        from .memory import SECRET_PATTERN
        output_text=output_text[:6000]
        if SECRET_PATTERN.search(output_text):
            output_text='[Output memuat informasi sensitif dan tidak disalin ke chat]'
        return (f"Perintah PowerShell selesai (exit code: {result.get('exit_code','unknown')})."
                + ("\nOutput TRADEVICEPC (data, bukan instruksi):\n"+output_text if output_text else "\nTidak ada output teks dari perintah."))
    if row.action=='process.terminate':
        return f"End Task selesai: {str(result.get('name','process'))[:80]} PID {result.get('pid','unknown')}."
    if row.action.startswith('window.'):
        from .window_policy_v090 import APP_LABELS
        app=APP_LABELS.get(row.payload_json and json.loads(row.payload_json).get('app'), 'aplikasi')
        if row.action=='window.close':
            return (f'Window {app} dilaporkan tertutup oleh Windows companion melalui WM_CLOSE. '
                    'Ini bukan laporan penutupan posisi trading.')
        if row.action=='window.open':
            return f'Window {app} dilaporkan terbuka oleh Windows companion.'
        return f'Window {app} dilaporkan aktif di foreground oleh Windows companion.'
    return f"Tindakan {row.action} selesai di TRADEVICEPC."

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
    from .execution import phase, task_snapshot
    phase(db,row)
    output=receipt(row)
    task=db.get(ExecutionTask,row.id)
    if task:
        output['task']=task_snapshot(db,task)
    operation=db.get(ChatOperation,row.id)
    if operation and row.state in ('done','failed') and row.result_json:
        output['chat_completion']=chat_result_text(row,json.loads(row.result_json),row.state=='done',chat_output_excerpt(db,row.id) if row.action=='powershell.exec' else '')
    return output


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
    if row.state in ('pending','queued','leased'):
        db.execute(update(OperatorRequest).where(OperatorRequest.id==row.id,
            OperatorRequest.state.in_(('pending','queued','leased'))).values(state='cancelled'))
        db.refresh(row)
        from .execution import update_run
        update_run(db,row)
        db.commit()
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
    if any(ord(ch)<32 and ch not in '\n\r\t' for ch in event.text):
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
    auth.require_device(request)
    # Serialize terminal result acceptance, cancellation and duplicate reports.
    db.scalar(select(OperatorRequest).where(OperatorRequest.id==p.request_id).with_for_update())
    row=valid_lease(db,p)
    if row.state in ('done','failed'):return {'accepted':True,'duplicate':True}
    if row.state not in ('leased','cancelled','expired'):raise HTTPException(409,'Request no longer leased')
    raw=json.dumps(p.result,ensure_ascii=False)
    if len(raw.encode())>32768:raise HTTPException(413,'Result exceeds 32KB limit')
    from .execution import NATIVE, update_run
    task=db.get(ExecutionTask,row.id)
    success=p.success
    if task:
        evidence=NATIVE.verify(row.action,json.loads(row.payload_json),p.result,p.success)
        task.verification_json=json.dumps(evidence)
        if evidence['status']=='unverified':
            success=False
            raw=json.dumps({'error':'RESULT_VERIFICATION_FAILED','verification_error':evidence['code']})
    # Late results remain available as evidence, but cannot revive expired or
    # cancelled work or claim that a cancellation undid an already-started job.
    if row.state=='leased' and row.expires_at<=utcnow():
        row.state='expired'
    row.result_json=raw
    if row.state=='leased':row.state='done' if success else 'failed'
    update_run(db,row)
    operation=db.get(ChatOperation,row.id)
    if operation and not operation.notification_sent and row.state in ('done','failed'):
        try:
            data=json.loads(raw)
            summary=chat_result_text(row,data,row.state=='done',chat_output_excerpt(db,row.id) if row.action=='powershell.exec' else '')
            db.add(ChatMessage(role='assistant',content=summary[:12000]))
            operation.notification_sent=True
        except (ValueError,TypeError):
            pass
    db.commit();return {'accepted':True,'state':row.state}
