# SONIC V0.8.3 | Voice → PC Actions + Windows Desktop

Release target: 26 October 2026, Railway **staging** and authorized TRADEVICEPC Limited Windows companion.

## Why this release

Owner mobile screenshots showed that typed chat could queue a folder, but Talk to SONIC Realtime replied that SONIC could not control Windows. Root cause: voice.py still had a read-only/no-PC system instruction and Realtime transcription bypassed the owner chat action engine. A separate issue: all safe file.mkdir requests were confined to D:\Sonic\work, even when owner explicitly asked for the Windows Desktop.

## Implemented

- `sonic/voice.py`: Realtime model waits for transcription routing (`server_vad.create_response=false`). Authenticated voice transcript dispatch is bound to the active owner session, a stable provider item_id and a durable once-only dispatch record. The browser then requests a Realtime response after authorization.
- `web/voice.js`: user transcript callback is awaited; verified queued/done results are added as read-only conversation context and spoken through the existing realtime session. No model text automatically executes a command.
- `web/app.js`: voice commands, Desktop folder creation, inline one-time approval, live Windows job receipts and voice completion status are all visible on the same Chat page, including mobile.
- `sonic/chat_actions.py`: natural Indonesian/English phrases identify a dedicated Desktop target. Handles misheard name `Threadvice PC` when preceded by `di desktop`. The word `desktop` *within a folder name* does not change the location.
- `sonic/device_contract.py` and `sonic/operator.py`: `desktop.mkdir` is an allowlisted, idempotent, low-risk action with a single folder name and the same authenticated leased-job control as `file.mkdir`. End Task/PowerShell remain per-command owner confirmed.
- `scripts/windows_workspace_v082.py`: Windows Known Folder Desktop GUID resolution supports redirection to OneDrive inside the owner's profile. Rejects other users' profiles, external shares, unsafe names, traversal, symlink targets and arbitrary paths.
- `scripts/windows_agent_v05.py`: dispatches `desktop.mkdir` only to the verified local helper; reports version 0.8.3.
- `sonic/voice.py`: Realtime can inspect registered device capabilities and read aggregate owner chat audit, without granting model shell execution.

## Owner examples

- `SONIC, tolong buatkan folder bernama Today di desktop TRADEVICEPC.` → automatic queue, then verified Desktop path receipt.
- `Tolong buat folder QA di TRADEVICEPC.` → workspace-only creation.
- `PowerShell: Get-Date` → preview and reply SETUJU/BATAL in the same conversation; no manual Devices navigation.
- `SONIC, cek log chat history` → aggregate audit from owner's SONIC database.

## QA

- 193 Python tests passed, 1 skipped, plus new parser regression cases (next run includes them).
- 18 JavaScript tests passed.
- Chrome desktop and mobile synthetic owner/browser voice routing: Desktop queue, same-chat approval, Windows receipt, and no page hops. No JS errors.
- Chrome PC Command Center and Neural Brain existing browser regressions passed, including 5,880 particle graphics.
- Real authorized Windows desktop smoke: verified Known Folder, created an isolated QA folder, confirmed idempotence and removed only the folder created during the test.

## Security and limitations

OpenAI Realtime speech-to-text can mishear a folder name. To mitigate double execution, duplicate provider item IDs cannot execute twice. A separate owner action must pass server-side intent matching and a Windows-side path validator. SONIC doesn't store raw microphone audio. Recognized PC action transcripts/receipts are persisted in owner chat history; unrelated voice transcripts are not automatically stored.

Actual mobile microphone + OpenAI Realtime connection and Windows job execution from the **real logged-in owner** requires a final physical iPhone acceptance test after deployment. The synthetic tests do not prove the provider connection.

Rollback: Railway staging branch `feature/sonic-chat-first-actions-v082-20261026`; Windows Scheduled Task has a local preinstall backup and Limited run-level guard. No production trading workflow changed.