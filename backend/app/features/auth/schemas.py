import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

from app.features.auth.models import UserRole
from app.features.validation.gstin import check_gstin, normalize_gstin


class SignupRequest(BaseModel):
    company_name: str = Field(min_length=2, max_length=200)
    company_gstin: str | None = Field(default=None, max_length=20)
    full_name: str = Field(min_length=2, max_length=200)
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)

    @field_validator("company_name", "full_name")
    @classmethod
    def _strip(cls, value: str) -> str:
        return value.strip()

    @field_validator("company_gstin")
    @classmethod
    def _valid_gstin(cls, value: str | None) -> str | None:
        gstin = normalize_gstin(value)
        if gstin is None:
            return None
        check = check_gstin(gstin)
        if not check.valid:
            raise ValueError(f"GSTIN is not valid: {check.reason}")
        return gstin


class LoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class CompanyOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    name: str
    gstin: str | None
    state_code: str | None


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str
    role: UserRole


class AuthResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_at: datetime
    user: UserOut
    company: CompanyOut


class MeResponse(BaseModel):
    user: UserOut
    company: CompanyOut
