# SONIC Mission Checkpoints v1.4.9

Staging-only incremental release, 15 November 2026.
This follows `SONIC_PRODUCTIVITY_V148.md` and keeps the guest preview security boundary intact.

## Owner capabilities

- Mission approval: `draft -> approved -> in_progress -> completed`, with explicit cancel and no automatic PC execution.
- Each mission step has an owner-confirmed checkpoint with evidence (10-600 characters), an optimistic mission revision and a durable timestamp.
- Steps must be completed in order. Reopening only the latest completed step is permitted, and requires a stated reason.
- Closing a mission now requires evidence for every step plus final completion evidence. Previously completed records remain intact; this is an additive gate on new completion attempts.
- An append-only `productivity_mission_events_v149` table records status transitions, step completion and step reopening. The audit contains the SHA-256 of evidence, not duplicate raw evidence or credentials.
- The owner-only mission list includes progress counts, and the Devices productivity UI exposes Complete step, Reopen, Mark completed and Audit log actions.
- Replaying an old revision returns 409. Owner writes require a valid owner session and CSRF; guest preview cannot access the endpoints.

## Isolated PC bridge E2E

`tests/test_productivity_bridge_v149.py` uses a synthetic owner token, synthetic device token, disposable SQLite DB and FastAPI TestClient. It routes the real Windows Companion function `run_once()` through the same HTTP endpoint contracts, without connecting to Railway, real owner sessions, or trading applications.

The Windows-specific test also executes four bounded read-only diagnostic adapters locally:

1. `diagnostics.clock`: local clock with explicitly unverified NTP status.
2. `diagnostics.ping`: two fixed public ICMP destinations.
3. `diagnostics.processes`: process-count/top-memory only, or explicit unavailable status if psutil is absent in the test environment.
4. `diagnostics.events`: recent System error event IDs/provider/timestamps, no message body.

This validates code-path and protocol compatibility, NOT owner-initiated cloud-to-PC production access. That remains blocked by staging's intentionally enabled Open Preview and disabled owner login/passkey mode. Do not bypass the authentication gate or reuse real device credentials to impersonate an owner.

## Testing

- `python -m pytest -q` for all backend tests.
- `python scripts/e2e_productivity_v148.py` for browser QA at 1440px/390px/360px with synthetic data and no paid model calls. Requires Playwright Chromium.
- `node --check web/productivity-v148.js` and `node --test tests/js/*.test.cjs`.
- GitHub checks, Railway staging deployment status SUCCESS, `/api/health`, guest 401 and Companion heartbeat 200 must be verified after publishing.

## Deferred

- Live owner sign-in coexisting with Open Preview. This requires an explicit review of account authentication and staging exposure. It is not enabled automatically.
- Workflow scheduler, autonomous worker, calendar, email, WhatsApp, router Syslog and multi-agent execution are not active.
- Physical iPhone microphone/speaker voice QA is not established by these tests.
