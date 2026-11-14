# SONIC v1.4.6: Safari WebRTC negotiation and stable voice option

## Verified user symptom
On 2026-11-14 at 12:11 WIB, Railway staging recorded two Safari Mac
POST /api/preview/voice/sessions requests that returned HTTP 200 and
corresponding /stop calls about 8 and 13 seconds later. This proves upstream
signaling succeeded, but does not identify which transport event caused
disconnect. The previous UI labeled all such reasons as network failure.

## Realtime repair
- The browser now waits for ICE gathering completion (up to 10 seconds)
  before sending a single complete offer to the OpenAI Realtime calls API.
- If candidates never appear, it fails before reserving a paid provider session
  and displays an actionable message. The old timeout of 2 seconds sent
  incomplete SDP offers, which can break on Safari or constrained networks.
- Existing 7-second bounded reconnect behavior remains in place.
- No automatic creation of fresh paid Realtime sessions.
- Staging logs output an allowlisted preview Stop reason code without speech,
  transcripts, SDP, IP or API secrets.

## Mode suara stabil
- The opt-in button appears after WebRTC fails or the demo reaches its limit.
- Safari SpeechRecognition captures exactly one question after user click.
- Recognized text goes to the selected SONIC guest chat model; the browser
  speaks its reply via local speechSynthesis, separate from OpenAI Realtime.
- No private PC, files or memory access. No hidden microphone or auto-retry.
- Stop and page-hide cancel recognition and stale response playback.

## Validation and limitations
- JS: WebRTC ICE candidate completion, timeout, Stop, and compatible voice.
- Python: full suite; Playwright desktop, Mac and iPhone sized browser QA.
- Safari may use its own cloud speech service. Browser speech permissions apply.
- Actual Mac/iPhone microphone and speaker QA must still be checked by user.
