"""Bounded orchestration and owner-visible execution receipts, not a shell agent."""
import json
import time
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session
from . import auth
from .db import EngineRun, get_db
from .graph_commands import direct_graph_command, direct_graph_reply, run_graph_tool

router = APIRouter()


async def execute_chat(db: Session, text: str, selected_node_id: str | None, owner:dict|None=None) -> dict:
    from .brain import reply, _record_user, _record_answer
    from .memory import parse_memory_intent
    from .chat_actions import classify, confirmation_intent
    from .chat_audit import is_chat_log_request, summarize_chat_friction
    from fastapi import HTTPException
    start = time.monotonic()
    run_id = str(uuid4())
    db.info.update(ui_actions=[], memory_events=[], memory_references=[], engine_steps=[], selected_node_id=selected_node_id)
    from .operator import direct_device_command, direct_capability_question, capability_reply, device_metrics, metrics_reply
    audit_intent=is_chat_log_request(text)
    confirm_intent=None if audit_intent else confirmation_intent(text)
    chat_action=None
    action_parse_error=None
    if not confirm_intent and not audit_intent:
        try:chat_action=classify(text)
        except ValueError as exc:action_parse_error=str(exc)
    pc_capabilities = direct_capability_question(text)
    pc_request = not (pc_capabilities or audit_intent or chat_action or confirm_intent or action_parse_error) and direct_device_command(text)
    command = None if pc_request or pc_capabilities or audit_intent or chat_action or confirm_intent or action_parse_error else direct_graph_command(text, selected_node_id)
    route = 'chat_audit' if audit_intent else 'chat_approval' if confirm_intent else 'chat_pc_action' if chat_action or action_parse_error else 'device_capabilities' if pc_capabilities else 'device_metrics' if pc_request else 'graph_command' if command else 'explicit_memory' if parse_memory_intent(text) else 'model_conversation'
    status = 'completed'
    operator_jobs=[]
    operator_proposals=[]
    try:
        if audit_intent:
            _record_user(db,text)
            answer=_record_answer(db,summarize_chat_friction(db))
            db.info['engine_steps'].append({'tool':'chat.history_audit','status':'read'})
        elif confirm_intent or chat_action or action_parse_error:
            from .operator import chat_queue, chat_decide
            _record_user(db,text)
            if owner is None:raise HTTPException(401,'Owner session required for PC chat actions')
            if action_parse_error:
                answer=_record_answer(db,'Saya tidak menjalankan perintah itu karena path/argumen tidak aman: '+action_parse_error+'. Sebutkan nama folder relatif di workspace SONIC.')
            elif confirm_intent:
                try:
                    proposal=chat_decide(db,owner,confirm_intent=='approve')
                    if proposal is None:
                        answer=_record_answer(db,'Tidak ada operasi PC yang menunggu persetujuan di chat ini.')
                    elif confirm_intent=='approve':
                        operator_jobs.append({'id':proposal['id'],'action':proposal['action']})
                        answer=_record_answer(db,'Disetujui dalam chat. SONIC mengirim '+proposal['action']+' ke TRADEVICEPC. Hasilnya akan muncul otomatis di percakapan ini.')
                    else:
                        answer=_record_answer(db,'Perintah '+proposal['action']+' dibatalkan. Tidak dieksekusi.')
                    db.info['engine_steps'].append({'tool':'operator.chat_decision','status':'queued' if confirm_intent=='approve' and proposal else 'cancelled'})
                except HTTPException as exc:
                    answer=_record_answer(db,'Persetujuan tidak dapat diproses: '+str(exc.detail))
            else:
                try:
                    job=chat_queue(db,owner,chat_action.action,chat_action.payload,
                                   db.info['source_message_id'],chat_action.kind=='automatic')
                    if chat_action.kind=='automatic':
                        operator_jobs.append({'id':job['id'],'action':job['action']})
                        desc=(f"folder {chat_action.payload.get('path')}" if chat_action.action=='file.mkdir'
                              else chat_action.action)
                        answer=_record_answer(db,'Saya jalankan '+desc+' langsung di workspace TRADEVICEPC, tanpa konfirmasi tambahan. Menunggu hasil terverifikasi dari Windows agent...')
                    else:
                        operator_proposals.append({'id':job['id'],'action':job['action']})
                        preview=json.dumps(chat_action.payload,ensure_ascii=False,indent=2)
                        answer=_record_answer(db,'Perintah sensitif membutuhkan persetujuan sekali di chat ini. Tidak perlu membuka Devices.\n'
                              'Action: '+job['action']+'\n'+preview+'\nBalas SETUJU untuk menjalankan atau BATAL untuk membatalkan.')
                    db.info['engine_steps'].append({'tool':chat_action.action,'status':job['state']})
                except HTTPException as exc:
                    answer=_record_answer(db,'Tidak dapat menjalankan perintah PC: '+str(exc.detail))
        elif pc_capabilities:
            _record_user(db,text)
            data=device_metrics(db)
            db.info['engine_steps'].append({'tool':'device.capabilities','status':'read' if data['connected'] else 'offline'})
            answer=_record_answer(db,capability_reply(data))
        elif pc_request:
            _record_user(db, text)
            data = device_metrics(db)
            db.info['ui_actions'].append({'type':'device.metrics','device_id':data['device_id']})
            db.info['engine_steps'].append({'tool':'system.metrics','status':'read' if data['metrics_available'] else 'unavailable'})
            answer = _record_answer(db, metrics_reply(data))
        elif command:
            _record_user(db, text)
            result = run_graph_tool(db, command[0], command[1])
            db.info['engine_steps'].append({'tool': command[0], 'status': 'rejected' if result.get('error') else 'prepared'})
            answer = _record_answer(db, direct_graph_reply(result, command[0]))
        else:
            answer = await reply(db, text)
        return {'reply': answer, 'operator_jobs':operator_jobs, 'operator_proposals':operator_proposals, 'memory_events': db.info.get('memory_events', []),
                'ui_actions': db.info.get('ui_actions', []), 'memory_references': db.info.get('memory_references', []),
                'engine': {'run_id': run_id, 'route': route, 'status': status}}
    except Exception:
        status = 'failed'
        raise
    finally:
        # No prompt, transcript, tool arguments or credentials in the audit trail.
        db.rollback()
        try:
            db.add(EngineRun(id=run_id, channel='chat', route=route, status=status,
                steps_json=json.dumps(db.info.get('engine_steps', [])[:20]),
                duration_ms=int((time.monotonic()-start)*1000)))
            db.commit()
        except Exception:
            db.rollback()  # Never obscure the real result with a telemetry failure.


@router.get('/api/engine/runs')
def recent_runs(_: dict = Depends(auth.require_owner), db: Session = Depends(get_db)):
    rows = db.scalars(select(EngineRun).order_by(EngineRun.created_at.desc()).limit(30)).all()
    return {'runs': [{'id': r.id, 'channel': r.channel, 'route': r.route, 'status': r.status,
                     'steps': json.loads(r.steps_json), 'duration_ms': r.duration_ms,
                     'at': r.created_at.isoformat()+'Z'} for r in rows],
            'note': 'Execution receipts only. No chain of thought or hidden reasoning is recorded.'}
