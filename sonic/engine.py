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


async def execute_chat(db: Session, text: str, selected_node_id: str | None) -> dict:
    from .brain import reply, _record_user, _record_answer
    from .memory import parse_memory_intent
    start = time.monotonic()
    run_id = str(uuid4())
    db.info.update(ui_actions=[], memory_events=[], memory_references=[], engine_steps=[], selected_node_id=selected_node_id)
    command = direct_graph_command(text, selected_node_id)
    route = 'graph_command' if command else 'explicit_memory' if parse_memory_intent(text) else 'model_conversation'
    status = 'completed'
    try:
        if command:
            _record_user(db, text)
            result = run_graph_tool(db, command[0], command[1])
            db.info['engine_steps'].append({'tool': command[0], 'status': 'rejected' if result.get('error') else 'prepared'})
            answer = _record_answer(db, direct_graph_reply(result, command[0]))
        else:
            answer = await reply(db, text)
        return {'reply': answer, 'memory_events': db.info.get('memory_events', []),
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
