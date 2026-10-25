#!/usr/bin/env python3
"""Real HTTP + read-only companion + restart checks, using synthetic LOCAL credentials.
No production credentials, no OpenAI network calls, no persistent PC agent.
"""
from __future__ import annotations
from contextlib import contextmanager
import hashlib
import json
import os
from pathlib import Path
import secrets
import socket
import subprocess
import sys
import tempfile
import time
import httpx

ROOT = Path(__file__).resolve().parent.parent


def stop_child(process):
    if process.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=15)
    else:
        process.terminate()
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


@contextmanager
def local_server():
    with tempfile.TemporaryDirectory(prefix="sonic-e2e-") as temp:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        base = "http://127.0.0.1:%d" % port
        owner, device = secrets.token_urlsafe(48), secrets.token_urlsafe(48)
        env = {k: v for k, v in os.environ.items()
               if not k.startswith(("SONIC_", "RAILWAY_")) and k not in ("DATABASE_URL", "OPENAI_API_KEY")}
        env.update({
            "SONIC_ENV": "local", "SONIC_PUBLIC_URL": base,
            "SONIC_LOCAL_DB": str(Path(temp) / "test.sqlite3"),
            "SONIC_OWNER_TOKEN_SHA256": hashlib.sha256(owner.encode()).hexdigest(),
            "SONIC_DEVICE_TOKEN_SHA256": hashlib.sha256(device.encode()).hexdigest(),
            "SONIC_SESSION_SECRET": secrets.token_urlsafe(48),
            "SONIC_DEVICE_ID": "SONIC-E2E-ONLY"
        })
        child = None
        with (Path(temp) / "server.log").open("wb") as log:
            def start():
                nonlocal child
                child = subprocess.Popen([sys.executable, "-m", "uvicorn", "sonic.api:app",
                    "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT, env=env,
                    stdout=log, stderr=subprocess.STDOUT)
                for _ in range(120):
                    if child.poll() is not None:
                        raise RuntimeError("Local SONIC test server exited; no production resources were used")
                    try:
                        if httpx.get(base + "/api/health", timeout=1, trust_env=False).status_code == 200:
                            return
                    except httpx.RequestError:
                        pass
                    time.sleep(0.1)
                raise RuntimeError("Local SONIC test server did not become ready")
            def restart():
                stop_child(child)
                start()
            try:
                start()
                yield base, owner, device, env, restart
            finally:
                if child:
                    stop_child(child)


def run():
    passed = []
    with local_server() as (base, owner, device, env, restart):
        with httpx.Client(base_url=base, trust_env=False, timeout=10) as client:
            assert client.get("/api/health").json()["setup_required"] is True
            assert client.get("/api/history").status_code == 401
            assert client.post("/api/login", json={"token": "incorrect-test-token"}).status_code == 401
            login = client.post("/api/login", json={"token": owner})
            assert login.status_code == 200
            assert "httponly" in login.headers["set-cookie"].lower()
            headers = {"X-Sonic-CSRF": login.json()["csrf"]}
            passed.append("real_http_login_and_denial")
            assert client.post("/api/memories", json={"text":"Temporary E2E note"}).status_code == 403
            note = client.post("/api/memories", json={"text":"Temporary E2E note"}, headers=headers)
            assert note.status_code == 200
            note_id = note.json()["id"]
            restart()
            assert any(x["id"] == note_id for x in client.get("/api/memories").json()["memories"])
            passed.append("memory_and_session_survive_backend_restart")
            setup = client.get("/api/setup/status")
            assert setup.status_code == 200 and setup.json()["database_connected"] is True
            assert setup.json()["provider_key_configured"] is False
            assert client.post("/api/setup/test-provider", headers=headers).status_code == 503
            assert client.post("/api/chat", json={"message":"Offline test"}, headers=headers).status_code == 503
            passed.append("missing_provider_fails_closed")
            agent_env = dict(env, SONIC_BASE_URL=base, SONIC_DEVICE_TOKEN=device)
            def cycle():
                result = subprocess.run([sys.executable, "scripts/windows_agent.py", "--once"],
                    cwd=ROOT, env=agent_env, capture_output=True, text=True, timeout=25)
                assert result.returncode == 0, "Local read-only companion failed"
            cycle()
            assert client.get("/api/device/status").json()["connected"] is True
            assert client.post("/api/device/jobs", json={"action":"shell.exec"}, headers=headers).status_code == 403
            job = client.post("/api/device/jobs", json={"action":"system.status"}, headers=headers).json()
            cycle()
            outcome = client.get("/api/device/jobs/" + job["id"]).json()
            assert outcome["state"] == "done"
            assert outcome["result"]["capabilities"] == ["system.status"]
            assert outcome["result"]["hostname"] == socket.gethostname()[:120]
            passed.append("actual_companion_http_status_roundtrip")
            assert client.delete("/api/memories/%s" % note_id, headers=headers).status_code == 200
            cookie = client.cookies.get("sonic_session")
            assert client.post("/api/logout", headers=headers).status_code == 200
            client.cookies.set("sonic_session", cookie)
            assert client.get("/api/history").status_code == 401
            passed.append("memory_delete_and_logged_out_cookie_replay_denied")
    print(json.dumps({"status":"PASS", "checks":passed,
        "live_openai_tested":False, "permanent_agent_installed":False,
        "environment":"isolated loopback with disposable synthetic credentials"}))


if __name__ == "__main__":
    run()
