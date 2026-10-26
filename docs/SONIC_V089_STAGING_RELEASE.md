# SONIC V0.8.9 | Combined staging release checkpoint
Date: 2026-10-26 (Asia/Jakarta)

## Baseline and intent
- Current stable staging before this release: `9dbit/Sonic` commit `738885324bd730ff7913333312bd6baa28bd03fb`, SONIC 0.8.8.
- This branch is built from tested PC Workspace commit `8155a7685a9f85aec59892148e5cd6e96cbf2110`, plus the exact voice diagnostic files from PR #11.
- PR #10: read-only TRADEVICEPC folder listing and safe text previews via existing outbound Windows companion.
- PR #11: sanitize and classify upstream OpenAI Realtime errors, including 429 credit, budget and rate limit. This is diagnostic-only; it **does not** change the billing account, request budget or user voice model.
- Existing realtime voice has already successfully initialized in staging again following billing recovery (HTTP 200 and normal end-to-end dispatch logs), so do not automatically rotate provider credentials or create new keys.

## Release behavior
- On choosing TRADEVICEPC, only read online capability metadata; do not enumerate the PC without a separate owner click.
- Explicit owner browser confirmation and a digest-bound operator request are required for each file.list/read.
- The Windows companion controls the authorized root; no arbitrary system drives, write operations, file deletions or shell.
- Read-only preview is plain text. PC files never sync into the SONIC Cloud notes automatically.
- Voice error responses show allowlisted codes, with no raw provider message, token, SDP, transcript or audio logging.
- Memory Vault and Neural Brain retain V0.8.8 behavior. Family Voice Profiles remains backlog and does not capture biometric samples.

## Release gates
1. On the **combined release commit**, all GitHub workflows relevant to the new PR pass; specifically SONIC CI, Workspace/Voice Invocation, PC Workspace Read Only, Neural Memory QA, PC Command Center, Motion and Persona.
2. Deploy **staging only**, pinning the exact passing commit SHA. Preserve `7388853` as a rollback target.
3. Verify Railway deployment status SUCCESS and `/api/health` version 0.8.9. Verify `/assets/pc-workspace-v089.js` is served.
4. Verify the current owner-approved Windows device heartbeat and callable file.list/file.read via the normal authenticated UI. Do not fabricate PC read results from unit tests.
5. In the UI, create a disposable SONIC Cloud note, refresh, check persistence, then test one disposable text file placed under the authorized Windows root, only after an explicit owner click. Do not inspect private Windows files autonomously.
6. Confirm actual Realtime voice once on the owner's microphone and stop it deliberately. A passing automated synthetic test is **not** acceptance on physical hardware.
7. If a regression appears, revert only the staging service's pinned source back to V0.8.8; do not reset Postgres or other environments.

## Deployment decisions
- No production deployment.
- No background audio enrollment, provider key replacement, admin privileges, trading process operations or remote desktop.
- Save the exact deployed SHA and CI outcome in the continuation record.
