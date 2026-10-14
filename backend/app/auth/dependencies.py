"""
Phase 10 — FastAPI Authentication & Role-Based Authorization Dependencies.
Provides:
- Dual-source token extraction: Authorization Header (Bearer) or HttpOnly Cookie (access_token).
- Strict token validation: algorithm, signature, expiration, issuer/audience, revocation.
- Inactive user rejection with 403 status.
- Granular permission-level and role-level RBAC enforcement.
"""

from typing import Callable, List, Optional, Union
from fastapi import Cookie, Depends, Header, HTTPException, Request, status
import jwt

from app.auth.security import decode_token
from app.config import get_settings
from app.schemas.auth import UserOut, UserRole
from app.services.user_service import user_service


async def get_token_from_request(
    request: Request,
    authorization: Optional[str] = Header(None, alias="Authorization"),
    access_token_cookie: Optional[str] = Cookie(None, alias="access_token"),
) -> Optional[str]:
    """
    Extracts JWT from either:
    1. Authorization Header: 'Bearer <token>'
    2. HttpOnly Cookie: 'access_token'
    """
    if authorization:
        parts = authorization.split()
        if len(parts) == 2 and parts[0].lower() == "bearer":
            return parts[1]
    if access_token_cookie:
        return access_token_cookie
    return None


async def get_current_user(
    request: Request,
    token: Optional[str] = Depends(get_token_from_request),
) -> UserOut:
    """
    Validates token and returns the authenticated UserOut.
    Rejects missing, expired, revoked, or invalid tokens with HTTP 401.
    Rejects disabled users with HTTP 403.
    """
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication credentials were not provided.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    try:
        payload = decode_token(token, expected_type="access")
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication token has expired.",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token", error_description="The token has expired"'},
        )
    except jwt.InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid authentication token: {str(exc)}",
            headers={"WWW-Authenticate": 'Bearer error="invalid_token"'},
        )

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Malformed token: missing subject claim.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    user = user_service.get_by_id(user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User account associated with this token no longer exists.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated. Contact an administrator.",
        )

    return user_service.to_out(user)


async def get_optional_current_user(
    request: Request,
    token: Optional[str] = Depends(get_token_from_request),
) -> Optional[UserOut]:
    """Returns the authenticated user if token is present and valid, otherwise None."""
    if not token:
        return None
    try:
        return await get_current_user(request, token)
    except HTTPException:
        return None


def require_permission(permission: str) -> Callable:
    """
    Dependency factory enforcing that the authenticated user possesses a specific permission.
    Returns 401 if unauthenticated, 403 if unauthorized.
    """
    async def permission_checker(current_user: UserOut = Depends(get_current_user)) -> UserOut:
        # Admin role automatically has wildcard access
        if "admin:all" in current_user.permissions or permission in current_user.permissions:
            return current_user

        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Forbidden: User role '{current_user.role.value}' lacks required permission: '{permission}'.",
        )

    return permission_checker


def require_role(roles: Union[UserRole, List[UserRole]]) -> Callable:
    """
    Dependency factory enforcing that the authenticated user holds one of the specified roles.
    """
    allowed = [roles] if isinstance(roles, UserRole) else roles

    async def role_checker(current_user: UserOut = Depends(get_current_user)) -> UserOut:
        if current_user.role in allowed:
            return current_user

        role_names = [r.value for r in allowed]
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=f"Forbidden: Action requires one of the following roles: {role_names}.",
        )

    return role_checker


# Convenient aliases
require_admin = require_role(UserRole.ADMIN)
require_analyst_or_admin = require_role([UserRole.FRAUD_ANALYST, UserRole.ADMIN])
require_authenticated_user = get_current_user
