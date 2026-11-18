# SONIC Coding Pipeline v2.1 · 2026-11-18

## Implementation
- Chat (Local GGUF) and Artifact Studio (Coding) are separate work modes.
- The owner explicitly selects either `Local GGUF` or `DeepSeek Cloud` on every
  generation. No model changes, automatic fallback, retries, installation, code
  execution on TRADEVICEPC, or auto-save occur.
- Local Coding uses the existing authenticated outbound-only Companion queue,
  a dedicated `code` action, and one in-flight model job across Chat and Code.
- The local runtime is kept at its already-tested 1024-token context. Code
  output is capped at 384 tokens, with a bounded 125-second local HTTP call.
  Tiny prototypes may work; complex full HTML generally requires explicit
  DeepSeek Cloud or smaller iterations. No benchmark supports larger context yet.
- DeepSeek Cloud uses the server's allowlisted model and configured key. One
  explicit paid request receives up to 4500 output tokens. It does not receive
  PC credentials or execute code. It can receive existing HTML if the owner
  explicitly selects the revision option.
- The server requires a complete HTML document; partial output is rejected,
  not executed or saved. Successful output enters a draft for manual inspection.
- Existing Artifact Studio isolated iframe preview, versioned storage, and
  export remain the only supported post-generation actions.
- Local inference failures are translated from bounded error codes into clear
  owner-facing messages; raw model prompts/errors never appear in receipts.

## Security / Operating limits
- No automatic cloud switching or hidden paid retries.
- Cloud coding sends the prompt and optional owner-provided HTML to DeepSeek
  only after an explicit user selection and consent interaction.
- Local Coding does not emit or execute tool calls or Windows actions.
- The model output is untrusted source. Browser sandbox has opaque origin,
  no network, no SONIC cookies, and no host filesystem/shell permissions.
- Only one GPU-intensive Chat/Code job at a time. The Trading PC workload,
  MT5 sessions and other applications are not terminated or reconfigured.
- 6 GB RTX 2060 with 12 GPU layers and ~3 GB free VRAM is not enough to
  assume fast high-token coding. No automatic runtime restart or context
  growth is part of the initial release.

## Rollout gates
1. Unit tests for owner access, queue locking, typed errors, explicit cloud
   request, incomplete HTML, and no changes to selected Chat model.
2. Playwright desktop/iPhone on Chromium/WebKit for explicit model choice,
   source editor, sandbox execution and save.
3. Deploy backend/frontend to sonic-web staging only, verify HTTP 200,
   guest API rejection and current owner session.
4. Update signed Companion script in a controlled maintenance-safe way;
   never modify live trading engines. Confirm the Companion reports `code`
   action support and a code job completes before calling Local Coding ready.
5. Verify local and cloud generation through the owner browser.
6. Production remains unchanged until a separate approval.

## Rollback
Railway staging can roll back to the preceding release. The new Coding API
adds no database schema, and existing artifacts are unchanged. The companion
script must be restored from its verified backup if a future update fails.
