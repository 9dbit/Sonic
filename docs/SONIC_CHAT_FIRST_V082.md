# SONIC V0.8.2: Chat-first PC Actions

Release date: 26 October 2026. Deployment target: Railway staging and TRADEVICEPC.

## Evidence and intent
Railway HTTP logs record /api/chat, /api/operator/requests, and /confirm calls, but not user message bodies. The actual chat history is owner-authenticated and cannot be inferred from HTTP access logs.

## Risk-based interaction
- No separate approval for strictly scoped folder creation (file.mkdir), workspace listing (file.list), reading allowed text files (file.read), listing processes (process.list), and listing Windows (window.list).
- PowerShell and End Task always need one explicit approval inside the same Chat or Neural console. The owner replies SETUJU or BATAL or presses an inline button. Owner cookie, CSRF, owner session and device lease stay enforced.
- No automatic destructive file deletion, wholesale changes, trading, OS administrator escalation, or credential exposure.

## Workspace
Folders may only be created beneath D:\Sonic\work. Names and traversal are independently validated by both server and local Windows companion. Existing folders produce idempotent exists=true receipts.

## Commands
- SONIC, buat folder Kumpulan Renders di TRADEVICEPC
- SONIC, lihat folder Kumpulan Renders
- SONIC, cek proses
- PowerShell: Get-Date (then reply SETUJU or BATAL)
- SONIC, cek log chat history (direct aggregate audit; no raw user message bodies leaked)

## QA
- 172 Python tests passed and 1 skipped; 14 Node tests passed.
- Chrome desktop/mobile with disposable owner and synthetic Windows agent verified no-confirm folder workflow and same-chat PowerShell approval; existing PC Command Center and Neural Brain browser tests passed.
- Real TRADEVICEPC standalone workspace helper test passed folder creation and idempotency.

## Security caveat
PowerShell runs as the existing Limited Windows account after one explicit owner approval and is NOT a true OS sandbox. The server never interprets tool output or AI text as a second owner command.

## Rollback
Reconnect Railway staging to fix/sonic-internal-awareness-v081-20261026 and restore the previous Windows Scheduled Task and helper through the existing companion backup if needed.