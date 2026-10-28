"""Password hashing and purpose-bound signed tokens. Never log token values."""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError
from jose import JWTError, jwt

from app.core.config import get_settings

settings = get_settings()
password_hasher = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1, type=Type.ID)
# Unknown accounts still perform a real password verification.
DUMMY_PASSWORD_HASH = password_hasher.hash(secrets.token_urlsafe(32))
ISSUER = "changeguard"


def get_password_hash(password: str) -> str:
    return password_hasher.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        if hashed_password.startswith("$argon2id$"):
            return password_hasher.verify(hashed_password, plain_password)
        if hashed_password.startswith(("$2a$", "$2b$", "$2y$")):
            import bcrypt

            # Legacy bcrypt has a 72-byte limit; never silently truncate.
            encoded = plain_password.encode("utf-8")
            return len(encoded) <= 72 and bcrypt.checkpw(encoded, hashed_password.encode("ascii"))
    except (InvalidHashError, VerificationError, ValueError):
        return False
    return False


def token_hash(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def identifier_hash(value: str) -> str:
    return hmac.new(settings.jwt_secret.encode(), value.encode(), hashlib.sha256).hexdigest()


def create_access_token(
    subject: str,
    tenant_id: str,
    roles: list[str],
    expires_delta: timedelta | None = None,
    *,
    version: int = 0,
) -> str:
    return _signed_token(
        subject,
        tenant_id,
        "access",
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.access_token_expire_minutes),
        version,
        roles=roles,
    )


def create_password_reset_token(subject: str, tenant_id: str, version: int) -> str:
    return _signed_token(
        subject,
        tenant_id,
        "password_reset",
        timedelta(minutes=settings.password_reset_expire_minutes),
        version,
    )


def _signed_token(
    subject: str, tenant_id: str, purpose: str, lifetime: timedelta, version: int, **extra
) -> str:
    now = datetime.now(timezone.utc)
    return jwt.encode(
        {
            "sub": subject,
            "tenant_id": tenant_id,
            "type": purpose,
            "ver": version,
            "jti": str(uuid4()),
            "iat": now,
            "exp": now + lifetime,
            "iss": ISSUER,
            "aud": f"changeguard-{purpose}",
            **extra,
        },
        settings.jwt_secret,
        algorithm=settings.jwt_algorithm,
    )


def decode_token(value: str, purpose: str = "access") -> dict[str, Any]:
    claims = jwt.decode(
        value,
        settings.jwt_secret,
        algorithms=[settings.jwt_algorithm],
        issuer=ISSUER,
        audience=f"changeguard-{purpose}",
        options={
            "require_exp": True,
            "require_iat": True,
            "require_sub": True,
            "require_jti": True,
            "require_aud": True,
            "require_iss": True,
        },
    )
    if claims.get("type") != purpose or type(claims.get("ver")) is not int:
        raise JWTError("Invalid token")
    return claims


def create_refresh_token() -> str:
    return secrets.token_urlsafe(48)


def generate_api_key() -> str:
    return f"cg_{secrets.token_urlsafe(32)}"


def hash_api_key(api_key: str) -> str:
    return get_password_hash(api_key)


def verify_api_key(plain_key: str, hashed_key: str) -> bool:
    return verify_password(plain_key, hashed_key)
