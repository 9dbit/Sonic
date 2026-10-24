# SONIC: secure staging deployment and companion pairing

## Required services

Create a dedicated Railway project named SONIC and a staging environment, with:
- a PostgreSQL service using its private Railway network;
- a SONIC web service built from 9dbit/Sonic, branch feature/sonic-foundation-20261024;
- the root Dockerfile;
- healthcheck GET /api/health and injected PORT.

Do not expose a public domain before setting owner credentials. A 200 healthcheck only proves the server is alive; setup_required may still be true.

## Credentials

Run locally on a trusted computer:

    python scripts/generate_secrets.py

Store both raw tokens in your own password manager. Do not post raw tokens or API keys in chat, GitHub or screenshots.

Set the following variables on the SONIC web service using Railway Variables, not GitHub source:

    SONIC_ENV=staging
    SONIC_OWNER_TOKEN_SHA256=<generated owner SHA-256>
    SONIC_SESSION_SECRET=<generated random secret>
    DATABASE_URL=<reference to Postgres DATABASE_URL>
    OPENAI_API_KEY=<OpenAI provider key>
    SONIC_MODEL=gpt-4.1-mini
    SONIC_PUBLIC_URL=https://<SONIC Railway service domain>
    SONIC_DEVICE_ID=TRADEVICEPC
    SONIC_DEVICE_TOKEN_SHA256=<generated device SHA-256>

The server requires a durable database in staging or production; SQLite is for local development only. The OpenAI key never reaches browser JavaScript.

## Local test

PowerShell example on a machine you control:

    py -3.12 -m venv .venv
    .\.venv\Scripts\Activate.ps1
    pip install -r requirements.txt
    python scripts/generate_secrets.py

After locally setting the generated hashes and API key in environment variables:

    python -m uvicorn sonic.api:app --host 127.0.0.1 --port 8080

Verify login, a chat response, explicit memory save/delete, and logout.

## Windows companion (only after approval)

The companion is intentionally not automatically deployed to TRADEVICEPC. Once authorized:

    $env:SONIC_BASE_URL = "https://<SONIC-domain>"
    $env:SONIC_DEVICE_ID = "TRADEVICEPC"
    $env:SONIC_DEVICE_TOKEN = "<raw device token>"
    py -3.12 scripts/windows_agent.py

SONIC_DEVICE_TOKEN is different from SONIC_OWNER_TOKEN. It sends only an outbound TLS-validated heartbeat and processes the allowlisted system.status job. Ctrl+C stops it. No Windows service or autostart is created.

## Preflight security checks

1. Unauthenticated chat/history/memory must return 401.
2. Wrong owner token must be rejected.
3. Authenticated data mutations without X-Sonic-CSRF must return 403.
4. The device endpoint rejects missing or invalid device bearer tokens.
5. Commands such as shell.exec, filesystem.delete, browser.click and trading orders must remain unavailable.
6. Memory is user-approved, can be deleted, and must not include credentials.
7. Avoid attaching other projects' Postgres, API credentials or service secrets to SONIC.
8. Never run untested agents with administrative Windows permissions.
9. Browser speech recognition may use the browser vendor's transcription service: enable microphone only when intended.

## Outstanding for full production

- Persistent login revocation and edge-level distributed login rate limiting.
- Per-device registration, token rotation, immutable audit trail, task retry and approval receipts.
- Application-specific permissions, isolation, safe filesystem tools and GUI automation.
- End-to-end Windows physical-device test.
- OpenAI usage caps, budget limits, optional private/on-device speech, and model upgrades.
