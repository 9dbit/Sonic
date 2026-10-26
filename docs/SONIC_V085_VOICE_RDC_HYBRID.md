# SONIC V0.8.5 | Voice job reliability and RDC hybrid operator plan

## Evidence, 26 October 2026

The owner said voice still failed to create Desktop folder `Today`. Staging HTTP access logs at ~04:20-04:22 UTC show repeated voice dispatch requests returning HTTP 200, several `/api/voice/sessions/.../tools` calls returning HTTP 403, and concurrent successful outbound heartbeat and operator polling. No corresponding Windows agent result for `Today` appeared in those HTTP logs. The Desktop folder `Today` did not exist when checked on TRADEVICEPC. HTTP logs **do not show private message bodies** and HTTP 200 from dispatch is not a job completion receipt. No conclusion about exact stored voice transcript can be drawn from those logs alone.

## Engineering fix

- Server-side natural Indonesian speech parser handles word order differences, polite prefixes, ASR misrecognitions and a single unambiguous Desktop folder name. Strict filesystem validation still occurs on the server and locally on Windows.
- Recognized voice actions are canonicalized into the same authenticated, leased operator path as text chat and `desktop.mkdir` is autoqueued. It never requires owner confirmation for this safe single folder creation.
- The pending name/location slot can ask a follow-up within the same voice session and is bound to the original owner login, expires in two minutes, and never accepts dangerous paths or unspecified destructive actions.
- Unrecognized/ambiguous PC-looking utterances produce an explicit **not executed** status. Never let a model reply imply shell/desktop action without a server receipt.
- Each recognized voice action is idempotent by session+provider input item ID and recorded in the `VoiceActionDispatch` table (hash of transcript, not audio). `EngineRun.channel='voice'` distinguishes voice actions from text chat.
- Owner chat audit now includes aggregate voice attempts, route decisions and job counts. An authenticated device-only diagnostics endpoint exposes recent **aggregate** voice/chat/agent states, with no transcript bodies, credentials or session IDs.
- Windows-side job results are shown directly in chat, with a separate queued/status/verified-completion message. Question `Sudah jadi?` reads the most recent job from the authenticated voice session.
- The voice transcriber is set to Indonesian and prompted with SONIC/TRADEVICEPC/Desktop vocabulary. PowerShell remains protected by an explicit, owner-authenticated **in-chat button** after preview; speech-only agreement does not authorize powerful commands.

## Quality gates

- All Python unit/integration regression tests pass (252 passed, 1 skipped) and all JavaScript tests pass (22).
- Chrome desktop and mobile E2E passes voice transcript UI, safe folder action, inline approval, Windows receipt simulation, PC Command Center, and Neural Brain motion styling.
- Actual owner iPhone Realtime microphone and real Windows-agent job for folder `Today` require a physical live acceptance test. Do not mark this release fully solved until the owner sees both the real folder and a verified agent receipt.

## Owner acceptance

1. Stop existing voice session; refresh `https://sonic-web-staging.up.railway.app`; verify version 0.8.5.
2. Start a new Talk to SONIC voice session.
3. Speak: `SONIC, buatkan folder di desktop dengan nama Today.`
4. Confirm that the chat shows `Voice -> desktop.mkdir / queued for Windows verification` and then a verified Windows agent result with the Windows path. The actual folder should exist under the desktop of the account running the Limited agent.
5. Speak `Sudah jadi?`. SONIC must answer from the actual job state, not offer a manual solution.
6. From text chat ask `SONIC, cek log chat history` to retrieve aggregate voice route and operator state counts. Do not expect the private raw audio or transcripts to appear in HTTP logs.

## SONIC hybrid PC operating architecture

iPhone Voice/Text -> authenticated SONIC intent parser -> action planner -> capability router & approval gate -> durable idempotent task queue -> outbound companion on TRADEVICEPC -> execution adapter -> receipt/evidence -> same SONIC conversation.

Supported execution adapters:

1. **SONIC Native Windows Adapter (primary)**: safe files/folders, inspect telemetry, Task Manager process listing, Windows services, volumes/disks, jobs that must not depend on a third-party MCP service. No open inbound ports or admin elevation.
2. **Desktop Commander MCP Adapter (optional)**: shell, local filesystem, process, searching and developer-focused workflows. Requires the user to authorize SONIC as a separate MCP/OAuth client; the user's existing ChatGPT connector credentials are not transferable to the independent SONIC web app. Local stdio MCP offers a separate bridge option. Start as a fallback, not as the exclusive executor.
3. **Windows Interactive GUI Adapter (future)**: runs under the owner's interactive desktop session with UI Automation, app-specific APIs, or a guarded computer-use driver. Must provide window targeting, screenshot/element evidence, stop and rollback. Needed for SketchUp/Revit and click/type workflows; RDC's exposed filesystem/terminal interface alone is not adequate proof of full GUI control.
4. **Browser Adapter (future)**: Playwright/CDP for authenticated browser tasks and status validation; fenced by origin/permissions.

### Rollout

- **0.8.5**: finish real iPhone voice acceptance and voice audit, verify Desktop result.
- **0.9**: local capability registry and job router with `native`, `rdc-mcp`, `gui`, `browser`; use a single job ID and reliable progress receipts; idempotent retries for safe operations.
- **0.9.5**: full Task Manager telemetry (CPU/GPU/RAM/disk/network/processes/services/startup) and multi-step natural commands, with a clear risk policy.
- **1.0**: guarded GUI companion in interactive Windows session, screenshot+UIA evidence, window focusing/typing/clicking, SketchUp/Revit APIs where reliable, emergency stop.
- **1.1**: reliable voice conversation across multi-step tasks and saved memory with explicit privacy/approval policy.

### Safety and reliability conditions

Do not grant arbitrary administrator privileges or run model-authored raw PowerShell without a reviewed per-command approval. Never claim an operation succeeded unless the Windows agent posted a matching, authenticated completion receipt. Keep an absolute kill switch, per-command timeouts, audit ledger, capability allowlists, encryption of credentials and rollback snapshots. Treat app screen and file content as untrusted data and not new executable instructions.

## Rollback

On staging only: revert Railway `sonic-web` source to `feature/sonic-voice-command-v084-20261026`. Windows companion V0.8.3 remains compatible; no existing Desktop folder or trading installation was changed by the V0.8.5 regression suite.