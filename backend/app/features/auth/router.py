from fastapi import APIRouter, Depends, status

from app.features.auth.dependencies import CurrentUser, get_auth_service, get_current_user
from app.features.auth.schemas import (
    AuthResponse,
    CompanyOut,
    LoginRequest,
    MeResponse,
    SignupRequest,
    UserOut,
)
from app.features.auth.service import AuthResult, AuthService

router = APIRouter(prefix="/auth", tags=["auth"])


def _to_response(result: AuthResult) -> AuthResponse:
    return AuthResponse(
        access_token=result.token.token,
        expires_at=result.token.expires_at,
        user=UserOut.model_validate(result.user),
        company=CompanyOut.model_validate(result.company),
    )


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
def signup(body: SignupRequest, service: AuthService = Depends(get_auth_service)) -> AuthResponse:
    return _to_response(service.signup(body))


@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest, service: AuthService = Depends(get_auth_service)) -> AuthResponse:
    return _to_response(service.login(body.email, body.password))


@router.get("/me", response_model=MeResponse)
def me(current: CurrentUser = Depends(get_current_user)) -> MeResponse:
    return MeResponse(
        user=UserOut.model_validate(current.user),
        company=CompanyOut.model_validate(current.company),
    )
