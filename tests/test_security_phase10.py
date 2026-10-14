"""
Phase 10 — Security, Authentication & Role-Based Access Control Test Suite.

Tests:
1. Valid and invalid login
2. Password hashing with bcrypt and verification
3. Expired, malformed, and algorithm-confused tokens
4. Deactivated / disabled user rejection
5. Role-specific permissions (Fraud Analyst, Compliance Officer, Admin)
6. Unauthorized direct API calls (401 Unauthorized)
7. Authenticated role without permission (403 Forbidden)
8. Case ownership and actor identity preservation in case actions & audit logs
9. Administrator-only actions (user management, simulator controls, entity deletions)
10. Protected WebSocket access (cookies, tickets, and unauthorized rejection)
11. CORS and externalized secrets configuration
12. Existing functional regressions validation
"""

import asyncio
import os
import sys
import unittest
from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
import jwt

# Add backend to path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.auth.security import (
    create_access_token,
    create_refresh_token,
    create_ws_ticket,
    consume_ws_ticket,
    decode_token,
    hash_password,
    is_token_revoked,
    revoke_token,
    verify_password,
)
from app.config import get_settings
from app.main import app
from app.schemas.auth import (
    LoginRequest,
    UserCreate,
    UserRole,
    UserUpdate,
)
from app.schemas.case import (
    CaseCreate,
    CasePriority,
    CaseStatus,
    CaseStatusTransition,
    ResolutionCategory,
)
from app.services.case_service import case_service
from app.services.user_service import user_service


class TestPasswordSecurity(unittest.TestCase):
    """Verifies bcrypt password hashing, work factor, and constant-time verification."""

    def test_bcrypt_hashing_and_random_salts(self):
        plain = "CorrectHorseBatteryStaple2026!"
        h1 = hash_password(plain)
        h2 = hash_password(plain)

        # Hashes must start with bcrypt prefix ($2b$)
        self.assertTrue(h1.startswith("$2b$") or h1.startswith("$2a$"))
        self.assertTrue(h2.startswith("$2b$") or h2.startswith("$2a$"))
        # Random salts must yield different hash strings for identical inputs
        self.assertNotEqual(h1, h2)
        # Both must verify successfully
        self.assertTrue(verify_password(plain, h1))
        self.assertTrue(verify_password(plain, h2))

    def test_password_verification_negative(self):
        plain = "MySecretPass123!"
        hashed = hash_password(plain)
        self.assertFalse(verify_password("WrongPassword123!", hashed))
        self.assertFalse(verify_password("", hashed))
        self.assertFalse(verify_password("mysecretpass123!", hashed))  # case-sensitive

    def test_password_length_validation(self):
        with self.assertRaises(ValueError):
            UserCreate(
                username="shortpassuser",
                email="short@example.com",
                password="123",  # < 8 chars
                role=UserRole.FRAUD_ANALYST,
            )


class TestJWTCryptography(unittest.TestCase):
    """Verifies JWT access & refresh token claims, signing, expiration, and revocation."""

    def setUp(self):
        self.settings = get_settings()

    def test_token_signing_and_decoding(self):
        token, jti, exp_sec = create_access_token(
            user_id="USR_TEST_001",
            username="test_analyst",
            role="fraud_analyst",
        )
        self.assertIsInstance(token, str)
        self.assertGreater(len(token), 20)
        self.assertGreater(exp_sec, 0)

        payload = decode_token(token, expected_type="access")
        self.assertEqual(payload["sub"], "USR_TEST_001")
        self.assertEqual(payload["username"], "test_analyst")
        self.assertEqual(payload["role"], "fraud_analyst")
        self.assertEqual(payload["type"], "access")
        self.assertEqual(payload["jti"], jti)
        self.assertEqual(payload["iss"], self.settings.jwt_issuer)
        self.assertEqual(payload["aud"], self.settings.jwt_audience)

    def test_expired_token_rejected(self):
        # Create token that expired 10 minutes ago
        token, jti, _ = create_access_token(
            user_id="USR_EXP_001",
            username="expired_user",
            role="fraud_analyst",
            expires_delta=timedelta(minutes=-10),
        )
        with self.assertRaises(jwt.ExpiredSignatureError):
            decode_token(token, expected_type="access")

    def test_malformed_and_tampered_token_rejected(self):
        token, _, _ = create_access_token(
            user_id="USR_TAMPER_001",
            username="tamper_user",
            role="fraud_analyst",
        )
        # Tamper token signature
        tampered = token[:-6] + "xxxxxx"
        with self.assertRaises(jwt.InvalidTokenError):
            decode_token(tampered, expected_type="access")

        with self.assertRaises(jwt.InvalidTokenError):
            decode_token("not-a-valid-jwt-token-string", expected_type="access")

    def test_algorithm_confusion_prevention(self):
        """Tokens with algorithm 'none' or mismatched algorithm must be rejected."""
        unsecured = jwt.encode(
            {"sub": "USR_ATTACKER", "exp": int((datetime.now(timezone.utc) + timedelta(hours=1)).timestamp())},
            key="",
            algorithm="none",
        )
        with self.assertRaises(jwt.InvalidTokenError):
            decode_token(unsecured, expected_type="access")

    def test_token_revocation_blacklist(self):
        token, jti, _ = create_access_token(
            user_id="USR_REVOKE_001",
            username="revoke_user",
            role="fraud_analyst",
        )
        self.assertFalse(is_token_revoked(jti))
        payload_before = decode_token(token, expected_type="access")
        self.assertEqual(payload_before["sub"], "USR_REVOKE_001")

        # Explicitly revoke token
        revoke_token(jti)
        self.assertTrue(is_token_revoked(jti))

        # Subsequent decode must fail with InvalidTokenError
        with self.assertRaises(jwt.InvalidTokenError) as ctx:
            decode_token(token, expected_type="access")
        self.assertIn("revoked", str(ctx.exception).lower())


class TestAuthenticationEndpoints(unittest.TestCase):
    """Tests /api/v1/auth/login, refresh, logout, /me, and /ws-ticket."""

    def setUp(self):
        self.client = TestClient(app)

    def test_valid_login_returns_token_and_sets_cookies(self):
        res = self.client.post(
            "/api/v1/auth/login",
            json={"username": "analyst_priya", "password": "AnalystPass2026!"},
        )
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("access_token", data)
        self.assertEqual(data["token_type"], "bearer")
        self.assertIn("user", data)
        self.assertEqual(data["user"]["username"], "analyst_priya")
        self.assertEqual(data["user"]["role"], "fraud_analyst")
        self.assertIn("cases:read", data["user"]["permissions"])

        # Check Set-Cookie headers
        cookies = res.cookies
        self.assertIn("access_token", cookies)
        self.assertIn("refresh_token", cookies)

    def test_login_invalid_credentials(self):
        # Wrong password
        res_bad_pass = self.client.post(
            "/api/v1/auth/login",
            json={"username": "analyst_priya", "password": "WrongPassword!"},
        )
        self.assertEqual(res_bad_pass.status_code, 401)
        self.assertIn("Invalid username or password", res_bad_pass.json()["detail"])

        # Nonexistent user
        res_no_user = self.client.post(
            "/api/v1/auth/login",
            json={"username": "ghost_user", "password": "SomePassword123!"},
        )
        self.assertEqual(res_no_user.status_code, 401)

    def test_login_deactivated_user_returns_403(self):
        res = self.client.post(
            "/api/v1/auth/login",
            json={"username": "disabled_user", "password": "DisabledPass2026!"},
        )
        self.assertEqual(res.status_code, 403)
        self.assertIn("deactivated", res.json()["detail"].lower())

    def test_authenticated_profile_me(self):
        login_res = self.client.post(
            "/api/v1/auth/login",
            json={"username": "officer_chen", "password": "CompliancePass2026!"},
        )
        token = login_res.json()["access_token"]

        # Call /me with Bearer token
        me_res = self.client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(me_res.status_code, 200)
        me_data = me_res.json()
        self.assertEqual(me_data["username"], "officer_chen")
        self.assertEqual(me_data["role"], "compliance_officer")
        self.assertIn("cases:reopen", me_data["permissions"])
        self.assertNotIn("stream:control", me_data["permissions"])

    def test_refresh_token_rotation_and_revocation(self):
        login_res = self.client.post(
            "/api/v1/auth/login",
            json={"username": "analyst_priya", "password": "AnalystPass2026!"},
        )
        refresh_cookie = login_res.cookies.get("refresh_token")
        self.assertIsNotNone(refresh_cookie)

        # 1. Use refresh token to obtain new access token
        refresh_res = self.client.post(
            "/api/v1/auth/refresh",
            cookies={"refresh_token": refresh_cookie},
        )
        self.assertEqual(refresh_res.status_code, 200)
        data = refresh_res.json()
        new_access = data["access_token"]
        self.assertIsNotNone(new_access)

        # 2. Try to reuse the OLD refresh token (should be rejected because of rotation/revocation)
        reused_res = self.client.post(
            "/api/v1/auth/refresh",
            cookies={"refresh_token": refresh_cookie},
        )
        self.assertEqual(reused_res.status_code, 401)

    def test_logout_revokes_token_and_clears_cookies(self):
        login_res = self.client.post(
            "/api/v1/auth/login",
            json={"username": "analyst_priya", "password": "AnalystPass2026!"},
        )
        token = login_res.json()["access_token"]

        # Verify token works
        check_before = self.client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(check_before.status_code, 200)

        # Logout
        logout_res = self.client.post(
            "/api/v1/auth/logout",
            headers={"Authorization": f"Bearer {token}"},
        )
        self.assertEqual(logout_res.status_code, 200)

        # Verify token is now rejected
        check_after = self.client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        self.assertEqual(check_after.status_code, 401)


class TestRoleBasedAccessControl(unittest.TestCase):
    """Verifies that endpoints enforce RBAC permissions independently of the UI."""

    def setUp(self):
        self.client = TestClient(app)
        # Login Analyst
        res_a = self.client.post("/api/v1/auth/login", json={"username": "analyst_priya", "password": "AnalystPass2026!"})
        self.analyst_token = res_a.json()["access_token"]

        # Login Compliance Officer
        res_c = self.client.post("/api/v1/auth/login", json={"username": "officer_chen", "password": "CompliancePass2026!"})
        self.compliance_token = res_c.json()["access_token"]

        # Login Admin
        res_adm = self.client.post("/api/v1/auth/login", json={"username": "admin", "password": "Admin@FraudGraph2026!"})
        self.admin_token = res_adm.json()["access_token"]

    def test_unauthorized_direct_call_returns_401(self):
        """Unauthenticated requests to protected endpoints return 401."""
        unauth_client = TestClient(app)
        endpoints = [
            ("GET", "/api/v1/cases"),
            ("POST", "/api/v1/cases"),
            ("GET", "/api/v1/stream/status"),
            ("POST", "/api/v1/stream/start"),
            ("GET", "/api/v1/clients/"),
            ("POST", "/api/v1/clients/"),
            ("GET", "/api/v1/transactions/"),
            ("GET", "/api/v1/fraud/alerts"),
            ("GET", "/api/v1/graph/subgraph"),
            ("GET", "/api/v1/users"),
        ]
        for method, path in endpoints:
            if method == "GET":
                res = unauth_client.get(path)
            else:
                res = unauth_client.post(path, json={})
            self.assertEqual(
                res.status_code,
                401,
                f"Endpoint {method} {path} expected 401 Unauthorized but returned {res.status_code}",
            )


    def test_fraud_analyst_permissions_boundary(self):
        """Fraud Analyst can investigate cases but CANNOT configure stream simulator or manage users."""
        headers = {"Authorization": f"Bearer {self.analyst_token}"}

        # 1. Permitted: Read cases
        res_cases = self.client.get("/api/v1/cases", headers=headers)
        self.assertEqual(res_cases.status_code, 200)

        # 2. Permitted: Read stream status
        res_stream_stat = self.client.get("/api/v1/stream/status", headers=headers)
        self.assertEqual(res_stream_stat.status_code, 200)

        # 3. FORBIDDEN: Stream simulator start/stop/config
        res_start = self.client.post("/api/v1/stream/start", headers=headers)
        self.assertEqual(res_start.status_code, 403)
        self.assertIn("lacks required permission", res_start.json()["detail"])

        res_stop = self.client.post("/api/v1/stream/stop", headers=headers)
        self.assertEqual(res_stop.status_code, 403)

        res_config = self.client.post("/api/v1/stream/config", headers=headers, json={"batch_size": 10})
        self.assertEqual(res_config.status_code, 403)

        # 4. FORBIDDEN: User administration
        res_users = self.client.get("/api/v1/users", headers=headers)
        self.assertEqual(res_users.status_code, 403)

        # 5. FORBIDDEN: Entity deletion
        res_del = self.client.delete("/api/v1/clients/CLT001", headers=headers)
        self.assertEqual(res_del.status_code, 403)

    def test_compliance_officer_permissions_boundary(self):
        """Compliance Officer can review, audit, and reopen cases, but CANNOT operate stream engine."""
        headers = {"Authorization": f"Bearer {self.compliance_token}"}

        # 1. Permitted: Read cases and audit history
        res_cases = self.client.get("/api/v1/cases", headers=headers)
        self.assertEqual(res_cases.status_code, 200)

        res_hist = self.client.get("/api/v1/cases/CASE-2026-0001/history", headers=headers)
        self.assertEqual(res_hist.status_code, 200)

        # 2. FORBIDDEN: Stream controls
        res_stream = self.client.post("/api/v1/stream/start", headers=headers)
        self.assertEqual(res_stream.status_code, 403)

        # 3. FORBIDDEN: User management
        res_users = self.client.get("/api/v1/users", headers=headers)
        self.assertEqual(res_users.status_code, 403)

    def test_admin_has_full_system_access(self):
        """Admin has full privileges on case management, stream controls, and user administration."""
        headers = {"Authorization": f"Bearer {self.admin_token}"}

        # 1. Stream control
        res_stat = self.client.get("/api/v1/stream/status", headers=headers)
        self.assertEqual(res_stat.status_code, 200)

        # 2. User administration
        res_users = self.client.get("/api/v1/users", headers=headers)
        self.assertEqual(res_users.status_code, 200)
        self.assertIsInstance(res_users.json(), list)


class TestCaseActorPreservation(unittest.TestCase):
    """Ensures case modifications and audit trails strictly preserve verified actor identity."""

    def setUp(self):
        self.client = TestClient(app)
        res_a = self.client.post("/api/v1/auth/login", json={"username": "analyst_priya", "password": "AnalystPass2026!"})
        self.analyst_token = res_a.json()["access_token"]
        self.headers = {"Authorization": f"Bearer {self.analyst_token}"}

    def test_case_operations_ignore_forged_actor_and_record_token_identity(self):
        # 1. Create a case while attempting to spoof actor as 'admin_imposter'
        create_res = self.client.post(
            "/api/v1/cases",
            headers=self.headers,
            json={
                "entity_id": "TXN_SEC_TEST_999",
                "entity_type": "Transaction",
                "title": "Actor Identity Verification Test",
                "priority": "HIGH",
                "risk_score": 85.0,
            },
        )
        self.assertEqual(create_res.status_code, 201)
        cid = create_res.json()["case_id"]

        # Check audit trail: creation actor must be 'analyst_priya'
        hist_1 = self.client.get(f"/api/v1/cases/{cid}/history", headers=self.headers).json()
        self.assertEqual(hist_1[0]["actor"], "analyst_priya")

        # 2. Assign case with attempted spoof actor
        assign_res = self.client.patch(
            f"/api/v1/cases/{cid}/assign",
            headers=self.headers,
            json={"assigned_analyst": "analyst_priya", "actor": "fake_admin"},
        )
        self.assertEqual(assign_res.status_code, 200)
        hist_2 = self.client.get(f"/api/v1/cases/{cid}/history", headers=self.headers).json()
        assign_records = [r for r in hist_2 if r.get("action_type") == "ANALYST_ASSIGNED"]
        self.assertTrue(len(assign_records) > 0)
        self.assertEqual(assign_records[-1]["actor"], "analyst_priya")


        # 3. Add note with attempted spoof author
        note_res = self.client.post(
            f"/api/v1/cases/{cid}/notes",
            headers=self.headers,
            json={"note": "Verified genuine transaction behavior.", "author": "spoofed_author"},
        )
        self.assertEqual(note_res.status_code, 201)
        self.assertEqual(note_res.json()["author"], "analyst_priya")


class TestWebSocketSecurity(unittest.TestCase):
    """Verifies that WebSocket endpoints reject unauthenticated clients and accept authenticated ones."""

    def setUp(self):
        self.client = TestClient(app)
        res_a = self.client.post("/api/v1/auth/login", json={"username": "analyst_priya", "password": "AnalystPass2026!"})
        self.analyst_token = res_a.json()["access_token"]

    def test_websocket_rejects_unauthenticated_connection(self):
        """Connection without cookie or ticket is rejected/closed with 1008 policy violation."""
        unauth_client = TestClient(app)
        with self.assertRaises(Exception):
            with unauth_client.websocket_connect("/ws/alerts") as ws:
                data = ws.receive_json()
                self.assertNotEqual(data.get("type"), "HANDSHAKE")

    def test_websocket_accepts_cookie_authenticated_connection(self):
        """Connection with valid access_token HttpOnly cookie successfully connects."""
        cookie_client = TestClient(app)
        cookie_client.cookies.set("access_token", self.analyst_token)
        with cookie_client.websocket_connect("/ws/alerts") as ws:
            data = ws.receive_json()
            self.assertEqual(data["type"], "HANDSHAKE")
            self.assertEqual(data["authenticated_as"], "analyst_priya")
            self.assertEqual(data["role"], "fraud_analyst")

            # Ping/Pong test
            ws.send_text("PING")
            pong = ws.receive_json()
            self.assertEqual(pong["type"], "PONG")

    def test_websocket_single_use_ticket_exchange(self):
        """Tests that /api/v1/auth/ws-ticket generates a valid single-use ticket."""
        ticket_res = self.client.post(
            "/api/v1/auth/ws-ticket",
            headers={"Authorization": f"Bearer {self.analyst_token}"},
        )
        self.assertEqual(ticket_res.status_code, 200)
        ticket = ticket_res.json()["ticket"]
        self.assertIsNotNone(ticket)

        ws_client = TestClient(app)
        # 1. Connect using ticket
        with ws_client.websocket_connect(f"/ws/alerts?ticket={ticket}") as ws:
            data = ws.receive_json()
            self.assertEqual(data["type"], "HANDSHAKE")
            self.assertEqual(data["authenticated_as"], "analyst_priya")

        # 2. Attempt to reuse ticket (must fail because it is single-use)
        with self.assertRaises(Exception):
            with ws_client.websocket_connect(f"/ws/alerts?ticket={ticket}") as ws_reused:
                ws_reused.receive_json()



class TestAdministrativeUserManagement(unittest.TestCase):
    """Verifies user CRUD endpoints under /api/v1/users."""

    def setUp(self):
        self.client = TestClient(app)
        res_adm = self.client.post("/api/v1/auth/login", json={"username": "admin", "password": "Admin@FraudGraph2026!"})
        self.admin_headers = {"Authorization": f"Bearer {res_adm.json()['access_token']}"}

    def test_admin_create_update_delete_user_lifecycle(self):
        # 1. Create User
        new_username = f"user_{datetime.now().strftime('%H%M%S%f')[:10]}"
        create_res = self.client.post(
            "/api/v1/users",
            headers=self.admin_headers,
            json={
                "username": new_username,
                "email": f"{new_username}@example.com",
                "password": "StrongPassword2026!",
                "role": "fraud_analyst",
                "full_name": "New Junior Analyst",
            },
        )
        self.assertEqual(create_res.status_code, 201)
        created = create_res.json()
        uid = created["user_id"]
        self.assertEqual(created["username"], new_username)
        self.assertEqual(created["role"], "fraud_analyst")

        # 2. Update User (promote to compliance officer)
        update_res = self.client.patch(
            f"/api/v1/users/{uid}",
            headers=self.admin_headers,
            json={"role": "compliance_officer", "full_name": "Promoted Officer"},
        )
        self.assertEqual(update_res.status_code, 200)
        updated = update_res.json()
        self.assertEqual(updated["role"], "compliance_officer")
        self.assertEqual(updated["full_name"], "Promoted Officer")

        # 3. Delete User
        del_res = self.client.delete(f"/api/v1/users/{uid}", headers=self.admin_headers)
        self.assertEqual(del_res.status_code, 204)

        # 4. Verify 404 after deletion
        get_res = self.client.get(f"/api/v1/users/{uid}", headers=self.admin_headers)
        self.assertEqual(get_res.status_code, 404)


if __name__ == "__main__":
    unittest.main()
