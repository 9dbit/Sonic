# SONIC V0.8.4 | Voice command reliability

Release target: Railway staging (SONIC web) with existing Windows companion V0.8.3 on TRADEVICEPC.

## User reproduction, 26 October 2026

Mobile Realtime microphone transcript: `Buatkan di desktop dengan nama foldernya Today.` SONIC claimed it would start, then apologized and suggested manual Windows/PowerShell steps without an actual PC action receipt. The HTTP trace near 04:00 UTC showed authenticated `POST /api/voice/sessions/<id>/dispatch` HTTP 200, two `/tools` HTTP 403 responses, and regular Windows heartbeat and operator polling HTTP 200. No successful Windows job result was observed for that window.

## Root cause

- Earlier deterministic parser only matched `buat folder <name> di desktop`; it did not handle `buatkan di desktop dengan nama foldernya <name>` and similar spoken word order.
- Unrecognized voice commands fell into a general unconstrained Realtime model response, which could promise an operation without the SONIC Windows action engine having queued anything.
- A generic tool call to a disallowed voice tool yielded HTTP 403. Voice tools intentionally cannot execute raw PowerShell or arbitrary commands.

## Fix

- Explicit spoken phrase variants are accepted by the same server-side owner intent parser used for text chat. Desktop and workspace paths remain distinct and validated.
- Realtime speech for PC requests now uses a response with `conversation=none`, `tool_choice=none`, `tools=[]` and the actual bounded backend status as its only input. The unconstrained model is not asked to invent a PC plan for an accepted action.
- A task is complete only after the authorized Windows Agent posts a receipt. Queued, failed, already existing and completed states are different, grounded voice outcomes.
- Repeated transcription item IDs are ignored in the browser and deduplicated on the server; a duplicate cannot enqueue another folder creation.
- Questions such as `Sudah jadi?` resolve against the most recent owner-authenticated PC job within the current voice session.
- A voice-only `setuju` cannot authorize PowerShell/End Task. An explicitly reviewed action must be approved through its in-chat button; the click is tagged as such and remains owner-authenticated. Safe folder creation needs no additional confirmation.
- Unrecognized PC-looking requests receive a clear *no action queued* explanation, rather than an unsupported claim or manual workaround.

## QA

- 215 Python tests passed; 1 skipped. 22 JS tests passed.
- Desktop/mobile Chromium QA: voice transcript to PC action view, inline sensitive-action button, existing PC Command Center and Neural Brain motion all passed.
- The original user phrase, paraphrases, unsafe paths, duplicate item IDs, a real leased-job state transition, voice-only approval denial, and Windows result follow-up have automated regression coverage.
- Windows companion capabilities from V0.8.3 require no installer change for this web/backend-only patch.

## Acceptance to perform on the real iPhone

1. Hard refresh SONIC staging; verify header version 0.8.4.
2. Stop any prior Realtime session and start a fresh Talk to SONIC call.
3. Say `Buatkan di desktop dengan nama foldernya Today.`
4. Confirm chat shows `desktop.mkdir` queued, then a Windows Agent completion receipt or an explicit failure reason. Check Desktop `Today` on TRADEVICEPC.
5. Say `Sudah jadi?` and confirm SONIC reports the observed folder state, without inventing another command.

## Rollback

Reconfigure `sonic-web` staging source to `feature/sonic-voice-desktop-bridge-v083-20261026`; Windows companion can stay at V0.8.3. No data migration is required.
