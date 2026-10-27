"""Owner-only readiness and explicit, bounded provider connectivity test."""
from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
import httpx
import time
from . import auth
from .config import setting, owner_ready, device_ready
from .db import get_db, Device, utcnow
from .providers import complete, configured, record_usage, selected_model

router = APIRouter()


@router.get("/api/setup/status")
def setup_status(request: Request, _: dict = Depends(auth.require_owner), db: Session = Depends(get_db)):
    try:
        db.connection().exec_driver_sql("SELECT 1")
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=503, detail="Database not ready")
    device = db.get(Device, setting("SONIC_DEVICE_ID", "TRADEVICEPC"))
    selected = selected_model(db)
    key_present = configured(selected.provider)
    online = bool(device and (utcnow() - device.last_seen).total_seconds() < 120)
    return {
        "version": request.app.version, "owner_configured": owner_ready(),
        "database_connected": True, "provider_key_configured": key_present,
        "provider_verified": False, "provider_verification": "Use Test selected model for a live check",
        "provider": selected.provider, "model": selected.model,
        "openai_key_configured": configured("openai"),
        "openrouter_key_configured": configured("openrouter"),
        "device_credential_configured": device_ready(),
        "device_online": online, "device_id": setting("SONIC_DEVICE_ID", "TRADEVICEPC"),
        "voice_mode": "realtime_opt_in" if setting("SONIC_REALTIME_ENABLED", "false").lower() == "true" else "browser_speech", "computer_control_enabled": False,
        "ready_for_chat_request": key_present,
        "remaining": [] if key_present else ["OPENAI_API_KEY" if selected.provider == "openai" else "OPENROUTER_API_KEY"]
    }


@router.post("/api/setup/test-provider")
async def test_provider(_: dict = Depends(auth.require_owner_write), db: Session = Depends(get_db)):
    """Explicit, low-token real test of only the currently selected model.

    Never triggered on login or model selection. No automatic fallback.
    Does not expose API keys, responses or private model reasoning.
    """
    selection = selected_model(db)
    if not configured(selection.provider):
        raise HTTPException(status_code=503, detail="Configure the selected provider API key in Railway Variables")
    payload = {
        "model": selection.model,
        "instructions": "Reply only with SONIC_OK, no explanation.",
        "input": [{"role": "user", "content": "Reply SONIC_OK only."}],
        "tools": [], "store": False, "max_output_tokens": 280
    }
    started = time.monotonic()
    try:
        async with httpx.AsyncClient(timeout=75) as client:
            data = await complete(client, payload, selection)
        answer = "\n".join(c.get("text", "") for part in data.get("output", [])
                           if part.get("type") == "message"
                           for c in part.get("content", []) if c.get("type") == "output_text")
        verified = data.get("status") == "completed" and "SONIC_OK" in answer
        record_usage(db, selection, round((time.monotonic()-started)*1000),
                     "ok" if verified else "error", data.get("usage"))
        if not verified:
            raise HTTPException(502, "Selected model did not return the expected SONIC_OK response")
        return {"verified": True, "provider": selection.provider, "model": selection.model,
                "store": False, "note": "Only chat model tested. Voice remains OpenAI Realtime."}
    except HTTPException:
        # A semantic verification failure is already counted above; failures
        # before a response are recorded as safe status-only telemetry.
        raise
