"""SONIC 0.3 browser + real local HTTP QA, with disposable synthetic data.

No OpenAI calls, production DB, credentials, or TRADEVICEPC operations.
Uses system Chromium when present, otherwise Playwright's Chromium install.
"""
import contextlib
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import subprocess
import sys
import tempfile
import time

import httpx

ROOT = Path(__file__).resolve().parents[1]


@contextlib.contextmanager
def local_server(app_path='sonic.api:app', settings=None):
    # Windows antivirus/SQLite can briefly retain a handle after uvicorn exits.
    # Ignore only the temporary *test* directory cleanup error on Windows.
    with tempfile.TemporaryDirectory(prefix='sonic-neural-qa-',
                                      ignore_cleanup_errors=os.name == 'nt') as temp:
        owner = secrets.token_urlsafe(32)
        with socket.socket() as s:
            s.bind(('127.0.0.1', 0)); port = s.getsockname()[1]
        env = {k: v for k, v in os.environ.items() if not k.startswith(('SONIC_', 'OPENAI_', 'DATABASE_', 'RAILWAY_'))}
        env.update(SONIC_ENV='local', SONIC_PUBLIC_URL=f'http://127.0.0.1:{port}',
                   SONIC_LOCAL_DB=str(Path(temp) / 'qa.sqlite3'), SONIC_SESSION_SECRET=secrets.token_urlsafe(48),
                   SONIC_OWNER_TOKEN_SHA256=hashlib.sha256(owner.encode()).hexdigest(), PYTHONPATH=str(ROOT))
        env.update(settings or {})
        log = open(Path(temp) / 'server.log', 'w')
        proc = subprocess.Popen([sys.executable, '-m', 'uvicorn', app_path, '--host', '127.0.0.1', '--port', str(port)],
                                cwd=ROOT, env=env, stdout=log, stderr=log)
        base = f'http://127.0.0.1:{port}'
        try:
            for _ in range(100):
                try:
                    if httpx.get(base + '/api/health', timeout=.5).status_code == 200: break
                except httpx.HTTPError: pass
                if proc.poll() is not None: raise RuntimeError('Local server exited')
                time.sleep(.08)
            else: raise RuntimeError('Local server not ready')
            yield base, owner
        finally:
            proc.terminate()
            try: proc.wait(timeout=5)
            except subprocess.TimeoutExpired: proc.kill(); proc.wait()
            log.close()

