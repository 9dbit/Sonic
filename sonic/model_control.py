"""Owner-only SONIC chat-model selection. Voice and device permissions unchanged."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from . import auth
from .db import get_db
from .providers import choose_model, public_model_status

router = APIRouter()


class ModelChoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider: str = Field(min_length=1, max_length=24)
    model: str = Field(min_length=1, max_length=100)


@router.get("/api/models")
def get_models(_: dict = Depends(auth.require_owner), db: Session = Depends(get_db)):
    return public_model_status(db)


@router.put("/api/models/selection")
def set_model(choice: ModelChoice, _: dict = Depends(auth.require_owner_write),
              db: Session = Depends(get_db)):
    selected = choose_model(db, choice.provider, choice.model)
    return {"saved": True, "selected": {"provider": selected.provider, "model": selected.model},
            "notice": "Chat model updated. OpenAI Realtime Voice and Vision are unchanged."}
