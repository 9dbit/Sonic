"""SONIC v1.5.3 owner/private vs public guest browser acceptance.

Uses a synthetic owner token, disposable local database and no actual PC/AI
actions or credentials. Run: python scripts/e2e_owner_portal_v153.py
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import shutil

from playwright.sync_api import sync_playwright, expect
from qa_server import local_server
from e2e_auth_isolation_v181 import assert_locked

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "owner-portal-v153"
OUT.mkdir(parents=True, exist_ok=True)

settings = {
    "SONIC_OPEN_PREVIEW": "true",
    "SONIC_OWNER_ENTRY_ENABLED": "true",
    "SONIC_PASSWORDLESS_LOGIN": "false",
    "SONIC_LOCAL_AI_ENABLED": "false",
    "SONIC_PREVIEW_PAID_ACTIONS": "false",
    "PYTHONPATH": str(ROOT) + os.pathsep + os.environ.get("PYTHONPATH", ""),
}

with local_server(settings=settings) as (base, owner_token), sync_playwright() as playwright:
    executable = shutil.which("chromium") or shutil.which("chrome")
    if not executable:
        executable = next((str(path) for path in (
            Path("C:/Program Files/Google/Chrome/Application/chrome.exe"),
            Path("C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe")
        ) if path.is_file()), None)
    browser = playwright.chromium.launch(
        executable_path=executable or None,
        headless=True, args=["--no-sandbox", "--enable-unsafe-swiftshader"])
    results = []
    for name, width, height, mobile in (
        ("iphone-390", 390, 844, True),
        ("compact-360", 360, 740, True),
        ("desktop", 1440, 900, False),
    ):
        guest = browser.new_page(viewport={"width": width, "height": height},
                                 device_scale_factor=1, has_touch=mobile, is_mobile=mobile)
        guest_errors = []
        guest.on("pageerror", lambda error: guest_errors.append(str(error)))
        guest.goto(base + "/", wait_until="domcontentloaded")
        expect(guest.locator("body")).to_have_class(__import__("re").compile("sonic-open-preview"))
        expect(guest.locator("#loginOverlay")).to_be_hidden()
        expect(guest.locator("#localAIControl")).to_be_hidden()
        preview_session = guest.request.get(base + "/api/session").json()
        assert preview_session.get("preview") is True and not preview_session.get("authenticated")
        assert guest.request.get(base + "/api/local-ai/status").status == 401
        assert not guest_errors, guest_errors

        page = browser.new_page(viewport={"width": width, "height": height},
                                device_scale_factor=1, has_touch=mobile, is_mobile=mobile)
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(base + "/owner", wait_until="domcontentloaded")
        expect(page.locator("#loginOverlay")).to_be_visible()
        expect(page.locator("#ownerToken")).to_be_visible()
        assert_locked(page)
        page.screenshot(path=str(OUT / (name + "-before-login.png")), full_page=False)
        assert "sonic-open-preview" not in (page.locator("body").get_attribute("class") or "")
        manifest = page.request.get(base + "/owner.webmanifest").json()
        assert manifest["start_url"] == "/owner"
        ui = page.evaluate("""() => ({
            width: document.documentElement.clientWidth,
            scrollWidth: document.documentElement.scrollWidth,
            bg: getComputedStyle(document.body).backgroundColor,
            accent: getComputedStyle(document.documentElement).getPropertyValue('--accent').trim()
        })""")
        assert ui["scrollWidth"] <= ui["width"] + 1, ui
        assert ui["bg"] == "rgb(5, 6, 7)" and ui["accent"] == "#3d95ff", ui
        page.locator("#ownerToken").fill(owner_token)
        page.locator('#loginForm button[type="submit"]').click()
        expect(page.locator("#loginOverlay")).to_be_hidden(timeout=15000)
        session = page.request.get(base + "/api/session").json()
        assert session["authenticated"] is True
        assert isinstance(session["csrf"], str) and len(session["csrf"]) >= 20
        assert page.request.get(base + "/api/local-ai/status").status == 200
        page.locator('.nav[data-tab="devices"]').click()
        expect(page.locator("#localAIControl")).to_be_visible()
        expect(page.locator("#localAIStart")).to_be_disabled()
        expect(page.locator("#localAIStop")).to_be_disabled()
        assert not errors, errors
        page.screenshot(path=str(OUT / (name + ".png")), full_page=False)

        # Explicit logout revokes the server-side owner session.
        result = page.request.post(base + "/api/logout",
                                   headers={"X-Sonic-CSRF": session["csrf"]})
        assert result.status == 200, result.text()
        assert page.request.get(base + "/api/session").json()["preview"] is True
        assert page.request.get(base + "/api/local-ai/status").status == 401
        page.reload(wait_until="domcontentloaded")
        expect(page.locator("#loginOverlay")).to_be_visible()
        assert_locked(page)
        page.screenshot(path=str(OUT / (name + "-after-logout.png")), full_page=False)
        results.append({"viewport": name, "guest": "isolated",
                        "private_login": "passed", "owner_status": "authenticated",
                        "after_logout": "guest", "no_overflow": True,
                        "js_errors": len(errors)})
        page.close()
        guest.close()
    browser.close()
    (OUT / "report.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
print("OWNER_PORTAL_BROWSER_QA_PASS")
# Keep model-selection/runtime truth under the existing owner-browser CI gate.
# This uses the same disposable QA server and synthetic tokens, not live APIs.
import runpy
runpy.run_path(str(ROOT / 'scripts' / 'e2e_model_truth_v182.py'), run_name='__main__')
