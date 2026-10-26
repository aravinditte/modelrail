"""API-key and admin-token security.

Gateway keys are high-entropy, shown once at creation, and stored ONLY as a
SHA-256 hash (peppered via environment). Lookup is by public prefix, then a
constant-time hash comparison. Plaintext keys are never persisted or logged.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from ..config import get_settings

KEY_ALPHABET_PREFIX = "mr_live_"


def _hash(value: str) -> str:
    pepper = get_settings().api_key_pepper
    return hashlib.sha256(f"{pepper}:{value}".encode()).hexdigest()


def generate_api_key() -> tuple[str, str, str]:
    """Returns (plaintext, prefix, hash). Plaintext is shown to the caller once."""
    plaintext = KEY_ALPHABET_PREFIX + secrets.token_urlsafe(32)
    prefix = plaintext[:16]
    return plaintext, prefix, _hash(plaintext)


def hash_api_key(plaintext: str) -> str:
    return _hash(plaintext)


def key_prefix_of(plaintext: str) -> str:
    return plaintext[:16]


def verify_api_key(plaintext: str, stored_hash: str) -> bool:
    return hmac.compare_digest(_hash(plaintext), stored_hash)


def hash_admin_token(token: str) -> str:
    return _hash("admin:" + token)


def verify_admin_token(token: str, stored_hash: str) -> bool:
    return hmac.compare_digest(hash_admin_token(token), stored_hash)


def is_bootstrap_admin(token: str) -> bool:
    return hmac.compare_digest(token, get_settings().admin_token)
