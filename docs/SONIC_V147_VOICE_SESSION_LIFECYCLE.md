# SONIC v1.4.7 | iPhone voice disconnect: root cause and fix

**Evidence (Railway staging, 2026-11-14 16:24 WIB).**
- iPhone Safari fetched /assets/voice.js?v=1.4.6.
- One POST /api/preview/voice/sessions returned 409 (a session was still in the shared gate).
- The next two starts returned 200 and were followed after a few seconds by browser
  /stop events with allowlisted reason channel_closed.
- No claim that provider credentials or the frontend version were missing.

**Root cause.** The common voice housekeeping loop runs every 15 seconds.
It fetched an OwnerSession row for every active VoiceSession. Public staging guests
use a signed, expiring preview cookie and have *no* OwnerSession. Thus owner=None
was interpreted as revoked, causing the backend to hang up a healthy provider
call, after which Safari observed its WebRTC data channel close.

**Fix.** Preview VoiceSession.owner_sid now uses a distinct 64-character
pseudonymous namespace: g_ plus 62 SHA-256 hex characters. Owner hashes
remain unchanged. This reuses the existing Postgres column without migration.
Housekeeping skips OwnerSession lookups for guest rows but still ends them at
the 60-second expiry or when a Stop has been requested. A forged or expired
preview cookie is still rejected by the existing origin, signed-cookie and CSRF
checks. Owner tool access remains unavailable to guest sessions.
Legacy guest rows remain stoppable for their short remaining lifetime.

**Secondary fix.** A 409 session conflict now occurs before preview daily
budget debit, and the browser does not send an invalid /stop for a rejected
session. Its error text distinguishes session conflict from WebRTC failure.
All per-network/global preview voice limits and staging-only restrictions remain.

**Regression tests.** Full backend, JavaScript, browser and GitHub CI.
In particular, synthetic provider tests assert that the sweeper preserves an
active preview guest (no provider hangup), closes it after expiry, and that
a 409 never debits the paid preview quota.

**Scope.** Only 9dbit/Sonic staging. No production, Chatvice, or
TRADEVICEPC companion changes. Live iPhone microphone + speaker experience
must be confirmed on the user's actual device.
