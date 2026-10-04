import uuid

from sqlalchemy import func, select

from app.core.tenant import BaseRepository
from app.features.auth.models import Company, User


class CompanyRepository(BaseRepository[Company]):
    model = Company

    def get(self, company_id: uuid.UUID) -> Company | None:
        return self.session.get(Company, company_id)


class UserRepository(BaseRepository[User]):
    """Not tenant-scoped on purpose: login resolves the tenant from the user."""

    model = User

    def get(self, user_id: uuid.UUID) -> User | None:
        return self.session.get(User, user_id)

    def get_by_email(self, email: str) -> User | None:
        stmt = select(User).where(func.lower(User.email) == email.lower())
        return self.session.scalars(stmt).first()
