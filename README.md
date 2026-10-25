# SONIC

**SONIC is your personal AI assistant powered by OpenAI.** It is a general-purpose assistant, not an architecture-only system. SONIC combines conversation, user-approved memory, voice, tools, and an optional companion on your authorized PC.

## V0.1 foundation

| Area | Status |
| --- | --- |
| Private owner-login dashboard | Implemented |
| OpenAI Responses chat and bounded tool-calling | Implemented; requires API key |
| Persistent chat and explicit memory | Implemented; Postgres on Railway |
| Browser voice input and playback | Implemented where browser supports it |
| Opt-in camera, one-frame screen capture, image analysis | Implemented; requires API key and browser permission |
| Windows companion | Written, not installed on TRADEVICEPC |
| Read-only PC status | Implemented behind distinct device credential |
| Unrestricted computer/software automation | Not yet available |

The current agent cannot run a shell, read arbitrary private files, operate software, or send trading commands.

## Architecture

Browser chat/voice -> SONIC FastAPI (Railway) -> OpenAI Responses API, Postgres memory, allowlisted tool dispatcher -> outbound-only Windows companion.

## Local setup

Python 3.12 recommended:

    python -m venv .venv
    pip install -r requirements.txt
    python scripts/generate_secrets.py
    # Configure SONIC_OWNER_TOKEN_SHA256, SONIC_SESSION_SECRET, OPENAI_API_KEY
    python -m uvicorn sonic.api:app --host 127.0.0.1 --port 8080

Open http://127.0.0.1:8080. The raw owner token is generated on your machine and must never be committed or pasted into chat.

## Windows companion

After explicit owner approval, set SONIC_BASE_URL, SONIC_DEVICE_TOKEN, SONIC_DEVICE_ID and run:

    python scripts/windows_agent.py

This companion runs only a read-only system.status capability and can be stopped with Ctrl+C. It is not installed or registered as a service in V0.1.

## Tests and guides

    python -m pip install -r requirements.txt
    pytest -q

See [deployment setup](docs/DEPLOY.md) and [system architecture](docs/ARCHITECTURE.md).

Development branch: feature/sonic-foundation-20261024. Keep source code, Postgres, provider keys and computer access separate from other projects.
