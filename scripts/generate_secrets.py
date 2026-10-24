#!/usr/bin/env python3
"""Generate SONIC preview credentials locally; never commit or paste them in chat."""
import hashlib
import secrets

print("SONIC secrets. Copy them directly into your own password manager and Railway.")
for label in ("OWNER", "DEVICE"):
    token = secrets.token_urlsafe(48)
    print(f"\nSONIC_{label}_TOKEN (secret; do not commit): {token}")
    print(f"SONIC_{label}_TOKEN_SHA256 (Railway): {hashlib.sha256(token.encode()).hexdigest()}")
print(f"\nSONIC_SESSION_SECRET (Railway): {secrets.token_urlsafe(48)}")
print("\nDo NOT use the OWNER token as a DEVICE token.")
