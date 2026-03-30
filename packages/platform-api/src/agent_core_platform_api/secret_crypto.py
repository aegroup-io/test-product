from __future__ import annotations

import base64
import hashlib

from cryptography.fernet import Fernet

from agent_core_platform_api.config import get_settings


class SecretCryptoError(RuntimeError):
    """Raised when a stored secret cannot be decrypted."""


def _fernet_key() -> bytes:
    seed = get_settings().crypto_seed.encode("utf-8")
    digest = hashlib.sha256(seed).digest()
    return base64.urlsafe_b64encode(digest)


def encrypt_secret(value: str) -> str:
    return Fernet(_fernet_key()).encrypt(value.encode("utf-8")).decode("utf-8")


def decrypt_secret(value: str) -> str:
    try:
        return Fernet(_fernet_key()).decrypt(value.encode("utf-8")).decode("utf-8")
    except Exception as exc:  # pragma: no cover - cryptography surfaces multiple subclasses.
        raise SecretCryptoError("Unable to decrypt stored secret.") from exc
