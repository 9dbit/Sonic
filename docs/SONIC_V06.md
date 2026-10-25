# SONIC V0.6 | Motion Core & Persona Studio

## User reference

Based on the user-supplied `Screen Recording 2026-10-26 at 00.26.22.mov` of a fluid, silver granular particle sphere. The user-supplied video was transcoded to 5-second, 480px H.264 MP4 (under 600 KB). Do not claim original vector geometry or exact 3D points are available. Reuse the recording only with rights appropriate to the app's intended distribution.

## Motion engine

- The motion clip is decoded as muted inline video and rendered into a truly transparent WebGL canvas by chroma keying black pixels; bounded 2D canvas fallback.
- Loops continuously, playback speed eased between idle (.55x), listening (.95x), thinking (1.18x) and speaking (1.85x). Audio state events, not fake microphone permissions, control these transitions. Speed is a state proxy, not a waveform-accurate audio amplitude measurement.
- Hover or single tap increases display scale by 10%; a second tap within 1000 ms focuses in the center with 820 ms transition. Escape, second double tap, or a 'minggir' / 'kembali ke tempat semula' command restores its original floating position.
- Works with mouse, keyboard, touchscreen, desktop/mobile layouts, reduced-motion preference, and page visibility.
- Canvas transparency comes from shader output alpha, not from an opaque MP4 file. If WebGL is unavailable, the slower pixel-alpha fallback is used.

## Persona

- Owner-authenticated `GET /api/persona`, CSRF-validated `PUT /api/persona` and POST `/api/persona/presets/{work|personal|experimental}`.
- Database table `persona_preferences` is additive; existing memory, session and device tables are unaffected.
- Ten curated voice choices map to OpenAI's Realtime-supported voices: cedar, ash, echo, ballad, verse, marin, coral, shimmer, sage and alloy. Group labels 'male-inspired' and 'female-inspired' are subjective listening categories, not an official gender classification or promise of vocal pitch.
- Voice Preview sends consented text to the configured TTS API and does **not** save or change selected voice.
- Ten allowlisted language styles and three response intensities affect both model text instructions and new realtime voice sessions; no style overrides system safety, tool permissions, evidence rules or memory approval.
- Presets: work/professional/short, personal/friendly/balanced, experimental/glitch/expressive.
- Saved persona applies to subsequent messages and new voice sessions. OpenAI Realtime voice **cannot be switched after first audio output in an existing session**; stop/restart Talk to switch.

## Privacy and scope

- No new PC privileges or background microphone activation are part of this release.
- Source clip is not sent to OpenAI. Preview requests use OpenAI TTS and may incur API charges. Audio playback is presented as AI-generated voice.
- No provider voice is cloned from the original recording.
- Browser QA on desktop and mobile viewport uses disposable owner account and database. Physical iPhone acceptance and live TTS tonal categories require separate testing.

## Manual acceptance

1. Login -> Setup -> Persona Studio, choose one of ten voices and preview it. Set style and response intensity; Save, reload, verify persistence.
2. Open Neural: silver particle blob appears on transparent background, moving slowly. Hover/tap first: +10%. Double tap in <1s: centered and enlarged; command 'Sonic, kembali ke tempat semula' returns it.
3. Enable audio and speak: faster speaking motion, decaying back to idle. Confirm automatic rotation in Neural graph continues independently.
4. Start a **new** Realtime session after changing voice and confirm selection; existing session retains its previous voice.
5. Observe no changes to TRADEVICEPC, shell/mouse permissions, or MT5.
