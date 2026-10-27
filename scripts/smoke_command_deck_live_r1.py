"""SONIC Command Deck R1 external staging acceptance (GET only, no secrets).

Runs from GitHub Actions against a public Railway staging URL, not from the
owner's TRADEVICEPC. Does not log in, send prompts/audio, create data or invoke
device actions. This is a read-only health, assets and access-control check.
"""
from __future__ import annotations

import json
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE = "https://sonic-web-staging.up.railway.app"
TIMEOUT = 17


def get(path):
    if not path.startswith("/") or "//" in path or "?" in path:
        raise ValueError("unsafe smoke path")
    req = Request(
        BASE + path,
        method="GET",
        headers={
            "User-Agent": "SONIC-CommandDeck-R1-ReadOnlySmoke",
            "Accept": "application/json,text/html,text/css,application/javascript,image/svg+xml,*/*",
        },
    )
    try:
        with urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, resp.read(220_000)
    except HTTPError as error:
        with error:
            return error.code, b""


def check(path, status):
    actual, data = get(path)
    print(f"GET {path}: HTTP {actual}", flush=True)
    if actual != status:
        raise AssertionError(f"expected HTTP {status} got {actual} for {path}")
    return data


def main():
    for attempt in range(4):
        try:
            health = json.loads(check("/api/health", 200))
            if health.get("service") != "SONIC" or health.get("status") != "ok":
                raise AssertionError("health service/status mismatch")
            if health.get("version") != "0.9.0":
                raise AssertionError(f"expected deployed 0.9.0, got {health.get('version')}")
            print("PASS: SONIC health and app backend version verified")
            break
        except (URLError, TimeoutError, AssertionError, ValueError, json.JSONDecodeError):
            if attempt == 3:
                raise
            time.sleep(4)

    html = check("/", 200)
    for marker in [
        b'SONIC | Intelligence Console',
        b'body class="sonic-shell-v100"',
        b'/assets/sonic-shell-v100.css?v=1.0.0',
        b'/assets/sonic-shell-v100.js?v=1.0.0',
        b'/assets/sonic-mark.svg',
        b'id="graphStage"',
        b'id="sonicMotionAnchor"',
        b'id="pcWindowControl"',
        b'id="wsPcCloudTab"',
    ]:
        assert marker in html, f"HTML missing {marker.decode('utf-8')}"
    print("PASS: deployed Command Deck HTML with original motion/graph UI anchors")

    css = check("/assets/sonic-shell-v100.css", 200)
    assert b".sonic-shell-v100" in css
    assert b".app{isolation:auto}" in css, "Voice focus overlay Mute regression fix not deployed"
    assert b"brand-symbol" in css
    print("PASS: scoped sci-fi theme and voice overlay fix")

    ui = check("/assets/sonic-shell-v100.js", 200)
    assert b"MutationObserver" in ui
    assert b"goToWorkspace" in ui and b"goToDevices" in ui
    for disallowed in (b"localStorage", b"innerHTML", b"navigator.mediaDevices"):
        assert disallowed not in ui
    print("PASS: DOM-only navigation helper with no private API/media handling")

    svg = check("/assets/sonic-mark.svg", 200)
    assert b"<svg" in svg and b"</svg>" in svg and b"<script" not in svg
    print("PASS: original vector SONIC logo served")

    for path in [
        "/assets/graph.js", "/assets/graph-layout.js",
        "/assets/motion-core.js", "/assets/motion-math.js",
        "/assets/motion-v06.css",
        "/assets/window-manager-v090.js",
    ]:
        check(path, 200)
    print("PASS: existing Neural Brain, particle, and Window Control assets served")

    session = json.loads(check("/api/session", 200))
    assert session.get("authenticated") is False
    for path in (
        "/api/workspace/items",
        "/api/integrations",
        "/api/operator/capabilities",
        "/api/voice/status",
    ):
        check(path, 401)
    print("PASS: anonymous access is denied at four protected owner endpoints")
    print("PASS: all read-only staging acceptance checks")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FAIL: {type(exc).__name__}: {str(exc)[:170]}", file=sys.stderr)
        raise SystemExit(1)
