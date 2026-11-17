# SONIC v1.8.2: model truth and mobile UI repair

## Evidence and root cause
The owner screenshots show a local model selected, the local engine STOPPED, a research label claiming selected cloud AI availability, and a first-party question about SONIC's model answered by unrelated web search results. These are orchestration/UI defects, not evidence of a model refusing the question.

Inspection of the deployed a57f617 source confirmed:
- Research selected local inference whenever the local process was running, even if the owner had selected a cloud model.
- The UI used a cloud-feature flag as an availability indicator without checking the selected provider or live engine.
- Every Research question went through public search, including questions whose answer is first-party model state.
- A source-list fallback looked like an AI response even when neither local nor cloud inference had returned an answer.
- Legacy violet CSS overrides, oversized catalog cards, duplicated status text and an always-expanded preferences row crowded iPhone screens.

## Repairs
- New owner-only GET /api/intelligence/status separates selected model, local runtime heartbeat, cloud configuration and actual inference provenance. A configured cloud key is labelled unprobed, not guaranteed available.
- Both Chat and Research intercept narrow first-party model-status questions before any web/model call. No research-memory item is created for these status replies.
- Research captures the owner selection per request and calls only that provider. Running an unselected local model does not replace the cloud selection. Stopped/failed selected local inference never falls back to cloud.
- Local stopped responses explicitly state that no inference/search occurred and point to Start local or model selection.
- New responses show origin: local model, exact cloud model, system status, SONIC action, or source listing. Old historical messages are not retroactively assigned fabricated provenance.
- The Chat and Model Router panels show selected/runtime status with guarded Start local and model-selection actions. Choosing a model is labelled as selection, not starting an engine.
- Mobile research options are collapsible; the empty composer resets height; source details are quieter. HF result cards use rectangles rather than giant pills. The existing Local AI control is above the HF discovery catalog. Device name no longer wraps one character per line.
- Model names are short in the selector; exact identifiers stay in API metadata. Per-file cache keys invalidate changed JavaScript.
- Login-isolation CSS remains last and locked UI behavior remains in force.

## What is NOT changed
No model weights, content filters, owner authentication, device credentials, arbitrary-PC execution permissions, resource guards, MT5 operations, voice provider or database schema were changed. Local inference was not started. Existing saved research and history were not deleted.

Local runtime is still Q4_K_M GGUF with a 1024-token context and 256-token output cap. It remains text-only for model-generated actions. Local prompts transit Railway before TRADEVICEPC; this is not fully offline phone chat. These limits are app configuration, not the model's theoretical context limit.

## Cloud vs local evidence
- Cloud configuration uses the official `deepseek-flash` Chat Completions endpoint, non-thinking mode.
- Installed local artifact is mradermacher's GGUF quantization of xtools-at's community Qwen3.5-9B-derived Heretic model. It is not a copy of the official DeepSeek Flash/Pro service.
- The original modifier reports 3/100 refusals in its own evaluation. This is neither zero nor a universal guarantee. No new refusal comparison or independent benchmark was performed here.
- No safety bypass or unlimited-permission mode is added. The work corrects routing and observability, not claims about unrestricted generation.

Public sources checked 2026-11-18:
- https://huggingface.co/mradermacher/DeepSeek-V4-Pro-Qwen3.5-9B-UNCENSORED-heretic-GGUF
- https://huggingface.co/xtools-at/DeepSeek-V4-Pro-Qwen3.5-9B-UNCENSORED-heretic
- https://api-docs.deepseek.com/api/create-chat-completion/

## Acceptance
Synthetic backend tests cover own-status intent, public-topic exclusions, local selected/stopped, cloud selected/local running, local failures without cloud fallback, no research-memory pollution, owner API isolation, and explicit inference provenance. Browser tests in Chromium and WebKit cover 390x690, 360x640 and desktop, actual pointer paths, no horizontal overflow, composer/nav separation, runtime truth, and collapsed preferences. Screenshots use synthetic owner data, not private history. Physical Safari on the owner's iPhone remains a separate validation step.

Commands:
```
python -m pytest -q tests/test_model_truth_v182.py tests/test_research_agent_v160.py tests/test_research_memory_v170.py
python scripts/e2e_model_truth_v182.py
# Set SONIC_QA_BROWSER=webkit to repeat with WebKit.
python scripts/e2e_auth_isolation_v181.py
```

Deploy only to SONIC / staging / sonic-web after tests. No production merge. Roll back to a57f617 if the patch cannot be verified.
