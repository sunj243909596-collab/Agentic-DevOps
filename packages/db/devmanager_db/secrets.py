"""Secret encryption / decryption for settings table.

Uses Fernet (AES-128-CBC + HMAC-SHA256) with a key sourced from:
  1. `SECRETS_KEY` env var (base64-encoded Fernet key)
  2. A file at `<workspace>/.secrets.key` (auto-generated, mode 0o600)

The key is per-host. In production set `SECRETS_KEY` in the environment.
In dev, the file is created on first use with restrictive permissions.
"""

from __future__ import annotations

import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken

_KEY_FILE_NAME = ".secrets.key"


def _key_file() -> Path:
    """Default location for the auto-generated key file (next to the .env)."""
    # Use /tmp so it doesn't pollute the repo and survives container restarts differently
    return Path(os.getenv("SECRETS_KEY_FILE", f"/tmp/devmanager{_KEY_FILE_NAME}"))


def _generate_and_persist() -> bytes:
    key = Fernet.generate_key()
    p = _key_file()
    p.write_bytes(key)
    try:
        os.chmod(p, 0o600)
    except OSError:
        pass
    return key


def _load_or_create_key() -> bytes:
    env_key = os.getenv("SECRETS_KEY")
    if env_key:
        return env_key.encode()
    p = _key_file()
    if p.exists():
        return p.read_bytes()
    return _generate_and_persist()


_FERNET = Fernet(_load_or_create_key())


def encrypt_secret(plain: str) -> str:
    """Encrypt a plaintext string. Returns a Fernet token (URL-safe base64)."""
    if plain is None or plain == "":
        return ""
    return _FERNET.encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_secret(token: str) -> str:
    """Decrypt a Fernet token. Returns plaintext. Returns "" for empty token.
    Raises ValueError on invalid token / wrong key."""
    if not token:
        return ""
    try:
        return _FERNET.decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken as e:
        raise ValueError("invalid or corrupted secret") from e
