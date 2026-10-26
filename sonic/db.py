"""SQLAlchemy storage: local SQLite, durable Postgres on Railway."""
from datetime import datetime, timezone
from pathlib import Path
import os
from threading import Lock

from fastapi import HTTPException
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, sessionmaker
from .config import setting, database_ready


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class OwnerSession(Base):
    __tablename__ = "owner_sessions"
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class WorkspaceGate(Base):
    __tablename__ = 'workspace_gate_v088'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class WorkspaceItem(Base):
    """Owner's cloud text workspace, separate from Windows and Memory Vault."""
    __tablename__ = 'workspace_items_v088'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    parent_id: Mapped[str] = mapped_column(String(36), default='root', nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    slot: Mapped[str | None] = mapped_column(String(64), unique=True, nullable=True)
    kind: Mapped[str] = mapped_column(String(12), nullable=False)
    content: Mapped[str] = mapped_column(Text, default='', nullable=False)
    create_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    revision: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    trashed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class ChatMessage(Base):
    __tablename__ = "chat_messages"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    role: Mapped[str] = mapped_column(String(12), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class MemoryNote(Base):
    __tablename__ = "memory_notes"
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class MemorySource(Base):
    """Additive provenance. Existing memory_notes schema is not altered."""
    __tablename__ = "memory_sources"
    memory_id: Mapped[int] = mapped_column(ForeignKey("memory_notes.id", ondelete="CASCADE"), primary_key=True)
    content_sha256: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    source_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    source_message_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class MemoryLink(Base):
    """Only owner-confirmed, persisted relationships between existing notes."""
    __tablename__ = "memory_links"
    __table_args__ = (UniqueConstraint("source_id", "target_id", name="uq_memory_link_pair"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("memory_notes.id", ondelete="CASCADE"), nullable=False)
    target_id: Mapped[int] = mapped_column(ForeignKey("memory_notes.id", ondelete="CASCADE"), nullable=False)
    label: Mapped[str] = mapped_column(String(80), default="related to", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class Device(Base):
    __tablename__ = "devices"
    id: Mapped[str] = mapped_column(String(80), primary_key=True)
    hostname: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    platform: Mapped[str] = mapped_column(String(200), default="", nullable=False)
    last_seen: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class DeviceJob(Base):
    __tablename__ = "device_jobs"
    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    device_id: Mapped[str] = mapped_column(String(80), nullable=False)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    state: Mapped[str] = mapped_column(String(24), default="queued", nullable=False)
    result_json: Mapped[str] = mapped_column(Text, default="", nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


def database_url() -> str:
    raw = setting("DATABASE_URL")
    if raw:
        if raw.startswith("postgres://"):
            return "postgresql+psycopg://" + raw[len("postgres://"):]
        if raw.startswith("postgresql://"):
            return "postgresql+psycopg://" + raw[len("postgresql://"):]
        return raw
    return "sqlite:///" + str(Path(os.environ.get("SONIC_LOCAL_DB", "./sonic-local.sqlite3")).resolve())


_engine = None
_Session = None
_initialization_lock = Lock()


def session_factory():
    global _engine, _Session
    if not database_ready():
        raise HTTPException(status_code=503, detail="Durable database is required for hosted SONIC")
    with _initialization_lock:
        if _Session is None:
            url = database_url()
            kwargs = {"pool_pre_ping": True}
            if url.startswith("sqlite:"):
                kwargs["connect_args"] = {"check_same_thread": False}
            engine = create_engine(url, **kwargs)
            try:
                Base.metadata.create_all(engine)
            except Exception:
                engine.dispose()
                raise
            _engine = engine
            _Session = sessionmaker(bind=_engine, expire_on_commit=False)
    return _Session


def get_db():
    db = session_factory()()
    try:
        yield db
    finally:
        db.close()


def chat_history(db, limit: int = 16):
    messages = db.scalars(select(ChatMessage).order_by(ChatMessage.id.desc()).limit(limit)).all()
    return [{"role": m.role, "content": m.content} for m in reversed(messages)]


def recent_messages(db, limit: int = 60):
    return list(reversed(db.scalars(select(ChatMessage).order_by(ChatMessage.id.desc()).limit(limit)).all()))


# Additive V0.4 engine tables. Existing chat/memory/session tables remain intact.
class EngineRun(Base):
    __tablename__ = 'engine_runs'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    channel: Mapped[str] = mapped_column(String(24), nullable=False)
    route: Mapped[str] = mapped_column(String(32), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    steps_json: Mapped[str] = mapped_column(Text, default='[]', nullable=False)
    duration_ms: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)


class ExecutionTask(Base):
    """V0.8.7: atomic link between an input item and one leased PC operation.

    Existing tables are unchanged. Prompts, credentials and provider item IDs
    are not copied here; the replay identity and request content are hashed.
    """
    __tablename__ = 'execution_tasks_v087'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    request_key: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_sid: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    run_id: Mapped[str] = mapped_column(String(36), nullable=False)
    channel: Mapped[str] = mapped_column(String(24), nullable=False)
    adapter_id: Mapped[str] = mapped_column(String(40), nullable=False)
    response_json: Mapped[str] = mapped_column(Text, default='', nullable=False)
    verification_json: Mapped[str] = mapped_column(Text, default='{}', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)


class VoiceGate(Base):
    __tablename__ = 'voice_gate'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)


class VoiceSession(Base):
    __tablename__ = 'voice_sessions'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_sid: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    call_id: Mapped[str] = mapped_column(String(180), default='', nullable=False)
    state: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    model: Mapped[str] = mapped_column(String(100), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False, index=True)
    close_reason: Mapped[str] = mapped_column(String(40), default='', nullable=False)
    close_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class VoiceToolCall(Base):
    __tablename__ = 'voice_tool_calls'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    request_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(40), nullable=False)
    result_json: Mapped[str] = mapped_column(Text, default='{}', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


# V0.8.3 one durable dispatch per authenticated Realtime transcription item.
# Stores only the hash of user speech and a bounded action receipt, not audio.
class VoiceActionDispatch(Base):
    __tablename__ = 'voice_action_dispatch_v083'
    id: Mapped[str] = mapped_column(String(64), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    transcript_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(16), default='processing', nullable=False)
    result_json: Mapped[str] = mapped_column(Text, default='{}', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class VoicePendingFolder(Base):
    """Short-lived owner-audited slot for a missing name or destination."""
    __tablename__ = 'voice_pending_folder_v085'
    session_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_sid: Mapped[str] = mapped_column(String(64), nullable=False)
    scope: Mapped[str] = mapped_column(String(16), nullable=False)
    pending_name: Mapped[str] = mapped_column(String(70), default='', nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class VoiceProposal(Base):
    __tablename__ = 'voice_proposals'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    content: Mapped[str] = mapped_column(String(500), nullable=False)
    state: Mapped[str] = mapped_column(String(24), default='pending', nullable=False)
    memory_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

# Additive SONIC V0.5 device telemetry and per-session approved operations.
class DeviceTelemetry(Base):
    __tablename__ = 'device_telemetry'
    device_id: Mapped[str] = mapped_column(String(80), primary_key=True)
    agent_version: Mapped[str] = mapped_column(String(30), default='', nullable=False)
    capabilities_json: Mapped[str] = mapped_column(Text, default='[]', nullable=False)
    metrics_json: Mapped[str] = mapped_column(Text, default='{}', nullable=False)
    targets_json: Mapped[str] = mapped_column(Text, default='[]', nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)

class OperatorRequest(Base):
    __tablename__ = 'operator_requests'
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    owner_sid: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    device_id: Mapped[str] = mapped_column(String(80), nullable=False)
    action: Mapped[str] = mapped_column(String(40), nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    digest: Mapped[str] = mapped_column(String(64), nullable=False)
    state: Mapped[str] = mapped_column(String(20), default='pending', nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    lease_hash: Mapped[str] = mapped_column(String(64), default='', nullable=False)
    result_json: Mapped[str] = mapped_column(Text, default='', nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


# V0.8 append-only console stream; no changes to existing device or owner tables.
class OperatorOutput(Base):
    __tablename__ = 'operator_output_v08'
    __table_args__ = (UniqueConstraint('request_id','sequence',name='uq_operator_output_sequence'),)
    id: Mapped[int] = mapped_column(Integer,primary_key=True,autoincrement=True)
    request_id: Mapped[str] = mapped_column(String(36),nullable=False,index=True)
    sequence: Mapped[int] = mapped_column(Integer,nullable=False)
    channel: Mapped[str] = mapped_column(String(12),nullable=False)
    content: Mapped[str] = mapped_column(Text,nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime,default=utcnow,nullable=False)



# Chat-originated PC operations persist completion receipts in chat history.
# Additive table: existing SONIC Postgres tables remain untouched.
class ChatOperation(Base):
    __tablename__ = 'chat_operations_v082'
    request_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_message_id: Mapped[int] = mapped_column(Integer, nullable=False)
    notification_sent: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)


class PersonaPreference(Base):
    """One-owner settings; separate from saved facts and conversation history."""
    __tablename__ = 'persona_preferences'
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    voice_id: Mapped[str] = mapped_column(String(24), default='male_01', nullable=False)
    style: Mapped[str] = mapped_column(String(24), default='friendly', nullable=False)
    intensity: Mapped[str] = mapped_column(String(24), default='balanced', nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, nullable=False)
