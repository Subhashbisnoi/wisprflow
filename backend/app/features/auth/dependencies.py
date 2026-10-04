from dataclasses import dataclass

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.container import Container, get_container
from app.core.database import get_db
from app.core.exceptions import AuthenticationError, InvalidTokenError
from app.core.logging import company_id_var, user_id_var
from app.core.tenant import TenantContext
from app.features.auth.models import Company, User
from app.features.auth.repository import CompanyRepository, UserRepository
from app.features.auth.service import AuthService

bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    user: User
    company: Company
    tenant: TenantContext


def get_auth_service(
    db: Session = Depends(get_db), container: Container = Depends(get_container)
) -> AuthService:
    return AuthService(
        session=db,
        users=UserRepository(db),
        companies=CompanyRepository(db),
        hasher=container.password_hasher,
        tokens=container.token_service,
    )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
    db: Session = Depends(get_db),
    container: Container = Depends(get_container),
) -> CurrentUser:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError()
    claims = container.token_service.decode(credentials.credentials)
    user = UserRepository(db).get(claims.user_id)
    # The company always comes from the verified token + DB, never from the client (D-044).
    if user is None or not user.is_active or user.company_id != claims.company_id:
        raise InvalidTokenError()
    company_id_var.set(str(user.company_id))
    user_id_var.set(str(user.id))
    return CurrentUser(
        user=user,
        company=user.company,
        tenant=TenantContext(company_id=user.company_id, user_id=user.id),
    )


def get_tenant(current: CurrentUser = Depends(get_current_user)) -> TenantContext:
    return current.tenant
