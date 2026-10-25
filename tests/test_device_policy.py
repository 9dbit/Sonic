import pytest
from sonic.brain import run_tool
from sonic.config import database_ready
from sonic.db import Base
from scripts.windows_agent import config, execute_allowed
from sqlalchemy import create_engine
from sqlalchemy.orm import Session


def test_windows_companion_requires_https(monkeypatch):
    monkeypatch.setenv("SONIC_BASE_URL", "http://external.example.org")
    monkeypatch.setenv("SONIC_DEVICE_TOKEN", "x" * 45)
    with pytest.raises(RuntimeError, match="HTTPS"):
        config()
    monkeypatch.setenv("SONIC_BASE_URL", "https://sonic.example.com")
    assert config()[0] == "https://sonic.example.com"


def test_hosted_db_requires_postgres(monkeypatch):
    monkeypatch.setenv("SONIC_ENV", "staging")
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert database_ready() is False
    monkeypatch.setenv("DATABASE_URL", "postgresql://placeholder")
    assert database_ready() is True


def test_model_cannot_queue_pc_request_without_direct_owner_instruction():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        result = run_tool(db, "pc_request_snapshot", {}, "Tell me a joke")
        assert result["error"] == "EXPLICIT_PC_STATUS_REQUEST_REQUIRED"
        result = run_tool(db, "pc_request_snapshot", {}, "Check the status of my PC")
        assert result["error"] == "WINDOWS_COMPANION_OFFLINE"


def test_no_arbitrary_code_execution_or_trading():
    for value in ["cmd.exe /c dir", "powershell", "sketchup.run", "mt5.close", "files.list", "browser.click"]:
        with pytest.raises(ValueError):
            execute_allowed(value)
