"""
Phase 10 — Identity, User Management, and Credential Service.
Provides:
- Stable user entity management with unique login identifiers.
- Bcrypt password hashing and credential verification.
- Safe first-administrator bootstrap without committing production secrets.
- Neo4j persistence with seamless in-memory fallback for offline test suites.
- Centralized permission compilation per role.
"""

import copy
import logging
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

from app.auth.security import hash_password, verify_password
from app.config import get_settings
from app.db.neo4j_driver import get_driver
from app.schemas.auth import UserCreate, UserOut, UserRole, UserUpdate

logger = logging.getLogger(__name__)

# Canonical Role-to-Permissions Mapping
ROLE_PERMISSIONS: Dict[UserRole, Set[str]] = {
    UserRole.ADMIN: {
        "cases:read",
        "cases:create",
        "cases:assign",
        "cases:priority",
        "cases:transition",
        "cases:resolve",
        "cases:reopen",
        "cases:notes",
        "cases:audit",
        "graph:read",
        "fraud:read",
        "risk:read",
        "ml:read",
        "ml:evaluate",
        "stream:read",
        "stream:control",
        "stream:write",
        "entities:write",
        "users:manage",
        "admin:all",
    },
    UserRole.FRAUD_ANALYST: {
        "cases:read",
        "cases:create",
        "cases:assign",
        "cases:priority",
        "cases:transition",
        "cases:investigate",
        "cases:notes",
        "cases:audit",
        "graph:read",
        "fraud:read",
        "risk:read",
        "ml:read",
        "stream:read",
        "stream:write",
    },
    UserRole.COMPLIANCE_OFFICER: {
        "cases:read",
        "cases:transition",
        "cases:resolve",
        "cases:reopen",
        "cases:notes",
        "cases:audit",
        "graph:read",
        "fraud:read",
        "risk:read",
        "ml:read",
        "stream:read",
    },
}


def get_permissions_for_role(role: UserRole) -> List[str]:
    """Returns the list of permitted action keys for a given role."""
    return sorted(list(ROLE_PERMISSIONS.get(role, set())))


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class UserService:
    """Manages identity, credentials, roles, and administrative configuration."""

    def __init__(self):
        # In-memory storage indexed by user_id
        self._users: Dict[str, Dict[str, Any]] = {}
        # Secondary indexes for unique lookups
        self._username_index: Dict[str, str] = {}
        self._email_index: Dict[str, str] = {}
        self._bootstrap_users()

    def _bootstrap_users(self):
        """Initializes default admin and demo role personas if not already present."""
        settings = get_settings()

        # 1. Admin Bootstrap
        admin_pass = settings.initial_admin_password
        if not admin_pass:
            # If in dev, use a safe dev password; otherwise generate high-entropy token
            if settings.app_env == "development":
                admin_pass = "Admin@FraudGraph2026!"
            else:
                admin_pass = secrets.token_urlsafe(18)
                logger.warning(
                    "====================================================================\n"
                    "INITIAL ADMIN CREATED:\n"
                    "Username: %s\n"
                    "Password: %s\n"
                    "Save this password! It will not be shown again.\n"
                    "====================================================================",
                    settings.initial_admin_username,
                    admin_pass,
                )

        self._seed_user(
            user_id="USR_ADMIN_001",
            username=settings.initial_admin_username,
            email=settings.initial_admin_email,
            plain_password=admin_pass,
            role=UserRole.ADMIN,
            full_name="Platform Administrator",
            is_active=True,
        )

        # 2. Seed Demo Analyst (Priya Sharma)
        self._seed_user(
            user_id="USR_ANALYST_001",
            username="analyst_priya",
            email="priya.sharma@example.com",
            plain_password="AnalystPass2026!",
            role=UserRole.FRAUD_ANALYST,
            full_name="Priya Sharma (Fraud Analyst)",
            is_active=True,
        )

        # 3. Seed Demo Compliance Officer (David Chen)
        self._seed_user(
            user_id="USR_COMPLIANCE_001",
            username="officer_chen",
            email="david.chen@example.com",
            plain_password="CompliancePass2026!",
            role=UserRole.COMPLIANCE_OFFICER,
            full_name="David Chen (Compliance Officer)",
            is_active=True,
        )

        # 4. Seed Disabled User for explicit security test verification
        self._seed_user(
            user_id="USR_DISABLED_001",
            username="disabled_user",
            email="disabled@example.com",
            plain_password="DisabledPass2026!",
            role=UserRole.FRAUD_ANALYST,
            full_name="Deactivated Analyst",
            is_active=False,
        )


        # Attempt to sync or persist to Neo4j if available
        self._sync_to_neo4j()

    def _seed_user(
        self,
        user_id: str,
        username: str,
        email: str,
        plain_password: str,
        role: UserRole,
        full_name: str,
        is_active: bool = True,
    ):
        norm_user = username.strip().lower()
        norm_email = email.strip().lower()
        hashed = hash_password(plain_password)
        now = _now_iso()

        user_dict = {
            "user_id": user_id,
            "username": norm_user,
            "email": norm_email,
            "hashed_password": hashed,
            "role": role.value if isinstance(role, UserRole) else role,
            "full_name": full_name,
            "is_active": is_active,
            "created_at": now,
            "updated_at": now,
        }
        self._users[user_id] = user_dict
        self._username_index[norm_user] = user_id
        self._email_index[norm_email] = user_id

    def _sync_to_neo4j(self):
        """Attempts to sync in-memory seed users to Neo4j database."""
        try:
            driver = get_driver()
            with driver.session() as session:
                # Ensure unique constraints exist
                session.run("CREATE CONSTRAINT user_id_unique IF NOT EXISTS FOR (u:User) REQUIRE u.user_id IS UNIQUE")
                session.run("CREATE CONSTRAINT username_unique IF NOT EXISTS FOR (u:User) REQUIRE u.username IS UNIQUE")

                for u in self._users.values():
                    session.run(
                        """
                        MERGE (u:User {username: $username})
                        ON CREATE SET
                            u.user_id = $user_id,
                            u.email = $email,
                            u.hashed_password = $hashed_password,
                            u.role = $role,
                            u.full_name = $full_name,
                            u.is_active = $is_active,
                            u.created_at = $created_at,
                            u.updated_at = $updated_at
                        """,
                        **u,
                    )
            logger.info("Successfully synced %d users to Neo4j", len(self._users))
        except Exception as exc:
            logger.debug("Neo4j user sync skipped (offline or test environment): %s", exc)

    def authenticate(self, identifier: str, plain_password: str) -> Optional[Dict[str, Any]]:
        """
        Authenticates a user by username or email.
        Returns the user record if valid, or None if authentication fails.
        """
        user = self.get_by_identifier(identifier)
        if not user:
            return None
        if not verify_password(plain_password, user["hashed_password"]):
            return None
        return user

    def get_by_identifier(self, identifier: str) -> Optional[Dict[str, Any]]:
        """Finds user by normalized username or email address."""
        clean = identifier.strip().lower()

        # Check in-memory index first
        uid = self._username_index.get(clean) or self._email_index.get(clean)
        if uid and uid in self._users:
            return copy.deepcopy(self._users[uid])

        # Fallback query to Neo4j
        try:
            driver = get_driver()
            with driver.session() as session:
                rec = session.run(
                    "MATCH (u:User) WHERE u.username = $id OR u.email = $id RETURN u",
                    id=clean,
                ).single()
                if rec:
                    props = dict(rec["u"])
                    # Cache in memory
                    self._users[props["user_id"]] = props
                    self._username_index[props["username"]] = props["user_id"]
                    self._email_index[props["email"]] = props["user_id"]
                    return props
        except Exception:
            pass

        return None

    def get_by_id(self, user_id: str) -> Optional[Dict[str, Any]]:
        """Finds user by stable user_id."""
        if user_id in self._users:
            return copy.deepcopy(self._users[user_id])

        try:
            driver = get_driver()
            with driver.session() as session:
                rec = session.run("MATCH (u:User {user_id: $uid}) RETURN u", uid=user_id).single()
                if rec:
                    props = dict(rec["u"])
                    self._users[props["user_id"]] = props
                    return props
        except Exception:
            pass

        return None

    def create_user(self, payload: UserCreate) -> UserOut:
        """Creates a new user, hashes password, and persists."""
        norm_user = payload.username.strip().lower()
        norm_email = payload.email.strip().lower()

        # Uniqueness checks
        if self.get_by_identifier(norm_user) is not None:
            raise ValueError(f"Username '{norm_user}' is already registered")
        if self.get_by_identifier(norm_email) is not None:
            raise ValueError(f"Email '{norm_email}' is already registered")

        user_id = f"USR_{uuid.uuid4().hex[:8].upper()}"
        hashed = hash_password(payload.password)
        now = _now_iso()

        user_dict = {
            "user_id": user_id,
            "username": norm_user,
            "email": norm_email,
            "hashed_password": hashed,
            "role": payload.role.value if isinstance(payload.role, UserRole) else payload.role,
            "full_name": payload.full_name or norm_user,
            "is_active": payload.is_active,
            "created_at": now,
            "updated_at": now,
        }

        self._users[user_id] = user_dict
        self._username_index[norm_user] = user_id
        self._email_index[norm_email] = user_id

        # Neo4j write
        try:
            driver = get_driver()
            with driver.session() as session:
                session.run(
                    """
                    CREATE (u:User {
                        user_id: $user_id,
                        username: $username,
                        email: $email,
                        hashed_password: $hashed_password,
                        role: $role,
                        full_name: $full_name,
                        is_active: $is_active,
                        created_at: $created_at,
                        updated_at: $updated_at
                    })
                    """,
                    **user_dict,
                )
        except Exception as exc:
            logger.debug("Neo4j user creation write skipped: %s", exc)

        return self.to_out(user_dict)

    def update_user(self, user_id: str, payload: UserUpdate) -> UserOut:
        """Updates user profile, role, status, or password."""
        user = self._users.get(user_id)
        if not user:
            user = self.get_by_id(user_id)
        if not user:
            raise KeyError(f"User '{user_id}' not found")

        updates: Dict[str, Any] = {}
        if payload.email is not None:
            norm_email = payload.email.strip().lower()
            existing = self.get_by_identifier(norm_email)
            if existing and existing["user_id"] != user_id:
                raise ValueError(f"Email '{norm_email}' is already taken by another account")
            self._email_index.pop(user["email"], None)
            user["email"] = norm_email
            self._email_index[norm_email] = user_id
            updates["email"] = norm_email

        if payload.full_name is not None:
            user["full_name"] = payload.full_name
            updates["full_name"] = payload.full_name

        if payload.role is not None:
            user["role"] = payload.role.value if isinstance(payload.role, UserRole) else payload.role
            updates["role"] = user["role"]

        if payload.is_active is not None:
            user["is_active"] = payload.is_active
            updates["is_active"] = payload.is_active

        if payload.password is not None:
            user["hashed_password"] = hash_password(payload.password)
            updates["hashed_password"] = user["hashed_password"]

        user["updated_at"] = _now_iso()
        updates["updated_at"] = user["updated_at"]

        # Neo4j update
        try:
            driver = get_driver()
            with driver.session() as session:
                set_clause = ", ".join([f"u.{k} = ${k}" for k in updates])
                session.run(f"MATCH (u:User {{user_id: $uid}}) SET {set_clause}", uid=user_id, **updates)
        except Exception as exc:
            logger.debug("Neo4j user update skipped: %s", exc)

        return self.to_out(user)

    def delete_user(self, user_id: str) -> bool:
        """Removes a user from repository."""
        user = self._users.pop(user_id, None)
        if not user:
            return False
        self._username_index.pop(user["username"], None)
        self._email_index.pop(user["email"], None)

        try:
            driver = get_driver()
            with driver.session() as session:
                session.run("MATCH (u:User {user_id: $uid}) DETACH DELETE u", uid=user_id)
        except Exception:
            pass

        return True

    def list_users(self, skip: int = 0, limit: int = 50) -> Tuple[List[UserOut], int]:
        """Returns paginated list of users."""
        all_users = list(self._users.values())
        total = len(all_users)
        slice_users = all_users[skip : skip + limit]
        return [self.to_out(u) for u in slice_users], total

    def to_out(self, user_dict: Dict[str, Any]) -> UserOut:
        """Converts internal user dict to UserOut schema with permissions."""
        role_enum = UserRole(user_dict["role"])
        return UserOut(
            user_id=user_dict["user_id"],
            username=user_dict["username"],
            email=user_dict["email"],
            full_name=user_dict.get("full_name"),
            role=role_enum,
            is_active=bool(user_dict.get("is_active", True)),
            created_at=user_dict.get("created_at", _now_iso()),
            updated_at=user_dict.get("updated_at", _now_iso()),
            permissions=get_permissions_for_role(role_enum),
        )


# Global singleton instance
user_service = UserService()
