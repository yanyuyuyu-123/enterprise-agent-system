import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core.config import settings

_hasher = PasswordHasher()


def hash_password(raw: str) -> str:
    return _hasher.hash(raw)


def verify_password(raw: str, hashed: str) -> bool:
    try:
        return _hasher.verify(hashed, raw)
    except (VerificationError, InvalidHashError):
        return False


def create_access_token(user_id: int, positions: list[str]) -> str:
    ttl = timedelta(minutes=settings.access_token_minutes)
    return _encode(str(user_id), positions, "access", ttl)


def create_refresh_token(user_id: int, positions: list[str]) -> str:
    return _encode(str(user_id), positions, "refresh", timedelta(days=settings.refresh_token_days))


def _encode(subject: str, positions: list[str], token_type: str, ttl: timedelta) -> str:
    now = datetime.now(UTC)
    payload: dict[str, Any] = {
        "sub": subject,
        "pos": positions,
        "typ": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + ttl).timestamp()),
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def decode_token(token: str) -> dict[str, Any]:
    """解析并校验签名与过期时间；失败抛 jwt.PyJWTError，由调用方转 2000。"""
    return jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
