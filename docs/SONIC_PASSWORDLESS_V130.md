# SONIC 1.3.0: token-free owner sign-in

This release replaces repeated manual owner-token entry with WebAuthn passkeys.
It does not make the private control plane public. The existing cookie/CSRF,
per-action PC approvals, model routing and device authentication are retained.

## Runtime configuration

- `SONIC_PASSWORDLESS_LOGIN=true`: serve passkey UI and reject `/api/login` owner-token logins.
- `SONIC_PUBLIC_URL`: canonical HTTPS origin, currently the staging Railway hostname.
- Existing `SONIC_SESSION_SECRET`, `SONIC_OWNER_TOKEN_SHA256`, database and device settings remain in place. The old owner hash remains a readiness/recovery prerequisite, not a passwordless login credential.
- Initial enrollment only: `SONIC_PASSKEY_ENROLLMENT_SHA256` contains the SHA-256 of a cryptographically random, operator-issued enrollment key, and `SONIC_PASSKEY_ENROLLMENT_EXPIRES` is its Unix deadline (maximum 24 hours ahead).

The owner opens `https://<canonical-host>/#setup=<one-time-enrollment-key>` and chooses **Aktifkan passkey perangkat ini**. The fragment is immediately removed from browser history and never sent as a URL to the server. The key is submitted only in same-origin JSON requests and is not persisted in browser storage or the database. Do not log it or publish it in GitHub, screenshots or CI artifacts.

The link cannot read data or run PC commands. A verified WebAuthn registration with user verification is required before issuing the first owner session. Enrollment is rejected if the link expired, was used, or any passkey already exists. SQL gate locking and a unique enrollment receipt prevent two first-enrollment ceremonies from succeeding.

Future sign-in uses a discoverable passkey with user verification required. Biometrics and private keys remain with the authenticator; SONIC stores the credential public key and usage metadata. A hardware security key or device-unlock method may be used instead of a biometric, subject to platform support.

## Security and recovery

Challenges expire after 120 seconds, bind to HttpOnly same-site cookies, and are atomically consumed with DELETE RETURNING. Origin, relying-party ID, challenge, user verification, signature and counter checks are enforced. Rate limits are persisted and shared across replicas. No public self-registration and no automatic session from an enrollment link.

Authenticated Settings supports additional passkeys (maximum eight) and removal. Removing a passkey revokes all owner sessions. The last passkey cannot be removed via UI/API until another has been added. Logout still revokes the active owner session.

The additive tables are created through the existing SQLAlchemy initialization path. No existing chat, Memory Vault, model or device tables are modified.

Recovery remains an administrator action: restore `SONIC_PASSWORDLESS_LOGIN=false` through Railway, redeploy, then use the existing private owner recovery credential. Never create an anonymous admin session or expose the session secret. Before rolling back code, disable passwordless mode to prevent an owner-facing login mismatch. Existing passkey tables can remain; do not delete data merely to roll back the code.

## Validation

The dedicated tests construct real ES256 registration/authentication data and verify signatures using pinned `webauthn==3.0.1`. Tests include replay, invalid origin/RP/challenge, missing user verification, cookie binding, setup expiry/reuse, rate limiting, CSRF, last-key protection and session revocation.

The browser workflow uses Chromium's virtual authenticator on desktop/mobile viewports, a disposable local database and synthetic enrollment keys. A passed virtual-authenticator test is not evidence that the owner's actual Face ID/Windows Hello enrollment is complete. Real enrollment must be performed by the owner on their device.

Library references: https://duo-labs.github.io/py_webauthn/registration.html and https://duo-labs.github.io/py_webauthn/authentication.html.
