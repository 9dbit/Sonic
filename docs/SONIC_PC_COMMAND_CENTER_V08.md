# SONIC V0.8 PC Command Center

**Project:** 9dbit/Sonic. **Target:** Railway staging + owner's TRADEVICEPC.
**Release:** V0.8.0 (26 October 2026, Asia/Jakarta).

## What exists
- Browser-owned PowerShell console, examples that only prefill commands, exact review/confirm modal, one-time SHA-256 request digest, queued/leased/done/failed/cancelled/expired states.
- Append-only bounded stdout/stderr stream with ordered sequence, idempotency checks, per-session ownership and device lease.
- Owner-only command history and cancellation that tells Windows to terminate the associated process tree.
- Windows agent outbound HTTPS polling. No inbound port, no remote listener, no auto-execute based only on an AI text response.
- Windows subprocess uses PowerShell 5.1+, no profile, no interactive prompts, non-elevated existing user identity, timeout 1–60 seconds. The spawned PowerShell environment strips SONIC and other known API credential variables.
- Task Manager: CPU/RAM timeline, GPU names/metrics when available, disk and per-adapter network counters, processes and guarded End Task.
- Companion installed only after staged preflight, with source backup and Scheduled Task rollback. Existing DPAPI device token remains at its local location and is not printed.

## Architecture
Owner browser → cookie/CSRF → POST /api/operator/requests → confirm digest →
Railway Postgres queued request → authenticated outbound device poll →
lease-check → Windows limited-user PowerShell → streamed output events →
Postgres → owner-only browser stream poll.

The previous narrow shell recipes and Notepad UI controls are retained.
Windows companion imports scripts/windows_command_v08.py and advertises
powershell.exec only when explicitly enabled on the local Windows host.

## Configuration
Railway staging service (SONIC/sonic-web):
- SONIC_ENABLE_POWERSHELL_EXEC=true enables owner-reviewed PowerShell proposals.
- Owner/session/device tokens must remain private. Never paste them in chat.

TRADEVICEPC installation:
1. Inspect scripts/Install-Sonic-Companion.ps1, scripts/windows_agent_v05.py and
   scripts/windows_command_v08.py.
2. Ensure the existing D:\Sonic\.venv includes psutil.
3. Run dry-run installer with no flags.
4. To activate PowerShell locally use
   powershell -NoProfile -File scripts\Install-Sonic-Companion.ps1 -Install -EnablePowerShell
5. Confirm the Limited Scheduled Task returns fresh heartbeat with
   agent_version=0.8.0 and powershell.exec capability.

## User controls
Under Devices > PC Command Center:
- Choose an example or enter a PowerShell command (max 1200 characters).
- Select timeout 10 / 30 / 60 seconds.
- Review command: creates a pending, not-yet-executing record.
- Approve once: exact digest match, valid owner session and CSRF, then device
  receives a single leased operation.
- Cancel running: revokes the cloud lease. The Windows broker polls and kills
  its process tree. Cancelling cannot undo filesystem changes or launched apps
  that already finished.
- End Task: process PID and expected name must match and critical Windows/SONIC
  processes are protected. It also requires owner approval.
- History: owner-authenticated audit receipts.

## Security limitations (important)
A remote PowerShell session is **not an OS sandbox**. Commands that are approved
run with the Windows account permissions that started the SONIC companion.
Sanitizing inherited environment variables and blocking a few dangerous
arguments do not prevent a sufficiently determined script from accessing
files, executing programs or networking as that Windows user. Do not approve
untrusted scripts, secrets, or commands that modify security settings.
User-approved shell commands can modify files or start/stop applications.
Administrator access is NOT granted by SONIC; elevated operations must be
handled separately through local, interactive Windows authorization.

VOICE transcription, browser wake-word, memory, MetaTrader and trading engine
are unchanged. SONIC does not automatically send model-generated shell scripts
to the broker. The current Windows GUI click/type legacy adapter still targets
Notepad; general graphical desktop automation is a future feature.

## Verification and acceptance
- pytest for feature gate, strict payload, owner session, digest, stream
  deduplication/order, cancel, audit and lease expiry.
- Linux/Windows JS+browser QA against disposable user/database and synthetic
  agent. No production tokens involved.
- Real Windows broker QA: harmless Get-Date, stdout streaming, timed Start-Sleep,
  cancellation, scrubbed child environment and disposable End Task.
- Live staging health=200 and version=0.8.0.
- Live TRADEVICEPC heartbeat agent=0.8.0, powershell.exec capability.
- An owner manually approves a harmless Get-Date in real staging to complete
  the final real-browser authorization/E2E validation. This cannot be performed
  with an agent credential alone; owner credentials are never extracted.

## Rollback
- Reconnect Railway staging to the known-good V0.7.2 GitHub branch.
- Restore old Scheduled Task action and original
  D:\Sonic\companion\windows_agent_v05.before_v08.py using trusted local
  administration if needed; the installer takes that backup.
- Set SONIC_ENABLE_POWERSHELL_EXEC=false in Railway. Local host opt-in may be
  switched off by reinstalling without -EnablePowerShell.

No changes to the live trading environment are part of this release.
