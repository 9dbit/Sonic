# SONIC V0.9.0 | Windows Open / Focus / Close

**Status:** GitHub implementation + synthetic acceptance. Physical TRADEVICEPC acceptance remains separate.

## Problem addressed

The owner reported a voice exchange where SONIC said it would close MetaTrader 5, but no executable window-close action existed. A later unrelated greeting produced an invented "technical difficulty" response. V0.9.0 adds a deterministic native action path, durable approval and device receipts, and removes this unsupported promise.

## Commands supported

| Owner command | Action | Approval |
|---|---|---|
| "SONIC, buka Notepad" | `window.open`, `app=notepad` | Required |
| "Buka Microsoft Paint" | `window.open`, `app=paint` | Required |
| "Fokuskan Notepad" | `window.focus`, `app=notepad` | Automatic, only with opt-in live companion |
| "Fokus MetaTrader 5" | `window.focus`, `app=metatrader5` | Required |
| "Matiin kamu close MetaTrader 5 ya" | `window.close`, `app=metatrader5` | Required |
| "Tutup MetaTrader 5" | `window.close`, `app=metatrader5` | Required |

Unknown applications, additional arguments, PowerShell, window wildcards, multiple matching windows, trading positions and commands about examples/questions are rejected. No automatic close from model-generated text or background speech.

The **Devices → Window Control** panel exposes Buka, Fokus, Tutup for allowlisted apps and reuses the existing digest-bound owner approval dialog. Voice commands produce an approval card in the chat; owner must click **Setujui**. Spoken "ya", unrelated greetings and model replies cannot silently approve a voice request.

## Critical MetaTrader 5 behavior

- **Closing the MT5 window is not a broker trade close.** Local EAs, trailing stops and scripts may stop working. The owner must review this risk before approving.
- The Windows agent sends `WM_CLOSE` to one uniquely identified, visible top-level MT5 window from the correct `terminal64.exe` or `terminal.exe` process.
- The agent checks HWND, PID, and executable again just before sending. Multiple matching MT5 windows are refused as ambiguous.
- No `taskkill /F`, TerminateProcess, keyboard automation or synthetic clicking through confirmation dialogs occurs. MT5 is protected from the separate forceful End Task flow.
- If WM_CLOSE is accepted but the window remains visible (e.g. unsaved file prompt), the receipt is `close_requested=true, closed=false`; SONIC **must not claim success**.
- Closing a window is not proof the process exited. Evidence is always identified as **authenticated Windows agent report**, not independent filesystem verification.
- Opening MT5 when not already running requires an explicit local `SONIC_MT5_EXE_PATH` configured by the owner; no arbitrary application path from SONIC Chat or Voice is accepted. Focusing a running MT5 does not require this path.
- Starting a window is not permission to place orders. Tradevice/MT5 trading actions remain outside the window-control adapter.

## Local companion opt-in on TRADEVICEPC

The cloud UI cannot control the Windows desktop until the owner installs the updated outbound-only Limited-user companion. No inbound ports, administrator elevation or credential copying to chat.

From a **locally reviewed checkout of the V0.9.0 release branch** on TRADEVICEPC, in the existing non-elevated Windows user PowerShell:

```powershell
# Check and review candidate without modifying the Scheduled Task:
.\scripts\Install-Sonic-Companion.ps1 -EnableWindowControl

# Owner-controlled activation; run only after reviewing source + risk:
.\scripts\Install-Sonic-Companion.ps1 -Install -EnableWindowControl
```

If you also want to **launch a stopped MT5 terminal**, supply the exact installed path as a locally set parameter (never paste sensitive Windows secrets into chat):

```powershell
.\scripts\Install-Sonic-Companion.ps1 -Install -EnableWindowControl -MT5Executable 'C:\Program Files\MetaTrader 5\terminal64.exe'
```

The path above is illustrative; it must match the owner's actual executable. Installer verifies it exists and uses a filename allowlist. Do not add `-EnablePowerShell` unless separately intended.

The installer checks the existing Limited-user Scheduled Task, stages files, performs an authenticated preflight, backs up the agent/broker, restarts the task and restores the previous Scheduled Task on error. Only the agent and local Python helper gain the new capabilities; existing workspace and voice settings are preserved.

**After activation:** Devices reports companion agent 0.9.0 and advertises `window.open`, `window.focus`, `window.close`. If offline or not opted in, cloud declines all new actions and no job is queued.

## Acceptance gates

1. Python tests reject unknown apps, malformed/extra payload keys, trading-position text and negated commands.
2. Voice regression: screenshot phrase creates exactly one pending `window.close` proposal, "Hola" is not approval, spoken yes is not approval, a specific owner approval button is required.
3. Windows synthetic tests confirm WM_CLOSE only, no force-kill or arbitrary execution, window ambiguity rejection, local path safety, secret environment stripping and an unconfirmed-close response on dialogs.
4. Desktop/mobile browser synthetic QA: app buttons are disabled if no live advertised capability; MetaTrader close displays the risk; no job before approval; owner-approved Notepad launch requires an exact receipt. Screenshots contain synthetic test data only.
5. After reviewed staging deploy, verify `/api/health` reports 0.9.0, UI assets are served, private APIs still require owner authentication, and previous V0.8.9 Voice + Workspace flows are unaffected.
6. On TRADEVICEPC, test a disposable Notepad window first (open/focus/close) with user present. MT5 should be tested only after the user has assessed running EAs, live positions and risk; no unattended close.

## Rollback

- Cloud: pin staging back to V0.8.9 commit `fb82caabc8af0196b127f420b6d87fef918e6d1a`. Do not reset PostgreSQL.
- Device: remove local window-control opt-in / restore scheduled task previous action using the installer backup. No automatic remote agent upgrade or force-stop of MetaTrader.
