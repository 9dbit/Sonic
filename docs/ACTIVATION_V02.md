# SONIC V0.2 activation candidate

## Scope

SONIC remains a general-purpose personal assistant. Architecture, SketchUp, Revit and trading integration are not enabled.

This candidate adds:
- Owner-only Setup screen and explicit OpenAI connectivity test.
- Database-backed owner-session revocation; replaying a logged-out cookie is rejected.
- Browser security headers, no-store API responses, and whitespace-only memory rejection.
- Longer device-result polling and a visible timeout instead of indefinite waiting.
- Mobile-accessible sign out with errors reported instead of silently pretending logout succeeded.
- Read-only Windows companion `--once` mode for bounded validation.
- Reproducible HTTP/restart/companion test and optional Chromium/WebKit browser smoke script.
- Tool-output pairing for every returned function call, with bounded execution.

## Verified locally on TRADEVICEPC

`python -m pytest -q`: 24 tests passed (one upstream test-client deprecation warning).
`python scripts/e2e_smoke.py`: passed all five scenario groups:
1. Real HTTP login and unauthorized-access rejection.
2. Memory and session survive a backend restart.
3. Missing OpenAI key fails closed.
4. Actual read-only companion subprocess completes a local HTTP system.status job.
5. Memory deletion and logged-out session replay rejection.

Tests used a disposable loopback server, disposable SQLite database and newly generated synthetic test tokens. They did not use production tokens, call OpenAI, create a permanent companion, or change MT5. The disposable server and companion subprocesses are stopped when the test exits.

## Remaining activation gates

Automatic credential configuration was blocked. No workaround should bypass that boundary. The owner must configure secrets directly in Railway Variables.

Required for owner login:
- SONIC_OWNER_TOKEN_SHA256
- SONIC_SESSION_SECRET

Required for live AI requests:
- OPENAI_API_KEY

Optional for pairing the real companion later:
- SONIC_DEVICE_TOKEN_SHA256 (different credential from the owner login)

Run `python scripts/generate_secrets.py` yourself in a trusted terminal. Store raw owner/device tokens privately and copy only the required server values directly to Railway. Generate a fresh session secret; do not reuse anything displayed in a chat or tool log. Never paste provider keys into chat, memory or git.

After owner authentication is configured, expose the HTTPS service domain, set SONIC_PUBLIC_URL, sign in, open Setup, and use Test OpenAI. A successful healthcheck or passing mocked provider test is not proof of a successful live model request.

## Reproducible commands

    python -m pytest -q
    python scripts/e2e_smoke.py

Optional isolated browser checks:

    python -m pip install playwright==1.56.0
    python -m playwright install --with-deps chromium webkit
    python -m scripts.e2e_browser

Browser automation uses synthetic local credentials. Mobile viewport tests are not physical-iPhone camera/microphone tests. The existing GitHub workflow remains unchanged; the optional browser script is not yet wired into CI.

## Boundaries

No permanent agent, Windows autostart, arbitrary shell tool, account transaction, software automation or architecture execution is enabled by these changes. Existing architecture and trading projects are not modified. Provider credentials and cloud owner authentication remain prerequisites before calling the system end-to-end operational.
