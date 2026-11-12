# SONIC Orbit UI 1.4.2: unified design and functional open staging

## Root cause and constraints
The 1.4.1 open-preview mode hid authentication but set `csrf=null`, bypassed graph and configuration initialization, disabled every chat and voice control, and left old button colors on non-brain screens. This release does not replace the authenticated SONIC owner engine. No passkey or password is requested in staging.

## Visual design
- Reusable orb mascot continues bouncing, blinking and shifting gaze. Double tap summons the center orb and non-blocking purple/blue edge aura.
- Unified charcoal/violet language on Neural Brain, Chat, Workspace, Memory Vault, Devices and Setup. iPhone header wraps across two rows; model selector and voice are visible.
- Native original WebGL/Canvas perspective renderer is used for a 24-node / 43-link public **SONIC architecture** map. Rotate/pan, 2D/3D, selection, and zoom work. These are architecture metadata, **not** an assertion that private Memory Vault items were fetched or replaced.
- Private Memory, TRADEVICEPC, workspace and PC command controls show explicit **Protected** status rather than fabricated offline/empty metrics. Owner data is never exposed.

## Real provider routes without owner authority
- `SONIC_OPEN_PREVIEW=true` and `SONIC_PREVIEW_PAID_ACTIONS=true` enable anonymous guest chat / Realtime audio **on staging only**, still no public owner session.
- An HttpOnly SameSite signed guest cookie and CSRF token (delivered via `/api/session`) authenticate the **guest browser only**, with no user-visible login or passkey prompt. The signed guest cookie is reused across repeated session checks and expires server-side after 24 hours, avoiding stale-CSRF failures during chat and voice sessions. Requests enforce exact same-origin Origin and reject cross-site operations.
- `GET /api/preview/models` lists only configured preview-allowlisted DeepSeek Flash and OpenAI GPT-4.1 options; the UI selector switches the actual backend provider for subsequent text turns, not the owner's persisted preference.
- `POST /api/preview/chat` reuses the real SONIC `providers.complete` adapter, with a short, isolated single-turn context, no tools, no private memory, no account/PC context and no persistent owner chat history. No hidden fallback between providers.
- `POST /api/preview/voice/sessions` and `.../stop` reuse WebRTC/Realtime transport with OpenAI-only voice, **all functions/tools disabled**, no owner context, 60 seconds per session and consent initiated by the owner gesture. Provider voice is independent of selected text model.
- Durable global quotas: 80 chats/day and 6 Realtime sessions/day. Per-network: 12 chats/day and 2 sessions/day. Limits reserve budget before upstream calls and persist across restarts; no raw prompts or IP addresses stored in the quota table. Provider bills and credits may impose lower limits. Voice session closing is explicit; expiry/housekeeping is retained.
- All regular owner endpoints, memory writes/reads, settings mutations, signed Windows tasks, software installs, inbox, workspace and private operational telemetry remain under their original `auth.require_owner`/`auth.require_owner_write` checks. Live owner engine is unchanged.
- `SONIC_PREVIEW_PAID_ACTIONS=false` immediately disables public paid actions while preserving open UI and 3D graph. `SONIC_OPEN_PREVIEW=false` restores the previous login flow. **Never set open preview in production.**

## Validation scope
- Pure backend tests use synthetic model/provider responses and no real API key. They check guest cookie and CSRF, model routing, origin rejection, owner-route denial, durable budget enforcement, synthetic WebRTC startup/stop with no tools, and disabled flag behavior.
- Playwright tests run 4 viewports (1440, 820, 390, 360), including native 3D graph with 24 nodes, model switching, text send routing to fake provider, double-tap voice transport single-start, six working navigation tabs, protected endpoints, and browser JS errors. Existing owner route tests continue separately.
- A REAL iPhone microphone, live OpenAI WebRTC audio and DeepSeek billable response must be evaluated independently after staging is live; synthetic passing tests do not prove audio playback or sufficient API credit.

## Deployment
1. Publish this code to GitHub and wait for CI.
2. In SONIC Railway **staging only**, stage both reviewed commit and `SONIC_PREVIEW_PAID_ACTIONS=true`.
3. Observe terminal Railway deployment SUCCESS, check `/api/health` version 1.4.2, `/api/session` guest mode, `/api/preview/models`, and public HTML assets.
4. Verify unauthenticated `/api/history`, owner `/api/chat`, `/api/device/status` and login remain locked. A single bounded provider text request can verify production API response. Do not claim microphone tested until user tests it on device.

TRADEVICEPC Windows Companion, Markstudios and Chatvice remain untouched.

## v1.4.3 browser integration fix
- Four parallel browser components may request /api/session before the first cookie settles. Their responses can establish different signed guest cookies; the app's first CSRF token can then be stale. Backend cookies are persistent across repeated requests, but first-load concurrency still requires reconciliation.
- Client retries a paid preview POST once only upon exact server-generated guest CSRF/expiry rejection; it re-reads the same-origin /api/session and updates the signed guest CSRF for chat and WebRTC. The initial 403 reserves no upstream budget or API cost.
- End-to-end browser test injects the exact 403 for both chat and voice, verifies retry and no tools/provider execution, and checks 24-node 3D rendering across desktop/tablet/phones.
