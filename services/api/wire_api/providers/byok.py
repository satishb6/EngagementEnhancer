"""BYOK key handling: envelope encryption via Fernet.

Keys are never logged, never returned to any client, never sent to the
frontend. Decryption happens only inside the provider layer, immediately
before an outbound call.
"""

from cryptography.fernet import Fernet

from wire_api.settings import get_settings


def _fernet() -> Fernet:
    master = get_settings().byok_master_key
    if not master:
        raise RuntimeError(
            "BYOK_MASTER_KEY is not set. Generate one with "
            "python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
        )
    return Fernet(master.encode())


def encrypt_key(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt_key(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()
