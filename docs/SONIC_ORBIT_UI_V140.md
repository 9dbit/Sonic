# SONIC Orbit UI 1.4.1

## Scope

Implements the owner's supplied orb and purple-blue interface references on the
existing application. Based on deployed passkey release `650196c9`, not the older
DeepSeek-only branch. Existing chat, voice, graph, workspace, model selection,
Software Manager and PC action approval routes remain in place.

- Reusable animated SVG logo: repeating small jump, blink and left/right gaze.
- Existing motion controller now draws a matching glossy orb instead of the
  superseded 5,880-point sphere. The gesture API and knowledge graph are retained.
- Double tapping the header logo or brain orb centers SONIC and invokes the
  existing explicit voice-start path. A single tap never invokes the microphone.
- Purple-blue edge ribbons appear only in the summoned state. They cannot
  intercept clicks. Stop/Mute remain above the effect; Stop also returns the orb.
- Escape/Return minimizes the orb; it does not silently change microphone state.
- The state caption follows actual voice events, not visual animation timing.
- Cards show authenticated saved-note count, device connectivity/telemetry and
  selected chat model. No invented sample data from the concept board is used.
- Chat model and OpenAI voice are labeled separately.
- Dashboard cards clear on expired authentication and ignore late private data.
- Desktop navigation and the six-route mobile floating dock preserve all actions.
- Staging may set `SONIC_OPEN_PREVIEW=true` to hide the login/passkey overlay and
  allow UI/navigation review without issuing an owner session or CSRF token.
  Private data, chat/voice providers, settings writes and PC actions remain denied.
- Reduced-motion preference disables SVG bounce/eyes and edge ribbons; the orb
  renders a static pose. Canvas updates are capped at 30 fps and paused when the
  document is hidden. No external asset/CDN or animation dependency is added.

## Validation

Local Python: 549 passed, six skipped because disposable PostgreSQL is not
configured. Local JavaScript: 59 passed. Dedicated browser acceptance covers
1440, 820, 390 and 360 px viewports, actual orb pixels, no horizontal page overflow,
all six routes, one voice start per double tap, click-through decoration, real
Stop hit testing, reduced motion and locked-session data clearing.

Existing passkey enrollment/login/logout with Chromium virtual authenticators,
workspace CRUD/conflicts/voice routing and shell regression passed locally.
Virtual authenticator and synthetic voice results are not a real biometric or
provider-audio test. All browser test data is disposable and provider calls are
blocked or mocked. No live TRADEVICEPC operation is issued by these tests.

## Release

Target only `SONIC / staging / sonic-web`. Wait for the reviewed commit's CI,
then stage and apply that exact source. Confirm terminal deployment SUCCESS and
HTTP 200 at `/api/health` with version 1.4.1 and public assets before claiming live.
No Windows Companion change or restart of Postgres/TRADEVICEPC is required.

Rollback to `650196c9fcc06870be42597bc5e0845afaa7962e` restores the previous UI while
retaining the same passkey-capable authentication backend and existing data.
