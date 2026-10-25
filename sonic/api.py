"""SONIC FastAPI control plane. All data-changing owner APIs require a CSRF token."""
from __future__ import annotations
from datetime import timedelta
from pathlib import Path
import json
import re
from uuid import uuid4

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from . import auth
from .brain import reply
from .config import database_ready, device_ready, model_name, owner_ready, setting, public_url
from .db import ChatMessage, Device, DeviceJob, MemoryNote, get_db, recent_messages, utcnow

ROOT = Path(__file__).resolve().parent.parent
app = FastAPI(title="SONIC", version="0.2.0", docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/assets", StaticFiles(directory=ROOT / "web"), name="assets")


class LoginForm(BaseModel):
    token: str = Field(min_length=1, max_length=512)


class ChatForm(BaseModel):
    message: str = Field(min_length=1, max_length=3500)


class MemoryForm(BaseModel):
    text: str = Field(min_length=3, max_length=500)


class JobRequest(BaseModel):
    action: str


class DeviceHeartbeat(BaseModel):
    device_id: str = Field(min_length=1, max_length=80)
    hostname: str = Field(max_length=120)
    platform: str = Field(max_length=200)


class DeviceResult(BaseModel):
    device_id: str = Field(min_length=1, max_length=80)
    job_id: str = Field(min_length=1, max_length=40)
    success: bool
    result: dict = Field(default_factory=dict)


def check_db():
    if not database_ready():
        raise HTTPException(status_code=503, detail="Durable database not configured for hosted deployment")


def expected_device() -> str:
    return setting("SONIC_DEVICE_ID", "TRADEVICEPC")


def safe_device_id(value: str):
    if value != expected_device():
        raise HTTPException(status_code=403, detail="Device not allowed")


@app.get("/")
def home():
    return FileResponse(ROOT / "web" / "index.html", headers={"Cache-Control": "no-store"})


@app.get("/api/health")
def health():
    return {
        "service": "SONIC", "status": "ok",
        "setup_required": not (owner_ready() and database_ready() and bool(setting("OPENAI_API_KEY"))),
        "version": "0.2.0"
    }


@app.get("/api/session")
def session_status(request: Request):
    try:
        owner = auth.read_session(request)
    except HTTPException:
        return {"authenticated": False}
    return {"authenticated": True, "csrf": owner["csrf"],
            "model": model_name(), "capabilities": ["chat", "explicit-memory", "voice-ui", "device-status"]}


@app.post("/api/login")
def login(payload: LoginForm, request: Request, response: Response):
    address = request.client.host if request.client else "unknown"
    if not auth.verify_login(payload.token, address):
        raise HTTPException(status_code=401, detail="Invalid owner access token")
    session, csrf = auth.issue_session()
    response.set_cookie(
        auth.COOKIE, session, httponly=True, samesite="strict",
        secure=bool(setting("RAILWAY_ENVIRONMENT_NAME")) or public_url().startswith("https://"),
        max_age=auth.SESSION_SECONDS, path="/"
    )
    return {"authenticated": True, "csrf": csrf}


@app.post("/api/logout")
def logout(response: Response, _: dict = Depends(auth.require_owner_write)):
    auth.revoke_session(_)
    response.delete_cookie(auth.COOKIE, path="/")
    return {"logged_out": True}


@app.get("/api/history")
def history(_: dict = Depends(auth.require_owner), db: Session = Depends(get_db)):
    check_db()
    return {"messages": [
        {"id": x.id, "role": x.role, "content": x.content, "at": x.created_at.isoformat() + "Z"}
        for x in recent_messages(db, 60)
    ]}


@app.post("/api/chat")
async def chat(payload: ChatForm, _: dict = Depends(auth.require_owner_write),
               db: Session = Depends(get_db)):
    check_db()
    text = payload.message.strip()
    if not text:
        raise HTTPException(status_code=422, detail="Message required")
    answer = await reply(db, text)
    return {"reply": answer}


@app.get("/api/memories")
def memories(_: dict = Depends(auth.require_owner), db: Session = Depends(get_db)):
    check_db()
    rows = db.scalars(select(MemoryNote).order_by(MemoryNote.id.desc()).limit(100)).all()
    return {"memories": [{"id": m.id, "text": m.content} for m in rows]}


@app.post("/api/memories")
def save_memory(payload: MemoryForm, _: dict = Depends(auth.require_owner_write),
                db: Session = Depends(get_db)):
    check_db()
    from .brain import SECRET_PATTERN
    text = payload.text.strip()
    if len(text) < 3:
        raise HTTPException(status_code=422, detail="Memory must contain at least 3 characters")
    if SECRET_PATTERN.search(text):
        raise HTTPException(status_code=422, detail="Credentials must not be stored in memory")
    note = MemoryNote(content=text)
    db.add(note)
    db.commit()
    return {"id": note.id, "text": note.content}


@app.delete("/api/memories/{memory_id}")
def delete_memory(memory_id: int, _: dict = Depends(auth.require_owner_write),
                  db: Session = Depends(get_db)):
    check_db()
    note = db.get(MemoryNote, memory_id)
    if note is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    db.delete(note)
    db.commit()
    return {"deleted": True}


@app.get("/api/device/status")
def device_status(_: dict = Depends(auth.require_owner), db: Session = Depends(get_db)):
    check_db()
    d = db.get(Device, expected_device())
    if not d:
        return {"connected": False, "device_id": expected_device()}
    age = max(0, (utcnow() - d.last_seen).total_seconds())
    return {"connected": age < 120, "device_id": d.id,
            "hostname": d.hostname, "platform": d.platform, "last_seen_seconds_ago": round(age)}


@app.post("/api/device/jobs")
def request_status(payload: JobRequest, _: dict = Depends(auth.require_owner_write),
                   db: Session = Depends(get_db)):
    check_db()
    if payload.action != "system.status":
        raise HTTPException(status_code=403, detail="Action not on SONIC allowlist")
    d = db.get(Device, expected_device())
    if not d or (utcnow() - d.last_seen).total_seconds() > 120:
        raise HTTPException(status_code=409, detail="Companion is offline")
    job = DeviceJob(id=str(uuid4()), device_id=d.id, action=payload.action, state="queued")
    db.add(job)
    db.commit()
    return {"id": job.id, "state": job.state, "action": job.action}


@app.get("/api/device/jobs/{job_id}")
def get_job(job_id: str, _: dict = Depends(auth.require_owner), db: Session = Depends(get_db)):
    check_db()
    job = db.get(DeviceJob, job_id[:40])
    if job is None or job.device_id != expected_device():
        raise HTTPException(status_code=404, detail="Job not found")
    result = json.loads(job.result_json) if job.result_json else None
    return {"id": job.id, "state": job.state, "action": job.action, "result": result}


@app.post("/api/device/heartbeat")
def device_heartbeat(data: DeviceHeartbeat, request: Request,
                     db: Session = Depends(get_db)):
    auth.require_device(request)
    check_db()
    safe_device_id(data.device_id)
    d = db.get(Device, data.device_id)
    if d is None:
        d = Device(id=data.device_id)
        db.add(d)
    d.hostname, d.platform, d.last_seen = data.hostname, data.platform, utcnow()
    db.commit()
    return {"ok": True, "permitted_actions": ["system.status"]}


@app.post("/api/device/next")
def device_next(request: Request, db: Session = Depends(get_db)):
    auth.require_device(request)
    check_db()
    target = expected_device()
    # Single known device / worker in V0.1; atomic queued->leased state.
    candidates = db.scalars(select(DeviceJob).where(
        DeviceJob.device_id == target, DeviceJob.state == "queued"
    ).order_by(DeviceJob.created_at.asc()).limit(5)).all()
    for job in candidates:
        result = db.execute(
            update(DeviceJob).where(DeviceJob.id == job.id, DeviceJob.state == "queued")
            .values(state="leased", updated_at=utcnow())
        )
        db.commit()
        if result.rowcount:
            return {"job": {"id": job.id, "action": job.action}}
    return {"job": None}


@app.post("/api/device/result")
def device_result(payload: DeviceResult, request: Request, db: Session = Depends(get_db)):
    auth.require_device(request)
    check_db()
    safe_device_id(payload.device_id)
    job = db.get(DeviceJob, payload.job_id)
    if not job or job.device_id != payload.device_id or job.state != "leased":
        raise HTTPException(status_code=409, detail="Job not in leased state")
    if job.action != "system.status":
        raise HTTPException(status_code=403, detail="Action forbidden")
    if len(json.dumps(payload.result)) > 2048:
        raise HTTPException(status_code=413, detail="Result too large")
    job.state = "done" if payload.success else "failed"
    job.result_json = json.dumps(payload.result)
    job.updated_at = utcnow()
    db.commit()
    return {"ok": True}


class VisionForm(BaseModel):
    mimeType: str = Field(min_length=8, max_length=20)
    base64: str = Field(min_length=24, max_length=4 * (3 * 1024 * 1024 // 3 + 3))
    question: str = Field(min_length=1, max_length=500)


@app.post("/api/vision")
async def vision(payload: VisionForm, _: dict = Depends(auth.require_owner_write)):
    # One-frame opt-in analysis. No image saved in SONIC's database.
    from .vision import analyze_image
    answer = await analyze_image(payload.mimeType, payload.base64, payload.question.strip())
    return {"reply": answer, "image_stored": False, "pc_action": "none"}


# Activation routes and browser security headers. These never return credentials.
from .activation import router as activation_router
app.include_router(activation_router)


@app.middleware("http")
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Content-Security-Policy"] = (
        "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
        "img-src 'self' data: blob:; media-src 'self' blob:; connect-src 'self'; "
        "frame-ancestors 'none'; base-uri 'none'; form-action 'self'"
    )
    response.headers["Permissions-Policy"] = "camera=(self), microphone=(self), display-capture=(self)"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    if setting("RAILWAY_ENVIRONMENT_NAME") or public_url().startswith("https://"):
        response.headers["Strict-Transport-Security"] = "max-age=31536000"
    return response
