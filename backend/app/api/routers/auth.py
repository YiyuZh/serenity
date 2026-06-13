from __future__ import annotations

from fastapi import APIRouter, HTTPException, status

from app.api.deps import AdminUser
from app.api.schemas import LoginRequest, MeResponse, TokenResponse
from app.config import get_settings
from app.infrastructure.security import create_access_token, verify_admin_password

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest) -> TokenResponse:
    if not verify_admin_password(payload.username, payload.password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid username or password")
    return TokenResponse(access_token=create_access_token())


@router.get("/me", response_model=MeResponse)
def me(_: AdminUser) -> MeResponse:
    return MeResponse(username=get_settings().admin_username)
