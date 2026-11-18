"""Authenticated, outbound-only SONIC Local AI bridge for one fixed GGUF model.

No arbitrary Windows commands, filesystem paths, model URLs or executable arguments
are accepted from browsers, model output or the cloud device channel.
"""
from __future__ import annotations

import asyncio
from datetime import timedelta
import json
import time
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session

from . import auth
from .config import setting
from .db import Device, LocalAIJob, LocalAIRuntime, get_db, session_factory, utcnow

router = APIRouter()
MODEL = "DeepSeek-V4-Pro-Qwen3.5-9B-UNCENSORED-heretic.Q4_K_M"
DEVICE = "TRADEVICEPC"
CONTROL = frozenset(("start", "stop"))
TERMINAL = frozenset(("done", "failed", "expired"))
STATES = frozenset(("running", "stopped", "starting", "unavailable", "error"))
MAX_RESULT = 6400
MAX_QUEUE_AGE = 105


def enabled() -> bool:
    return setting("SONIC_LOCAL_AI_ENABLED", "false").lower() in ("true", "1", "yes")


def target() -> str:
    return setting("SONIC_DEVICE_ID", DEVICE)


def companion_online(db: Session) -> bool:
    device = db.get(Device, target())
    return bool(device and (utcnow() - device.last_seen).total_seconds() < 120)


def runtime_snapshot(db: Session) -> dict:
    row = db.get(LocalAIRuntime, target())
    fresh = bool(row and (utcnow() - row.updated_at).total_seconds() < 40)
    state = row.state if fresh else "unavailable"
    return {
        "enabled": enabled(),
        "device_online": companion_online(db),
        "bridge_online": fresh,
        "state": state,
        "model": MODEL,
        "capabilities": ["text-chat", "code-draft", "start", "stop", "read-only-metrics"],
        "hardware": json.loads(row.metrics_json) if fresh else {},
        "checked_seconds_ago": max(0, int((utcnow()-row.updated_at).total_seconds())) if fresh else None,
        "notice": "SONIC relay passes chat text through Railway and sends it only to authenticated TRADEVICEPC; no external model API is called. Local model cannot invoke PC tools.",
    }


def require_available(db: Session, *, chat: bool = False):
    if not enabled():
        raise HTTPException(503, "Local AI bridge is disabled in SONIC staging.")
    status = runtime_snapshot(db)
    if not status["device_online"] or not status["bridge_online"]:
        raise HTTPException(409, "SONIC local Companion is offline or not updated.")
    if chat and status["state"] != "running":
        raise HTTPException(409, "Start the TRADEVICEPC local AI engine in Devices first.")
    return status


def expire_stale_jobs(db: Session):
    now = utcnow()
    db.execute(update(LocalAIJob).where(LocalAIJob.device_id == target(),
        LocalAIJob.state == "queued", LocalAIJob.created_at < now-timedelta(seconds=MAX_QUEUE_AGE))
        .values(state="expired", payload_json="", updated_at=now))
    # The Windows request has a bounded 75-second inference timeout. Never
    # requeue a leased job; discard abandoned leases after a generous margin.
    db.execute(update(LocalAIJob).where(LocalAIJob.device_id == target(),
        LocalAIJob.state == "leased", LocalAIJob.updated_at < now-timedelta(seconds=180))
        .values(state="expired", payload_json="", updated_at=now))


def create_job(db: Session, action: str, payload: dict, owner_sid: str,
               *, commit: bool = True) -> LocalAIJob:
    # Serialize slot admission on PostgreSQL, even across workers.
    db.scalar(select(Device).where(Device.id == target()).with_for_update())
    expire_stale_jobs(db)
    now = utcnow()
    db.execute(delete(LocalAIJob).where(LocalAIJob.created_at < now - timedelta(days=1)))
    # One resource-heavy inference at a time on the 6 GB RTX 2060.
    if action in ("chat", "code") and db.scalar(select(LocalAIJob.id).where(
        LocalAIJob.device_id == target(), LocalAIJob.action.in_(("chat", "code")), 
        LocalAIJob.state.in_(("queued", "leased"))).limit(1)):
        raise HTTPException(429, "Local model is busy. Try again after the active reply.")
    job = LocalAIJob(id=str(uuid4()), device_id=target(), owner_sid=owner_sid,
                     action=action, state="queued", payload_json=json.dumps(payload, ensure_ascii=False))
    db.add(job)
    if commit:
        db.commit()
    else:
        db.flush()
    return job


class Control(BaseModel):
    model_config = ConfigDict(extra="forbid")
    action: str = Field(pattern=r"^(start|stop)$")


class Heartbeat(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device_id: str = Field(min_length=1, max_length=80)
    state: str = Field(max_length=20)
    ram_free_mb: int = Field(ge=0, le=10_000_000)
    gpu_free_mb: int | None = Field(default=None, ge=0, le=100_000)
    gpu_used_mb: int | None = Field(default=None, ge=0, le=100_000)


class Receipt(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device_id: str = Field(min_length=1, max_length=80)
    job_id: str = Field(min_length=36, max_length=40)
    success: bool
    result: dict


@router.get("/api/local-ai/status")
def status(_: dict = Depends(auth.require_owner), db: Session = Depends(get_db)):
    return runtime_snapshot(db)


@router.post("/api/local-ai/control")
def control(body: Control, owner: dict = Depends(auth.require_owner_write),
            db: Session = Depends(get_db)):
    require_available(db)
    existing = db.scalar(select(LocalAIJob.id).where(
        LocalAIJob.device_id == target(), LocalAIJob.state.in_(("queued", "leased"))).limit(1))
    if existing:
        raise HTTPException(409, "Another local AI operation is in progress.")
    job = create_job(db, body.action, {}, auth.sha256(owner["sid"]))
    return {"id": job.id, "state": "queued", "action": job.action}


@router.get("/api/local-ai/jobs/{job_id}")
def job_status(job_id: str, owner: dict = Depends(auth.require_owner),
               db: Session = Depends(get_db)):
    job = db.get(LocalAIJob, job_id[:40])
    if not job or job.owner_sid != auth.sha256(owner["sid"]) or job.action not in CONTROL:
        raise HTTPException(404, "Local AI operation not found.")
    return {"id": job.id, "state": job.state, "action": job.action,
            "result": json.loads(job.result_json) if job.result_json else None}


@router.post("/api/device/local-ai/heartbeat")
def device_heartbeat(data: Heartbeat, request: Request, db: Session = Depends(get_db)):
    auth.require_device(request)
    if data.device_id != target():
        raise HTTPException(403, "Device identity mismatch.")
    if data.state not in STATES:
        raise HTTPException(422, "Invalid local AI runtime state.")
    row = db.get(LocalAIRuntime, target())
    if row is None:
        row = LocalAIRuntime(device_id=target())
        db.add(row)
    row.state = data.state
    row.metrics_json = json.dumps({
        "ram_free_mb": data.ram_free_mb,
        "gpu_free_mb": data.gpu_free_mb, "gpu_used_mb": data.gpu_used_mb
    })
    row.updated_at = utcnow()
    db.commit()
    return {"ok": True, "enabled": enabled()}


@router.post("/api/device/local-ai/next")
def device_next(request: Request, db: Session = Depends(get_db)):
    auth.require_device(request)
    if not enabled():
        return {"job": None}
    expire_stale_jobs(db)
    now = utcnow()
    # Expired jobs cannot be revived or executed after delayed reconnects.
    db.execute(update(LocalAIJob).where(
        LocalAIJob.device_id == target(), LocalAIJob.state == "queued",
        LocalAIJob.created_at < now - timedelta(seconds=MAX_QUEUE_AGE)
    ).values(state="expired", payload_json="", updated_at=now))
    db.commit()
    candidates = db.scalars(select(LocalAIJob).where(
        LocalAIJob.device_id == target(), LocalAIJob.state == "queued"
    ).order_by(LocalAIJob.created_at.asc()).limit(3)).all()
    for job in candidates:
        # Save the transient payload before ORM synchronize_session wipes it.
        payload = json.loads(job.payload_json or "{}")
        result = db.execute(update(LocalAIJob).where(
            LocalAIJob.id == job.id, LocalAIJob.state == "queued"
        ).values(state="leased", payload_json="", updated_at=utcnow()))
        if result.rowcount:
            db.commit()
            # Sanitized, fixed action and bounded text payload only.
            return {"job": {"id": job.id, "action": job.action,
                            "payload": payload if job.action in ("chat", "code") else {}}}
        db.rollback()
    return {"job": None}


@router.post("/api/device/local-ai/result")
def device_result(body: Receipt, request: Request, db: Session = Depends(get_db)):
    auth.require_device(request)
    if body.device_id != target():
        raise HTTPException(403, "Device identity mismatch.")
    # Serialize receipt acceptance with lease expiry and other receipts.
    # A stale ORM read must never revive expired work or replace terminal data.
    job = db.scalar(select(LocalAIJob).where(LocalAIJob.id == body.job_id)
                    .with_for_update().execution_options(populate_existing=True))
    if not job or job.device_id != body.device_id:
        raise HTTPException(409, "Local AI job is not leased.")
    if job.action in ("chat", "code") and job.state == "expired":
        return {"ok": True, "ignored": True, "reason": "expired_not_replayed"}
    if job.action in ("chat", "code") and job.state in ("done", "failed"):
        # A lost receipt upload acknowledgment must not wedge the Companion
        # forever. Accept identical chat receipts, never changed terminal data.
        if job.state == ("done" if body.success else "failed") and json.loads(job.result_json or '{}') == body.result:
            return {"ok": True, "duplicate": True}
        raise HTTPException(409, "Conflicting local AI receipt")
    if job.state != "leased":
        raise HTTPException(409, "Local AI job is not leased.")
    if job.action not in CONTROL | {"chat", "code"}:
        raise HTTPException(403, "Unsupported local AI operation.")
    raw = json.dumps(body.result, ensure_ascii=False)
    if len(raw) > MAX_RESULT:
        raise HTTPException(413, "Local AI receipt too large.")
    if job.action in ("chat", "code") and body.success:
        answer = body.result.get("text")
        if not isinstance(answer, str) or not 1 <= len(answer.strip()) <= 4000:
            raise HTTPException(422, "Invalid local AI text result.")
    # Device-controlled error strings are never inserted into a command.
    job.state = "done" if body.success else "failed"
    job.result_json = raw
    job.updated_at = utcnow()
    db.commit()
    if job.action == "chat":
        from .chat_delivery import ChatDelivery, settle
        turn = db.scalar(select(ChatDelivery).where(ChatDelivery.local_job_id == job.id))
        if turn and turn.response_json:
            settle(db, turn.id)
    return {"ok": True}


def compact_messages(request: dict) -> list[dict]:
    """Text-only; tool definitions, tool results and model-generated PC actions stay out."""
    messages = []
    for item in request.get("input", []):
        if not isinstance(item, dict) or item.get("role") not in ("user", "assistant"):
            continue
        content = item.get("content")
        if not isinstance(content, str):
            continue
        # Don't send structured SONIC server context; this 9B runtime only has 1024 tokens.
        if content.startswith(("VERIFIED SONIC PLATFORM CONTEXT", "UNTRUSTED UI CONTEXT",
                               "UNTRUSTED REFERENCE DATA")):
            continue
        messages.append({"role": item["role"], "content": content})
    messages = messages[-5:]
    if not messages or messages[-1]["role"] != "user":
        raise HTTPException(422, "Text user request required.")
    # Never silently cut the current request. Trim OLD turns to fit the
    # existing 1024-token deployment instead of failing every longer session.
    if len(messages[-1]["content"]) > 1100:
        raise HTTPException(413, "Model lokal saat ini memakai konteks 1024 token. Kirim pertanyaan kurang dari 1100 karakter atau pilih cloud.")
    latest = messages[-1]
    previous = []
    budget = 2200 - len(latest["content"])
    for item in reversed(messages[:-1]):
        text = item["content"][:min(650, budget)]
        if len(text) < 80:
            break
        previous.append({"role": item["role"], "content": text})
        budget -= len(text)
    return [{"role": "system", "content": "You are SONIC, a private assistant. Reply accurately in the user's language. PC commands are handled separately by an authenticated SONIC executor, never by text you generate. Never claim software was installed, an app ran or an installer file was built without a device receipt."},
            *reversed(previous), latest]


async def infer(request: dict) -> dict:
    """Wait only for a signed Companion receipt. Never connect Railway to arbitrary URLs."""
    messages = compact_messages(request)
    with session_factory()() as db:
        require_available(db, chat=True)
        job = create_job(db, "chat", {"messages": messages}, "sonic-brain")
        job_id = job.id
    deadline = time.monotonic() + 100
    while time.monotonic() < deadline:
        await asyncio.sleep(.7)
        with session_factory()() as db:
            job = db.get(LocalAIJob, job_id)
            if job is None:
                raise HTTPException(502, "Local AI job was lost.")
            if job.state in TERMINAL:
                if job.state != "done":
                    raise HTTPException(502, "Local AI on TRADEVICEPC could not complete.")
                result = json.loads(job.result_json)
                text = result.get("text")
                if not isinstance(text, str) or not text.strip():
                    raise HTTPException(502, "Local AI returned an invalid response.")
                return {"status": "completed",
                        "output": [{"type": "message", "content": [
                            {"type": "output_text", "text": text[:4000]}]}],
                        "usage": result.get("usage", {})}
    with session_factory()() as db:
        db.execute(update(LocalAIJob).where(
            LocalAIJob.id == job_id, LocalAIJob.state.in_(("queued", "leased"))
        ).values(state="expired", payload_json="", updated_at=utcnow()))
        db.commit()
    raise HTTPException(504, "Local AI exceeded the bounded response deadline.")