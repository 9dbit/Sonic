# SONIC Architecture v0.1

SONIC is a **general-purpose personal intelligence assistant**. ARCHON, SketchUp, Revit, Tradevice, Telemetry and other applications may become individually permissioned integrations later; they are not the core.

## Architecture

    Chrome / browser UI (chat, speech input, voice output)
                |
         HTTPS + owner session
                |
    SONIC Control Plane (FastAPI / Railway)
         |       |         |
      OpenAI   Postgres   Tool Dispatcher
     Responses (memory,    (allowlist)
       API      chat)         |
                              | outbound-only HTTPS polling
                       SONIC Windows Companion
                           on TRADEVICEPC

## In scope for v0.1

- Login with SHA-256 verifier for a separately generated owner token.
- Signed short-lived, HTTP-only, SameSite=Strict session and CSRF header on mutations.
- OpenAI Responses API, tool calling, bounded tool iterations and history.
- Durable owner-approved memory notes, including owner-controlled deletion.
- Web Speech API voice input where Chrome supports it, plus browser speech synthesis.
- Distinct device credential, outbound Windows polling and one read-only system.status action.
- GitHub CI and Railway deployment support.

## Explicit non-capabilities

- No arbitrary shell, PowerShell or Windows UI automation.
- No remote file reads, writes, deletions, trading, financial transactions, credentials capture, or auto-installers.
- No direct SketchUp or Revit manipulation until dedicated adapters pass approval and isolation tests.
- No autonomous background scheduling in v0.1.
- No webcam capture or continuous microphone transmission. A browser may use its speech recognition provider when enabled by the user; check browser privacy settings.
- No guarantee that all ChatGPT product features are exposed to the OpenAI API.

## Next milestones

1. Per-device registration/rotation, audit trail, durable task leases and role-scoped policies.
2. Tool adapter API with mandatory preview and per-action approvals for filesystem, browser, apps and CAD.
3. Document and image understanding plus selective memory retrieval.
4. Full voice conversation with a compliant realtime API, camera opt-in, screen observation opt-in.
5. Proactive scheduling and recurring routines with reviewable notifications.
6. Real SketchUp/Revit adapter inside an isolated worker, without touching MT5.

## Data and privacy boundaries

- Messages and memory stored in private PostgreSQL; in local mode only, SQLite.
- A single owner is supported, not a multi-tenant account system.
- The browser does not receive OPENAI_API_KEY, device token, or server session secret.
- Model requests use store=false but are sent to OpenAI to be processed. Do not promise fully offline processing.
- TLS certificate validation is enabled in the Windows companion.
- Memory content and tool results are untrusted instructions to the model.
- No file system/network sandbox beyond the hardcoded companion capability; tighten security before expanding.
- Owner authentication rate limits are in-process only; add edge rate limits before broader exposure.
- Do not log prompts, secrets, raw tokens, or device responses.

## V0.1 Opt-in Vision

Camera, screen and local-image inputs are all initiated by a visible user action. Only one frame is captured, all media tracks are stopped immediately, and the frame is sent through the owner-authenticated SONIC endpoint to the configured OpenAI vision model with store=false. SONIC does not persist images or automatically invoke any tools based on them. Screenshots can include sensitive information; enable only when intended. Vision is not constant surveillance or live video.
