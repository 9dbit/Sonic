# SONIC V0.6.1: Persona Playback, Visible Motion, PC Status

## Persona synchronization
- `Play selected style` generates a fixed sample appropriate to the selected style in **the currently selected voice and intensity**, using `/api/voice/speak` with allowlisted preview overrides.
- Preview does not save the profile. `Apply voice + style` saves all three fields at once.
- Chat and TTS use the persisted persona immediately; the next Realtime session uses the new voice and instructions.
- When a Realtime session is already active during Apply, SONIC stops it, then **asks for microphone consent again**. Realtime voice cannot be switched after audio has started. Never auto-start microphone.
- The app no longer silently falls back to an unrelated OS synthetic voice if the selected provider TTS fails.

## Motion
- `web/motion-core.js` is now an entirely alpha-transparent native Canvas2D particle field. It does **not** require H.264/WebM decoding, autoplay or WebGL to show the silver granular blob.
- Applies current app activity state to speed/energy, hover/single-tap 10%, double tap <= 1s focus, and voice/text return command.
- Reduced-motion honors OS preference; hidden pages stop rendering.
- Browser QA checks actual nontransparent canvas pixels, not just that an empty canvas node exists.

## TRADEVICEPC
- Reading RAM through an independent authorized RDC session succeeded, proving Windows reports available memory.
- The cloud Dashboard reads **authenticated telemetry only**; the existing V0.4 companion never transmitted RAM, so no server-side change alone will invent the number.
- `scripts/Install-Sonic-Companion.ps1` is a **user-executed** local upgrade with a preflight one-shot authenticated telemetry check, DPAPI credentials retained on device, limited Windows Scheduled Task, rollback of task action on failure.
- Source stays limited to allowlisted fixed shell recipes; file reads and directory browsing within `D:\Sonic\work`; process/window inventory; Notepad-only UI with owner approval. Existing MT5 must not be touched.
- Run locally from a reviewed branch checkout as the Windows user that owns the DPAPI credential:

```powershell
powershell -NoProfile -File .\scripts\Install-Sonic-Companion.ps1
powershell -NoProfile -File .\scripts\Install-Sonic-Companion.ps1 -Install
```

- Stop if the preflight fails or the task privileges are higher than Limited. Never paste device tokens or OpenAI keys into chat.

## Full access boundary
The owner requested broad computer control *except* shutdown/restart. Arbitrary shell plus a generic GUI would enable power operations indirectly, so those two exclusions cannot be guaranteed by keyword filtering. SONIC will expand capability by adding audited operation types with OS-level boundaries and explicit owner approval; unguarded arbitrary shell is **not** enabled in this release. A dedicated restricted Windows account/worker and owner-defined application/file scopes will be required for broader access.

## Required checks
- CI Python, Node, desktop/mobile Playwright end-to-end before staging deploy.
- Live TTS preview requires a configured OpenAI API account. CI mocks the provider, not the audio output.
- On actual TRADEVICEPC, the user must run the supervised installer; only after a V0.5+ heartbeat may RAM availability be claimed online.
