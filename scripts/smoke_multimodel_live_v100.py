"""Public GET-only smoke for SONIC V1.0 Multi-Model on Railway staging.

Does not use owner credentials, send API requests to paid model providers,
read private workspace/memory, or execute Windows/trading actions.
"""
from __future__ import annotations

import json
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

BASE="https://sonic-web-staging.up.railway.app"
def fetch(path):
    if not path.startswith("/") or "//" in path or "?" in path:
        raise ValueError("Unsafe smoke path")
    req=Request(BASE+path,method="GET",headers={"User-Agent":"SONIC-v100-ReadOnlySmoke/1.0",
        "Accept":"application/json,text/html,text/css,application/javascript,*/*"})
    try:
        with urlopen(req,timeout=18) as response:
            return response.status,response.read(180_000)
    except HTTPError as e:
        with e:
            return e.code,b""

def check(path,expected=200):
    status,body=fetch(path)
    print(f"GET {path} -> HTTP {status}",flush=True)
    if status!=expected:
        raise AssertionError(f"{path}: expected {expected}, got {status}")
    return body

def main():
    for attempt in range(4):
        try:
            h=json.loads(check("/api/health"))
            if h.get("service")!="SONIC" or h.get("status")!="ok" or h.get("version")!="1.0.0":
                raise AssertionError("Not the intended V1.0.0 staging release")
            break
        except (URLError,ValueError,AssertionError):
            if attempt==3:raise
            time.sleep(4)

    html=check("/")
    for marker in [
        b'id="brainModelControl"',b'id="brainModelSelect"',
        b'id="applyBrainModel"',b'model-router-v101.js',
        b'model-router-v101.css',b'id="graphStage"',
        b'id="sonicMotionAnchor"',
    ]:
        assert marker in html,f"Missing public UI marker {marker[:75]!r}"
    print("PASS: Model selector and original Neural/Motion anchors served")

    ui=check("/assets/model-router-v101.js")
    for expected in (b"/api/models",b"/api/models/selection",b"X-Sonic-CSRF",b"confirm("):
        assert expected in ui
    for forbidden in (b"localStorage",b"sessionStorage",b"innerHTML",b"OPENROUTER_API_KEY"):
        assert forbidden not in ui
    check("/assets/model-router-v101.css")
    check("/assets/sonic-mark.svg")
    check("/assets/graph.js")
    check("/assets/motion-core.js")
    check("/assets/voice.js")
    print("PASS: model router, privacy and retained animation/voice assets")

    assert json.loads(check("/api/session"))["authenticated"] is False
    for private in ["/api/models","/api/setup/status","/api/voice/status",
                    "/api/workspace/items","/api/operator/capabilities"]:
        check(private,401)
    print("PASS: all owner-only APIs denied for anonymous GET")
    print("PASS: V1.0 Multi-Model public staging smoke complete. Paid provider untested.")

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print(f"FAIL: {type(exc).__name__}: {str(exc)[:120]}",file=sys.stderr)
        raise SystemExit(1)
