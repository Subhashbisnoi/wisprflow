import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from functools import lru_cache

from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.exceptions import ConflictError, InvalidCredentialsError
from app.core.security import AccessToken, PasswordHasher, TokenService
from app.features.auth.models import Company, User, UserRole
from app.features.auth.repository import CompanyRepository, UserRepository
from app.features.auth.schemas import SignupRequest
from app.features.validation.gstin import state_code_of

logger = logging.getLogger("app.auth")


@lru_cache(maxsize=1)
def _dummy_hash(hasher: PasswordHasher) -> str:
    """Verifying against a dummy hash keeps login timing similar for unknown emails."""
    return hasher.hash("ledgerline-timing-equaliser")


@dataclass(frozen=True)
class AuthResult:
    token: AccessToken
    user: User
    company: Company


class AuthService:
    def __init__(
        self,
        session: Session,
        users: UserRepository,
        companies: CompanyRepository,
        hasher: PasswordHasher,
        tokens: TokenService,
    ) -> None:
        self._session = session
        self._users = users
        self._companies = companies
        self._hasher = hasher
        self._tokens = tokens

    def signup(self, cmd: SignupRequest) -> AuthResult:
        email = cmd.email.lower()
        if self._users.get_by_email(email):
            raise ConflictError("An account with this email already exists.", code="email_taken")

        company = self._companies.add(
            Company(
                name=cmd.company_name,
                gstin=cmd.company_gstin,
                state_code=state_code_of(cmd.company_gstin),
            )
        )
        self._companies.flush()
        user = self._users.add(
            User(
                company_id=company.id,
                email=email,
                full_name=cmd.full_name,
                password_hash=self._hasher.hash(cmd.password),
                role=UserRole.ADMIN,
                last_login_at=datetime.now(UTC),
            )
        )
        try:
            self._session.commit()
        except IntegrityError as exc:  # concurrent signup with the same email
            self._session.rollback()
            raise ConflictError(
                "An account with this email already exists.", code="email_taken"
            ) from exc
        logger.info("company signed up", extra={"company_id": str(company.id)})
        return AuthResult(self._tokens.issue(user.id, company.id), user, company)

    def login(self, email: str, password: str) -> AuthResult:
        user = self._users.get_by_email(email)
        if user is None:
            self._hasher.verify(password, _dummy_hash(self._hasher))
            raise InvalidCredentialsError()
        if not self._hasher.verify(password, user.password_hash) or not user.is_active:
            raise InvalidCredentialsError()
        user.last_login_at = datetime.now(UTC)
        self._session.commit()
        return AuthResult(self._tokens.issue(user.id, user.company_id), user, user.company)
