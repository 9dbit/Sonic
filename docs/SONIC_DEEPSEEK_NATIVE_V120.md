# SONIC 1.2.0 — Native DeepSeek chat

Prepared: 2026-11-10, Asia/Jakarta.
Base release: `1a7e7d9f00aa9e24c3d1729eea3e3dcae1617ea6` (Software Manager 1.1.0).
Target: existing `sonic-web` staging service.

## Behavior

DeepSeek is an additional owner-selectable chat/Brain provider in Settings → Model Router.
The existing owner model choice is preserved. OpenAI Realtime Voice, speech synthesis,
and image analysis retain their OpenAI integration. Companion permissions and software
approval rules are unchanged.

- Provider identifier: `deepseek`.
- Default model: `deepseek-flash`.
- Fixed request endpoint: `https://api.deepseek.com/chat/completions`.
- Server credential: `DEEPSEEK_API_KEY`, never supplied in a browser request or repository.
- Optional trusted server model override: `SONIC_DEEPSEEK_MODEL`.
- Explicit `thinking: {"type": "disabled"}` and bounded output tokens.
- No automatic provider fallback, paid retry, or replay of PC actions.

This first native integration uses ordinary Chat Completions with thinking disabled.
DeepSeek enables thinking by default and requires reasoning history to be returned in
subsequent tool rounds when thinking is enabled. SONIC intentionally does not persist
or transfer private provider reasoning. A thinking-mode option would require a separate
reviewed conversation-state design; it is not exposed by this release.

The adapter translates SONIC's canonical tool trace into assistant tool calls followed
by their authenticated tool results. Provider calls still pass through the same
allowlisted dispatcher and existing owner approvals. Malformed, incomplete, duplicate,
and unapproved tool calls are rejected before dispatch. HTTP errors expose a sanitized
status rather than an upstream body.

## Configuration and owner activation

1. In Railway → SONIC → staging → sonic-web → Variables, enter `DEEPSEEK_API_KEY` using
   the secret configuration UI. Keep the existing OpenAI key for its existing features.
2. Deploy the tested source. The default model is already `deepseek-flash`; an additional
   `SONIC_DEEPSEEK_MODEL` variable is only needed for a deliberate server override.
3. Sign in to SONIC as owner and open Settings → Model Router.
4. Select DeepSeek and confirm **Activate model**. The confirmation explains that chat
   context, relevant Memory Vault entries, and tool descriptions/results may be sent to
   DeepSeek. The choice is saved for subsequent chat requests.
5. Click **Test selected model** once, then test a non-sensitive chat and a read-only tool.

Key presence means configured, not successfully connected. Selecting a model does not
make a paid test call. A provider test is an explicit owner action. Missing keys disable
the corresponding model option. No key is displayed, entered, or saved in browser storage.

`SONIC_BRAIN_PROVIDER` supplies the initial default only when no saved owner preference
exists; changing it does not override an existing Model Router selection.

## Usage and test evidence

Usage records retain provider/model, duration, status, and token counts. A monetary cost
is shown only when the provider reports one; prices are not guessed. Prompts, response
bodies, tool payloads, private reasoning, and API keys are not added to usage records.

Release verification covers provider-key isolation, DeepSeek-only setup readiness,
owner/CSRF protection, persisted model selection, bounded native request parameters,
multi-round tool-call sequencing, malformed-response rejection, error redaction,
and existing OpenAI/OpenRouter/Voice/Software Manager regressions.

The desktop/mobile browser test uses synthetic provider keys and intercepted test
responses. It does not contact a paid provider. CI success is separate from a successful
live DeepSeek connection, which requires the owner's configured key and explicit test.

Local validation on 2026-11-10: **528 Python tests passed, 3 PostgreSQL tests skipped**
because a disposable PostgreSQL service was not configured, and **51 JavaScript tests
passed**. Python compilation, JavaScript syntax checks, and `git diff --check`
passed. The focused backend set passed 105 tests, including 59 new DeepSeek cases.
Local Chromium could not start because the execution environment denied its socket
operation; desktop/mobile browser results must come from the published CI run. No
real DeepSeek connection is claimed by these synthetic tests.

## Rollback

Redeploy the preceding tested source `1a7e7d9f00aa9e24c3d1729eea3e3dcae1617ea6` only after
choosing an OpenAI or OpenRouter model in Settings if DeepSeek has been activated: the
older allowlist does not recognize a saved `deepseek` preference. Do not delete chat,
Memory Vault, or usage data. This release needs no database schema change or companion
replacement.

## Official API references checked for this release

- https://api-docs.deepseek.com/ — model ID and official endpoint.
- https://api-docs.deepseek.com/api/create-chat-completion/ — native message/tool schema.
- https://api-docs.deepseek.com/guides/thinking_mode/ — explicit mode and reasoning history.
- https://api-docs.deepseek.com/guides/tool_calls/ — function calling.
