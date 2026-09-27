"""Fernet encryption for Nexus credentials. The key lives only in the backend environment."""

from cryptography.fernet import Fernet, InvalidToken

from .config import get_settings


class CryptoError(RuntimeError):
    pass


def _fernet() -> Fernet:
    key = get_settings().credentials_encryption_key
    if not key:
        raise CryptoError("CREDENTIALS_ENCRYPTION_KEY is not set (run `make keygen`)")
    return Fernet(key.encode())


def encrypt(plaintext: str) -> bytes:
    return _fernet().encrypt(plaintext.encode())


def decrypt(ciphertext: bytes) -> str:
    try:
        return _fernet().decrypt(bytes(ciphertext)).decode()
    except InvalidToken as e:
        raise CryptoError("ciphertext could not be decrypted — was the key rotated?") from e
