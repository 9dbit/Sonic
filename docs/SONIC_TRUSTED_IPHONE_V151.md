# SONIC v1.5.1 Personal iPhone Preview: private uptime only

## Goal
Allow the owner's personal iPhone to stay in the familiar guest/preview UI while safely reading **only** 24-hour uptime data, via dashboard, typed chat and OpenAI Realtime voice. Public visitors must not gain any private PC, memory, workspace, action, settings, health or trading privileges.

## One-time enrollment
1. The registered Windows Companion, authenticated with its existing device Bearer token, calls `POST /api/preview/trusted/issue`.
2. SONIC generates a random URL-safe 256-bit secret, saves only its SHA-256 hash, and returns a **single-use, 15-minute** HTTPS URL with the secret in its URL fragment (`#sonic-pair=...`). A new link invalidates other unused links.
3. On the intended iPhone browser/PWA, a same-origin script verifies the public preview guest cookie and CSRF, then POSTs the secret to `/api/preview/trusted/claim`. The server consumes the link and sets a **Secure, HttpOnly, SameSite=Strict, 90-day** personal cookie. The link is erased from the browser URL before reload. Do not share or screenshot the secret before it is redeemed.
4. Only the most recently paired iPhone remains trusted. Pairing a replacement revokes the previous personal session. The user can choose `Unpair this iPhone`; the authenticated Companion may also call `POST /api/preview/trusted/revoke-all` to revoke sessions.
5. Safari, a home-screen PWA and third-party in-app browsers may store cookies separately. Pair using the actual browser/app in which SONIC will be used.

## Least-privilege server policy
- Normal Open Preview retains `authenticated=false`; no owner `sid`, `OwnerSession` or general owner cookie is created.
- `/api/session` exposes only `trusted_uptime: true/false`, never the pairing credential.
- `GET /api/preview/trusted/uptime` requires an active personal cookie, signed preview guest cookie, signed guest CSRF and same-site headers. The existing owner-only `/api/uptime/summary` stays owner-only.
- `POST /api/preview/chat` intercepts only an uptime-related question for a paired visitor and returns a deterministic calculation from stored uptime records; other preview chat remains unchanged.
- Paired preview Realtime configuration advertises **only** the `internet_uptime` function. The bound tool endpoint verifies the original guest voice session and paired cookie, accepts exactly `{}` arguments, rate-limits to 12 calls per voice session and deduplicates via `VoiceToolCall`.
- Revocation takes effect on future tool calls, even when a WebRTC call is already running. Unpaired previews retain `tools=[]` and `tool_choice=none`.
- Private owner routes (memory, files, full diagnostics, missions, device commands, owner voice tools, trading) still require their original owner authorization and return HTTP 401 to paired guests.
- Staging is the ONLY eligible environment (`SONIC_OPEN_PREVIEW=true` and not production). This feature is not deployed into production.

## Verified QA requirements
- The synthetic device may issue a link; guest cannot. A link is time-limited, one-time and hashed in PostgreSQL. The personal session can be revoked.
- Owner-only endpoints remain inaccessible in paired and unpaired preview sessions.
- Synthetic paired voice WebRTC advertises one function, valid uptime calls use real DB results, other calls are rejected, and request-id replay is idempotent.
- Browser test both new-tab and hashchange navigation, desktop 1440px, iPhone 390px and 360px, owner widgets inaccessible, uptime-only dashboard, unpair flow, no JS errors, no overflow.
- Run `python -m pytest -q`, `node --test tests/js/*.test.cjs`, Playwright and pinned staging Railway release checks before issuing a live pairing link.

## Not implied
- Pairing does not transfer ownership or allow broader Windows diagnostics, microphone recording without explicit user consent, background microphone, payments or software installation.
- The 24-hour uptime metric still requires full monitoring coverage; partial data must be marked partial, never shown as a fabricated 100% 24-hour value.

## Windows Companion: one-shot link issuance without credential extraction

- Helper module scripts/windows_pairing_v151.py is imported by scripts/windows_agent_v05.py after the normal authenticated heartbeat.
- Request marker: D:\Sonic\companion\state\request-iphone-pairing.flag (empty file). Only the authorized TRADEVICEPC operator should create it.
- The running Companion consumes the flag once and calls its restricted device-authenticated pairing endpoint with the existing in-process API helper.
- The response is stored in D:\Sonic\companion\state\personal-iphone-pairing.json for local display. The result expires automatically after 15 minutes.
- Neither the Companion device credential nor the short-lived pairing URL is printed to agent logs. Failed requests never silently retry.
- The user may open the local one-time pair_url on the intended iPhone. Never publish it to source control or analytics.
- Upgrade the Windows Companion with a backup and Python compilation, then restart only the SONIC Read-only Companion Scheduled Task.
- This flow never reads/decrypts the device token outside the Companion, and never modifies MetaTrader or security settings.
