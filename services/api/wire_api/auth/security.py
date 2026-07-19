"""Password hashing (stdlib scrypt) and JWT session tokens."""

import base64
import hashlib
import hmac
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt

from wire_api.settings import get_settings

_SCRYPT_N = 2**14
_SCRYPT_R = 8
_SCRYPT_P = 1


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(
        password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32
    )
    return "scrypt${}${}".format(
        base64.b64encode(salt).decode(), base64.b64encode(digest).decode()
    )


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, salt_b64, digest_b64 = stored.split("$")
        if scheme != "scrypt":
            return False
        salt = base64.b64decode(salt_b64)
        expected = base64.b64decode(digest_b64)
        actual = hashlib.scrypt(
            password.encode(), salt=salt, n=_SCRYPT_N, r=_SCRYPT_R, p=_SCRYPT_P, dklen=32
        )
        return hmac.compare_digest(expected, actual)
    except (ValueError, TypeError):
        return False


def create_token(user_id: uuid.UUID, days: int = 30) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": str(user_id),
        "iat": int(now.timestamp()),
        "exp": int((now + timedelta(days=days)).timestamp()),
    }
    return jwt.encode(payload, get_settings().secret_key, algorithm="HS256")


def decode_token(token: str) -> uuid.UUID | None:
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=["HS256"])
        return uuid.UUID(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        return None
