"""Cifrado en reposo de plantillas biométricas (Fernet)."""

from __future__ import annotations

import numpy as np
from cryptography.fernet import Fernet, InvalidToken

from app.errors import AppError


class TemplateCipher:
    def __init__(self, key: str):
        self._fernet: Fernet | None = None
        self.error: str | None = None
        if not key:
            self.error = "Falta ENCRYPTION_KEY en .env (ejecuta scripts/setup.sh)"
            return
        try:
            self._fernet = Fernet(key.encode())
        except Exception:  # noqa: BLE001
            self.error = "ENCRYPTION_KEY de .env no es una clave Fernet válida"

    @property
    def available(self) -> bool:
        return self._fernet is not None

    def _require(self) -> Fernet:
        if self._fernet is None:
            raise AppError(self.error or "Cifrado no disponible", status_code=500, code="no_encryption_key")
        return self._fernet

    def encrypt_bytes(self, data: bytes) -> bytes:
        return self._require().encrypt(data)

    def decrypt_bytes(self, token: bytes) -> bytes:
        try:
            return self._require().decrypt(token)
        except InvalidToken as exc:
            raise AppError(
                "No se pudo descifrar una plantilla: la clave cambió. Ejecuta el re-indexado.",
                status_code=500,
                code="invalid_token",
            ) from exc

    def encrypt_embedding(self, emb: np.ndarray) -> bytes:
        return self.encrypt_bytes(np.asarray(emb, dtype=np.float32).tobytes())

    def decrypt_embedding(self, token: bytes) -> np.ndarray:
        return np.frombuffer(self.decrypt_bytes(token), dtype=np.float32).copy()


def generate_key() -> str:
    return Fernet.generate_key().decode()
