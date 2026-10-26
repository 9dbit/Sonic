# SONIC V0.8.9 | TRADEVICEPC read-only Workspace

**Branch**: `feature/sonic-pc-workspace-readonly-v089-20261026`  
**Base**: V0.8.8 `738885324bd730ff7913333312bd6baa28bd03fb`  
**Scope**: browser UI, read-only; **no Windows companion upgrade, cloud database migration, live pairing, or filesystem write**.

## What changed

- Workspace now has explicit **SONIC Cloud** and **TRADEVICEPC (Read-only)** storage tabs.
- SONIC Cloud retains all existing folder/notes editing and Trash/restore behavior.
- Selecting TRADEVICEPC checks the live `/api/integrations` Windows Native adapter (fresh heartbeat and advertised `file.list`/`file.read` capabilities), **without reading PC files automatically**.
- Only a deliberate click followed by a browser confirmation can queue a read-only `file.list` or `file.read` request. The exact relative path is visible to the owner in that confirmation.
- Requests use existing `POST /api/operator/requests`, digest-bound `POST /api/operator/requests/{id}/confirm`, and authenticated `GET /api/operator/requests/{id}` status polling.
- A Cancel button invokes the existing operator cancellation endpoint; cancellation cannot undo reads that already occurred.
- Folder breadcrumb, up, refresh, list and text preview use the existing V0.8.3 Windows companion, limited to its **configured SONIC_WORKSPACE_ROOT**. The UI does not reveal or browse arbitrary PC paths.
- Preview content uses `textContent` only. No rendered HTML, scripts, uploaded content or localStorage tokens. No new media, recorder, speaker recognition or background scanning.
- File list is bounded to 60 entries and companion-safe file types; file reading obeys existing 32 KiB input / 16,000-character output limits. A listing can be truncated; the UI reports it.
- Path check refuses absolute/UNC paths, traversal, hidden credential dirs, Windows reserved names, variable expansions, secret-style names, invalid text extensions, and attempts to move out of the authorized workspace.
- Logout/session expiry wipes in-browser PC list and preview; stale async responses cannot repopulate the UI. Windows companion and Cloud notes remain separate.

## What this is **not**

- Not a two-way file sync, Windows file manager write integration, Notepad editor or generic remote desktop.
- Not proof of an independent filesystem readback. Results are **authenticated Windows companion reports** and validated for requested suffix/shape before display.
- Not a new privilege grant. It uses only existing allowed `file.list` and `file.read` actions; the Windows process must still run as a Limited user with its configured root.
- Not a live owner-device acceptance test. Tests with mock receivers do not establish a successful real private file read or physical iPhone session.
- No claim that Google Drive/RDC plugins connected to ChatGPT are inherited by SONIC.

## Tests and release gates

- Node syntax checks on `web/pc-workspace-v089.js` and `web/app.js`.
- Node tests for relative path handling, evidence shape, read-only opt-in, offline rejection, and one-job dispatch.
- Inherited V0.8.8 browser/Workspace, 3D motion, voice and server regression workflows must remain green.
- **Owner staging acceptance** after a reviewed deployment: 
  1. Login, open Workspace, confirm Cloud notes still save and reload.
  2. Switch to PC; see the live capability status but **no file content** until clicking.
  3. Choose Buka root PC, approve read-only `file.list: .`, see agent-reported folder list.
  4. Choose a known test text file in the authorized Windows root, confirm exact path and verify preview matches.
  5. Switch to Cloud / logout and confirm previous PC preview is cleared.
  6. Try offline companion and cancelled request; neither may show invented contents.
- Use only a disposable known test file for physical acceptance. Do not expose secrets or personal documents in QA logs.
- No staging deployment or agent change is performed solely by opening this PR.

## Rollback

Disable the new PC Workspace tab by restoring V0.8.8 `web/index.html`, `web/app.js`, and removing V0.8.9 UI assets. Windows agent, database and existing Cloud notes are unchanged.
