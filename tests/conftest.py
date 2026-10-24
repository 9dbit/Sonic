import hashlib
import pytest
from fastapi.testclient import TestClient

@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("SONIC_OWNER_TOKEN_SHA256", hashlib.sha256(b"owner-test-token").hexdigest())
    monkeypatch.setenv("SONIC_DEVICE_TOKEN_SHA256", hashlib.sha256(b"device-test-token").hexdigest())
    monkeypatch.setenv("SONIC_SESSION_SECRET", "z" * 64)
    monkeypatch.setenv("SONIC_DEVICE_ID", "TRADEVICEPC")
    monkeypatch.setenv("SONIC_LOCAL_DB", str(tmp_path / "sonic.sqlite3"))
    monkeypatch.setenv("SONIC_ENV", "local")
    monkeypatch.delenv("RAILWAY_ENVIRONMENT_NAME", raising=False)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    import sonic.db as storage
    if storage._engine:
        storage._engine.dispose()
    storage._engine = None
    storage._Session = None
    from sonic.api import app
    with TestClient(app) as test_client:
        yield test_client
    if storage._engine:
        storage._engine.dispose()
    storage._engine = None
    storage._Session = None
