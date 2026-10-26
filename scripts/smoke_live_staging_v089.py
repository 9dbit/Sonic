"""Public staging smoke test for SONIC V0.8.9.

Only unauthenticated GET requests. No token, private content, Windows operation,
voice session, credit-consuming OpenAI call, database mutation, or local file read.
"""
import json
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ORIGIN = "https://sonic-web-staging.up.railway.app"
TIMEOUT = 18


def get(path: str):
    if not path.startswith("/") or "//" in path:
        raise ValueError("INVALID_PATH")
    req = Request(ORIGIN + path, method="GET",
                  headers={"User-Agent": "SONIC-release-smoke/0.8.9",
                           "Accept": "application/json,text/html,*/*"})
    try:
        with urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, resp.read(160_000), resp.headers.get("Content-Type", "")
    except HTTPError as error:
        with error:
            # Never print an error body or authentication-related diagnostics.
            return error.code, b"", error.headers.get("Content-Type", "")


def assert_status(path: str, expected: int):
    status, body, content_type = get(path)
    print(f"GET {path}: HTTP {status}")
    if status != expected:
        raise AssertionError(f"GET {path} expected HTTP {expected}, got {status}")
    return body, content_type


def main():
    # Bounded retries only for a brief in-progress blue/green deployment.
    for attempt in range(3):
        try:
            raw, _ = assert_status("/api/health", 200)
            health = json.loads(raw)
            assert health.get("service") == "SONIC", "not SONIC"
            assert health.get("status") == "ok", "not healthy"
            assert health.get("version") == "0.8.9", "wrong deployed version"
            print("Health status and expected release version verified")
            break
        except (URLError, TimeoutError, AssertionError, ValueError, json.JSONDecodeError):
            if attempt == 2:
                raise
            time.sleep(3)

    html, html_type = assert_status("/", 200)
    assert b"pc-workspace-v089.js" in html, "PC Workspace script not linked"
    assert b"pc-workspace-v089.css" in html, "PC Workspace stylesheet not linked"
    assert b"wsPcDeviceTab" in html, "PC Workspace tab missing"
    assert b"0.8.9" in html, "HTML version label missing"
    print("HTML V0.8.9 UI wiring verified")

    js, _ = assert_status("/assets/pc-workspace-v089.js", 200)
    assert b"SonicPCWorkspace" in js and b"file.read" in js and b"file.list" in js
    assert b"innerHTML" not in js and b"localStorage" not in js
    print("Read-only Windows UI script and safe text rendering verified")

    css, _ = assert_status("/assets/pc-workspace-v089.css", 200)
    assert b"ws-pc-mode" in css
    print("PC Workspace stylesheet served")

    raw, _ = assert_status("/api/session", 200)
    assert json.loads(raw).get("authenticated") is False
    print("Anonymous session contains no authenticated owner")

    for path in ("/api/workspace/items", "/api/integrations",
                 "/api/voice/status", "/api/operator/capabilities"):
        assert_status(path, 401)
    print("Private owner APIs all denied unauthenticated GETs")

    print("PASS: public staging smoke tests, no credentials or mutations")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FAIL: {type(exc).__name__}: {str(exc)[:160]}", file=sys.stderr)
        sys.exit(1)
