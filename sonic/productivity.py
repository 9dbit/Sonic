"""SONIC productivity foundations: scoped project notes, explicit missions, safe diagnostics."""
from __future__ import annotations

import json
import re
from datetime import timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import DateTime, Integer, String, Text, select, func
from sqlalchemy.orm import Mapped, Session, mapped_column

from . import auth
from .db import Base, Device, DeviceJob, get_db, utcnow
from .config import database_ready

router = APIRouter(prefix="/api/productivity", tags=["productivity"])
PROJECT = re.compile(r"^[a-z0-9][a-z0-9_-]{1,47}$")
DIAGNOSTICS = frozenset(("diagnostics.clock", "diagnostics.ping",
                         "diagnostics.processes", "diagnostics.events"))
MISSION_STATES = {"draft": {"approved", "cancelled"},
                  "approved": {"in_progress", "cancelled"},
                  "in_progress": {"completed", "cancelled"},
                  "completed": set(), "cancelled": set()}
TOOLS = (
    {"id": "diagnostics.clock", "kind": "read_only", "status": "implemented", "device": True},
    {"id": "diagnostics.ping", "kind": "read_only", "status": "implemented", "device": True},
    {"id": "diagnostics.processes", "kind": "read_only", "status": "implemented", "device": True},
    {"id": "diagnostics.events", "kind": "read_only", "status": "implemented", "device": True},
    {"id": "project.memory", "kind": "owner_write", "status": "implemented", "device": False},
    {"id": "mission.plan", "kind": "owner_write", "status": "implemented", "device": False},
    {"id": "daily.briefing", "kind": "read_only", "status": "implemented", "device": False},
    {"id": "workspace.search", "kind": "read_only", "status": "implemented", "device": False},
    {"id": "computer.operator", "kind": "review_required", "status": "existing_operator", "device": True},
    {"id": "router.syslog", "kind": "read_only", "status": "not_connected", "device": True},
    {"id": "workflow.scheduler", "kind": "review_required", "status": "planned", "device": False},
)

class ProjectFact(Base):
    __tablename__ = "productivity_project_facts_v148"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_key: Mapped[str] = mapped_column(String(48), index=True, nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    provenance: Mapped[str] = mapped_column(String(36), default="owner_entry", nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[object] = mapped_column(DateTime, default=utcnow, nullable=False)

class Mission(Base):
    __tablename__ = "productivity_missions_v148"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_key: Mapped[str] = mapped_column(String(48), index=True, nullable=False)
    goal: Mapped[str] = mapped_column(String(280), nullable=False)
    steps_json: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False)
    evidence: Mapped[str] = mapped_column(Text, default="", nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[object] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[object] = mapped_column(DateTime, default=utcnow, nullable=False)

class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")

class NewFact(Strict):
    project_key: str = Field(min_length=2, max_length=48)
    title: str = Field(min_length=2, max_length=120)
    content: str = Field(min_length=3, max_length=3000)

class NewMission(Strict):
    project_key: str = Field(min_length=2, max_length=48)
    goal: str = Field(min_length=5, max_length=280)
    steps: list[str] = Field(min_length=1, max_length=12)

class ChangeMission(Strict):
    status: str
    expected_revision: int = Field(ge=1)
    evidence: str = Field(default="", max_length=1200)

class DiagnosticRequest(Strict):
    action: str

def check_project(key: str) -> str:
    if not PROJECT.fullmatch(key):
        raise HTTPException(422, "Use a lowercase project key (letters, numbers, _ and -)")
    return key

def ensure_db():
    if not database_ready():
        raise HTTPException(503, "Database required")

def fact_record(x):
    return {"id": x.id, "project_key": x.project_key, "title": x.title,
            "content": x.content, "source": x.provenance,
            "updated_at": x.updated_at.isoformat()+"Z"}

def mission_record(x):
    return {"id": x.id, "project_key": x.project_key, "goal": x.goal,
            "steps": json.loads(x.steps_json), "status": x.status, "evidence": x.evidence,
            "revision": x.revision, "updated_at": x.updated_at.isoformat()+"Z",
            "execution": "no_automatic_actions"}

@router.get("/capabilities")
def capability_registry(_: dict = Depends(auth.require_owner), db: Session = Depends(get_db)):
    ensure_db()
    from .operator import device_metrics
    metrics = device_metrics(db)
    supported = set(metrics["capabilities"]) if metrics["connected"] else set()
    return {"tools": [{**t, "ready": (t["id"] in supported) if t["device"] and t["id"] in DIAGNOSTICS else
                       (metrics["connected"] if t["id"] == "computer.operator" else t["status"] == "implemented")}
                      for t in TOOLS], "device_connected": metrics["connected"],
            "notice": "Read-only diagnostics are queued only to an authenticated companion. Missions never execute automatically."}

@router.get("/projects/{project_key}/facts")
def list_facts(project_key: str, query: str = "", limit: int = 50,
               _: dict = Depends(auth.require_owner), db: Session = Depends(get_db)):
    ensure_db()
    key = check_project(project_key)
    if len(query) > 100 or not 1 <= limit <= 100:
        raise HTTPException(422, "Invalid search limits")
    stmt = select(ProjectFact).where(ProjectFact.project_key == key)
    if query.strip():
        stmt = stmt.where(ProjectFact.title.ilike("%"+query.strip()+"%") |
                          ProjectFact.content.ilike("%"+query.strip()+"%"))
    rows = db.scalars(stmt.order_by(ProjectFact.created_at.desc()).limit(limit)).all()
    return {"project_key": key, "facts": [fact_record(x) for x in rows],
            "source": "owner_saved_project_facts"}

@router.post("/facts", status_code=201)
def create_fact(data: NewFact, _: dict = Depends(auth.require_owner_write),
                db: Session = Depends(get_db)):
    ensure_db()
    key = check_project(data.project_key)
    from .memory import SECRET_PATTERN
    if SECRET_PATTERN.search(data.title + ' ' + data.content):
        raise HTTPException(422, 'Credentials must not be stored')
    x = ProjectFact(id=str(uuid4()), project_key=key, title=data.title.strip(),
                    content=data.content.strip())
    db.add(x)
    db.commit()
    return {"fact": fact_record(x)}

@router.delete("/facts/{fact_id}")
def delete_fact(fact_id: str, _: dict = Depends(auth.require_owner_write),
                db: Session = Depends(get_db)):
    ensure_db()
    x = db.get(ProjectFact, fact_id)
    if not x:
        raise HTTPException(404, "Fact not found")
    db.delete(x)
    db.commit()
    return {"deleted": True}

@router.get("/missions")
def list_missions(project_key: str | None = None, _: dict = Depends(auth.require_owner),
                  db: Session = Depends(get_db)):
    ensure_db()
    stmt = select(Mission)
    if project_key is not None:
        stmt = stmt.where(Mission.project_key == check_project(project_key))
    rows = db.scalars(stmt.order_by(Mission.created_at.desc()).limit(80)).all()
    return {"missions": [mission_record(x) for x in rows]}

@router.post("/missions", status_code=201)
def create_mission(data: NewMission, _: dict = Depends(auth.require_owner_write),
                   db: Session = Depends(get_db)):
    ensure_db()
    key = check_project(data.project_key)
    steps = [s.strip() for s in data.steps]
    if any(not 3 <= len(s) <= 200 for s in steps):
        raise HTTPException(422, "Each mission step must contain 3-200 characters")
    from .memory import SECRET_PATTERN
    if SECRET_PATTERN.search(data.goal+" "+" ".join(steps)):
        raise HTTPException(422, "Credentials must not be included in missions")
    x = Mission(id=str(uuid4()), project_key=key, goal=data.goal.strip(),
                steps_json=json.dumps(steps), status="draft")
    db.add(x)
    db.commit()
    return {"mission": mission_record(x)}

@router.post("/missions/{mission_id}/transition")
def transition_mission(mission_id: str, data: ChangeMission,
                       _: dict = Depends(auth.require_owner_write),
                       db: Session = Depends(get_db)):
    ensure_db()
    x = db.scalar(select(Mission).where(Mission.id == mission_id).with_for_update())
    if not x:
        raise HTTPException(404, "Mission not found")
    if x.revision != data.expected_revision:
        raise HTTPException(409, "Mission changed; refresh before retry")
    if data.status not in MISSION_STATES[x.status]:
        raise HTTPException(409, "Invalid mission state transition")
    if data.status == "completed":
        from .memory import SECRET_PATTERN
        if len(data.evidence.strip()) < 10:
            raise HTTPException(422, "Completion requires human-entered evidence")
        if SECRET_PATTERN.search(data.evidence):
            raise HTTPException(422, "Credentials must not be stored as mission evidence")
    x.status = data.status
    x.revision += 1
    x.updated_at = utcnow()
    if data.status == "completed":
        x.evidence = data.evidence.strip()
    db.commit()
    return {"mission": mission_record(x)}

@router.post("/diagnostics", status_code=202)
def queue_diagnostic(data: DiagnosticRequest, _: dict = Depends(auth.require_owner_write),
                     db: Session = Depends(get_db)):
    ensure_db()
    if data.action not in DIAGNOSTICS:
        raise HTTPException(403, "Diagnostic not allowlisted")
    from .operator import device_metrics
    m = device_metrics(db)
    if not m["connected"] or data.action not in m["capabilities"]:
        raise HTTPException(409, "Companion offline or diagnostics upgrade not activated")
    count = db.scalar(select(func.count()).select_from(DeviceJob).where(
        DeviceJob.device_id == m["device_id"],
        DeviceJob.action.in_(DIAGNOSTICS),
        DeviceJob.state.in_(("queued", "leased")),
        DeviceJob.created_at > utcnow()-timedelta(minutes=2))) or 0
    recent = db.scalar(select(func.count()).select_from(DeviceJob).where(
        DeviceJob.device_id == m["device_id"], DeviceJob.action.in_(DIAGNOSTICS),
        DeviceJob.created_at > utcnow()-timedelta(minutes=1))) or 0
    if count >= 4 or recent >= 8:
        raise HTTPException(429, "Diagnostic request rate limit exceeded")
    row = DeviceJob(id=str(uuid4()), device_id=m["device_id"],
                    action=data.action, state="queued")
    db.add(row)
    db.commit()
    return {"id": row.id, "action": row.action, "state": "queued",
            "poll": "/api/device/jobs/"+row.id}


@router.get("/briefing")
def daily_briefing(_: dict = Depends(auth.require_owner),
                   db: Session = Depends(get_db)):
    """Grounded internal snapshot only: no mailbox/calendar/provider calls."""
    ensure_db()
    from .db import WorkspaceItem
    from .operator import device_metrics
    missions = db.scalars(select(Mission).order_by(Mission.created_at.desc()).limit(80)).all()
    statuses = {k: sum(m.status == k for m in missions) for k in MISSION_STATES}
    facts = db.scalars(select(ProjectFact).order_by(ProjectFact.created_at.desc()).limit(5)).all()
    total_workspace = db.scalar(select(func.count()).select_from(WorkspaceItem).where(
        WorkspaceItem.trashed_at.is_(None))) or 0
    device = device_metrics(db)
    return {"generated_at": utcnow().isoformat()+"Z",
            "scope": "sonic_internal_only",
            "missions": {"latest_80_by_status": statuses,
                         "pending": [mission_record(m) for m in missions if m.status in ("draft","approved","in_progress")][:10]},
            "latest_project_facts": [{"project_key": f.project_key, "title": f.title,
                                      "updated_at": f.updated_at.isoformat()+"Z"} for f in facts],
            "workspace_active_items": total_workspace,
            "device": {"connected": device["connected"],
                       "metrics_available": device["metrics_available"],
                       "heartbeat_age_seconds": device["heartbeat_age_seconds"]},
            "not_connected": ["email", "calendar", "whatsapp", "router", "external_projects"]}


@router.get("/search")
def universal_search(q: str, _: dict = Depends(auth.require_owner),
                     db: Session = Depends(get_db)):
    """Owner-only metadata search; never searches remote PC or unconnected apps."""
    ensure_db()
    from .db import WorkspaceItem
    if not 2 <= len(q.strip()) <= 80:
        raise HTTPException(422, "Search query length must be 2-80")
    token = q.strip().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    needle = "%"+token+"%"
    facts = db.scalars(select(ProjectFact).where(
        ProjectFact.title.ilike(needle, escape="\\") |
        ProjectFact.content.ilike(needle, escape="\\")
    ).order_by(ProjectFact.created_at.desc()).limit(20)).all()
    files = db.scalars(select(WorkspaceItem).where(
        WorkspaceItem.trashed_at.is_(None),
        (WorkspaceItem.name.ilike(needle, escape="\\") |
         WorkspaceItem.content.ilike(needle, escape="\\"))
    ).order_by(WorkspaceItem.created_at.desc()).limit(20)).all()
    return {"query": q.strip(), "scope": ["project_memory", "sonic_cloud_workspace"],
            "results": (
                [{"source": "project_memory", "id": f.id, "title": f.title, "project_key": f.project_key}
                 for f in facts] +
                [{"source": "sonic_cloud_workspace", "id": x.id, "title": x.name, "kind": x.kind}
                 for x in files]
            ), "not_searched": ["tradevicepc", "google_drive", "email", "external_apps"]}
