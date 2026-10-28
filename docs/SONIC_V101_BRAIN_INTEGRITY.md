# SONIC V1.0.1 | Brain tool-call integrity hardening

**Date:** 2026-10-28 (Asia/Jakarta)  
**Base:** `feat/sonic-multi-model-router-20261027`, commit `d65545572892396cea33b0369e156ae9986dbc54`  
**Scope:** Code and regression tests only. This branch does **not** deploy Railway or modify the local Windows companion.

## Why this upgrade is needed

The V1.0 multi-model adapter already validates JSON syntax, fixed provider URLs, owner model selections, and existing PC approval policy. However, a subsequent OpenRouter conversation must also authenticate the *structure* of all replayed tool receipts. Otherwise, a malformed model trace could present an orphan output as tool data, replay one tool receipt twice, or leave pending calls while moving to a new conversation message. The OpenRouter response adapter must additionally reject tool names that were not offered and duplicate call IDs. An incomplete OpenAI Responses reply must never trigger tool dispatch even when a function call appears in its output.

## Implemented boundaries

1. `sonic/providers.py`: reconstruct OpenRouter messages only from well-formed call batches with unique IDs and exactly one matching string receipt for each call; reject orphan, duplicate, interleaved and unfinished tool messages. Preserve normal multi-tool batches and first-party user/system isolation.
2. `sonic/providers.py`: reject OpenRouter tool-call outputs containing names not offered in the current request or duplicate call IDs before returning any function call to SONIC's executor.
3. `sonic/brain.py`: fail closed on an explicitly incomplete model response *before* processing its tool calls. Still write a sanitized `incomplete` usage row; no tool dispatch or success claim.
4. `sonic/activation.py`: the explicit owner provider-connectivity test requires the exact `SONIC_OK` sentinel after whitespace trimming. An answer containing that string alongside other text is not accepted.

## Safety unchanged

- Chat provider remains owner-selected OpenAI/OpenRouter; **no automatic paid retry/fallback**.
- Realtime Voice and Vision remain OpenAI; their consent and microphone controls are untouched.
- MT5 window operations and all PC commands remain behind the existing companion, live capabilities, and owner-approval gates.
- No account tokens, prompts, transcripts, voice prints, device data or raw provider response bodies are added to metrics.
- No database schema modification, new settings, external dependency or Windows elevated rights.
- Family Voice Profiles remain *backlog*, not enabled.

## Acceptance

Run the inherited `SONIC Multi-Model Router V1.0` workflow and all related workflows against **the exact final branch SHA** before considering a source merge. Added regression cases cover orphan and mismatched receipts, duplicate IDs, unfinished tool batches, unoffered tools, incomplete OpenAI tool calls, and misleading provider-verification text. All provider tests use synthetic responses and keys; no paid provider request, live device action, or biometric capture.

Railway SONIC / staging has a separate pre-existing source patch for V1.0 commit `d6554557`. **Do not accept it or deploy V1.0.1 from this PR automatically.** After CI, review and explicitly authorize staging deployment, pinning the tested SHA, and retain prior Command Deck R1 commit `6ef97746a2033174078eb314b2069fb3107d0425` as the rollback anchor. Production is outside this scope.
