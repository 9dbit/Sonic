# SONIC Engine V0.4

General-purpose personal assistant. Architecture, computer control and trading stay deferred.

## Shipped engine interfaces

- One text orchestration entrypoint, with explicit memory, direct graph navigation and bounded model-tool routes.
- Real graph search/focus/neighbors/reset tools. IDs must exist in the authenticated graph snapshot. No arbitrary JavaScript, new relationships, file access or PC control.
- Memory references open saved source notes. UI plans are marked prepared by the server; the browser applies only its narrow allowlist and reports application results.
- Owner-only execution receipts record route, tool names, status and duration. They are not hidden reasoning or a chain-of-thought transcript.
- Existing memory storage, deduplication, source metadata and auth are preserved.

Examples: `Tampilkan memory tentang bakso`, `Buka memory #12`, `Perlihatkan hubungannya depth 2` after selecting a node, `Kembali ke seluruh brain`.

## Realtime voice

The Talk to SONIC button opens a consent dialog. Starting it requests the microphone, creates a browser WebRTC connection and exchanges SDP via the owner-authenticated server. The permanent OpenAI key stays server-side. No raw audio or SDP is stored by SONIC. OpenAI processes audio and has its own data policies; this is not an offline voice system.

The server uses the documented unified Realtime call interface at `/v1/realtime/calls`. Default model `gpt-realtime`; voice `marin`; server VAD with interruptions; input transcription `gpt-4o-mini-transcribe`. The endpoint may reject a session if the configured account lacks access or quota. The browser shows errors, never fabricates an audio connection.

Voice tools: graph_search, graph_focus, graph_neighbors, graph_reset, memory_search, memory_prepare. No generic shell, remote PC, payment, delete, graph-write or direct memory-save tool is offered.

Voice memory is a proposal until the owner reviews its text and clicks Confirm memory. A confirmed proposal uses the same save_note path as text. A rejected or expired proposal cannot be confirmed. Retries are idempotent; conflicting arguments for an already-used call ID are rejected. Saved facts are not recreated if the note was later deleted.

Transcripts are displayed transiently in the browser; they are not added to permanent chat history automatically. Session metadata, deduplicated tool results (which may contain retrieved notes) and memory proposals are persisted for safety and retry handling. Deleting a Memory Vault note is not a claim to erase all historical receipts or chat mentions. A separate data-retention/erasure control remains future work.

## Media lifecycle and limits

- No wake word or background always-listening mode. Start requires visible owner consent.
- Stop immediately ends local tracks, peer connection, audio playback and timers; server hangup is separately verified.
- Mute disables microphone tracks. Leaving/hiding the page stops the session rather than trying to listen in the background.
- Session expiry, owner-login scope, tool idempotency and daily admission count are persisted. One active voice session is admitted at a time.
- Defaults: 300 seconds/session, 12 sessions/UTC day, 80 tool calls/session, 3 pending proposals.
- Server cleanup checks expired/revoked sessions every 15 seconds, with at most four hangup attempts. Unconfirmed provider shutdown is reported honestly.
- These are application safeguards, not a guaranteed monetary billing cap. Unknown provider acceptance after a network failure cannot be fully confirmed without a returned call ID. Set provider-side budgets independently.
- API usage can incur charges. No automatic paid provider request is made at application startup.

## Configuration

Existing owner login and OpenAI key remain unchanged. Set these non-secret values only after passing tests:

    SONIC_REALTIME_ENABLED=true
    SONIC_REALTIME_MODEL=gpt-realtime
    SONIC_VOICE_MAX_SECONDS=300
    SONIC_VOICE_DAILY_SESSIONS=12

Disable only realtime using SONIC_REALTIME_ENABLED=false; text, graph and browser dictation remain available. Do not commit API keys or owner tokens.

## Tests and evidence boundaries

    python -m pytest -q
    node --test tests/js/*.test.cjs
    python scripts/e2e_engine.py

Python tests verify auth/CSRF/consent, allowed tools, node validation, proposal confirmation/rejection, expiry, owner-session scoping, limits, provider error handling and logout hangup. Node tests verify late-media cleanup, no microphone before Start, Stop, error cleanup and duplicate-tool suppression.

The browser suite uses actual disposable HTTP/database/UI with Chromium fake microphone media, a simulated WebRTC peer and a synthetic OpenAI response adapter in a test-only module. It tests desktop and mobile viewports. It DOES NOT establish actual OpenAI speech-to-speech quality, ICE/network compatibility, real microphone recognition, interruption latency, physical iPhone or Safari compatibility. Those require an ordinary owner session and a real device. The Dockerfile does not include the test-only provider module.

## Migration and rollback

Additive tables: engine_runs, voice_gate, voice_sessions, voice_tool_calls, voice_proposals. No prior chat/memory tables or columns are removed. The deployment remains one process/replica; schema initialization for a future multi-worker rollout must use a dedicated migration step. Rolling back to V0.3 leaves these additional tables harmlessly in place.

No changes to TRADEVICEPC, MT5, ARCHON, existing credentials or other projects.

## Primary implementation references

- https://developers.openai.com/api/docs/guides/realtime-webrtc
- https://developers.openai.com/api/docs/guides/realtime-conversations
- https://developers.openai.com/api/reference/resources/realtime/subresources/calls/methods/create
- https://developers.openai.com/api/reference/resources/realtime/subresources/calls/methods/hangup
