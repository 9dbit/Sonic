#!/usr/bin/env python3
"""SONIC Windows companion V0.1. No shell, no file IO, no GUI automation.

Run manually on TRADEVICEPC after the owner explicitly authorizes pairing.
Uses the Python standard library only and makes outbound HTTPS requests.
"""
import json
import os
import platform
import socket
import sys
import time
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


def config():
    base = os.environ.get("SONIC_BASE_URL", "").rstrip("/")
    token = os.environ.get("SONIC_DEVICE_TOKEN", "")
    device = os.environ.get("SONIC_DEVICE_ID", "TRADEVICEPC")
    url = urlparse(base)
    if not base or not token or len(token) < 32:
        raise RuntimeError("Set SONIC_BASE_URL and a 32+ character SONIC_DEVICE_TOKEN")
    if url.scheme != "https" and not (
        url.scheme == "http" and url.hostname in ("127.0.0.1", "localhost")
    ):
        raise RuntimeError("SONIC_BASE_URL must be HTTPS except localhost")
    if url.username or url.password or url.path not in ("", "/") or url.query or url.fragment:
        raise RuntimeError("Use an origin URL without credentials, paths or parameters")
    if len(device) > 80 or not device:
        raise RuntimeError("Invalid SONIC_DEVICE_ID")
    return base, token, device


def post(base, token, route, payload):
    data = json.dumps(payload).encode("utf-8")
    request = Request(
        base + route, data=data,
        headers={
            "Authorization": "Bearer " + token,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }, method="POST"
    )
    # urllib validates the server's TLS certificate by default.
    with urlopen(request, timeout=12) as response:
        if response.status != 200:
            raise RuntimeError("Unexpected response status")
        body = response.read(4096)
    return json.loads(body)


def system_status():
    """Read-only, deliberately narrow system snapshot; no process or file contents."""
    return {
        "hostname": socket.gethostname()[:120],
        "platform": platform.platform()[:200],
        "python": platform.python_version(),
        "logical_cpu_count": os.cpu_count(),
        "sonic_agent_version": "0.1.0",
        "capabilities": ["system.status"]
    }


def execute_allowed(action):
    if action == "system.status":
        return system_status()
    raise ValueError("Action not allowed")


def main():
    base, token, device = config()
    print("SONIC Windows companion started. Read-only: system.status. Stop with Ctrl+C.")
    while True:
        try:
            post(base, token, "/api/device/heartbeat", {
                "device_id": device, "hostname": socket.gethostname()[:120],
                "platform": platform.platform()[:200]
            })
            job = post(base, token, "/api/device/next", {}).get("job")
            if job:
                job_id = str(job.get("id", ""))
                action = str(job.get("action", ""))
                try:
                    result = execute_allowed(action)
                    success = True
                except Exception:
                    result, success = {"error": "UNSUPPORTED_ACTION"}, False
                post(base, token, "/api/device/result", {
                    "device_id": device, "job_id": job_id,
                    "success": success, "result": result
                })
        except (HTTPError, URLError, ValueError, RuntimeError, TimeoutError) as error:
            # Never print token or full request URL with query parameters.
            print("SONIC companion connection unavailable:", type(error).__name__)
        time.sleep(20)


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, RuntimeError) as error:
        print("SONIC companion stopped:", type(error).__name__)
        sys.exit(0 if isinstance(error, KeyboardInterrupt) else 1)
