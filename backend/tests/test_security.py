"""Purpose binding, expiration, and hashing tests independent of a database."""

import os
from datetime import timedelta
from unittest.mock import patch
from uuid import uuid4

import pytest
from jose import JWTError, jwt

from app.core.config import Settings
from app.core.security import (
    create_access_token,
    create_password_reset_token,
    create_refresh_token,
    decode_token,
    get_password_hash,
    settings,
    token_hash,
    verify_password,
)


def test_argon2id_hashing_and_invalid_password():
    value = "a very long password " * 10
    hashed = get_password_hash(value)
    assert hashed.startswith("$argon2id$")
    assert value not in hashed
    assert verify_password(value, hashed)
    assert not verify_password("incorrect", hashed)
    assert not verify_password("incorrect", "invalid-hash")
    assert get_password_hash(value) != hashed


def test_bcrypt_legacy_hash_is_verified_without_truncation():
    import bcrypt

    value = "legacy-password"
    hashed = bcrypt.hashpw(value.encode(), bcrypt.gensalt(rounds=4)).decode()
    assert verify_password(value, hashed)
    assert not verify_password(value + "wrong", hashed)
    assert not verify_password("a" * 100, hashed)


def test_expired_access_token_is_rejected():
    value = create_access_token(str(uuid4()), str(uuid4()), ["owner"], timedelta(seconds=-10))
    with pytest.raises(JWTError):
        decode_token(value)


def test_expired_reset_signature_is_rejected(monkeypatch):
    monkeypatch.setattr(settings, "password_reset_expire_minutes", -1)
    value = create_password_reset_token(str(uuid4()), str(uuid4()), 0)
    with pytest.raises(JWTError):
        decode_token(value, "password_reset")


def test_access_and_reset_tokens_are_not_interchangeable():
    access = create_access_token(str(uuid4()), str(uuid4()), ["owner"])
    reset = create_password_reset_token(str(uuid4()), str(uuid4()), 0)
    with pytest.raises(JWTError):
        decode_token(reset)
    with pytest.raises(JWTError):
        decode_token(access, "password_reset")
    claims = decode_token(access)
    assert claims["exp"] - claims["iat"] <= 1800


@pytest.mark.parametrize("mutation", ["signature", "issuer", "audience", "missing_exp"])
def test_invalid_signed_claims_are_rejected(mutation):
    original = create_access_token(str(uuid4()), str(uuid4()), ["owner"])
    claims = decode_token(original)
    secret = settings.jwt_secret
    if mutation == "signature":
        secret = "untrusted-secret-" * 3
    elif mutation == "issuer":
        claims["iss"] = "untrusted"
    elif mutation == "audience":
        claims["aud"] = "untrusted"
    else:
        del claims["exp"]
    value = jwt.encode(claims, secret, algorithm=settings.jwt_algorithm)
    with pytest.raises(JWTError):
        decode_token(value)


def test_refresh_tokens_are_random_and_only_hashes_are_persistable():
    first, second = create_refresh_token(), create_refresh_token()
    assert first != second
    assert len(first) >= 64
    assert first != token_hash(first)
    assert len(token_hash(first)) == 64


@pytest.mark.parametrize("unsafe", ["development_secret", "smtp_plaintext", "reset_http"])
def test_unsafe_production_auth_configuration_is_rejected(unsafe):
    values = {
        "ENVIRONMENT": "production",
        "DATABASE_URL": "postgresql+asyncpg://app:password@database/app",
        "REDIS_URL": "redis://redis/0",
        "OBJECT_STORAGE_ACCESS_KEY": "production-key",
        "OBJECT_STORAGE_SECRET_KEY": "production-secret",
    }
    if unsafe != "development_secret":
        values.update(
            JWT_SECRET="a" * 64, SMTP_HOST="smtp.example.com", FRONTEND_URL="https://example.com"
        )
        if unsafe == "smtp_plaintext":
            values["SMTP_STARTTLS"] = "false"
        else:
            values["FRONTEND_URL"] = "http://example.com"
    with patch.dict(os.environ, values, clear=True):
        with pytest.raises(ValueError, match="Production configuration validation failed"):
            Settings(_env_file=None)
