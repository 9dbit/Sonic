# SONIC Multi-Model Router V1.0

Branch: feat/sonic-multi-model-router-20261027
Base: design/sonic-command-deck-v100-20261027
Release status: feature branch only; no Railway deploy or provider key changes.

## Capabilities
- SONIC Chat/Brain chooses an allowlisted OpenAI Responses or OpenRouter Chat Completions model.
- OpenAI default remains gpt-4.1-mini or server-configured SONIC_MODEL; OpenRouter options include z-ai/glm-5.3-prime and z-ai/glm-5.3.
- Owner chooses the model in Settings / Model Router; one click plus explicit provider data-sharing confirmation and backend CSRF protection.
- Owner choice persists in an additive brain_preference_v100 table; no changes to existing chat, Memory Vault, PC, owner, or voice tables.
- Adapter normalizes OpenRouter function calls and results into the same SONIC server-side allowlisted, audited tool dispatcher; no new execution permission.
- Usage dashboard shows latency, input/output tokens and reported provider cost when available, not guessed prices. The additive brain_usage_v100 stores no prompt, transcript, memory, key or tool output.
- No automatic fallback, retry or replay: provider errors require owner review and an explicit model change.

## Privacy and isolation
OpenRouter receives chat context, tool schemas and potentially relevant Memory Vault records and tool responses when the owner explicitly switches to that provider. Data may travel to the selected downstream inference provider. Inspect those providers' privacy terms before transmitting confidential documents. No API key is entered or stored in browser UI.
OpenAI Realtime Voice and browser microphone remain on the existing OpenAI integration. Image analysis and speech synthesis remain OpenAI-only and require OPENAI_API_KEY. Model selection affects text chat/Brain only.
No permission is granted to bypass owner approval, start local Windows applications, send broker orders, transfer payments or modify files.

## Staging configuration (not yet applied)
- OPENROUTER_API_KEY: add through Railway staging Variables; never paste to chat, repository or memory.
- SONIC_BRAIN_PROVIDER=openai (default; optional).
- SONIC_OPENROUTER_MODEL=z-ai/glm-5.3-prime (optional trusted override).
- Existing OPENAI_API_KEY remains unchanged for OpenAI chat, Realtime Voice and Vision.
Without an OpenRouter key, GLM options appear in Settings as unavailable and cannot be activated.

## Acceptance checks
1. Python/Node syntax checks; provider adapter and existing SONIC engine, Voice and auth regressions.
2. Tests reject arbitrary model IDs, extra request fields, unauthenticated/CSRF-free changes and malformed provider tool events.
3. Tool roundtrip uses correct assistant tool_calls before tool results; provider HTTP failure does not echo raw error or automatically retry.
4. Browser acceptance runs in disposable SQLite with a fake OpenRouter key: desktop and mobile selection, persistence, empty metrics, no horizontal scroll and no JS exceptions. It does not spend provider tokens.
5. All inherited GitHub PR workflows pass before staging deploy. A real GLM call requires a valid owner-created OpenRouter key and explicit Test selected model click.

## Rollback
Last proven Command Deck R1 staging source: 6ef97746a2033174078eb314b2069fb3107d0425. Restoring that source reverts app behavior without deleting persistent notes or resetting PostgreSQL. Additive new tables may remain unused.
