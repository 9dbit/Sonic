# SONIC Command Deck | Interface R1

**Status:** UI-only redesign on `design/sonic-command-deck-v100-20261027`, based on the latest Windows-control candidate `0f5a5fbd4f45f31db92fec5e5a65d0903b4da533` (PR #13). Not merged or deployed.

## Creative direction

A calm futuristic command deck: true ink-black base, layered near-black panels, subtle glass reflections, electric cyan and SONIC blue for interaction, restrained hairlines, precise typography, deliberate negative space. Not a gaming dashboard, not a rainbow neon interface. App information and approvals stay the priority.

- **Mark:** original minimal S-shaped acoustic orbit, blue-to-cyan line. Vector source: `web/sonic-mark.svg`. Mounted by FastAPI at `/assets/sonic-mark.svg`, used for favicon, sidebar brand, Chat hero, and owner login.
- **Navigation:** 228px text-labeled rail on desktop, 76px icon rail on tablet, six-slot bottom dock on mobile; keeps original `.nav[data-tab=...]` events and all six pages.
- **Topbar:** page title, live owner-readable subtitle, existing voice/wake/model/device controls. Status colors remain meaningful.
- **Neural Brain:** dark technical grid, low-contrast HUD caption, inspector and filters as airy control panels, composer anchored in the usable center. The graph WebGL/Canvas code and its interaction/physics stay intact.
- **SONIC particles:** `web/motion-core.js`, `web/motion-math.js`, `web/motion-v06.css`, and `web/assets/sonic-particles.mp4` are left untouched. The original `#sonicMotionAnchor`, `#sonicMotionFloat`, double-tap gesture and focus overlay remain.
- **Chat:** restrained conversation surfaces, larger hero and functional navigation shortcuts to Neural Brain, Workspace and Devices. The model remains responsible for responses; this UI file makes no network/tool calls.
- **Workspace / Memory / Devices / Settings:** consistent card radii, spacing, dark surfaces, accessible type and compact device grid. Approval, cancel, direct audio controls and save actions are not replaced.
- **Responsive rules:** 1600, 1350, 1020, 720 and 390 px breakpoints with mobile safe-area handling; reduced-motion is respected.

## Files changed

- `web/index.html` (presentation semantics, logo links, functional shortcuts, existing IDs untouched).
- `web/sonic-shell-v100.css` (late-loaded, scoped visual layer; leaves earlier styling files in place).
- `web/sonic-shell-v100.js` (page subtitle synchronization; hero shortcuts call existing nav click handlers; no storage, microphone, requests or filesystem access).
- `web/sonic-mark.svg` (original vector logo).
- `scripts/e2e_shell_v100.py` and `.github/workflows/sonic-command-deck-v100.yml` (disposable owner/browser screenshot acceptance).

The backend version remains **V0.9.0**, because this is an interface skin, not a backend release. Do not infer that Window Control is activated merely from the version label.

## Acceptance

Five Chromium viewports: 1600x950, 1366x850, 820x1000, 390x844, and 360x740. QA logs and screenshot artifact cover:

1. Owner login and logo rendering.
2. Neural screen displays both its original WebGL/Canvas graph and SONIC particle animation canvas without route regressions.
3. Desktop inspector and mobile inspector/filter toggles.
4. Chat hero and real shortcuts to original Workspace/Devices route handlers.
5. Workspace, Memory Vault, Devices and Settings remain reachable and their core controls remain present.
6. No horizontal page overflow and no uncaught JavaScript errors.
7. No production keys, remote Windows calls, external fonts, remote assets, microphone use or live OpenAI API spend in QA.

## Release boundary

**Keep Railway staging unchanged** while V0.9.0 Window Control PR #13 remains staged for approval. This design branch is based on PR #13, not the outdated `main`. After QA, review this design PR against `feature/sonic-window-control-v090-20261026`; merge in source control only after owner review. Do not commit the existing staged Railway patch or deploy the design without explicit deployment permission. No MT5 operations, Windows agent upgrade or schema migration.
