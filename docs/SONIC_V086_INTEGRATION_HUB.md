# SONIC V0.8.6 | Integration particle and executor registry

## User request

Add exactly **one** Integration particle to the Neural Brain. Selecting it displays the tools that SONIC can use, or may collaborate with in the future, as execution adapters. Examples: Remote Desktop Commander (RDC), Google Drive, Notepad and additional future connectors.

## Implemented in this release

- `integration:hub` is one real knowledge graph node (category `integration`) connected structurally to `system:sonic`; when TRADEVICEPC exists, it also links to that registered Windows device.
- The normal Knowledge Graph remains evidence-backed. The Integration inspector is populated by SONIC's own `sonic.integrations.CATALOG` and live device telemetry; it does not assert that a ChatGPT connector authorizes the separate SONIC web application.
- One cyan/blue sharp particle without glow, prominent label and an Integration focus shortcut in the graph toolbar. The iPhone view uses a compact icon and opens the same inspector without navigating away.
- The inspector lists four initial adapters and shows purpose, verified state, requirements, runtime capabilities and the last Windows native job status when available.
- `GET /api/integrations` is authenticated owner-only, read-only. It returns a sanitized adapter capability registry and no OAuth tokens, local secrets or raw desktop content.
- Windows Native is online only with a fresh authenticated device heartbeat **and** fresh capability advertisement. It is not considered online merely because a registered device exists in the database. Distinguish `offline` from `not_ready`.
- RDC, Google Drive and Notepad are listed as candidates with explicit `not_connected` or `not_ready` status. A ChatGPT OAuth or plugin connection is **not** inherited by SONIC.
- The text/realtime assistant receives a compact, read-only status summary so it can answer honestly about integration availability. `Buka Integration` is a deterministic, read-only graph focus instruction.
- No new arbitrary execution privileges, no OAuth grant, no unrestricted PowerShell, no GUI automation, and no production trading effects are introduced by this release.

## Initial registry

| Adapter | Status from SONIC | Current execution basis | Next milestone |
| --- | --- | --- | --- |
| Windows Native | `online` only when verified; otherwise `offline` / `not_ready` | Existing leased-command Windows companion, Limited user | Operational voice acceptance and multi-step audit |
| RDC / Desktop Commander | `not_connected` | No independent SONIC-to-RDC MCP handshake exists yet | Explicit SONIC-side MCP auth and bound executor with result receipts |
| Google Drive | `not_connected` | No independent SONIC Google OAuth grant exists yet | Owner OAuth with minimum scopes and revocation controls |
| Notepad | `not_ready` | Windows app, not yet an approved UI Automation executor | Local GUI interaction, explicit window targeting and screenshot/UIA evidence |

## Design rules

Screen background 100% black, charcoal Inspector cards, no decorative borders/glow, blue solid focused button, cyan/blue Integration particle, white primary text and orange for unavailable states. One hub particle; the four adapters appear as inspector entries, not fake extra graph particles.

## QA

- 260 Python tests pass, 1 skipped; 22 JavaScript tests pass on the final integration release.
- Chromium browser tests for desktop 1440x900 and iPhone-size 390x844: exactly one Integration node, four adapters, correct verified status, real status refresh, no horizontal overflow, no JS errors, no change to existing Neural Brain motion. Neural Brain motion regression (desktop/mobile) passed with 5,880 cyan-blue particles and no glow.
- Owner/production sign-in is not used in these synthetic tests. Verify live staging `/api/health` and `/api/integrations` after Railway deploy.

## Next: functional adapter connection, not just a visual catalog

1. Design a single `ExecutorAdapter` interface with `health`, `capabilities`, `prepare`, `execute`, `verify` and `cancel`. The owner grants each adapter independently.
2. RDC: implement SONIC-owned MCP client over a supported authenticated/local bridge, connection setup, per-tool allowlists, audit trail, explicit owner approval for sensitive actions, health checks and short timeouts.
3. Google Drive: implement SONIC-owned OAuth consent, narrowly scoped permissions, encryption and revocation, idempotent file operations and verification receipts.
4. Notepad/SketchUp/Revit: first implement a Windows interactive session GUI bridge with UI Automation and application-specific APIs. Never treat `notepad.exe` being installed as proof SONIC can control it.
5. After validated adapters are connected, elevate their status to online using independent health checks and verified receipts. Route tasks based on capabilities and reliability, with a safe fallback and stop switch.

## Rollback

Repoint Railway staging `sonic-web` to `fix/sonic-voice-dispatch-audit-v085-20261026`. No DB migration, Windows agent installer change or external connector authorization was introduced.
