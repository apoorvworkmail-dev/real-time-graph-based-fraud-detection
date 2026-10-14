"""
Phase 10 — Security & Cryptographic Utilities.
Implements:
- Bcrypt password hashing and constant-time verification.
- HMAC-SHA256 JWT access and refresh token generation and decoding.
- Token revocation tracking (JTI blacklist with TTL expiration).
- Single-use short-lived WebSocket authentication tickets.
"""

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Optional, Tuple

import bcrypt
import jwt
from app.config import get_settings

logger = logging.getLogger(__name__)

# In-memory revocation set {jti: expiry_datetime}
_revoked_tokens: Dict[str, datetime] = {}

# In-memory single-use WebSocket tickets {ticket_str: (user_id, expiry_datetime)}
_ws_tickets: Dict[str, Tuple[str, datetime]] = {}


def _cleanup_revoked_tokens():
    """Removes expired entries from the revocation store to prevent memory leaks."""
    now = datetime.now(timezone.utc)
    expired = [jti for jti, exp in _revoked_tokens.items() if exp <= now]
    for jti in expired:
        _revoked_tokens.pop(jti, None)


def _cleanup_ws_tickets():
    """Removes expired entries from the WebSocket ticket cache."""
    now = datetime.now(timezone.utc)
    expired = [t for t, (_, exp) in _ws_tickets.items() if exp <= now]
    for t in expired:
        _ws_tickets.pop(t, None)


def hash_password(password: str) -> str:
    """Securely hashes a plaintext password using bcrypt with work factor 12."""
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode("utf-8"), salt).decode("utf-8")


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verifies a plaintext password against a bcrypt hash in constant time."""
    try:
        return bcrypt.checkpw(plain_password.encode("utf-8"), hashed_password.encode("utf-8"))
    except Exception as exc:
        logger.warning("Password verification encountered an error: %s", exc)
        return False


def create_access_token(
    user_id: str,
    username: str,
    role: str,
    expires_delta: Optional[timedelta] = None,
) -> Tuple[str, str, int]:
    """
    Creates a signed JWT access token.
    Returns: (token_str, jti, expires_in_seconds)
    """
    settings = get_settings()
    delta = expires_delta or timedelta(minutes=settings.access_token_expire_minutes)
    now = datetime.now(timezone.utc)
    exp = now + delta
    jti = str(uuid.uuid4())

    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "type": "access",
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }

    token = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return token, jti, int(delta.total_seconds())


def create_refresh_token(
    user_id: str,
    username: str,
    role: str,
    expires_delta: Optional[timedelta] = None,
) -> Tuple[str, str, int]:
    """
    Creates a signed JWT refresh token.
    Returns: (token_str, jti, expires_in_seconds)
    """
    settings = get_settings()
    delta = expires_delta or timedelta(days=settings.refresh_token_expire_days)
    now = datetime.now(timezone.utc)
    exp = now + delta
    jti = str(uuid.uuid4())

    payload = {
        "sub": user_id,
        "username": username,
        "role": role,
        "type": "refresh",
        "jti": jti,
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
        "iss": settings.jwt_issuer,
        "aud": settings.jwt_audience,
    }

    token = jwt.encode(
        payload,
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    return token, jti, int(delta.total_seconds())


def decode_token(token: str, expected_type: str = "access") -> Dict[str, Any]:
    """
    Decodes and validates a JWT token.
    Enforces algorithm, signature, expiration, issuer, audience, token type, and revocation.
    Raises jwt.PyJWTError subclasses on failure.
    """
    settings = get_settings()
    _cleanup_revoked_tokens()

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
            issuer=settings.jwt_issuer,
            audience=settings.jwt_audience,
            options={"require": ["exp", "iat", "sub", "jti"]},
        )
    except jwt.PyJWTError as exc:
        raise exc

    # Validate token type
    token_type = payload.get("type")
    if token_type != expected_type:
        raise jwt.InvalidTokenError(f"Expected token type '{expected_type}', got '{token_type}'")

    # Check revocation blacklist
    jti = payload.get("jti")
    if jti and jti in _revoked_tokens:
        raise jwt.InvalidTokenError("Token has been revoked")

    return payload


def revoke_token(jti: str, exp_timestamp: Optional[int] = None):
    """Adds a token's JTI to the revocation list."""
    if not jti:
        return
    if exp_timestamp:
        exp_dt = datetime.fromtimestamp(exp_timestamp, tz=timezone.utc)
    else:
        # Default 7 days retention
        exp_dt = datetime.now(timezone.utc) + timedelta(days=7)
    _revoked_tokens[jti] = exp_dt
    _cleanup_revoked_tokens()
    logger.info("Revoked token JTI: %s (expires %s)", jti, exp_dt.isoformat())


def is_token_revoked(jti: str) -> bool:
    """Checks whether a token JTI has been revoked."""
    _cleanup_revoked_tokens()
    return jti in _revoked_tokens


def create_ws_ticket(user_id: str, expires_seconds: int = 30) -> str:
    """Generates a single-use short-lived ticket for WebSocket connection establishment."""
    _cleanup_ws_tickets()
    ticket = str(uuid.uuid4())
    expiry = datetime.now(timezone.utc) + timedelta(seconds=expires_seconds)
    _ws_tickets[ticket] = (user_id, expiry)
    return ticket


def consume_ws_ticket(ticket: str) -> Optional[str]:
    """
    Validates and immediately consumes a single-use WebSocket ticket.
    Returns the associated user_id if valid, or None if invalid/expired.
    """
    _cleanup_ws_tickets()
    entry = _ws_tickets.pop(ticket, None)
    if not entry:
        return None
    user_id, expiry = entry
    if datetime.now(timezone.utc) > expiry:
        return None
    return user_id
