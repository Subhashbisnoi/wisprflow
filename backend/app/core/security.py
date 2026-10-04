"""Password hashing and JWT issuing/verification (D-057)."""

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import bcrypt
import jwt

from app.core.config import Settings
from app.core.exceptions import InvalidTokenError, TokenExpiredError


class PasswordHasher:
    def __init__(self, rounds: int = 12) -> None:
        self._rounds = rounds

    def hash(self, raw: str) -> str:
        return bcrypt.hashpw(raw.encode(), bcrypt.gensalt(self._rounds)).decode()

    def verify(self, raw: str, hashed: str) -> bool:
        try:
            return bcrypt.checkpw(raw.encode(), hashed.encode())
        except ValueError:
            return False


@dataclass(frozen=True)
class AccessToken:
    token: str
    expires_at: datetime


@dataclass(frozen=True)
class TokenClaims:
    user_id: uuid.UUID
    company_id: uuid.UUID


class TokenService:
    def __init__(self, settings: Settings) -> None:
        self._secret = settings.jwt_secret_value
        self._algorithm = settings.jwt_algorithm
        self._ttl = timedelta(minutes=settings.jwt_expire_minutes)

    def issue(self, user_id: uuid.UUID, company_id: uuid.UUID) -> AccessToken:
        now = datetime.now(UTC)
        expires_at = now + self._ttl
        payload = {
            "sub": str(user_id),
            "cid": str(company_id),
            "iat": int(now.timestamp()),
            "exp": int(expires_at.timestamp()),
        }
        return AccessToken(jwt.encode(payload, self._secret, self._algorithm), expires_at)

    def decode(self, token: str) -> TokenClaims:
        try:
            payload = jwt.decode(
                token,
                self._secret,
                algorithms=[self._algorithm],
                options={"require": ["sub", "cid", "exp"]},
            )
            return TokenClaims(uuid.UUID(payload["sub"]), uuid.UUID(payload["cid"]))
        except jwt.ExpiredSignatureError as exc:
            raise TokenExpiredError() from exc
        except (jwt.InvalidTokenError, ValueError, KeyError) as exc:
            raise InvalidTokenError() from exc
