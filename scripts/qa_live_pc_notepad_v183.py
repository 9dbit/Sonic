"""Manual Windows proof: synthetic authenticated backend + REAL Notepad open.

Requires explicit --run-notepad. Runs the installed independent allowlist under
the current limited interactive user. Never reads live credentials/database,
changes the Companion task, installs software, types in or closes any app.
Notepad is deliberately left open. This is not a live Railway-owner-session test.
"""
from __future__ import annotations
import argparse
import ctypes
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import secrets
import sys
import time
from uuid import uuid4

import httpx
from qa_server import local_server

INSTALLED = Path(r"D:\Sonic\companion\windows_window_v090.py")
OUTPUT = Path("artifacts/pc-tools-v183/live-notepad.json")


def mt5_snapshot():
    import psutil
    return sorted((p.pid, p.create_time()) for p in psutil.process_iter(["name"])
                  if (p.info.get("name") or "").casefold() in ("terminal64.exe", "terminal.exe"))


def run():
    if os.name != "nt":
        raise RuntimeError("This explicit live proof requires Windows")
    if ctypes.windll.shell32.IsUserAnAdmin():
        raise RuntimeError("Run under the existing limited Windows account")
    session = ctypes.c_uint()
    if not ctypes.windll.kernel32.ProcessIdToSessionId(os.getpid(), ctypes.byref(session)) or not session.value:
        raise RuntimeError("An interactive Windows session is required")
    spec = importlib.util.spec_from_file_location("sonic_installed_window_proof", INSTALLED)
    if spec is None or spec.loader is None:
        raise RuntimeError("Installed Windows allowlist module not found")
    control = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(control)
    # This explicit manual proof enables only its own process, never the task.
    old_flag = os.environ.get("SONIC_WINDOW_CONTROL_ENABLED")
    os.environ["SONIC_WINDOW_CONTROL_ENABLED"] = "1"
    report = {"scope": "synthetic_backend_real_installed_notepad_control",
              "live_railway_owner_session": False, "limited_user": True,
              "interactive_session": session.value, "status": "preparing",
              "software_install_executed": False, "app_closed": False}
    try:
        before = control._window_list("notepad")
        if len(before) > 1:
            raise RuntimeError("Multiple Notepad windows exist; no user window will be closed")
        mt5_before = mt5_snapshot()
        token = secrets.token_urlsafe(32)
        settings = {"SONIC_DEVICE_TOKEN_SHA256": hashlib.sha256(token.encode()).hexdigest(),
                    "SONIC_DEVICE_ID": "TRADEVICEPC"}
        with local_server(settings=settings) as (base, owner), httpx.Client(base_url=base, timeout=15) as browser:
            def agent(route, payload):
                response = httpx.post(base + route, headers={"Authorization": "Bearer " + token},
                                      json=payload, timeout=15)
                if response.status_code != 200:
                    raise RuntimeError("Synthetic device endpoint failed: " + route + " status=" + str(response.status_code))
                return response.json()

            login = browser.post("/api/login", json={"token": owner})
            if login.status_code != 200:
                raise RuntimeError("Synthetic owner login failed")
            headers = {"X-Sonic-CSRF": login.json()["csrf"], "X-Sonic-Async": "1"}

            def chat(message, **extra):
                response = browser.post("/api/chat", headers=headers,
                    json={"message": message, "request_id": str(uuid4()), **extra})
                if response.status_code != 200:
                    raise RuntimeError("Synthetic owner chat failed with status=" + str(response.status_code))
                return response.json()

            agent("/api/device/heartbeat", {
                "device_id": "TRADEVICEPC", "hostname": "SONIC isolated Windows proof", "platform": "Windows",
                "agent_version": "0.10.0", "capabilities": [
                    "system.status", "system.metrics", "window.list", "window.open", "window.focus", "window.close"],
                "metrics": {}, "gui_targets": []})
            proposal = chat("run notepad")
            proposals = proposal.get("operator_proposals", [])
            if len(proposals) != 1 or proposals[0].get("action") != "window.open":
                raise RuntimeError("Expected exactly one allowlisted Notepad approval proposal")
            proposal_id = proposals[0]["id"]
            if agent("/api/device/operator/next", {}).get("job") is not None:
                raise RuntimeError("A job became executable before approval")
            report["no_execution_before_approval"] = True
            approved = chat("setuju", approval_request_id=proposal_id)
            if not any(job.get("id") == proposal_id for job in approved.get("operator_jobs", [])):
                raise RuntimeError("Exact proposal was not approved")
            job = None
            for _ in range(25):
                job = agent("/api/device/operator/next", {}).get("job")
                if job:
                    break
                time.sleep(.2)
            if (not job or job.get("id") != proposal_id or job.get("action") != "window.open"
                    or job.get("payload") != {"app": "notepad"}):
                raise RuntimeError("Lease is not the exact approved Notepad operation")
            lease = {"request_id": job["id"], "lease": job["lease"]}
            if not agent("/api/device/operator/check", lease).get("execute"):
                raise RuntimeError("Approved lease is no longer executable")
            report["status"] = "executing_notepad"
            result = control.control(job["action"], job["payload"])
            opened = result.get("opened") is True
            agent("/api/device/operator/result", {**lease, "success": opened, "result": result})
            if not opened:
                raise RuntimeError("Installed Windows broker did not verify a visible Notepad window")
            after = control._window_list("notepad")
            if len(after) != 1:
                raise RuntimeError("Visible Notepad target is ambiguous after execution")
            control._verify_target("notepad", after[0])
            receipt = browser.get("/api/operator/requests/" + proposal_id)
            if receipt.status_code != 200 or receipt.json().get("state") != "done":
                raise RuntimeError("Authenticated result was not retained as done")
            mt5_unchanged = mt5_snapshot() == mt5_before
            if not mt5_unchanged:
                raise RuntimeError("MT5 process snapshot changed during proof; investigate separately")
            report.update(status="passed", authenticated_approval=True, authenticated_device_receipt=True,
                retained_state="done", actual_result=result, notepad_windows_before=len(before),
                notepad_windows_after=len(after), verified_notepad_pid=after[0]["pid"],
                mt5_process_snapshot_unchanged=mt5_unchanged, notepad_left_open=True)
    except Exception as exc:
        report.update(status="failed", error_type=type(exc).__name__, error=str(exc)[:240])
        raise
    finally:
        if old_flag is None:
            os.environ.pop("SONIC_WINDOW_CONTROL_ENABLED", None)
        else:
            os.environ["SONIC_WINDOW_CONTROL_ENABLED"] = old_flag
        OUTPUT.parent.mkdir(parents=True, exist_ok=True)
        OUTPUT.write_text(json.dumps(report, indent=2), encoding="utf-8")
        print(json.dumps(report, indent=2))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-notepad", action="store_true",
                        help="Explicitly permit one real allowlisted Notepad open/focus; leave it open")
    args = parser.parse_args()
    if not args.run_notepad:
        parser.error("Explicit --run-notepad is required; no PC action has been performed")
    run()
