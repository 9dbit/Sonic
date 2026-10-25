"""Owner-only readiness and explicit, bounded provider connectivity test."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy.exc import SQLAlchemyError
import httpx
from . import auth
from .config import setting, model_name, owner_ready, device_ready
from .db import get_db, Device, utcnow

router = APIRouter()


@router.get("/api/setup/status")
def setup_status(_: dict = Depends(auth.require_owner), db: Session = Depends(get_db)):
    try:
        db.connection().exec_driver_sql("SELECT 1")
    except SQLAlchemyError:
        db.rollback()
        raise HTTPException(status_code=503, detail="Database not ready")
    device = db.get(Device, setting("SONIC_DEVICE_ID", "TRADEVICEPC"))
    key_present = bool(setting("OPENAI_API_KEY"))
    online = bool(device and (utcnow() - device.last_seen).total_seconds() < 120)
    return {
        "version": "0.5.0", "owner_configured": owner_ready(),
        "database_connected": True, "provider_key_configured": key_present,
        "provider_verified": False, "provider_verification": "Use Test OpenAI for a live check",
        "model": model_name(), "device_credential_configured": device_ready(),
        "device_online": online, "device_id": setting("SONIC_DEVICE_ID", "TRADEVICEPC"),
        "voice_mode": "realtime_opt_in" if setting("SONIC_REALTIME_ENABLED", "false").lower() == "true" else "browser_speech", "computer_control_enabled": False,
        "ready_for_chat_request": key_present,
        "remaining": [] if key_present else ["OPENAI_API_KEY"]
    }


@router.post("/api/setup/test-provider")
async def test_provider(_: dict = Depends(auth.require_owner_write)):
    key = setting("OPENAI_API_KEY")
    if not key:
        raise HTTPException(status_code=503, detail="Set OPENAI_API_KEY in SONIC Railway Variables; never paste it into chat")
    try:
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": "Bearer " + key, "Content-Type": "application/json"},
                json={"model": model_name(), "input": "Reply with SONIC_OK only.", "store": False, "max_output_tokens": 40}
            )
        if response.status_code != 200:
            raise HTTPException(status_code=502, detail="OpenAI connectivity check failed (HTTP %d)" % response.status_code)
        data = response.json()
        if data.get("status") != "completed":
            raise HTTPException(status_code=502, detail="OpenAI check did not complete")
        output = "".join(c.get("text", "") for p in data.get("output", []) if p.get("type") == "message"
                         for c in p.get("content", []) if c.get("type") == "output_text")
        if "SONIC_OK" not in output:
            raise HTTPException(status_code=502, detail="OpenAI check response was not verified")
        return {"verified": True, "model": model_name(), "provider": "OpenAI", "store": False}
    except (httpx.RequestError, ValueError, KeyError, TypeError):
        raise HTTPException(status_code=502, detail="OpenAI connectivity check unavailable")
