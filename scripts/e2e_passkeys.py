"""Desktop/mobile passwordless UI using a real Chromium virtual authenticator.

Local disposable database only. No provider requests, genuine biometric samples,
Windows companion commands or production credentials.
"""
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
from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "passkeys-v130"
OUT.mkdir(parents=True, exist_ok=True)
reports = []

with sync_playwright() as pw:
    browser = pw.chromium.launch(headless=True, args=["--no-sandbox", "--enable-unsafe-swiftshader"])
    for name, viewport in (("desktop", {"width": 1440, "height": 900}),
                           ("mobile", {"width": 390, "height": 844})):
        with tempfile.TemporaryDirectory(prefix="sonic-passkey-qa-") as folder:
            with socket.socket() as sock:
                sock.bind(("127.0.0.1", 0)); port = sock.getsockname()[1]
            origin = f"http://localhost:{port}"
            enrollment = secrets.token_urlsafe(32)
            env = {k: v for k, v in os.environ.items()
                   if not k.startswith(("SONIC_", "OPENAI_", "OPENROUTER_", "DEEPSEEK_", "DATABASE_", "RAILWAY_"))}
            env.update(SONIC_ENV="local", SONIC_PASSWORDLESS_LOGIN="true", SONIC_PUBLIC_URL=origin,
                SONIC_SESSION_SECRET=secrets.token_urlsafe(48),
                SONIC_OWNER_TOKEN_SHA256=hashlib.sha256(b"synthetic-owner").hexdigest(),
                SONIC_LOCAL_DB=str(Path(folder) / "test.sqlite3"),
                SONIC_PASSKEY_ENROLLMENT_SHA256=hashlib.sha256(enrollment.encode()).hexdigest(),
                SONIC_PASSKEY_ENROLLMENT_EXPIRES=str(int(time.time()) + 600))
            with open(Path(folder) / "server.log", "w") as log:
                process = subprocess.Popen([sys.executable, "-m", "uvicorn", "sonic.api:app",
                    "--host", "127.0.0.1", "--port", str(port)], cwd=ROOT, env=env, stdout=log, stderr=log)
                context = None
                try:
                    for _ in range(100):
                        try:
                            if httpx.get(origin + "/api/health", timeout=.5).status_code == 200: break
                        except httpx.HTTPError: pass
                        if process.poll() is not None: raise RuntimeError("Local server exited")
                        time.sleep(.1)
                    else: raise RuntimeError("Local server did not start")
                    context = browser.new_context(viewport=viewport, is_mobile=name == "mobile", has_touch=name == "mobile")
                    page = context.new_page()
                    errors = []
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    cdp = context.new_cdp_session(page)
                    cdp.send("WebAuthn.enable")
                    cdp.send("WebAuthn.addVirtualAuthenticator", {"options": {
                        "protocol": "ctap2", "transport": "internal", "hasResidentKey": True,
                        "hasUserVerification": True, "isUserVerified": True,
                        "automaticPresenceSimulation": True}})
                    page.goto(origin + "/#setup=" + enrollment, wait_until="networkidle")
                    expect(page.locator("#passkeySetup")).to_be_visible()
                    expect(page.locator("#ownerToken")).to_be_hidden()
                    assert "setup=" not in page.url
                    assert enrollment not in page.content()
                    page.locator("#passkeySetup").click()
                    expect(page.locator("#loginOverlay")).to_be_hidden(timeout=20000)
                    assert page.request.get(origin + "/api/session").json()["authenticated"]
                    page.locator('.nav[data-tab="setup"]').click()
                    expect(page.locator("#passkeyRegister")).to_be_visible()
                    expect(page.locator("#passkeyList .passkey-row")).to_have_count(1)
                    expect(page.locator("#passkeyList button")).to_be_disabled()
                    page.locator("#setupLogout").click()
                    expect(page.locator("#passkeyLogin")).to_be_visible(timeout=15000)
                    expect(page.locator("#ownerToken")).to_be_hidden()
                    assert not page.request.get(origin + "/api/session").json()["authenticated"]
                    page.screenshot(path=str(OUT / (name + "-login.png")))
                    page.locator("#passkeyLogin").click()
                    expect(page.locator("#loginOverlay")).to_be_hidden(timeout=20000)
                    assert page.request.get(origin + "/api/session").json()["authenticated"]
                    page.locator('.nav[data-tab="setup"]').click()
                    expect(page.locator("#passkeyList .passkey-row")).to_have_count(1)
                    page.screenshot(path=str(OUT / (name + "-settings.png")))
                    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth + 2")
                    assert not errors, errors
                    reports.append({"viewport": name, "enrollment_without_owner_token": True,
                        "native_webauthn_login": True, "logout_verified": True,
                        "token_input_hidden": True, "real_biometric_test": False,
                        "javascript_errors": errors})
                finally:
                    if context: context.close()
                    process.terminate()
                    try: process.wait(timeout=5)
                    except subprocess.TimeoutExpired: process.kill(); process.wait()
    browser.close()
(OUT / "report.json").write_text(json.dumps(reports, indent=2), encoding="utf-8")
print(json.dumps(reports, indent=2))
