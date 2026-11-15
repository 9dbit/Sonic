# SONIC Internet Uptime Monitor v1.5.0

Scope: read-only network reachability from TRADEVICEPC. Staging rollout and Windows Companion update only; nothing touches MetaTrader or user trading commands.

## Monitoring engine

- New Windows Companion module: `scripts/windows_uptime_v150.py`.
- Daemon thread runs independently from owner GUI sessions and the cloud job polling loop.
- Every 30 seconds, check HTTPS GET endpoints `https://www.google.com/generate_204` and `https://cp.cloudflare.com/generate_204`. Both are expected to return HTTP 204. Timeout 3 seconds each.
- A sample is UP if at least one target responds 204, DEGRADED if exactly one does, and DOWN if neither does. This is reachability from this PC, not ISP-wide availability.
- Each sample records UUIDv4, UTC milliseconds, two boolean results and successful response latency in milliseconds. There are no IP addresses, page bodies, DNS listings, proxy details or exception text.
- Local SQLite journal uses WAL under `D:\Sonic\companion\state\internet-uptime-v150.sqlite3`. It retains 30 days of samples, including acknowledged samples, and stores upload status separately.
- Offline data is uploaded in batches of up to 60 samples when the Companion heartbeat and cloud become reachable. A sample is marked uploaded only after the server acknowledges its exact UUID. Retries are idempotent; conflicting replays are rejected.
- Automatic monitoring is enabled on the authorized Windows Companion by default. Set `SONIC_UPTIME_ENABLED=0` in its local environment for an opt-out. No inbound ports, elevated permissions, arbitrary URLs, or PC command execution are introduced.

## Cloud

- `POST /api/uptime/ingest` is device Bearer-only, bound to the registered device, accepts at most 60 strictly validated samples/batch and rejects timestamps older than 30 days or over 5 minutes in the future.
- Additive table `internet_uptime_samples_v150`, composite unique `(device_id, sample_id)`, with 30-day retention. Existing SONIC tables and records are unchanged.
- `GET /api/uptime/summary?hours=24` is owner-session-only. Guest/Open Preview returns 401. Range 1-168h.
- Report includes a 48-bin timeline, sampled coverage, observed uptime, unknown time, approximate downtime seconds, degraded seconds, outage incidents, and average successful HTTPS response latency.
- For 24 hours, the full-window uptime percentage is shown only when measured coverage is at least 99% and coverage begins within 90 seconds of the window start. Until then it is **null** and marked `partial` or `no_data`.
- Missing samples (PC off, hibernate, sampler stopped) are UNKNOWN, never assumed uptime or downtime. Each sample approximates one 30-second interval; outage durations are estimates.
- HTTPS reachability failures are NOT measured ICMP packet loss, speed test data, router faults, or an ISP SLA report. The dashboard intentionally labels them as such.

## SONIC interactions

- Chat: `Sonic, berapa persen uptime koneksi internet dalam 24 jam?` routes deterministically to actual stored samples without a generative estimate.
- Voice: owner-authenticated Realtime tool `internet_uptime` with no arguments returns a compact read-only summary, including coverage and an Indonesian spoken report.
- UI: Devices > Productivity > Internet Uptime Monitor, with live database figures and 48 time bars; only rendered after successful owner authentication.
- Staging Open Preview remains guest-only and does not expose owner monitoring data. Owner live-to-PC iPhone QA requires owner authentication to be enabled in a separately reviewed access mode.

## QA gates

1. Python unit tests for source validation, idempotence, offline retry, no-data, 24h coverage, outages, voice/chat routing, authentication boundaries and local sampler.
2. Playwright owner UI at 1440px, 390px, 360px, synthetic data/no provider spend; guest live smoke returns 401 for private endpoints.
3. Full Python and JavaScript regression plus GitHub CI.
4. Deploy pinned commit to SONIC Railway staging, observe terminal SUCCESS and /api/health v1.5.0.
5. Back up the existing TRADEVICEPC Companion, copy only reviewed scripts, compile, restart scheduled task, verify cloud device heartbeat and first uploads.
6. After 24 hours of actual sampling, verify coverage >=99% and only then report 24-hour uptime. Do not backfill older uptime.

## Not included

- WhatsApp alerts, notification subscriptions, router/SNMP integration, ISP-level outage attribution, automatic Windows changes or an end-to-end iPhone speaker test. These need explicit integrations and further testing.
