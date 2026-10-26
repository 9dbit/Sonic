# SONIC Family Voice Profiles | feasibility and privacy gate

**Status: backlog / specification only. Not activated.**  
Project-source basis: `SONIC_VOICE_PROFILES_PLAN_2026-10-25_2012_WIB.md` (25 Oct 2026, 20:12 WIB). This file translates that source plan into an engineering evaluation without claiming new user permission, provider selection, or runtime capability.

## Goal and scope

Let SONIC personalize conversation for **voluntarily enrolled** and consented family speakers. Only compare to authorized enrolled profiles. If uncertain, overlapping, noisy or unregistered, return **Unknown speaker**, ask who is speaking, and do not guess. Profile roles: consenting adult; later child subject to lawful guardian permission and age-appropriate participation; infant/baby remains exploratory and not suitable for any promised accuracy.

**Explicit distinction:** existing browser microphone authorization and SONIC's double-tap voice session are permissions to converse, **not** consent to create, process, or store a voice-biometric profile.

## Preconditions before any audio enrollment

Decisions to be made and approved:
1. Exact purpose and consent record, participant identities (without unnecessary child names in design specs), guardian authorization/age-appropriate assent, withdrawal mechanism.
2. Speech model/provider and regional processing geography. Prefer on-device/local processing when feasible; no transfer until recipient, processing purpose and lawful basis are clear.
3. Data classes and minimization: decide whether raw enrollment samples can be discarded after deriving protected templates. Define encryption at rest/in transit, keys, account/profile isolation, audit events and access-control boundaries.
4. Retention and deletion: samples, templates, linked data, backups and expiry. Explain separately that deleting a voice profile does not erase references in chat history.
5. Financial budget and per-user data/storage costs. No estimated accuracy or cost numbers without evaluation.
6. Threat model: spoofing, replayed audio, synthetic voice, cross-profile confusion, multiple speakers, noise, language and changing speech patterns.

## Proposed non-operational states

`disabled` (default) -> `consent_review` -> `consented` -> `sampling` -> `quality_checked` -> `enrolled` -> `suspended` / `revoked` / `deleted`.

Never infer a state change from a microphone session, a background voice or a chat correction. All mutating transitions must be deliberate, authenticated, and evidenced by an explicit consent receipt. The model may not authorize consent on another person's behalf.

## Candidate UI flow (not implemented)

1. Voice Profiles Settings explains purpose, processing, storage, retention, deletion and role.
2. Adult enrollee gives explicit consent; guardian and age-appropriate child controls would need separate verification before child support.
3. Show a **visible** recording indicator, Stop and Cancel; record only inside the enrollment step.
4. Check sample quality; let the participant retry, discard or cancel.
5. Present candidate speaker only when a threshold validated against consented test data is met. Otherwise say Unknown and request clarification. Corrections do not silently train.
6. Allow Disable, Re-enroll, Withdraw consent, Delete samples and Delete profile; show what each control does and does not delete.

## Security invariants

- Speaker match is **personalization only**, never sole authentication for payments, data disclosure, security settings or other sensitive operations.
- Never identify unknown/unregistered people or automatically enroll background conversations.
- No active enrollment endpoints, templates, provider calls, recording scripts or automatic feature flags may be introduced while this milestone remains a plan.
- No speaker match confidence is exposed as a misleading 'verified identity' guarantee.
- Children require separate review; infant voice identification requires dedicated feasibility work and should not be relied on.
- Replaying or imitating a registered voice must not grant permissions.

## Acceptance test matrix for a future consented adult-only prototype

| Scenario | Required outcome |
| --- | --- |
| No enrollment consent | Reject sample capture and profile creation |
| Participant cancels/presses Stop | Recording visibly ends and temporary buffers are disposed per approved policy |
| Known consenting adult, clean audio | Evaluate both false acceptance and false rejection, with measured threshold |
| Unknown/unregistered person | Return Unknown, never confidently identify |
| Overlapping speakers / low signal / noisy environment | Return Unknown or request clarification |
| Replay/synthetic imitation | No protected action; spoof risk evaluated |
| Corrections in conversation | No automatic template update |
| Disable/withdraw/delete | No new matching; verify profile/sample/template removal and backup policy |
| Multiple profiles | Verify isolation and no unintended cross-profile data access |
| Indonesian language, devices/distances and drift | Explicit test cohorts and documented results |

## Proposed delivery sequence

1. Architecture / DPIA-style privacy and threat-model decision record.
2. Consent UX wireframe and storage/retention decision, **without capturing audio**.
3. Isolated adult-only prototype under a disabled-by-default flag, after affirmative decisions.
4. Evaluation of false matches, unknown-speaker behavior, replay protection and revocation.
5. Separate discussion for child/infant scope; no default activation.

This document is not evidence that Family Voice Profiles is working, deployed, or authorized to collect samples.
