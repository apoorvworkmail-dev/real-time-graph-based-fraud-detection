"""
Phase 10 — Authentication and Role-Based Access Control Schemas.
Defines user models, roles, token payloads, and request/response contracts.
"""

from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, EmailStr, Field, field_validator


class UserRole(str, Enum):
    ADMIN = "admin"
    FRAUD_ANALYST = "fraud_analyst"
    COMPLIANCE_OFFICER = "compliance_officer"

    @classmethod
    def normalize_role(cls, value: str) -> "UserRole":
        """Normalizes human or case-insensitive role representations into enum."""
        v = value.strip().lower().replace(" ", "_")
        if v in ("admin", "administrator"):
            return cls.ADMIN
        if v in ("fraud_analyst", "analyst"):
            return cls.FRAUD_ANALYST
        if v in ("compliance_officer", "compliance", "officer"):
            return cls.COMPLIANCE_OFFICER
        raise ValueError(f"Invalid role '{value}'. Must be one of: {[r.value for r in cls]}")


class UserBase(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="Normalized unique login identifier")
    email: EmailStr = Field(..., description="Unique email address")
    full_name: Optional[str] = Field(None, max_length=100, description="User full display name")
    role: UserRole = Field(default=UserRole.FRAUD_ANALYST, description="RBAC authorization role")
    is_active: bool = Field(default=True, description="Account active/disabled status")

    @field_validator("username")
    @classmethod
    def validate_username(cls, v: str) -> str:
        cleaned = v.strip().lower()
        if not cleaned:
            raise ValueError("Username cannot be empty")
        if len(cleaned) < 3:
            raise ValueError("Username must be at least 3 characters")
        return cleaned

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: str) -> str:
        return v.strip().lower()


class UserCreate(UserBase):
    password: str = Field(..., min_length=8, max_length=128, description="Plaintext password to be securely hashed")

    @field_validator("password")
    @classmethod
    def validate_password_strength(cls, v: str) -> str:
        if len(v) < 8:
            raise ValueError("Password must be at least 8 characters long")
        return v


class UserUpdate(BaseModel):
    email: Optional[EmailStr] = None
    full_name: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(None, min_length=8, max_length=128)

    @field_validator("email")
    @classmethod
    def validate_email(cls, v: Optional[str]) -> Optional[str]:
        return v.strip().lower() if v else None


class UserOut(UserBase):
    user_id: str = Field(..., description="Stable user ID")
    created_at: str = Field(..., description="Creation ISO-8601 timestamp")
    updated_at: str = Field(..., description="Last update ISO-8601 timestamp")
    permissions: List[str] = Field(default_factory=list, description="Computed RBAC permissions for the active role")


class LoginRequest(BaseModel):
    username: str = Field(..., description="Username or email address")
    password: str = Field(..., description="User password")


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in: int
    user: UserOut


class TokenPayload(BaseModel):
    sub: str
    username: str
    role: str
    type: str  # "access" or "refresh"
    jti: str
    exp: int
    iat: int
    iss: Optional[str] = None
    aud: Optional[str] = None


class RefreshTokenRequest(BaseModel):
    refresh_token: Optional[str] = Field(None, description="Optional refresh token if not provided via cookie")


class WsTicketResponse(BaseModel):
    ticket: str = Field(..., description="Single-use short-lived WebSocket authentication ticket")
    expires_in: int = Field(default=30, description="Validity period in seconds")


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str = Field(..., min_length=8, max_length=128)
