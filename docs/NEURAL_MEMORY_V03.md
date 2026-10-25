# SONIC 0.3: explicit memory and interactive knowledge graph

This release implements the node-network reference, not an anatomical brain image.
SONIC remains a personal assistant; architecture and computer control are deferred.

## Memory fix

The exact command `SONIC, simpan ke memoriku bahwa saya suka bakso` now takes a
server-side deterministic save path. A paid model call is not required for an
unambiguous memory imperative. Negations, questions and quoted examples do not
permit writes. This is a deliberately conservative Indonesian/English parser,
not a universal natural-language intent classifier.

A successful database commit returns a receipt containing a memory ID, source,
source-message ID where available, timestamp and graph-node ID. Identical notes
are deduplicated. Chat displays the receipt, and clicking it opens the real node.
No receipt is displayed for an unconfirmed or failed save. Ordinary chat reads
persisted records as untrusted reference data on each turn. Search is lexical;
this release does not claim embeddings or semantic memory inference.

## Persisted data and migrations

`memory_notes` and all previous data are preserved. Two additive tables are
introduced via existing SQLAlchemy create_all: `memory_sources` and
`memory_links`. Initialization is guarded within the single service process.
Do not deploy multiple uninitialized workers concurrently without a dedicated
migration step. No existing columns or tables are dropped or rewritten.

Memory deletion removes its provenance and saved edges. Previously stored
conversation history is separate from the Memory Vault and is not deleted by
this action. This distinction must not be presented as erasing every historical
mention. Legacy notes retain their IDs and are marked `legacy_memory` when their
original source is unknown.

## Graph truth

- Blue: real saved memory records.
- Yellow: literal words extracted from those records, marked derived.
- Pink: tools from the actual SONIC tool registry, not external connected accounts.
- White: application structure (SONIC and the Memory Vault).
- Teal: an actually registered companion, with its real heartbeat status.
- Solid edges: application structure or a persisted, owner-confirmed relation.
- Dashed edges: a literal term in the source note, not an inferred fact.

The graph is a knowledge UI, not a visualization of the OpenAI model's internal
neural network. Empty vaults do not receive artificial memories or dummy nodes.
Limits: newest 500 memories and 300 literal topics, with total and truncation
reported explicitly. Only the existing owner-authenticated session can read it.
Creating/deleting note relations requires CSRF and deliberate owner action.

## Interaction

Perspective 3D positions, spherical nodes, drag-to-orbit, pan, wheel/pinch zoom,
Fit, 2D/3D, optional orbit, search, filters, inspector, depth 1/2/3, top connections,
path tracing, and confirmed note-to-note relations. The renderer uses WebGL when
available and a Canvas perspective fallback otherwise. Assets are same-origin;
no external graph CDN receives user data. A separate assistant ring reflects
actual local request/microphone/speech activity, not simulated online states.

Mobile inspector/filter panels collapse. Full chat, Memory Vault, Devices,
Setup, voice input/output, and one-frame opt-in vision remain accessible.

## Verification

Run existing and new Python tests: `python -m pytest -q`.
Run real HTTP/browser QA: `python scripts/e2e_neural.py`.
Optional PostgreSQL QA uses only an explicit localhost sonic_test database,
never the application DATABASE_URL. Browser QA uses disposable synthetic notes.
Screenshots must be labeled QA data, not the owner's production graph.

No live OpenAI requests or production credentials are required by these tests.
The local UI was also checked using inline assets and in-process FastAPI
TestClient transport in an environment blocking browser network access.
That check is not a live HTTP browser check or physical iPhone verification.

## Activation and rollback

No new owner token or OpenAI key is needed. Existing Railway settings remain.
Deploy this branch only after CI checks pass, then verify health version 0.3.0
and unauthenticated graph rejection. Live owner memory verification requires a
normal logged-in session; never bypass authentication or inspect private tokens.
Rollback to the preceding app commit is compatible with the original tables;
the additive tables can remain without deleting any user information.
