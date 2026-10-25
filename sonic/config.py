"""Fail-closed runtime configuration. No hard-coded credentials."""
import os
import re

SHA256_RE = re.compile(r"^[a-f0-9]{64}$", re.I)


def setting(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def owner_ready() -> bool:
    return bool(SHA256_RE.fullmatch(setting("SONIC_OWNER_TOKEN_SHA256"))) and len(setting("SONIC_SESSION_SECRET")) >= 32


def database_ready() -> bool:
    # Neither staging nor production may put private chats in an ephemeral container.
    hosted = bool(setting("RAILWAY_ENVIRONMENT_NAME")) or setting("SONIC_ENV").lower() in {"staging", "production"}
    return not hosted or bool(setting("DATABASE_URL"))


def device_ready() -> bool:
    return bool(SHA256_RE.fullmatch(setting("SONIC_DEVICE_TOKEN_SHA256")))


def model_name() -> str:
    return setting("SONIC_MODEL", "gpt-4.1-mini")


def public_url() -> str:
    return setting("SONIC_PUBLIC_URL", "http://127.0.0.1:8080").rstrip("/")
