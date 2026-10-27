# SONIC V1.0 | Multi-Model Brain Router

**Continuity checkpoint:** 2026-10-27 WIB  
**Branch:** `feat/sonic-multi-model-router-20261027`  
**Base:** SONIC Command Deck R1, commit `6ef97746a2033174078eb314b2069fb3107d0425`.

## What it does

The owner can choose a text/reasoning model from **SONIC → Settings → Model Router**. Each request passes through the existing authenticated SONIC chat engine, with its unchanged tool allowlist, bounded loops, memory permission checks and PC approval layer.

- **OpenAI:** `POST https://api.openai.com/v1/responses`, selected OpenAI text model, existing `OPENAI_API_KEY`. Preserves `store: false` and the existing Responses tool format.
- **OpenRouter:** `POST https://openrouter.ai/api/v1/chat/completions`, fixed reviewed model ID, new `OPENROUTER_API_KEY`. Tool calls are normalized into the same existing SONIC tool engine.
- **Allowlisted models:** `gpt-4.1-mini`, `gpt-4.1`, `z-ai/glm-5.3-prime`, `z-ai/glm-5.3`, plus safe model IDs explicitly configured in trusted server variables.
- **No automatic paid fallback, retries or cross-provider execution replay.** OpenRouter may route its chosen model among inference hosts under its own provider policies; SONIC does not silently switch from GLM to OpenAI.
- The selector never receives API keys and rejects arbitrary URLs/model IDs from client requests.

## Privacy & unchanged features

Switching to OpenRouter **sends text conversation context, relevant Memory Vault records and tool schemas/results** to that service and the inference provider. Settings displays this transfer warning before activation.

**Voice Realtime and Vision remain OpenAI**, using their existing routes. The SONIC 3D Neural Brain and particle animation source files are unchanged. PC Window Control remains separately gated by the local Windows companion and explicit approval. GLM selection does not authorize trading, shell, file writes, or administrative access.

## Railway staging configuration

Set in Railway **staging / sonic-web / Variables**, not in GitHub, browser storage, chat or Memory Vault:

```dotenv
OPENROUTER_API_KEY=<set-in-Railway-Variables-only>
SONIC_BRAIN_PROVIDER=openai
SONIC_OPENROUTER_MODEL=z-ai/glm-5.3-prime
# Keep existing OPENAI_API_KEY for OpenAI chat, voice and vision.
```

Default OpenAI behavior is retained until an owner selects another model. A missing OpenRouter key is normal during preparation: its models show as disabled. Never paste real keys into the chat.

## Owner APIs and storage

- `GET /api/models` requires owner login; includes model labels, selected model, provider-key configured **booleans**, voice provider and recent sanitized usage.
- `PUT /api/models/selection` requires owner cookie + CSRF, a reviewed provider/model pair, and a configured provider key. No extra JSON fields or custom endpoints accepted.
- `POST /api/setup/test-provider` requires owner cookie + CSRF and is **deliberately initiated**, never automatic on login or selection.
- Additive PostgreSQL tables: `brain_preference_v100` and `brain_usage_v100`. Existing chat, voice, memory, PC, and workspace tables are unchanged.
- Usage telemetry records provider, model, latency, token counts, **provider-reported cost when available**, status and timestamp. No prompts, content, response bodies, private reasoning, credentials or tool payloads.
- Malformed, unexpected, or incomplete model responses are rejected; tool arguments must be valid JSON objects. Unknown tools remain rejected by the unchanged SONIC executor.

## Test and release gates

1. CI: owner auth/CSRF, model allowlist and persistence, OpenAI regression, OpenRouter Chat Completions normalizer, invalid JSON tool calls, no fallback, voice independence, error redaction and usage privacy.
2. Browser: disposable localhost owner and fake key; desktop/mobile model switching, persisted choice, no horizontal overflow, Neural and motion anchors untouched. Never call a paid provider in automated QA.
3. Deploy **staging only** after exact-commit CI is green, then verify public health, JS/CSS, model selector and anonymous endpoint protection.
4. Once the owner has configured an OpenRouter key, select GLM, run **Test selected model** once and compare safe, non-sensitive prompts with OpenAI. Test read-only tools first. No MT5/window operations in initial acceptance.
5. No claim of real GLM latency or quality until the provider responds successfully on staging.

**Rollback:** use existing Command Deck R1 source `6ef97746a2033174078eb314b2069fb3107d0425`. Additive tables may remain dormant; do not delete DB records. Production and TRADEVICEPC companion are outside this release.
