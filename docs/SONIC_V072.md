# SONIC V0.7.2: Sharp Neural Particles + Black/Dark-Grey UI

## Owner request (26 October 2026)
- No particle glow or blur.
- Each particle 50% smaller than V0.7.1.
- Particle count 2x from 2,940 to **5,880**.
- Only cyan-to-blue gradient for the particle sphere.
- Black 100% (#000000) workspace background.
- Borderless dark-grey UI surfaces (#171717 / raised #222222).
- Solid blue action buttons (#156BFF) without gradients.
- White, blue (#4DA3FF), and orange (#FF9F2F) typography.

## Implementation
- web/motion-math.js: immutable 5,880 point profile, pure exact half-diameter function, 48-step cyan-blue palette.
- web/motion-core.js: Fibonacci sphere preserves orbit, breathing, perspective, activity intensity and return gestures. Replaces halo sprites/additive compositing with small source-over Canvas2D fillRect points with rounded pixel positions. No radial-gradients, shadow blur, filter bloom or sprites.
- web/motion-v06.css: removes all blue/cyan drop-shadow filters and canvas glow.
- web/sonic-theme-v072.css: late-loaded scoped theme override, true black workspace, dark-grey panels, borderless surfaces and flat blue buttons. Keeps blue focus outlines and actual knowledge-graph links.
- web/graph.js: canvas text labels white and blue instead of teal/grey, no label text shadow. Graph node categories and connection data are unchanged.
- web/index.html: 0.7.2 version and cache-busting, theme stylesheet loaded last.
- sonic/api.py: 0.7.2 version.

## Validated on authorized TRADEVICEPC with local disposable QA server
- Python tests: 124 passed, 1 skipped (1 Starlette/httpx deprecation warning).
- Node JS tests: 14 passed, 0 failed.
- Chrome real Canvas2D desktop 1440x900 and mobile viewport 390x844:
  - 5,880 points; previous 2,940; mathematical dot diameter ratio 0.5.
  - No sprite, Canvas filter none, composite source-over, shadowBlur 0.
  - Desktop: 5,088 alpha pixels, all tested pixels in cyan-blue range; mean draw 3.4ms.
  - Mobile: 3,038 alpha pixels, all tested pixels in cyan-blue range; mean draw 3.55ms.
  - Verified #000 workspace, #171717 panels, borderless surfaces and #156BFF flat buttons.
  - Blue labels / white body / orange offline warning are correctly computed.
  - Focus via double tap, speaking state, return command, chat and device panels pass.
  - No browser page errors.
- These timings describe this test computer only, not guaranteed FPS across devices.

## Deployment
Staging service: SONIC > sonic-web, domain sonic-web-staging.up.railway.app.
Source branch: feature/sonic-sharp-blue-theme-v072-20261026.

This release only changes presentation and canvas behavior plus the API display
version. It does **not** modify Windows companion capabilities, trading, model
limits, stored owner memory or device credentials.

## QA
- node --check web/motion-core.js
- node --test tests/js/*.test.cjs
- python -m pytest -q
- python scripts/e2e_motion_v072.py

CI: .github/workflows/motion-v072.yml. Screenshots and JSON metrics in
artifacts/motion-v072/ are produced from fake owner credentials in local QA.
