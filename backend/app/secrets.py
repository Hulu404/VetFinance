"""Encryption of third-party API keys (Vetmanager) before they are stored. Fernet (AES-128-CBC + HMAC).

The key is never stored in plain text and never returned by the API; only its last four characters
(`key_hint`) are kept next to the ciphertext.
"""

from typing import Annotated, Protocol

from cryptography.fernet import Fernet, InvalidToken
from fastapi import Depends

from app.errors import ApiError
from app.settings import Settings, get_settings

KEY_HINT_LENGTH = 4


class SecretBox(Protocol):
    def encrypt(self, plain: str) -> str: ...
    def decrypt(self, cipher: str) -> str: ...


class FernetBox:
    def __init__(self, key: str) -> None:
        try:
            self._fernet = Fernet(key.encode())
        except (ValueError, TypeError) as exc:
            raise ApiError(503, "sync_failed", "Хранилище ключей настроено неверно.") from exc

    def encrypt(self, plain: str) -> str:
        return self._fernet.encrypt(plain.encode()).decode()

    def decrypt(self, cipher: str) -> str:
        try:
            return self._fernet.decrypt(cipher.encode()).decode()
        except InvalidToken as exc:
            raise ApiError(503, "sync_failed", "Не удалось расшифровать сохранённый ключ.") from exc


def key_hint(plain: str) -> str:
    return plain[-KEY_HINT_LENGTH:]


def box_from_settings(settings: Settings) -> SecretBox:
    key = settings.secrets_key.get_secret_value()
    if not key:
        raise ApiError(503, "sync_failed", "Хранилище ключей не настроено.")
    return FernetBox(key)


def get_secret_box(settings: Annotated[Settings, Depends(get_settings)]) -> SecretBox:
    return box_from_settings(settings)
