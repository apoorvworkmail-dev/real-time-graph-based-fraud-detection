"""
Phase 10 — Authentication API Endpoints.
Provides:
- Secure login with bcrypt verification and cookie/bearer issuance.
- Stateless token refresh with rotation and revocation.
- Explicit logout with token JTI revocation and cookie clearing.
- Identity profile inspection (/me).
- Single-use short-lived WebSocket ticket exchange (/ws-ticket).
"""

from typing import Optional
from fastapi import APIRouter, Cookie, Depends, Header, HTTPException, Request, Response, status

from app.auth.dependencies import get_current_user, get_token_from_request
from app.auth.security import (
    create_access_token,
    create_refresh_token,
    create_ws_ticket,
    decode_token,
    revoke_token,
)
from app.config import get_settings
from app.schemas.auth import (
    LoginRequest,
    RefreshTokenRequest,
    Token,
    UserOut,
    WsTicketResponse,
)
from app.services.user_service import user_service
import jwt

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/login", response_model=Token, summary="Authenticate and acquire JWT access token")
def login(payload: LoginRequest, response: Response):
    """
    Authenticates user via username or email and bcrypt password verification.
    Issues signed access and refresh tokens.
    Sets secure HttpOnly cookies and returns token payload for Bearer header use.
    """
    settings = get_settings()
    user = user_service.authenticate(payload.username, payload.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated. Contact an administrator.",
        )

    user_out = user_service.to_out(user)
    access_token, _, access_exp_sec = create_access_token(
        user_id=user_out.user_id,
        username=user_out.username,
        role=user_out.role.value,
    )
    refresh_token, _, refresh_exp_sec = create_refresh_token(
        user_id=user_out.user_id,
        username=user_out.username,
        role=user_out.role.value,
    )

    # Set secure HttpOnly cookies
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=access_exp_sec,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=refresh_token,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=refresh_exp_sec,
        path="/",
    )

    return Token(
        access_token=access_token,
        token_type="bearer",
        expires_in=access_exp_sec,
        user=user_out,
    )


@router.post("/refresh", response_model=Token, summary="Refresh access token using valid refresh token")
def refresh_token(
    request: Request,
    response: Response,
    body: Optional[RefreshTokenRequest] = None,
    refresh_token_cookie: Optional[str] = Cookie(None, alias="refresh_token"),
):
    """
    Validates a refresh token (from cookie or payload).
    Rotates the refresh token (revokes old JTI, issues new refresh token),
    and sets fresh HttpOnly cookies.
    """
    settings = get_settings()
    token_str = (body.refresh_token if body and body.refresh_token else None) or refresh_token_cookie
    if not token_str:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token was not provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_token(token_str, expected_type="refresh")
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired. Please log in again.",
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid refresh token: {str(exc)}",
        )

    user_id = payload.get("sub")
    old_jti = payload.get("jti")
    old_exp = payload.get("exp")

    # Revoke old refresh token (secure rotation)
    if old_jti:
        revoke_token(old_jti, old_exp)

    user = user_service.get_by_id(user_id)
    if not user or not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account no longer active or valid.",
        )

    user_out = user_service.to_out(user)
    new_access, _, access_exp_sec = create_access_token(
        user_id=user_out.user_id,
        username=user_out.username,
        role=user_out.role.value,
    )
    new_refresh, _, refresh_exp_sec = create_refresh_token(
        user_id=user_out.user_id,
        username=user_out.username,
        role=user_out.role.value,
    )

    response.set_cookie(
        key="access_token",
        value=new_access,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=access_exp_sec,
        path="/",
    )
    response.set_cookie(
        key="refresh_token",
        value=new_refresh,
        httponly=True,
        secure=settings.cookie_secure,
        samesite=settings.cookie_samesite,
        max_age=refresh_exp_sec,
        path="/",
    )

    return Token(
        access_token=new_access,
        token_type="bearer",
        expires_in=access_exp_sec,
        user=user_out,
    )


@router.post("/logout", summary="Logout, revoke current token, and clear cookies")
def logout(
    request: Request,
    response: Response,
    token: Optional[str] = Depends(get_token_from_request),
    refresh_token_cookie: Optional[str] = Cookie(None, alias="refresh_token"),
):
    """
    Revokes the current access token and refresh token JTIs, and clears auth cookies.
    """
    if token:
        try:
            payload = decode_token(token, expected_type="access")
            revoke_token(payload.get("jti"), payload.get("exp"))
        except Exception:
            pass

    if refresh_token_cookie:
        try:
            payload = decode_token(refresh_token_cookie, expected_type="refresh")
            revoke_token(payload.get("jti"), payload.get("exp"))
        except Exception:
            pass

    response.delete_cookie(key="access_token", path="/")
    response.delete_cookie(key="refresh_token", path="/")
    return {"message": "Logged out successfully", "status": "revoked"}


@router.get("/me", response_model=UserOut, summary="Retrieve current user profile and RBAC permissions")
def get_current_user_profile(current_user: UserOut = Depends(get_current_user)):
    """Returns currently authenticated user profile with active permissions."""
    return current_user


@router.post("/ws-ticket", response_model=WsTicketResponse, summary="Obtain a single-use short-lived WebSocket ticket")
def generate_ws_ticket(current_user: UserOut = Depends(get_current_user)):
    """
    Generates a single-use ticket valid for 30 seconds to authenticate WebSocket connections
    without exposing bearer tokens in query strings.
    """
    ticket = create_ws_ticket(current_user.user_id, expires_seconds=30)
    return WsTicketResponse(ticket=ticket, expires_in=30)
