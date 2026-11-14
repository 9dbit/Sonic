"""Bounded, read-only Windows diagnostics for SONIC Companion v1.4.8.

No user-controlled commands, addresses, file reads, or process termination.
All processes stay in the non-elevated Windows Companion identity.
"""
from __future__ import annotations
from datetime import datetime
import os
import platform
import re
import subprocess
import time

ACTIONS = frozenset(("diagnostics.clock", "diagnostics.ping",
                     "diagnostics.processes", "diagnostics.events"))

def _powershell(command, timeout=8):
    p = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", command],
                       capture_output=True, text=True, errors="replace",
                       shell=False, timeout=timeout, creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
    if p.returncode:
        raise RuntimeError("DIAGNOSTIC_UNAVAILABLE")
    return p.stdout.strip()

def _clock():
    from datetime import datetime
    now = datetime.now().astimezone()
    return {"observed_at": now.isoformat(), "timezone": str(now.tzinfo),
            "utc_offset_seconds": int(now.utcoffset().total_seconds()),
            "source": "windows_local_clock", "ntp_verified": False}

def _ping():
    import socket
    # Only two fixed public endpoints. Do not scan ports or use arbitrary targets.
    out = []
    for label, target in (("cloudflare_dns", "1.1.1.1"), ("google_dns", "8.8.8.8")):
        # Standard Windows ping, count 2, timeout 900ms, total bounded.
        try:
            p = subprocess.run(["ping.exe", "-n", "2", "-w", "900", target],
                               capture_output=True, text=True, errors="replace",
                               shell=False, timeout=7, creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
            # Locale-independent packet loss from simple response TTL indicators.
            received = len(re.findall(r"\bTTL\s*=", p.stdout, flags=re.I))
            out.append({"target": label, "sent": 2, "received": min(2,received),
                        "reachable": received > 0, "status": "sampled"})
        except (OSError, subprocess.TimeoutExpired):
            out.append({"target": label, "sent": 2, "received": 0,
                        "reachable": False, "status": "unavailable"})
    return {"targets": out, "sampling": "2 ICMP echoes each; no latency assumed",
            "observed_at": datetime.now().astimezone().isoformat()}

def _processes():
    try:
        import psutil
    except ImportError:
        return {"available": False, "reason": "psutil_missing", "top_memory": []}
    rows = []
    for p in psutil.process_iter(["pid","name","memory_info"]):
        try:
            info = p.info
            rows.append({"pid": int(info["pid"]),
                         "name": str(info.get("name") or "")[:90],
                         "memory_bytes": max(0,int(info["memory_info"].rss if info.get("memory_info") else 0))})
        except (psutil.Error, ValueError, TypeError, OSError):
            continue
    rows.sort(key=lambda x: x["memory_bytes"], reverse=True)
    return {"count": len(rows), "top_memory": rows[:12],
            "observed_at": datetime.now().astimezone().isoformat(),
            "notice": "Read only; total CPU time is not instantaneous CPU load."}

def _events():
    # No event message content is retrieved, because Windows logs may hold sensitive data.
    cmd = ("Get-WinEvent -FilterHashtable @{LogName='System';StartTime=(Get-Date).AddHours(-24);Level=2} "
           "-MaxEvents 12 -ErrorAction SilentlyContinue | "
           "ForEach-Object { [pscustomobject]@{Id=$_.Id;ProviderName=$_.ProviderName;ObservedAt=$_.TimeCreated.ToUniversalTime().ToString(\'o\')} } | "
           "ConvertTo-Json -Compress -Depth 3")
    try:
        raw = _powershell(cmd, 9)
        import json
        parsed = json.loads(raw) if raw else []
        rows = parsed if isinstance(parsed, list) else [parsed]
        events = [{"id": max(0,int(e.get("Id",0))),
                   "provider": str(e.get("ProviderName",""))[:80],
                   **({"at_utc": str(e["ObservedAt"])[:40]} if e.get("ObservedAt") else {})}
                  for e in rows[:12] if isinstance(e,dict)]
        return {"system_errors_last_24h_sample": events,
                "max_events": 12, "message_text_collected": False,
                "notice": "Most recent errors, not necessarily a complete count."}
    except (RuntimeError, ValueError, OSError, subprocess.TimeoutExpired):
        return {"system_errors_last_24h_sample": [], "available": False,
                "message_text_collected": False}

def run(action):
    if os.name != "nt" or action not in ACTIONS:
        raise PermissionError("DIAGNOSTIC_NOT_PERMITTED")
    result = {"diagnostics.clock": _clock, "diagnostics.ping": _ping,
              "diagnostics.processes": _processes, "diagnostics.events": _events}[action]()
    return {"kind": action, "read_only": True, "result": result}
