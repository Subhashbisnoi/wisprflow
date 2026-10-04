import uuid

import jwt
import pytest

from app.core.config import Settings
from app.core.exceptions import InvalidTokenError, TokenExpiredError
from app.core.security import PasswordHasher, TokenService


def _settings(**overrides: object) -> Settings:
    return Settings(  # type: ignore[call-arg]
        DATABASE_URL="postgresql://localhost/unused",
        jwt_secret="unit-test-secret-0123456789-abcdefghijklmnop",
        llm_provider="fake",
        **overrides,
    )


def test_password_hash_round_trip() -> None:
    hasher = PasswordHasher(rounds=4)
    hashed = hasher.hash("s3cret-pass")
    assert hashed != "s3cret-pass"
    assert hasher.verify("s3cret-pass", hashed)
    assert not hasher.verify("wrong", hashed)
    assert not hasher.verify("x", "not-a-bcrypt-hash")


def test_token_round_trip_carries_user_and_company() -> None:
    service = TokenService(_settings())
    user_id, company_id = uuid.uuid4(), uuid.uuid4()
    claims = service.decode(service.issue(user_id, company_id).token)
    assert (claims.user_id, claims.company_id) == (user_id, company_id)


def test_expired_token_raises_token_expired() -> None:
    settings = _settings()
    token = jwt.encode(
        {"sub": str(uuid.uuid4()), "cid": str(uuid.uuid4()), "exp": 1},
        settings.jwt_secret_value,
        "HS256",
    )
    with pytest.raises(TokenExpiredError):
        TokenService(settings).decode(token)


def test_tampered_token_raises_invalid_token() -> None:
    service = TokenService(_settings())
    token = service.issue(uuid.uuid4(), uuid.uuid4()).token
    header, payload, signature = token.split(".")
    with pytest.raises(InvalidTokenError):
        service.decode(f"{header}.{payload}.{signature[::-1]}")
    with pytest.raises(InvalidTokenError):
        service.decode("not-a-jwt")


def test_settings_normalise_db_url_and_accept_db_url_alias() -> None:
    settings = Settings(  # type: ignore[call-arg]
        DB_URL="postgresql://u:p@host/db?sslmode=require", jwt_secret="x" * 40, llm_provider="fake"
    )
    assert settings.database_url == "postgresql+psycopg://u:p@host/db?sslmode=require"


def test_production_requires_jwt_secret() -> None:
    with pytest.raises(ValueError, match="JWT_SECRET"):
        Settings(  # type: ignore[call-arg]
            DATABASE_URL="postgresql://x/y",
            app_env="production",
            llm_provider="fake",
            jwt_secret=None,
        )
