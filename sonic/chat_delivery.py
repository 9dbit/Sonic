"""Durable local replies: short submit + authenticated polling, not a long fetch.

No background model executor or new device powers. The existing authenticated
Windows Companion leases the LocalAIJob. Request IDs are session-bound, single
use and fingerprint checked. A receipt, never a poll, proves model completion.
"""
from __future__ import annotations

from datetime import datetime, timedelta
import hashlib
import json
import threading
from uuid import NAMESPACE_URL, uuid5

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import DateTime, String, Text, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Mapped, Session, mapped_column

from . import auth
from .db import Base, ChatMessage, EngineRun, LocalAIJob, get_db, utcnow

router = APIRouter()
_lock = threading.RLock()  # SQLite test/single-worker serialization; PG also locks rows.


class ChatDelivery(Base):
    __tablename__ = 'chat_delivery_v183'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_sid: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(16), default='preparing', nullable=False)
    local_job_id: Mapped[str | None] = mapped_column(String(40), nullable=True, unique=True)
    response_json: Mapped[str] = mapped_column(Text, default='', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


def key(owner: dict, request_id: str) -> str:
    return str(uuid5(NAMESPACE_URL, 'sonic-chat:' + auth.sha256(owner['sid']) + ':' + request_id))


def _failure(message: str, status: int = 502) -> dict:
    return {'reply': message, 'error': {'status': status, 'message': message},
            'answer_origin': {'kind': 'system_status', 'provider': None, 'model': None,
                              'inference_performed': False, 'fallback': False}}


def _engine_state(db: Session, output: dict, status: str):
    if output.get('engine'):
        output['engine']['status'] = status
        run = db.get(EngineRun, output['engine']['run_id'])
        if run:
            run.status = status
            steps = json.loads(run.steps_json or '[]')
            for step in steps:
                if step.get('tool') == 'local.chat':
                    step['status'] = status
            run.steps_json = json.dumps(steps, ensure_ascii=False)


def _mark_failed(db: Session, row: ChatDelivery, message: str, status: int = 502):
    output = json.loads(row.response_json or '{}')
    output.update(_failure(message, status))
    _engine_state(db, output, 'failed')
    row.state = 'failed'
    row.finished_at = utcnow()
    row.response_json = json.dumps(output, ensure_ascii=False)


def view(row: ChatDelivery) -> dict:
    output = json.loads(row.response_json) if row.response_json else {
        'reply': 'Permintaan sudah diterima. Memeriksa status pekerjaan yang sama.',
        'answer_origin': {'kind': 'queued', 'provider': None, 'model': None,
                          'inference_performed': False, 'fallback': False}}
    output['delivery'] = {'id': row.id, 'state': row.state,
        'elapsed_seconds': max(0, round((utcnow() - row.created_at).total_seconds())),
        'poll_after_ms': 1800, 'resubmission_required': False}
    return output


def settle(db: Session, delivery_id: str) -> ChatDelivery:
    """Atomically retain a delivered answer in ChatMessage once, even after reload."""
    with _lock:
        row = db.scalar(select(ChatDelivery).where(ChatDelivery.id == delivery_id)
                        .with_for_update().execution_options(populate_existing=True))
        if row is None:
            raise HTTPException(404, 'Permintaan chat tidak ditemukan pada sesi ini.')
        if row.state in ('done', 'failed'):
            return row
        # A fast receipt/poll must not finalize before execute_chat has saved
        # its response envelope. Otherwise submit could overwrite done with
        # queued and persist the same assistant answer twice.
        if row.local_job_id and row.response_json:
            job = db.scalar(select(LocalAIJob).where(LocalAIJob.id == row.local_job_id)
                            .with_for_update().execution_options(populate_existing=True))
            if job and job.state == 'done':
                result = json.loads(job.result_json or '{}')
                answer = result.get('text')
                if isinstance(answer, str) and answer.strip():
                    from .local_ai import MODEL
                    from .providers import Selection, record_usage
                    from .model_runtime import origin
                    output = json.loads(row.response_json or '{}')
                    output['reply'] = answer[:4000]
                    output['answer_origin'] = origin('model_output', Selection('local', MODEL))
                    _engine_state(db, output, 'completed')
                    row.response_json = json.dumps(output, ensure_ascii=False)
                    row.state = 'done'
                    row.finished_at = utcnow()
                    db.add(ChatMessage(role='assistant', content=answer[:4000]))
                    record_usage(db, Selection('local', MODEL),
                        max(0, round((utcnow()-row.created_at).total_seconds()*1000)),
                        'ok', result.get('usage'))
                    db.commit()
                    return row
            if not job or job.state in ('failed', 'expired'):
                _mark_failed(db, row,
                    'Model lokal tidak menyelesaikan jawaban. Tidak ada pengiriman ulang atau perpindahan ke cloud otomatis. Periksa engine, lalu kirim permintaan baru.')
                db.commit()
        if row.state not in ('done', 'failed') and row.created_at < utcnow()-timedelta(seconds=190):
            _mark_failed(db, row,
                'Batas tunggu pekerjaan lokal berakhir. Hasil belum terverifikasi; pekerjaan tidak diulang otomatis.', 504)
            if row.local_job_id:
                db.execute(update(LocalAIJob).where(LocalAIJob.id == row.local_job_id,
                    LocalAIJob.state.in_(('queued','leased'))).values(state='expired', payload_json='', updated_at=utcnow()))
            db.commit()
        return row


def queue_local(db: Session, request: dict, selection) -> str:
    from .local_ai import require_available, compact_messages, create_job
    from .model_runtime import origin
    delivery_id = db.info.get('delivery_id')
    row = db.get(ChatDelivery, delivery_id)
    if row is None:
        raise HTTPException(409, 'Delivery record missing')
    require_available(db, chat=True)
    messages = compact_messages(request)
    # The job and delivery link become visible together. A process failure
    # cannot leave an executable job whose reply has no recoverable owner ID.
    with _lock:
        job = create_job(db, 'chat', {'messages': messages}, row.owner_sid, commit=False)
        row.local_job_id = job.id
        row.state = 'queued'
        db.commit()
    db.info['answer_origin'] = origin('queued', selection)
    db.info['engine_steps'].append({'tool': 'local.chat', 'status': 'queued'})
    return 'Permintaan diterima. TRADEVICEPC sedang menyiapkan jawaban; koneksi dapat dipulihkan tanpa mengirim ulang.'


async def submit(db: Session, payload, owner: dict) -> dict:
    if not payload.request_id:
        raise HTTPException(422, 'request_id is required for recoverable chat')
    delivery_id = key(owner, payload.request_id)
    canonical = json.dumps(payload.model_dump(), sort_keys=True, separators=(',', ':'))
    fingerprint = hashlib.sha256(canonical.encode()).hexdigest()
    row = db.get(ChatDelivery, delivery_id)
    if row is not None:
        if row.fingerprint != fingerprint:
            raise HTTPException(409, 'Request ID already belongs to a different message')
        return view(settle(db, delivery_id))
    row = ChatDelivery(id=delivery_id, owner_sid=auth.sha256(owner['sid']), fingerprint=fingerprint)
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        row = db.get(ChatDelivery, delivery_id)
        if row is None or row.fingerprint != fingerprint:
            raise HTTPException(409, 'Request ID conflict') from None
        return view(settle(db, delivery_id))
    db.info['delivery_id'] = delivery_id
    try:
        from .engine import execute_chat
        output = await execute_chat(db, payload.message.strip(), payload.selected_node_id,
            owner, request_id=payload.request_id, approval_request_id=payload.approval_request_id)
        with _lock:
            row = db.scalar(select(ChatDelivery).where(ChatDelivery.id == delivery_id)
                            .with_for_update().execution_options(populate_existing=True))
            # A concurrent timeout is terminal, even if the original submit
            # resumes later. Never revive a failed or completed delivery.
            if row.state in ('done', 'failed'):
                # A timeout can win before the response envelope existed.
                # Attach its now-known run without changing the terminal result.
                if row.state == 'failed' and row.local_job_id and output.get('engine'):
                    failed = json.loads(row.response_json or '{}')
                    failed.setdefault('engine', output['engine'])
                    row.response_json = json.dumps(failed, ensure_ascii=False)
                    error = failed.get('error', {})
                    _mark_failed(db, row, error.get('message', failed.get('reply', 'Pekerjaan gagal.')),
                                 error.get('status', 502))
                    db.commit()
                return view(row)
            row.response_json = json.dumps(output, ensure_ascii=False)
            row.state = 'queued' if row.local_job_id else 'done'
            if not row.local_job_id:
                row.finished_at = utcnow()
            else:
                output.setdefault('engine', {})['status'] = 'queued'
                row.response_json = json.dumps(output, ensure_ascii=False)
            db.commit()
        return view(settle(db, delivery_id))
    except HTTPException as exc:
        db.rollback()
        with _lock:
            row = db.scalar(select(ChatDelivery).where(ChatDelivery.id == delivery_id)
                            .with_for_update().execution_options(populate_existing=True))
            if row.state not in ('done', 'failed'):
                _mark_failed(db, row, str(exc.detail), exc.status_code)
                db.commit()
        return view(row)
    except Exception:
        db.rollback()
        with _lock:
            row = db.scalar(select(ChatDelivery).where(ChatDelivery.id == delivery_id)
                            .with_for_update().execution_options(populate_existing=True))
            if row.state not in ('done', 'failed'):
                _mark_failed(db, row, 'Permintaan tidak selesai. Periksa ID pekerjaan sebelum mencoba kembali.')
                db.commit()
        raise
    finally:
        db.info.pop('delivery_id', None)


@router.get('/api/chat/delivery/{request_id}')
def delivery_status(request_id: str, response: Response, owner: dict = Depends(auth.require_owner),
                    db: Session = Depends(get_db)):
    response.headers['Cache-Control']='no-store'
    if not 1 <= len(request_id) <= 128:
        raise HTTPException(404, 'Chat delivery not found')
    row = db.get(ChatDelivery, key(owner, request_id))
    if row is None or row.owner_sid != auth.sha256(owner['sid']):
        raise HTTPException(404, 'Chat delivery not found')
    return view(settle(db, row.id))
