# SONIC Productivity Core v1.4.8

Status: staging candidate, 15 November 2026. Target branch: `feat/sonic-productivity-core-20261115`.
This release is an integrated, conservative foundation, NOT a fully autonomous assistant.

## What is implemented

- Owner-authenticated Project Memory, scoped by a validated project key, searchable and deleteable, saved to durable PostgreSQL via additive tables.
- Owner-authenticated Mission Planner. A mission is a draft with 1-12 explicit steps. It may transition draft -> approved -> in_progress -> completed with entered evidence, or cancel. This is a workflow record only, not background PC execution.
- Read-only capability registry with actual device readiness, not model guesses. Unsupported router Syslog and scheduler are labeled not connected/planned.
- Read-only Windows diagnostics: local clock (NTP not claimed), two fixed internet ICMP targets, bounded top-memory process list, and last 12 system error event metadata. No event body messages, file contents, credentials or raw arbitrary commands.
- Authenticated owner request -> existing SONIC durable DeviceJob -> outbound Companion -> bounded result. Guest/staging preview has NO access.
- Devices panel UI: Project Memory, Missions, Diagnostics and capability status. Hidden until owner session is verified, with CSRF headers on all writes.

## Safety

- No general network scanning, arbitrary PowerShell, background automation, MetaTrader manipulation or service termination.
- New action names are immutable allowlists on both cloud and Windows.
- No NTP verification from clock display; timezone is local Windows clock.
- Per-device queue permits at most four active diagnostics over 2 minutes.
- Existing `system.status` and other device actions remain unchanged.
- Missions require an explicit owner operation to change state; completion evidence is *user-entered*, not independently verified.
- Owner routes require session + CSRF, preview routes remain isolated.
- Do not claim full feature implementation for Email, Calendar, WhatsApp, multi-agent orchestration or router logs without further integrations/authorization.

## Release and QA gates

1. Tests: `python -m pytest -q`, `node --test tests/js/*.test.cjs`, `node --check web/productivity-v148.js`.
2. Verify staging /api/health returns 1.4.8, /api/productivity/* returns 401 to guest, old private endpoints return 401, static JS and CSS serve HTTP 200.
3. Do not switch Railway production. Keep current orbit feature branch unchanged.
4. A Windows Companion upgrade requires preserving the old scheduled task and backing up files. New capability is only advertised once the new script is active.
5. Verify physically that owner can queue and receive all four bounded diagnostics. Do not confuse a local Python test with end-to-end queue delivery.
6. SONIC voice iPhone v1.4.7 still requires actual iPhone microphone/speaker confirmation independently.

## Future extensions

Project Memory source provenance from connectors, document search and retrieval, richer mission checkpoints, supervised execution receipts, notifications, vendor router adapters, and genuine multi-agent worker orchestration. Each needs its own integration and security acceptance gates.

## Additional owner capabilities

- `GET /api/productivity/briefing`: snapshot of SONIC internal mission states, recent project-note titles, cloud workspace count and Companion freshness. Email/calendar/router/external project systems are explicitly reported unconnected.
- `GET /api/productivity/search?q=...`: bounded metadata-only search across the owner's project facts and SONIC Cloud Workspace, excluding trashed items and not silently accessing Google Drive, TRADEVICEPC files or other external systems.
- `GET /api/productivity/capabilities`: owner-only registry with actual device readiness for each diagnostic.
- `POST /api/productivity/diagnostics`: owner + CSRF, allowlisted job queue, with existing signed Companion polling, results via `GET /api/device/jobs/{id}`.
- `POST /api/productivity/missions/{id}/transition`: owner + CSRF with revision check and explicit human-entered completion evidence.

The DeviceHeartbeat capability list now permits 32 entries (was 24) to accommodate the existing software/window capabilities plus diagnostics, while the server retains allowlist filtering. Tests enforce an over-limit rejection.
