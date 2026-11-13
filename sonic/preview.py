"""Limited anonymous staging surface. Never grants owner, memory, workspace or PC authority.

The main SONIC engine, owner sessions and operator authorization are unchanged.
Anonymous visitors receive a same-site browser cookie/CSRF (no login UI), with
durable global and per-network daily paid-provider quotas.
"""
from __future__ import annotations

from typing import Literal

import hashlib
import hmac
import json
import secrets
from datetime import timedelta
from time import time
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import auth, voice
from .config import public_url, setting
from .db import PreviewBudget, get_db, utcnow
from .providers import (Selection, available_models, complete, configured,
                        selected_model, validate_model)

router = APIRouter()
COOKIE = "sonic_preview_guest"
CHAT_GLOBAL_DAILY = 80
CHAT_PER_NETWORK_DAILY = 12
VOICE_GLOBAL_DAILY = 6
VOICE_PER_NETWORK_DAILY = 2
VOICE_MAX_SECONDS = 60
COOKIE_SECONDS = 24 * 3600


def preview_active() -> bool:
    return (setting("SONIC_OPEN_PREVIEW", "false").lower() == "true"
            and setting("SONIC_ENV", "").lower() not in ("production", "prod"))


def paid_preview_enabled() -> bool:
    return preview_active() and setting("SONIC_PREVIEW_PAID_ACTIONS", "false").lower() == "true"


def _mac(text: str) -> str:
    secret = setting("SONIC_SESSION_SECRET")
    if len(secret) < 32:
        raise HTTPException(503, "Preview signing secret is not configured")
    return hmac.new(secret.encode(), text.encode(), hashlib.sha256).hexdigest()


def _verified_guest_cookie(cookie: str) -> str | None:
    """Stable, signed, expiring guest identity across repeated session probes."""
    if not cookie or len(cookie) > 200 or cookie.count(".") != 2:
        return None
    raw, supplied_signature = cookie.rsplit(".", 1)
    if len(supplied_signature) != 64 or not hmac.compare_digest(
            supplied_signature, _mac("guest:" + raw)):
        return None
    issued, _, nonce = raw.partition(".")
    if not issued.isdigit() or len(nonce) < 24:
        return None
    age = int(time()) - int(issued)
    return raw if 0 <= age < COOKIE_SECONDS else None


def issue_browser_guest(request: Request, response: Response, selected: Selection) -> dict:
    if not preview_active():
        raise HTTPException(404, "Preview mode is unavailable")
    raw = _verified_guest_cookie(request.cookies.get(COOKIE, ""))
    if raw is None:
        raw = str(int(time())) + "." + secrets.token_urlsafe(24)
        signature = _mac("guest:" + raw)
        response.set_cookie(COOKIE, raw + "." + signature, max_age=COOKIE_SECONDS,
                            httponly=True, samesite="strict",
                            secure=public_url().startswith("https://"), path="/")
    return {"authenticated": False, "preview": True, "preview_csrf": _mac("csrf:" + raw),
            "provider": selected.provider, "model": selected.model,
            "capabilities": (["preview-ui", "preview-chat", "preview-voice"]
                             if paid_preview_enabled() else ["preview-ui"]),
            "preview_paid_enabled": paid_preview_enabled()}


def guest(request: Request) -> dict:
    if not preview_active():
        raise HTTPException(404, "Preview is disabled")
    raw = _verified_guest_cookie(request.cookies.get(COOKIE, ""))
    if raw is None:
        raise HTTPException(403, "Invalid or expired preview browser. Refresh the page.")
    origin = request.headers.get("origin", "")
    expected = public_url().rstrip("/") or str(request.base_url).rstrip("/")
    if origin != expected:
        raise HTTPException(403, "Same-origin preview action required")
    if request.headers.get("sec-fetch-site", "same-origin") not in ("same-origin", "none"):
        raise HTTPException(403, "Cross-site preview actions are disabled")
    csrf = request.headers.get("x-sonic-preview-csrf", "")
    if not csrf or not hmac.compare_digest(csrf, _mac("csrf:" + raw)):
        raise HTTPException(403, "Preview CSRF token required")
    if not paid_preview_enabled():
        raise HTTPException(503, "Paid preview provider calls are disabled")
    # Never reuse an owner token or owner session SID here.
    return {"sid": "guest:" + raw, "network": request.client.host if request.client else "unknown"}


def _ensure_budget_row(db: Session, key: str) -> None:
    if db.get(PreviewBudget, key) is not None:
        return
    db.add(PreviewBudget(id=key))
    try:
        db.commit()
    except IntegrityError:
        db.rollback()


def take_budget(db: Session, kind: str, network: str) -> None:
    """Reserve before upstream call; failures intentionally consume budget."""
    if kind not in ("chat", "voice"):
        raise ValueError("Unknown preview budget")
    day = utcnow().strftime("%Y%m%d")
    global_key = day + ":global"
    network_id = hashlib.sha256(network.encode()).hexdigest()[:20]
    network_key = day + ":network:" + network_id
    _ensure_budget_row(db, global_key)
    # Serialize all preview provider starts on Postgres, even across replicas.
    global_row = db.scalar(select(PreviewBudget).where(PreviewBudget.id == global_key).with_for_update())
    # Only the locked global transaction can create a per-network budget row.
    network_row = db.get(PreviewBudget, network_key)
    if network_row is None:
        network_row = PreviewBudget(id=network_key)
        db.add(network_row)
        db.flush()
    field = kind + "_count"
    global_limit = CHAT_GLOBAL_DAILY if kind == "chat" else VOICE_GLOBAL_DAILY
    network_limit = CHAT_PER_NETWORK_DAILY if kind == "chat" else VOICE_PER_NETWORK_DAILY
    if getattr(global_row, field) >= global_limit or getattr(network_row, field) >= network_limit:
        db.rollback()
        raise HTTPException(429, "Daily staging preview limit reached; try again after 00:00 UTC")
    setattr(global_row, field, getattr(global_row, field) + 1)
    setattr(network_row, field, getattr(network_row, field) + 1)
    db.commit()


class PreviewStop(BaseModel):
    # Only bounded transport state codes, never user speech or arbitrary error text.
    model_config = ConfigDict(extra="forbid", strict=True)
    reason: Literal[
        "owner_stop", "channel_closed", "channel_error", "rtc_disconnected",
        "rtc_failed", "rtc_closed", "ice_disconnected", "ice_failed",
        "microphone_ended", "page_hidden", "start_failed", "connect_timeout",
        "duration_limit", "provider_error", "persona_changed", "voice_command",
        "voice_stop_all", "tool_limit", "session_expired", "logout"
    ] = "owner_stop"


class PreviewChat(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    message: str = Field(min_length=1, max_length=1000)
    provider: str = Field(min_length=1, max_length=20)
    model: str = Field(min_length=1, max_length=100)


@router.get("/api/preview/models")
def model_status(db: Session = Depends(get_db)):
    if not preview_active():
        raise HTTPException(404, "Preview is disabled")
    selected = selected_model(db)
    models = [{"provider": x["provider"], "model": x["model"], "label": x["label"]}
              for x in available_models()
              if configured(x["provider"]) and
              (x["provider"], x["model"]) in {
                  ("deepseek", "deepseek-flash"), ("openai", "gpt-4.1-mini"),
                  ("openai", "gpt-4.1")
              }]
    return {"enabled": paid_preview_enabled(), "selected": {"provider": selected.provider,
            "model": selected.model}, "models": models,
            "voice": {"enabled": paid_preview_enabled() and voice.enabled()
                     and bool(setting("OPENAI_API_KEY")), "provider": "openai",
                     "model": voice.voice_model(), "max_session_seconds": VOICE_MAX_SECONDS},
            "notice": "Anonymous staging: no owner memory, PC actions or file access. "
                      "Calls have strict daily limits. Voice uses OpenAI, independently of chat model."}


@router.post("/api/preview/chat")
async def preview_chat(payload: PreviewChat, visitor: dict = Depends(guest),
                       db: Session = Depends(get_db)):
    requested = validate_model(payload.provider, payload.model)
    if (requested.provider, requested.model) not in {
        ("deepseek", "deepseek-flash"), ("openai", "gpt-4.1-mini"),
        ("openai", "gpt-4.1")
    } or not configured(requested.provider):
        raise HTTPException(403, "Model not enabled for public preview")
    take_budget(db, "chat", visitor["network"])
    # Reuse the real selected-provider adapter, but NEVER call the owner reply/
    # executor, memory, history, tools, workspace or device endpoints.
    request = {"instructions": "You are SONIC, an AI assistant in public staging demo mode. "
               "Answer in the user's language, normally Bahasa Indonesia. "
               "You have no access to devices, files, accounts, saved memory or tools. "
               "Never claim to execute an action. Be concise and helpful.",
               "input": [{"role": "user", "content": payload.message.strip()}],
               "tools": [], "store": False, "max_output_tokens": 420}
    try:
        async with httpx.AsyncClient(timeout=35, follow_redirects=False) as client:
            result = await complete(client, request, requested)
    except HTTPException:
        raise
    except (ValueError, TypeError):
        raise HTTPException(502, "SONIC preview model response unavailable") from None
    answer = "\n".join(
        c.get("text", "") for item in result.get("output", [])
        if item.get("type") == "message" for c in item.get("content", [])
        if isinstance(c, dict) and c.get("type") == "output_text"
    ).strip()
    if not answer:
        raise HTTPException(502, "No usable model response received")
    return {"reply": answer[:3500], "provider": requested.provider, "model": requested.model,
            "operator_jobs": [], "operator_proposals": [], "memory_events": [],
            "memory_references": [], "ui_actions": []}


def _validate_sdp(payload: voice.StartVoice) -> None:
    try:
        if str(UUID(payload.session_id)) != payload.session_id:
            raise ValueError()
    except ValueError:
        raise HTTPException(422, "Invalid voice session ID") from None
    if not payload.sdp.startswith("v=0") or "m=audio " not in payload.sdp or "m=video " in payload.sdp:
        raise HTTPException(422, "Microphone-only WebRTC SDP required")


@router.post("/api/preview/voice/sessions")
async def preview_voice_start(payload: voice.StartVoice, visitor: dict = Depends(guest),
                              db: Session = Depends(get_db)):
    if not voice.enabled() or not setting("OPENAI_API_KEY"):
        raise HTTPException(503, "OpenAI realtime voice is not configured")
    _validate_sdp(payload)
    take_budget(db, "voice", visitor["network"])
    # Existing global voice gate still prevents overlapping live sessions.
    async with voice._create_lock:
        row = voice.reserve_session(db, payload.session_id, visitor)
        row.expires_at = utcnow() + timedelta(seconds=VOICE_MAX_SECONDS)
        db.commit()
    config = voice.session_config()
    config["instructions"] = (
        "You are SONIC in a public demo, replying naturally in Bahasa Indonesia. "
        "This is not an owner session. No files, memory, device, trading, actions or tools. "
        "Never claim to access or change a device or account. Keep spoken answers concise."
    )
    config["tools"] = []
    config["tool_choice"] = "none"
    config["max_output_tokens"] = 300
    try:
        async with httpx.AsyncClient(timeout=30, follow_redirects=False) as client:
            result = await client.post(voice.CREATE_URL, headers={
                "Authorization": "Bearer " + setting("OPENAI_API_KEY")
            }, files={"sdp": (None, payload.sdp, "application/sdp"),
                      "session": (None, json.dumps(config), "application/json")})
    except httpx.RequestError:
        db.refresh(row)
        row.state = "uncertain"
        row.close_reason = "preview_connect_uncertain"
        db.commit()
        raise HTTPException(502, "Voice provider connection was not confirmed") from None
    if result.status_code not in (200, 201):
        db.refresh(row)
        row.state = "failed"
        row.close_reason = "preview_provider_rejected"
        db.commit()
        raise HTTPException(502, "OpenAI realtime voice rejected the preview session")
    call_id = result.headers.get("location", "").rstrip("/").split("/")[-1]
    answer = result.text
    if not voice.CALL_RE.fullmatch(call_id) or len(answer) > 131072 or not answer.startswith("v=0"):
        db.refresh(row)
        row.state = "uncertain"
        row.close_reason = "preview_invalid_answer"
        db.commit()
        raise HTTPException(502, "Voice provider returned an invalid session") from None
    db.refresh(row)
    row.call_id = call_id
    row.state = "active" if row.state == "starting" else "stop_pending"
    db.commit()
    if row.state != "active":
        await voice.close_call(db, row, "preview_cancelled")
        raise HTTPException(409, "Preview voice was already cancelled")
    return {"session_id": row.id, "sdp": answer,
            "expires_at": row.expires_at.isoformat() + "Z",
            "model": row.model, "max_seconds": VOICE_MAX_SECONDS,
            "memory_policy": "disabled_in_public_preview"}


@router.post("/api/preview/voice/sessions/{session_id}/stop")
async def preview_voice_stop(session_id: str, payload: PreviewStop | None = None,
                             visitor: dict = Depends(guest), db: Session = Depends(get_db)):
    row = voice.owned_session(db, session_id, visitor)
    reason = payload.reason if payload else "owner_stop"
    return await voice.close_call(db, row, "preview_" + reason)
