# SONIC Engine V0.5: Presence, Windows Tools & Blue Command Center

**Status:** code candidate; live availability requires passing CI, Railway deployment `SUCCESS`, and authenticated TRADEVICEPC v0.5 heartbeat. Model-led PC actions and background OS wake-word recording are not provided.

## Scope

- Blue-first SONIC UI: borderless glass surfaces, pill controls, refreshed neural/device icons; 3D graph starts orbiting unless the OS requests reduced motion. Pointer/scroll gestures pause orbit temporarily. Focus animates the camera toward a real node; unique graph searches can focus automatically.
- Device insight uses authenticated telemetry from TRADEVICEPC, including RAM total/available and bounded disk capacities. A read-only `device_metrics` tool is available in Realtime Talk, so voice can show the same popup and speak actual values. No fake metrics; offline/stale companion reports unavailable. `cek TRADEVICEPC berapa memory yang tersisa` returns read-only data and opens a popup.
- Operator PC actions are **not** an unrestricted remote command channel. They are individually proposed by the owner, reviewed in a modal, confirmed with a digest, expire in 90 seconds, are leased once, and are checked again by the device. Logout revokes owner authorization.
- Allowed shell *recipes*: clock, memory and system overview only. File reads are UTF-8 text files of at most 32 KB located **inside `D:\Sonic\work`**, excluding known secret-file names. Mouse and keyboard controls require a foreground **Notepad** window and are not general software automation. MT5/trading/system administration remain excluded.
- Opt-in foreground wake-word uses the browser's SpeechRecognition API. Microphone starts only after user activation, with a visible indicator. Saying **SONIC** can launch Talk, and SONIC plus a recognized command can use the regular owner-authenticated chat route. The browser may send speech to its provider. This is **not** an always-on OS assistant, and cannot promise listening while an iPhone browser is hidden or locked.
- Realtime Talk can hide its panel without stopping microphone and can re-expand it via the bar. Voice commands for stopping the session or stopping all are supported when the speech transcript is delivered. Session expiry and visible Stop remain authoritative.
- A default synthetic `cedar` TTS endpoint and an optional, explicit audio-to-text reference-transcription endpoint are provided. The uploaded recording is not retained by SONIC, and speech-to-text asks the provider to ignore music but does **not** perform reliable music separation. There is **no voice cloning**, film-character impersonation, or original reference voice replication. TTS is billed via OpenAI API.

## Setup and deployment

1. Deploy GitHub candidate branch to the SONIC **staging** service on Railway. Do not deploy to an unrelated app or trading service.
2. Keep existing owner/device credentials intact. Verify `/api/health` returns `0.5.0` and service `SUCCESS`.
3. Pair the Windows companion **only** after reviewing `scripts/windows_agent_v05.py` and creating a private environment that loads the existing DPAPI-protected device token; verify the local workspace path is present. Running v0.4 companion continues to supply heartbeat but does not expose v0.5 capabilities.
4. On Devices, request a RAM reading, then a clock recipe with **Review PC action → Approve once**. Verify both visible completion and no access to trading or non-allowlisted files. Only then test Notepad.
5. For wake mode, opt in via **Standby off → Standby on** while the browser tab is visible. Click **Standby off** or close the tab to stop recording. Audio that the browser sends to a speech-recognition service is governed by that service.
6. For reference transcription, choose the audio file from your own device and press **Transcribe spoken words**. No original reference audio is committed into SONIC.

## Security and limitations

- The device is an outbound HTTPS client, no new inbound port or administrative Windows service. All device tool capabilities have a second independent local allowlist. No arbitrary PowerShell arguments, shell strings, hidden listening, secret reads, clipboard shortcuts, cross-app input or domain-wide access.
- Voice operations need separate owner consent; WebRTC media or provider transcription is not guaranteed to work on physical iPhone/Safari until tested. Foreground wake recognition may stop unexpectedly on mobile, and continuous recognition may use cloud services.
- A response marked **prepared** in graph command routing is not proof it animated in a browser. UI tests must verify selection and actual popup rendering.
- Telemetry is time-bounded: >120 seconds without a valid heartbeat is considered stale.
- Existing memory and chats remain intact; schema changes are additive. A rollback to 0.4 keeps the additional telemetry tables without removing data.
- Do not copy API keys, voice recordings or device tokens to the code repository.

## Tests

```
python -m pytest -q
node --test tests/js/*.test.cjs
node --check web/app.js
node --check web/graph.js
node --check web/wake-v05.js
```

CI must pass before branch cutover. Physical PC UI/Notepad tests are still required after pairing, and synthetic voice tests do not prove real provider compatibility.
