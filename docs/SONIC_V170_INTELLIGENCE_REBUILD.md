# SONIC v1.7.0 Intelligence Experience Rebuild
## User experience
- iPhone header 58px high, black/grey/blue palette. Talk button remains within header.
- Bottom nav has 5 items: Neural, Chat, Memory, Devices, More. More opens Workspace and Setup. Existing desktop six-section navigation preserved.
- Chat is mobile default. Slim welcome state, one composer with expandable extras, safe area and Safari keyboard handling. All chat messages remain in chat, not shown as overlapping Neural answer cards.
- Neural: Knowledge List on mobile default, optional Explore 3D. Saved Memory Vault/topic/integration plus linked Research Memory cards. Graph controls no longer cover mode selector.
- Research Agent: compact Chat/Research toggle with purpose, explicit Save research option and project, source cards in disclosure, stored research search and delete.

## Research engine repairs
- Expand known cybersecurity acronyms (MITM, XSS, CSRF, API) to full search terms; avoid broad Bing RSS matches on "MAN" for MITM.
- Validate technical concepts before citing. When Bing returns no relevant source, optionally search Wikimedia public REST API for definitions, then read selected public sources via fixed Jina Reader.
- Real smoke test from TRADEVICEPC: MITM returned valid Man-in-the-middle attack and Kazakhstan man-in-the-middle attack Wikipedia references, both readable. Unrelated MAN trucks/Man Group discarded.
- Optional `SONIC_RESEARCH_CLOUD_SUMMARY_ENABLED=true` lets **selected** and configured SONIC cloud chat model provide source-based summaries when local model stopped. This sends query, public source excerpts and relevant saved Research Memory text to the already selected cloud provider. No new provider switch, tool permission, or model action granted. Applies to public concept questions without sources with explicitly unverified prefix; targets/prices/statistics without sources do not get invented answers.
- Default cloud summary flag false in repo; environment staging opt-in needed. Local GGUF still read-only with no model tools.

## Persistent Research Memory
- New additive `research_memory_v170` table in existing SQLite/PostgreSQL, no migration altering old chat, account or Memory Vault tables.
- Owner explicitly approves retention via visible Save research checkbox. Only results with at least one public source are retained. Projects, sources, bounded excerpts, summary, mode and timestamp.
- Owner APIs (all require valid session, delete requires CSRF): GET /api/agent/memory, GET /api/agent/memory/{id}, DELETE /api/agent/memory/{id}.
- Retrieval currently lexical alias-aware matching, not vector semantic search; next version can improve embeddings.
- Owner controls deletion of a saved research item. Deleting it does NOT delete pre-existing chat history.
- Saved research summaries can be reused in subsequent read-only synthesis; old research is always labeled as prior unverified-current reference.

## Privacy, safety and rollback
- Preview guests remain isolated, cannot access research memory or PC controls. Research only touches public data; no Windows commands, trading, file changes, payments, websites login or deployments.
- Public research queries sent to Bing or Wikimedia as needed; public URLs to Jina. With fallback cloud summary enabled, selected cloud provider receives the query, source excerpts and relevant saved research text. Do not send secrets.
- Separate staging branch and draft PR; no production or MT5 changes.
- Rollback: set `SONIC_RESEARCH_CLOUD_SUMMARY_ENABLED=false` to stop fallback; set `SONIC_RESEARCH_AGENT_ENABLED=false` to stop research; restore prior v1.6 staging commit if UI rollback needed. New additive research table may remain without harm.
- Browser QA: 390x844, 360x740, 1440x900 in Chromium, synthetically authenticated owner. Physical Safari iPhone owner E2E remains a separate acceptance gate.

## Source QA commands
```sh
python -m pytest -q tests/test_research_memory_v170.py tests/test_research_agent_v160.py
python scripts/e2e_mobile_v170.py
node --test tests/js/*.test.cjs
```
