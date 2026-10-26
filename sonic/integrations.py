"""SONIC's own execution-adapter registry.

This is a capability *inventory*, not a credentials bridge. A ChatGPT connector
grant is not a grant to the independent SONIC app. Only authenticated local
heartbeat/capability observations can mark the Windows native adapter online.
Third-party candidates stay unconnected until an explicit SONIC-side handshake
and independently verified integration health check are implemented.
"""
from __future__ import annotations

import json
from datetime import datetime

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import auth
from .config import setting
from .db import Device, DeviceTelemetry, OperatorRequest, get_db, utcnow

router = APIRouter()

# The initial allowlisted candidates. A provider in this list is not necessarily
# installed, authenticated, connected, callable, or given execution rights.
CATALOG = (
    {
        "id": "windows-native",
        "name": "Windows Native",
        "type": "local_agent",
        "purpose": "File, folder, process, Task Manager and approved Windows operations.",
        "description": "SONIC's own outbound-only limited Windows companion on TRADEVICEPC.",
        "requires": "Windows companion heartbeat, live capabilities, owner command policy.",
        "actions": ("desktop.mkdir", "file.mkdir", "file.list", "process.list",
                    "system.metrics", "powershell.exec"),
    },
    {
        "id": "rdc",
        "name": "RDC / Desktop Commander",
        "type": "mcp",
        "purpose": "Remote filesystem, terminal and process workflows.",
        "description": "RDC in ChatGPT is not automatically an MCP connection inside SONIC.",
        "requires": "Separate owner-approved SONIC MCP connection and verified capability handshake.",
        "actions": ("filesystem", "terminal", "process"),
    },
    {
        "id": "google-drive",
        "name": "Google Drive",
        "type": "oauth",
        "purpose": "Documents, Sheets, search and authorized file collaboration.",
        "description": "The independent SONIC app has not been granted Google Drive OAuth permissions.",
        "requires": "SONIC-specific Google OAuth consent, least-privilege scopes and health check.",
        "actions": ("drive.search", "drive.read", "drive.write"),
    },
    {
        "id": "notepad",
        "name": "Notepad",
        "type": "windows_gui",
        "purpose": "Open and edit plain-text documents on TRADEVICEPC.",
        "description": "Notepad is a Windows application candidate, not an active SONIC GUI executor.",
        "requires": "Owner-session GUI agent, application detection and UI Automation receipts.",
        "actions": ("notepad.open", "notepad.edit", "notepad.save"),
    },
)

def integration_snapshot(db: Session) -> dict:
    device_id = setting("SONIC_DEVICE_ID", "TRADEVICEPC")
    device = db.get(Device, device_id)
    telemetry = db.get(DeviceTelemetry, device_id)
    age = max(0, int((utcnow() - device.last_seen).total_seconds())) if device else None
    online = bool(device and age is not None and age < 120)
    telemetry_age = max(0, int((utcnow() - telemetry.updated_at).total_seconds())) if telemetry else None
    # A heartbeat alone proves reachability, not that desktop.mkdir is callable.
    fresh = bool(online and telemetry and telemetry_age is not None and telemetry_age < 120)
    try:
        capabilities = sorted({
            item for item in json.loads(telemetry.capabilities_json)
            if isinstance(item, str)
        }) if fresh else []
    except (TypeError, ValueError, AttributeError):
        capabilities = []
    verified_actions = set(capabilities)

    recent = db.scalars(select(OperatorRequest).where(
        OperatorRequest.device_id == device_id
    ).order_by(OperatorRequest.created_at.desc()).limit(40)).all()
    completed = sum(1 for task in recent if task.state == "done")
    latest = recent[0] if recent else None

    adapters = []
    for descriptor in CATALOG:
        entry = dict(descriptor)
        entry["actions"] = list(descriptor["actions"])
        entry["connected"] = False
        entry["state"] = "not_connected"
        entry["verification"] = "none"
        entry["last_verified_at"] = None
        entry["current_capabilities"] = []
        entry["recent_completed_jobs"] = 0
        if entry["id"] == "windows-native":
            entry["connected"] = fresh and bool(verified_actions)
            entry["state"] = "online" if entry["connected"] else "offline"
            entry["verification"] = "live_device_heartbeat_and_capabilities" if entry["connected"] else "none"
            entry["last_verified_at"] = (
                telemetry.updated_at.isoformat() + "Z" if entry["connected"] else None
            )
            entry["current_capabilities"] = capabilities
            entry["recent_completed_jobs"] = completed
            entry["last_job_state"] = latest.state if latest else None
            entry["last_job_action"] = latest.action if latest else None
            entry["heartbeat_seconds_ago"] = age
            entry["description"] = (
                "Verified outbound companion heartbeat and capabilities. "
                "This does not prove a particular voice command completed."
                if entry["connected"] else
                "The registered Windows companion is offline or its capability snapshot is stale."
            )
        elif entry["id"] == "notepad":
            entry["state"] = "not_ready"
        adapters.append(entry)
    return {
        "schema": "sonic.integrations.v1",
        "device_id": device_id,
        "adapters": adapters,
        "counts": {
            "total": len(adapters),
            "connected": sum(1 for entry in adapters if entry["connected"]),
            "not_connected": sum(1 for entry in adapters if entry["state"] == "not_connected"),
            "not_ready": sum(1 for entry in adapters if entry["state"] == "not_ready"),
            "offline": sum(1 for entry in adapters if entry["state"] == "offline"),
        },
        "generated_at": utcnow().isoformat() + "Z",
        "notice": (
            "Catalog entries do not grant execution rights. RDC/Google Drive access "
            "granted to ChatGPT cannot be reused by SONIC without separate authorization."
        ),
    }


@router.get("/api/integrations")
def integrations(_: dict = Depends(auth.require_owner), db: Session = Depends(get_db)):
    return integration_snapshot(db)
