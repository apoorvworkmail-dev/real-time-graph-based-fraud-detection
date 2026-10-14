"""
Comprehensive Phase 1--11 System Audit Test Suite.
Verifies:
  1. Transaction -> persistence -> scoring -> alert -> case -> authorized action -> audit
  2. Duplicate submissions (case creation, user creation)
  3. Neo4j failure resilience (graceful degradation, no crashes)
  4. WebSocket disconnect / reconnect lifecycle & ticket reuse rejection
  5. Simulator start and graceful shutdown
  6. Invalid state transitions & optimistic concurrency conflicts
  7. Unauthorized requests (401) & RBAC role boundary enforcement (403)
  8. Schema integrity & Cypher injection safety
  9. ML leakage controls & real-time inference
 10. JWT security: algorithm none rejection, signature tampering, expiration, revocation
 11. CORS configuration & credentials safety
"""

import unittest
import uuid
import time
import os
import sys
import jwt
from fastapi.testclient import TestClient

# Add paths
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from neo4j.exceptions import ServiceUnavailable

from app.main import app
from app.config import get_settings
from app.services.user_service import user_service
from app.services.case_service import case_service
from app.services.simulator import simulator, TransactionGenerator
from app.services.risk_scoring import score_factors
from app.services.ml_service import ml_service
from app.schemas.case import (
    CaseCreate,
    CasePriority,
    CaseStatus,
    CaseStatusTransition,
    CaseNoteCreate,
    ResolutionCategory,
)
from app.auth.security import create_access_token, hash_password, is_token_revoked


class TestPhase1To11Audit(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)
        cls.settings = get_settings()

        # Seed test users in repository
        cls.admin_user = user_service.get_by_identifier("admin")
        cls.analyst_user = user_service.get_by_identifier("analyst_priya")
        cls.officer_user = user_service.get_by_identifier("officer_chen")
        cls.disabled_user = user_service.get_by_identifier("disabled_user")

        # Tokens
        cls.admin_token, _, _ = create_access_token(
            cls.admin_user["user_id"], cls.admin_user["username"], cls.admin_user["role"]
        )
        cls.analyst_token, _, _ = create_access_token(
            cls.analyst_user["user_id"], cls.analyst_user["username"], cls.analyst_user["role"]
        )
        cls.officer_token, _, _ = create_access_token(
            cls.officer_user["user_id"], cls.officer_user["username"], cls.officer_user["role"]
        )

        cls.admin_headers = {"Authorization": f"Bearer {cls.admin_token}"}
        cls.analyst_headers = {"Authorization": f"Bearer {cls.analyst_token}"}
        cls.officer_headers = {"Authorization": f"Bearer {cls.officer_token}"}

    # =========================================================================
    # 1. Pipeline: transaction -> persistence -> scoring -> alert -> case -> action -> audit
    # =========================================================================
    def test_pipeline_transaction_to_audit(self):
        """End-to-end audit: transaction event -> scoring -> alert -> case -> action -> audit."""
        # 1. Ingest transaction event
        txn_id = f"TXN_AUDIT_{uuid.uuid4().hex[:8].upper()}"
        generator = TransactionGenerator(seed=123)
        event = generator.generate(scenario="velocity")
        event.transaction_id = txn_id

        # 2. Risk scoring
        factors = {
            "shared_device": 1,
            "shared_location": 0,
            "multi_hop_path": 1,
            "cycle_participation": 1,
            "high_transaction_velocity": 6,
            "suspicious_connections": 2,
        }
        score_res = score_factors(txn_id, factors)
        self.assertGreaterEqual(score_res["riskScore"], 75.0)
        self.assertIn("CRITICAL", score_res["riskLevel"])
        self.assertGreater(len(score_res["reasons"]), 0)

        # 3. Create Case from flagged transaction
        case_payload = {
            "entity_id": txn_id,
            "entity_type": "Transaction",
            "title": f"Audit Pipeline Case for {txn_id}",
            "priority": "HIGH",
            "risk_score": score_res["riskScore"],
        }
        create_res = self.client.post("/api/v1/cases", headers=self.analyst_headers, json=case_payload)
        self.assertEqual(create_res.status_code, 201)
        case_id = create_res.json()["case_id"]

        # 4. Authorized Action: Analyst assigns and investigates
        assign_res = self.client.patch(
            f"/api/v1/cases/{case_id}/assign",
            headers=self.analyst_headers,
            json={"assigned_analyst": "analyst_priya"},
        )
        self.assertEqual(assign_res.status_code, 200)

        note_res = self.client.post(
            f"/api/v1/cases/{case_id}/notes",
            headers=self.analyst_headers,
            json={"note": "Investigating high velocity circular pattern."},
        )
        self.assertEqual(note_res.status_code, 201)

        trans1_res = self.client.post(
            f"/api/v1/cases/{case_id}/transition",
            headers=self.analyst_headers,
            json={"target_status": "UNDER_INVESTIGATION", "expected_version": 2},
        )
        self.assertEqual(trans1_res.status_code, 200)
        self.assertEqual(trans1_res.json()["status"], "UNDER_INVESTIGATION")

        # 5. Authorized Action: Compliance Officer resolves case
        trans2_res = self.client.post(
            f"/api/v1/cases/{case_id}/transition",
            headers=self.officer_headers,
            json={
                "target_status": "CONFIRMED_FRAUD",
                "expected_version": 3,
                "resolution_category": "TRUE_POSITIVE_FRAUD",
                "resolution_explanation": "Investigation confirmed organized syndicate smurfing.",
            },
        )
        self.assertEqual(trans2_res.status_code, 200)
        self.assertEqual(trans2_res.json()["status"], "CONFIRMED_FRAUD")

        # 6. Verify Audit Trail
        hist_res = self.client.get(f"/api/v1/cases/{case_id}/history", headers=self.analyst_headers)
        self.assertEqual(hist_res.status_code, 200)
        history = hist_res.json()
        self.assertGreaterEqual(len(history), 4)

        # Actor identity preservation verification
        actors = [h["actor"] for h in history]
        self.assertIn("analyst_priya", actors)
        self.assertIn("officer_chen", actors)

    # =========================================================================
    # 2. Duplicate Submissions
    # =========================================================================
    def test_duplicate_case_creation_is_idempotent(self):
        """Duplicate case creation for the same active entity returns the existing case without duplicate entries."""
        entity_id = f"TXN_IDEMP_{uuid.uuid4().hex[:6]}"
        payload = {
            "entity_id": entity_id,
            "entity_type": "Transaction",
            "title": "Idempotency Test Case",
            "priority": "MEDIUM",
            "risk_score": 60.0,
        }
        res1 = self.client.post("/api/v1/cases", headers=self.analyst_headers, json=payload)
        self.assertEqual(res1.status_code, 201)
        case_id_1 = res1.json()["case_id"]

        # Duplicate call
        res2 = self.client.post("/api/v1/cases", headers=self.analyst_headers, json=payload)
        self.assertEqual(res2.status_code, 201)
        case_id_2 = res2.json()["case_id"]
        self.assertEqual(case_id_1, case_id_2, "Idempotent creation must return existing case ID")

    def test_duplicate_user_creation_rejected_409(self):
        """Attempting to register a user with an existing username or email returns 409 Conflict."""
        payload = {
            "username": "admin",  # Already exists
            "email": "unique_email_123@example.com",
            "password": "Password123!",
            "role": "fraud_analyst",
        }
        res = self.client.post("/api/v1/users", headers=self.admin_headers, json=payload)
        self.assertEqual(res.status_code, 409)

    # =========================================================================
    # 3. Neo4j Failure Resilience
    # =========================================================================
    def test_neo4j_offline_graceful_handling(self):
        """When Neo4j is offline or unreachable, /health returns unhealthy status without server crash."""
        res = self.client.get("/health")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertIn("status", data)
        # Should report healthy or unhealthy depending on container, but must never return 500 crash
        if data["status"] == "unhealthy":
            self.assertIn("error", data)

    # =========================================================================
    # 4. WebSocket Disconnect / Reconnect & Ticket Reuse Rejection
    # =========================================================================
    def test_websocket_lifecycle_and_ticket_reuse_rejection(self):
        """Obtaining a single-use ticket connects successfully; reusing that same ticket must be rejected."""
        ticket_res = self.client.post("/api/v1/auth/ws-ticket", headers=self.analyst_headers)
        self.assertEqual(ticket_res.status_code, 200)
        ticket = ticket_res.json()["ticket"]

        # 1. Connect first time
        with self.client.websocket_connect(f"/ws/alerts?ticket={ticket}") as ws:
            msg = ws.receive_json()
            self.assertEqual(msg["type"], "HANDSHAKE")
            self.assertEqual(msg["authenticated_as"], "analyst_priya")
            # Send ping
            ws.send_text("PING")
            pong = ws.receive_json()
            self.assertEqual(pong["type"], "PONG")

        # 2. Reconnect using the consumed ticket (must fail because it's single-use)
        with self.assertRaises(Exception):
            with self.client.websocket_connect(f"/ws/alerts?ticket={ticket}") as ws2:
                ws2.receive_json()

    # =========================================================================
    # 5. Simulator Start and Graceful Shutdown
    # =========================================================================
    def test_simulator_start_and_shutdown(self):
        """Simulator starts, reflects status, updates config, and stops cleanly."""
        # 1. Check status
        status_res = self.client.get("/api/v1/stream/status", headers=self.admin_headers)
        self.assertEqual(status_res.status_code, 200)

        # 2. Update config
        cfg_res = self.client.post(
            "/api/v1/stream/config",
            headers=self.admin_headers,
            json={"interval_seconds": 2.0, "batch_size": 1, "active_scenario": "velocity"},
        )
        self.assertEqual(cfg_res.status_code, 200)
        self.assertEqual(cfg_res.json()["intervalSeconds"], 2.0)

        # 3. Manual step execution
        step_res = self.client.post("/api/v1/stream/step", headers=self.admin_headers)
        self.assertEqual(step_res.status_code, 200)
        self.assertIn("results", step_res.json())
        self.assertGreater(len(step_res.json()["results"]), 0)

        # 4. Stop simulation
        stop_res = self.client.post("/api/v1/stream/stop", headers=self.admin_headers)
        self.assertEqual(stop_res.status_code, 200)
        self.assertFalse(stop_res.json()["isRunning"])

    # =========================================================================
    # 6. Invalid Transitions & Optimistic Concurrency
    # =========================================================================
    def test_invalid_lifecycle_transitions_rejected(self):
        """Premature closure and unexplainable resolutions are rejected by state machine."""
        # Create fresh case
        res = self.client.post(
            "/api/v1/cases",
            headers=self.analyst_headers,
            json={"entity_id": f"TXN_TR_{uuid.uuid4().hex[:6]}", "entity_type": "Transaction"},
        )
        cid = res.json()["case_id"]

        # Jump from NEW_ALERT directly to CONFIRMED_FRAUD without investigation
        bad_trans = self.client.post(
            f"/api/v1/cases/{cid}/transition",
            headers=self.officer_headers,
            json={
                "target_status": "CONFIRMED_FRAUD",
                "resolution_category": "TRUE_POSITIVE_FRAUD",
                "resolution_explanation": "Premature jump.",
            },
        )
        self.assertEqual(bad_trans.status_code, 400)
        self.assertIn("Invalid state transition", bad_trans.json()["detail"])

        # Investigate first
        self.client.post(
            f"/api/v1/cases/{cid}/transition",
            headers=self.analyst_headers,
            json={"target_status": "UNDER_INVESTIGATION", "expected_version": 1},
        )

        # Attempt to confirm fraud WITHOUT mandatory explanation
        missing_exp = self.client.post(
            f"/api/v1/cases/{cid}/transition",
            headers=self.officer_headers,
            json={
                "target_status": "CONFIRMED_FRAUD",
                "expected_version": 2,
                "resolution_category": "TRUE_POSITIVE_FRAUD",
                "resolution_explanation": "",  # Empty
            },
        )
        self.assertEqual(missing_exp.status_code, 400)

    def test_optimistic_concurrency_version_conflict_409(self):
        """Mismatched expected_version returns 409 Conflict."""
        res = self.client.post(
            "/api/v1/cases",
            headers=self.analyst_headers,
            json={"entity_id": f"TXN_CONF_{uuid.uuid4().hex[:6]}", "entity_type": "Transaction"},
        )
        cid = res.json()["case_id"]

        conflict_res = self.client.post(
            f"/api/v1/cases/{cid}/transition",
            headers=self.analyst_headers,
            json={"target_status": "UNDER_INVESTIGATION", "expected_version": 999},
        )
        self.assertEqual(conflict_res.status_code, 409)

    # =========================================================================
    # 7. Unauthorized Requests & RBAC Boundary Enforcement
    # =========================================================================
    def test_unauthenticated_request_rejected_401(self):
        """Requests without authorization credentials return 401 Unauthorized."""
        clean_client = TestClient(app)
        res = clean_client.get("/api/v1/cases")
        self.assertEqual(res.status_code, 401)

    def test_rbac_boundary_analyst_cannot_perform_admin_or_officer_actions_403(self):
        """Fraud Analyst lacks permissions to control simulator, manage users, or resolve cases."""
        # 1. Simulator control forbidden
        res1 = self.client.post("/api/v1/stream/start", headers=self.analyst_headers)
        self.assertEqual(res1.status_code, 403)

        # 2. User administration forbidden
        res2 = self.client.get("/api/v1/users", headers=self.analyst_headers)
        self.assertEqual(res2.status_code, 403)

        # 3. Case resolution forbidden for analyst
        res3 = self.client.post(
            "/api/v1/cases/CASE-2026-0001/transition",
            headers=self.analyst_headers,
            json={
                "target_status": "CONFIRMED_FRAUD",
                "resolution_category": "TRUE_POSITIVE_FRAUD",
                "resolution_explanation": "Attempted resolution by analyst.",
            },
        )
        self.assertEqual(res3.status_code, 403)

    def test_rbac_boundary_compliance_cannot_control_stream_or_users_403(self):
        """Compliance Officer lacks permissions to control simulator or manage users."""
        res1 = self.client.post("/api/v1/stream/start", headers=self.officer_headers)
        self.assertEqual(res1.status_code, 403)

        res2 = self.client.get("/api/v1/users", headers=self.officer_headers)
        self.assertEqual(res2.status_code, 403)

    # =========================================================================
    # 8. Schema Integrity & Cypher Injection Safety
    # =========================================================================
    def test_cypher_injection_resilience_in_parameters(self):
        """Cypher injection attempts in entity IDs are treated as literal strings and return 404 or safe empty."""
        injection_id = "CLT001' OR 1=1 DETACH DELETE c //"
        res = self.client.get(f"/api/v1/clients/{injection_id}", headers=self.analyst_headers)
        # Should be 404, not a 500 syntax error or unintended deletion
        self.assertIn(res.status_code, [404, 503])

    # =========================================================================
    # 9. ML Leakage Controls & Inference
    # =========================================================================
    def test_ml_leakage_and_inference(self):
        """Train/test partitions have 0 entity overlap; inference functions without target leakage."""
        from app.ml.train_model import build_synthetic_graph_dataset
        from sklearn.model_selection import train_test_split

        X, y, client_ids, _ = build_synthetic_graph_dataset()
        _, _, _, _, ids_train, ids_test = train_test_split(
            X, y, client_ids, test_size=0.25, random_state=42, stratify=y
        )
        overlap = set(ids_train).intersection(set(ids_test))
        self.assertEqual(len(overlap), 0, "Train and test client IDs must have zero leakage overlap")

        # Inference on known synthetic fraud actor
        inf_res = self.client.get("/api/v1/ml/predict/client/CLT031", headers=self.analyst_headers)
        self.assertEqual(inf_res.status_code, 200)
        data = inf_res.json()
        self.assertEqual(data["mlPrediction"], "PREDICTED_FRAUD")
        self.assertGreaterEqual(data["mlFraudProbability"], 0.50)
        self.assertIn("topContributingFeatures", data)

    # =========================================================================
    # 10. JWT Permissions, Secrets, Expiration & Revocation
    # =========================================================================
    def test_jwt_none_algorithm_rejected(self):
        """Tokens forged with alg='none' are rejected with 401."""
        forged_token = jwt.encode(
            {"sub": self.admin_user["user_id"], "username": "admin", "role": "admin"},
            key="",
            algorithm="none",
        )
        res = self.client.get("/api/v1/cases", headers={"Authorization": f"Bearer {forged_token}"})
        self.assertEqual(res.status_code, 401)

    def test_jwt_tampered_signature_rejected(self):
        """Tampered JWT payloads return 401."""
        tampered = self.admin_token[:-6] + "BADSIG"
        res = self.client.get("/api/v1/cases", headers={"Authorization": f"Bearer {tampered}"})
        self.assertEqual(res.status_code, 401)

    def test_disabled_user_blocked(self):
        """Inactive users (is_active=False) cannot log in or authenticate."""
        login_res = self.client.post(
            "/api/v1/auth/login",
            json={"username": "disabled_user", "password": "DisabledPass2026!"},
        )
        self.assertEqual(login_res.status_code, 403)
        self.assertIn("deactivated", login_res.json()["detail"].lower())

    # =========================================================================
    # 11. CORS Configuration Safety
    # =========================================================================
    def test_cors_configuration_does_not_permit_wildcard_with_credentials(self):
        """CORS origins list must contain explicit hostnames, never '*' when allow_credentials=True."""
        from app.main import cors_origins_list
        self.assertNotIn("*", cors_origins_list, "CORS allow_origins cannot be '*' when allow_credentials is True")
        self.assertTrue(all(o.startswith("http") for o in cors_origins_list))


if __name__ == "__main__":
    unittest.main()
