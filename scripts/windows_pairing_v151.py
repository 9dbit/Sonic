"""One-shot trusted iPhone pairing issued by the ALREADY AUTHENTICATED Companion.

The owner places an empty request flag in Companion/state. The running agent
consumes it, calls its existing authenticated API helper, and saves one short
link for local display. This module never opens, decrypts, or copies credentials.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path
from urllib.parse import urlsplit

FLAG = "request-iphone-pairing.flag"
RESULT = "personal-iphone-pairing.json"


def process(here, base, api, *, now=None):
    current = time.time() if now is None else now
    state = Path(here)/"state"
    request = state/FLAG
    result_path = state/RESULT
    if result_path.exists():
        try:
            stored = json.loads(result_path.read_text(encoding="utf-8"))
            if current >= int(stored["expires_at_epoch"]):
                result_path.unlink(missing_ok=True)
        except (OSError, ValueError, KeyError, TypeError):
            result_path.unlink(missing_ok=True)
    if not request.is_file():
        return {"issued": False}
    # Consume before sending: a failed request never silently reissues links.
    request.unlink()
    reply = api("/api/preview/trusted/issue", {})
    link = reply.get("pair_url")
    ttl = reply.get("expires_in_seconds")
    if not isinstance(link, str) or not isinstance(ttl,int) or not 30 <= ttl <= 900:
        raise RuntimeError("INVALID_PAIRING_ISSUE_RECEIPT")
    actual = urlsplit(link)
    expected = urlsplit(base)
    if (actual.scheme != "https" or actual.netloc != expected.netloc or
            actual.path != "/" or not actual.fragment.startswith("sonic-pair=")):
        raise RuntimeError("INVALID_PAIRING_URL_ORIGIN")
    # The URL includes a secret; never print it into logs or generic telemetry.
    state.mkdir(parents=True,exist_ok=True)
    tmp = state/"personal-iphone-pairing.tmp"
    tmp.write_text(json.dumps({"pair_url":link,"expires_at_epoch":int(current+ttl)},
                              separators=(",",":")),encoding="utf-8")
    os.replace(tmp,result_path)
    return {"issued":True,"expires_in_seconds":ttl}
