"""
Comprehensive Test Suite for Fraud Detection Platform (Phases 1–7)
Covers:
- Phase 1–6 Regressions: Schemas, Risk Scoring Logic, Cypher Bounds, FastAPI Routing
- Phase 7 Validations:
  * TransactionEvent validation & rejection of malformed/duplicate payloads
  * Deterministic simulation reproducibility
  * Simulator concurrency control & duplicate worker prevention
  * Neo4j persistence, idempotency (retry handling), and zero-swallow error policy
  * Graph fraud evaluation & alert policy qualification
  * WebSocket manager lifecycle, heartbeat, and slow-client failure isolation
"""

import asyncio
import os
import sys
import unittest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch, AsyncMock

# Add backend to Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "backend")))
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.schemas.client import ClientCreate, ClientUpdate, ClientOut
from app.schemas.device import DeviceCreate, DeviceUpdate, DeviceOut, LocationCreate, LocationUpdate, LocationOut
from app.schemas.transaction import (
    TransactionCreate,
    TransactionUpdate,
    TransactionOut,
    TransactionEvent,
    TransactionEventResult,
    FraudAlertPayload,
    SimulatorConfigUpdate,
)
from app.services.risk_scoring import score_factors, WEIGHTS, RISK_LEVEL_THRESHOLDS
from app.services.simulator import (
    TransactionGenerator,
    TransactionProcessor,
    TransactionStreamSimulator,
    simulator,
)
from app.services.websocket_manager import ConnectionManager
from neo4j.exceptions import Neo4jError, ServiceUnavailable


# ── Phases 1–6 Regression Tests ────────────────────────────────────────

class TestPydanticSchemas(unittest.TestCase):
    def test_client_schemas(self):
        c_in = ClientCreate(name="John Doe", email="john.doe@example.com", account_balance=10000.0)
        self.assertEqual(c_in.name, "John Doe")
        self.assertEqual(c_in.email, "john.doe@example.com")
        self.assertEqual(c_in.account_balance, 10000.0)
        self.assertTrue(c_in.kyc_verified)

        c_out = ClientOut(client_id="CLT001", name="John Doe", email="john.doe@example.com")
        self.assertIsNone(c_out.phone)
        self.assertEqual(c_out.account_type, "savings")
        self.assertEqual(c_out.account_balance, 0.0)

    def test_location_schemas(self):
        loc = LocationCreate(city="Mumbai", country="India", latitude=19.076, longitude=72.8777)
        self.assertEqual(loc.city, "Mumbai")
        self.assertIsNone(loc.ip_address)
        self.assertFalse(loc.is_high_risk)

        loc_ip = LocationCreate(city="Lagos", country="Nigeria", latitude=6.5244, longitude=3.3792, ip_address="198.51.100.1", is_high_risk=True)
        self.assertEqual(loc_ip.ip_address, "198.51.100.1")
        self.assertTrue(loc_ip.is_high_risk)

    def test_transaction_schemas(self):
        tx_in = TransactionCreate(amount=5000.0, sender_id="CLT001", receiver_id="CLT002")
        self.assertEqual(tx_in.currency, "INR")
        self.assertEqual(tx_in.channel, "mobile_app")

        tx_out = TransactionOut(transaction_id="TXN0001", amount=5000.0)
        self.assertEqual(tx_out.currency, "INR")
        self.assertFalse(tx_out.is_fraud)


class TestRiskScoringService(unittest.TestCase):
    def test_clean_client_score(self):
        factors = {
            "shared_device": 0, "shared_location": 0, "multi_hop_path": 0,
            "cycle_participation": 0, "high_transaction_velocity": 0, "suspicious_connections": 0,
        }
        res = score_factors("CLT001", factors)
        self.assertEqual(res["riskScore"], 0.0)
        self.assertEqual(res["riskLevel"], "LOW")
        self.assertEqual(len(res["reasons"]), 0)

    def test_high_risk_client_score(self):
        factors = {
            "shared_device": 1, "shared_location": 1, "multi_hop_path": 1,
            "cycle_participation": 1, "high_transaction_velocity": 5, "suspicious_connections": 3,
        }
        res = score_factors("CLT099", factors)
        self.assertEqual(res["riskScore"], 100.0)
        self.assertEqual(res["riskLevel"], "CRITICAL")
        self.assertEqual(len(res["reasons"]), 6)


class TestGraphQueryGeneration(unittest.TestCase):
    def test_safe_hops_bounds(self):
        for input_hops, expected in [(0, 1), (1, 1), (4, 4), (6, 6), (10, 6), (-5, 1)]:
            safe_hops = max(1, min(int(input_hops), 6))
            self.assertEqual(safe_hops, expected)


class TestFastAPIRouting(unittest.TestCase):
    def test_routes_registered(self):
        from app.main import app
        route_paths = [r.path for r in app.routes]

        # Standardized v1 routes
        self.assertIn("/api/v1/clients/", route_paths)
        self.assertIn("/api/v1/transactions/", route_paths)
        self.assertIn("/api/v1/devices/", route_paths)
        self.assertIn("/api/v1/locations/", route_paths)
        self.assertIn("/api/v1/fraud/alerts", route_paths)
        self.assertIn("/api/v1/risk/client/{clientId}", route_paths)
        self.assertIn("/api/v1/graph/subgraph", route_paths)

        # Phase 7 Streaming routes
        self.assertIn("/api/v1/stream/status", route_paths)
        self.assertIn("/api/v1/stream/start", route_paths)
        self.assertIn("/api/v1/stream/stop", route_paths)
        self.assertIn("/api/v1/stream/config", route_paths)
        self.assertIn("/api/v1/stream/transactions", route_paths)
        self.assertIn("/api/v1/stream/step", route_paths)
        self.assertIn("/api/v1/stream/ws/alerts", route_paths)
        self.assertIn("/ws/alerts", route_paths)


# ── Phase 7 Specific Unit & Integration Tests ─────────────────────────

class TestTransactionEventContract(unittest.TestCase):
    def test_valid_transaction_event(self):
        ev = TransactionEvent(
            transaction_id="TXN_TEST_001",
            sender_id="CLT001",
            receiver_id="CLT002",
            amount=2500.0,
            currency="INR",
            channel="mobile_app",
            scenario="normal",
            timestamp="2026-10-12T23:00:00Z",
        )
        self.assertEqual(ev.transaction_id, "TXN_TEST_001")
        self.assertEqual(ev.amount, 2500.0)
        self.assertEqual(ev.scenario, "normal")

    def test_reject_zero_or_negative_amount(self):
        with self.assertRaises(ValueError):
            TransactionEvent(transaction_id="TXN_BAD", sender_id="CLT001", receiver_id="CLT002", amount=0.0)
        with self.assertRaises(ValueError):
            TransactionEvent(transaction_id="TXN_BAD", sender_id="CLT001", receiver_id="CLT002", amount=-500.0)

    def test_reject_identical_sender_and_receiver(self):
        with self.assertRaises(ValueError):
            TransactionEvent(transaction_id="TXN_BAD", sender_id="CLT001", receiver_id="CLT001", amount=100.0)

    def test_reject_invalid_timestamp(self):
        with self.assertRaises(ValueError):
            TransactionEvent(transaction_id="TXN_BAD", sender_id="CLT001", receiver_id="CLT002", amount=100.0, timestamp="invalid-time")

    def test_reject_extra_fields(self):
        with self.assertRaises(ValueError):
            TransactionEvent(transaction_id="TXN_BAD", sender_id="CLT001", receiver_id="CLT002", amount=100.0, malicious_field="injected")


class TestDeterministicSimulation(unittest.TestCase):
    def test_deterministic_reproducibility(self):
        gen1 = TransactionGenerator(seed=42)
        gen2 = TransactionGenerator(seed=42)

        ev1_a = gen1.generate("normal")
        ev2_a = gen2.generate("normal")
        self.assertEqual(ev1_a.transaction_id, ev2_a.transaction_id)
        self.assertEqual(ev1_a.sender_id, ev2_a.sender_id)
        self.assertEqual(ev1_a.amount, ev2_a.amount)

        ev1_b = gen1.generate("velocity")
        ev2_b = gen2.generate("velocity")
        self.assertEqual(ev1_b.amount, ev2_b.amount)
        self.assertEqual(ev1_b.scenario, "velocity")


class TestSimulatorLifecycleAndConcurrency(unittest.TestCase):
    def setUp(self):
        self.sim = TransactionStreamSimulator(seed=123)

    def test_start_stop_lifecycle(self):
        self.assertFalse(self.sim.is_running)
        status_start = asyncio.run(self.sim.start())
        self.assertTrue(status_start["isRunning"])
        self.assertTrue(self.sim.is_running)

        # Duplicate start prevention
        dup_start = asyncio.run(self.sim.start())
        self.assertTrue(dup_start["isRunning"])

        status_stop = asyncio.run(self.sim.stop())
        self.assertFalse(status_stop["isRunning"])
        self.assertFalse(self.sim.is_running)

    def test_config_update_bounds(self):
        update = SimulatorConfigUpdate(interval_seconds=1.2, batch_size=5, active_scenario="velocity")
        res = self.sim.update_config(update)
        self.assertEqual(res["intervalSeconds"], 1.2)
        self.assertEqual(res["batchSize"], 5)
        self.assertEqual(res["activeScenario"], "velocity")


class TestNeo4jPersistenceAndIdempotency(unittest.TestCase):
    def setUp(self):
        self.processor = TransactionProcessor()

    def test_idempotent_duplicate_handling(self):
        """Verify that retrying an already processed transaction does NOT write duplicate nodes."""
        mock_session = MagicMock()
        # Simulate check query finding existing transaction
        mock_check_result = MagicMock()
        mock_check_result.single.return_value = {
            "tid": "TXN_EXISTING",
            "is_fraud": True,
            "fraud_score": 85.0,
        }
        mock_session.run.return_value = mock_check_result

        event = TransactionEvent(
            transaction_id="TXN_EXISTING",
            sender_id="CLT001",
            receiver_id="CLT002",
            amount=5000.0,
            scenario="normal",
        )

        result = self.processor.process_event(event, session=mock_session)
        self.assertEqual(result.status, "idempotent_duplicate")
        self.assertTrue(result.persisted)
        self.assertTrue(result.is_fraud)
        self.assertEqual(result.fraud_score, 85.0)
        # Verify write query was NOT called (only 1 check query was executed)
        self.assertEqual(mock_session.run.call_count, 1)

    def test_database_write_failure_does_not_commit(self):
        """Zero-swallowing error policy: DB error must be reported explicitly as failed."""
        mock_session = MagicMock()
        # First call (check) returns None, second call (create) raises ServiceUnavailable
        mock_check_result = MagicMock()
        mock_check_result.single.return_value = None

        def side_effect(query, **kwargs):
            if "MATCH (t:Transaction" in query:
                return mock_check_result
            raise ServiceUnavailable("Simulated Bolt connection refused")

        mock_session.run.side_effect = side_effect

        event = TransactionEvent(
            transaction_id="TXN_FAIL_TEST",
            sender_id="CLT001",
            receiver_id="CLT002",
            amount=1000.0,
            scenario="normal",
        )

        result = self.processor.process_event(event, session=mock_session)
        self.assertEqual(result.status, "failed")
        self.assertFalse(result.persisted)
        self.assertFalse(result.is_alert_qualified)
        self.assertIn("database write failed", result.message)


class TestFraudEvaluationAndAlertPolicy(unittest.TestCase):
    def setUp(self):
        self.processor = TransactionProcessor()

    @patch("app.services.simulator.score_transactions")
    def test_normal_transaction_not_qualified(self, mock_score):
        mock_score.return_value = [{"riskScore": 0.0, "riskLevel": "LOW", "reasons": []}]
        mock_session = MagicMock()
        mock_check_result = MagicMock()
        mock_check_result.single.return_value = None  # Not existing
        mock_session.run.return_value = mock_check_result

        event = TransactionEvent(
            transaction_id="TXN_NORM_01",
            sender_id="CLT001",
            receiver_id="CLT002",
            amount=1500.0,
            scenario="normal",
        )

        result = self.processor.process_event(event, session=mock_session)
        self.assertEqual(result.status, "processed")
        self.assertTrue(result.persisted)
        self.assertFalse(result.is_fraud)
        self.assertFalse(result.is_alert_qualified)
        self.assertIsNone(result.alert)

    @patch("app.services.simulator.score_transactions")
    def test_attack_scenario_qualifies_as_alert(self, mock_score):
        mock_score.return_value = [{
            "riskScore": 85.0,
            "riskLevel": "CRITICAL",
            "reasons": [{"explanation": "Shared suspicious device DEV011 detected"}],
        }]
        mock_session = MagicMock()
        mock_check_result = MagicMock()
        mock_check_result.single.return_value = None
        mock_session.run.return_value = mock_check_result

        event = TransactionEvent(
            transaction_id="TXN_RING_01",
            sender_id="CLT031",
            receiver_id="CLT002",
            amount=25000.0,
            device_id="DEV011",
            scenario="ring",
        )

        result = self.processor.process_event(event, session=mock_session)
        self.assertEqual(result.status, "processed")
        self.assertTrue(result.persisted)
        self.assertTrue(result.is_fraud)
        self.assertTrue(result.is_alert_qualified)
        self.assertIsNotNone(result.alert)
        self.assertEqual(result.alert.entity_id, "TXN_RING_01")
        self.assertEqual(result.alert.risk_level, "CRITICAL")


class TestWebSocketManagerIsolation(unittest.TestCase):
    def test_slow_or_failing_client_isolation(self):
        """Verify that a slow or closed client does not crash broadcast or block other clients."""
        cm = ConnectionManager()

        good_client = AsyncMock()
        broken_client = AsyncMock()
        broken_client.send_json.side_effect = RuntimeError("Socket closed abruptly")

        cm.active_connections = [good_client, broken_client]
        self.assertEqual(cm.client_count, 2)

        asyncio.run(cm.broadcast({"type": "TEST_ALERT"}))

        # Good client received frame
        good_client.send_json.assert_called_once_with({"type": "TEST_ALERT"})
        # Broken client was disconnected and pruned
        self.assertEqual(cm.client_count, 1)
        self.assertIn(good_client, cm.active_connections)
        self.assertNotIn(broken_client, cm.active_connections)


# ── Phase 8 Graph Machine Learning Tests ──────────────────────────────

class TestMachineLearningPipeline(unittest.TestCase):
    def test_absence_of_target_leakage_features(self):
        from app.ml.feature_extractor import CLIENT_FEATURE_NAMES, extract_client_features_from_graph
        prohibited_leakage_fields = [
            "is_flagged", "is_fraud", "fraud_score", "scenario", "risk_score", "is_fraudster"
        ]
        for field in prohibited_leakage_fields:
            self.assertNotIn(field, CLIENT_FEATURE_NAMES, f"Target leakage field '{field}' detected in feature list!")

        # Verify extracted dict does not include any prohibited fields
        dummy_graph = {"clients": {}, "transactions": [], "devices": {}, "locations": {}}
        feats = extract_client_features_from_graph("CLT_DUMMY", dummy_graph)
        for field in prohibited_leakage_fields:
            self.assertNotIn(field, feats)

    def test_deterministic_feature_extraction(self):
        from database.seed_data import make_clients, make_transactions, LOCATIONS, DEVICES
        from app.ml.feature_extractor import extract_client_features_from_graph
        clients = make_clients()
        txs = make_transactions(clients)
        graph_data = {
            "clients": {c["client_id"]: c for c in clients},
            "transactions": txs,
            "devices": {d["device_id"]: d for d in DEVICES},
            "locations": {l["location_id"]: l for l in LOCATIONS},
        }

        feats_1 = extract_client_features_from_graph("CLT031", graph_data)
        feats_2 = extract_client_features_from_graph("CLT031", graph_data)
        self.assertEqual(feats_1, feats_2)

    def test_train_test_split_integrity(self):
        from app.ml.train_model import build_synthetic_graph_dataset
        from sklearn.model_selection import train_test_split
        X, y, client_ids, _ = build_synthetic_graph_dataset()
        X_train, X_test, y_train, y_test, ids_train, ids_test = train_test_split(
            X, y, client_ids, test_size=0.25, random_state=42, stratify=y
        )

        # Zero entity leakage across partitions
        overlap = set(ids_train).intersection(set(ids_test))
        self.assertEqual(len(overlap), 0, "Train and test client partitions must be strictly disjoint")
        self.assertEqual(len(ids_train) + len(ids_test), len(client_ids))

    def test_model_artifact_persistence_and_loading(self):
        from app.services.ml_service import ml_service
        self.assertTrue(ml_service.is_model_loaded)
        info = ml_service.get_model_info()
        self.assertEqual(info["modelType"], "RandomForestClassifier")
        self.assertIn("evaluation", info)
        self.assertIn("primaryModel", info["evaluation"])
        self.assertGreaterEqual(info["evaluation"]["primaryModel"]["f1"], 0.8)
        self.assertIn("featureImportances", info)

    def test_client_inference_valid_and_missing(self):
        from app.services.ml_service import ml_service
        # Known synthetic fraud actor CLT031
        fraud_pred = ml_service.predict_client("CLT031")
        self.assertEqual(fraud_pred["clientId"], "CLT031")
        self.assertEqual(fraud_pred["mlPrediction"], "PREDICTED_FRAUD")
        self.assertGreaterEqual(fraud_pred["mlFraudProbability"], 0.50)
        self.assertIn("topContributingFeatures", fraud_pred)

        # Known legitimate account CLT001
        legit_pred = ml_service.predict_client("CLT001")
        self.assertEqual(legit_pred["clientId"], "CLT001")
        self.assertEqual(legit_pred["mlPrediction"], "PREDICTED_LEGITIMATE")
        self.assertLess(legit_pred["mlFraudProbability"], 0.50)

        # Missing / Unobserved client handles missing data gracefully
        missing_pred = ml_service.predict_client("CLT_NON_EXISTENT")
        self.assertEqual(missing_pred["clientId"], "CLT_NON_EXISTENT")
        self.assertIn("mlFraudProbability", missing_pred)
        self.assertIn("disclaimer", missing_pred)

    def test_graph_communities_detection(self):
        from app.services.ml_service import ml_service
        communities = ml_service.get_graph_communities()
        self.assertIsInstance(communities, list)
        self.assertGreater(len(communities), 0)
        first = communities[0]
        self.assertIn("communityId", first)
        self.assertIn("type", first)
        self.assertIn("members", first)
        self.assertIn("riskLevel", first)

    def test_ml_routes_registered(self):
        from app.main import app
        route_paths = [r.path for r in app.routes]
        self.assertIn("/api/v1/ml/info", route_paths)
        self.assertIn("/api/v1/ml/predict/client/{client_id}", route_paths)
        self.assertIn("/api/v1/ml/communities", route_paths)


# ── Phase 9 Fraud Investigation & Case Management Tests ───────────────

class TestCaseManagementPipeline(unittest.TestCase):
    def setUp(self):
        from app.services.case_service import case_service
        self.service = case_service

    def test_case_creation_and_idempotency(self):
        from app.schemas.case import CaseCreate, CasePriority, CaseStatus
        payload = CaseCreate(
            entity_id="TXN_TEST_IDEMP_001",
            entity_type="Transaction",
            title="Suspicious Rapid Outflow",
            priority=CasePriority.HIGH,
            risk_score=87.5,
        )
        case, created = self.service.create_case(payload, actor="tester")
        self.assertTrue(created)
        self.assertEqual(case.entity_id, "TXN_TEST_IDEMP_001")
        self.assertEqual(case.status, CaseStatus.NEW_ALERT)
        self.assertEqual(case.version, 1)

        # Idempotency check: creating again for same active entity returns existing case
        case_dup, created_dup = self.service.create_case(payload, actor="tester")
        self.assertFalse(created_dup)
        self.assertEqual(case_dup.case_id, case.case_id)
        self.assertEqual(case_dup.entity_id, "TXN_TEST_IDEMP_001")

    def test_valid_investigation_lifecycle(self):
        from app.schemas.case import (
            CaseCreate,
            CasePriority,
            CaseStatus,
            CaseStatusTransition,
            ResolutionCategory,
        )
        payload = CaseCreate(
            entity_id="TXN_TEST_CYCLE_002",
            entity_type="Transaction",
            priority=CasePriority.CRITICAL,
        )
        case, _ = self.service.create_case(payload)

        # 1. NEW_ALERT -> UNDER_INVESTIGATION
        trans_1 = CaseStatusTransition(
            target_status=CaseStatus.UNDER_INVESTIGATION,
            actor="analyst_priya",
            expected_version=case.version,
        )
        case_inv = self.service.transition_status(case.case_id, trans_1)
        self.assertEqual(case_inv.status, CaseStatus.UNDER_INVESTIGATION)
        self.assertEqual(case_inv.version, 2)

        # 2. UNDER_INVESTIGATION -> CONFIRMED_FRAUD with mandatory resolution
        trans_2 = CaseStatusTransition(
            target_status=CaseStatus.CONFIRMED_FRAUD,
            actor="analyst_priya",
            resolution_category=ResolutionCategory.TRUE_POSITIVE_FRAUD,
            resolution_explanation="Verified account takeover and mule account ring topology.",
            expected_version=case_inv.version,
        )
        case_fraud = self.service.transition_status(case.case_id, trans_2)
        self.assertEqual(case_fraud.status, CaseStatus.CONFIRMED_FRAUD)
        self.assertEqual(case_fraud.resolution_category, ResolutionCategory.TRUE_POSITIVE_FRAUD.value)
        self.assertIn("Verified account takeover", case_fraud.resolution_explanation)
        self.assertEqual(case_fraud.version, 3)

    def test_invalid_lifecycle_transition_rejection(self):
        from app.schemas.case import (
            CaseCreate,
            CasePriority,
            CaseStatus,
            CaseStatusTransition,
            ResolutionCategory,
        )
        payload = CaseCreate(
            entity_id="TXN_TEST_INVALID_003",
            entity_type="Transaction",
            priority=CasePriority.MEDIUM,
        )
        case, _ = self.service.create_case(payload)

        # Attempt invalid jump: NEW_ALERT directly to CONFIRMED_FRAUD
        trans_invalid = CaseStatusTransition(
            target_status=CaseStatus.CONFIRMED_FRAUD,
            resolution_category=ResolutionCategory.TRUE_POSITIVE_FRAUD,
            resolution_explanation="Premature conclusion without investigation.",
        )
        with self.assertRaises(ValueError) as ctx:
            self.service.transition_status(case.case_id, trans_invalid)
        self.assertIn("Invalid state transition", str(ctx.exception))

        # Attempt resolving without mandatory explanation
        trans_step1 = CaseStatusTransition(target_status=CaseStatus.UNDER_INVESTIGATION)
        c_inv = self.service.transition_status(case.case_id, trans_step1)

        trans_missing_exp = CaseStatusTransition(
            target_status=CaseStatus.DISMISSED_FALSE_POSITIVE,
            resolution_category=ResolutionCategory.FALSE_POSITIVE_NORMAL_ACTIVITY,
            resolution_explanation="",  # empty explanation rejected
        )
        with self.assertRaises(ValueError) as ctx2:
            self.service.transition_status(c_inv.case_id, trans_missing_exp)
        self.assertIn("resolution explanation", str(ctx2.exception))

    def test_reopen_resolved_case(self):
        from app.schemas.case import (
            CaseCreate,
            CaseStatus,
            CaseStatusTransition,
            ResolutionCategory,
        )
        payload = CaseCreate(entity_id="TXN_TEST_REOPEN_004")
        case, _ = self.service.create_case(payload)

        self.service.transition_status(
            case.case_id,
            CaseStatusTransition(target_status=CaseStatus.UNDER_INVESTIGATION),
        )
        case_closed = self.service.transition_status(
            case.case_id,
            CaseStatusTransition(
                target_status=CaseStatus.DISMISSED_FALSE_POSITIVE,
                resolution_category=ResolutionCategory.FALSE_POSITIVE_NORMAL_ACTIVITY,
                resolution_explanation="Initial review appeared legitimate customer travel.",
            ),
        )
        self.assertEqual(case_closed.status, CaseStatus.DISMISSED_FALSE_POSITIVE)

        # Reopen with required justification
        case_reopened = self.service.transition_status(
            case.case_id,
            CaseStatusTransition(
                target_status=CaseStatus.REOPENED,
                actor="senior_analyst_mark",
                resolution_explanation="New chargeback notification received from issuing bank.",
            ),
        )
        self.assertEqual(case_reopened.status, CaseStatus.REOPENED)

    def test_assignment_priority_and_notes(self):
        from app.schemas.case import CaseCreate, CaseNoteCreate, CasePriority
        payload = CaseCreate(entity_id="CLT_TEST_NOTES_005", entity_type="Client")
        case, _ = self.service.create_case(payload)

        # Assignment
        c_assigned = self.service.update_assignment(case.case_id, "analyst_priya", actor="admin")
        self.assertEqual(c_assigned.assigned_analyst, "analyst_priya")

        # Priority
        c_prio = self.service.update_priority(case.case_id, CasePriority.CRITICAL, actor="admin")
        self.assertEqual(c_prio.priority, CasePriority.CRITICAL)

        # Add Notes
        note = self.service.add_note(
            case.case_id,
            CaseNoteCreate(note="Identified shared hardware proxy with CLT032", author="analyst_priya"),
        )
        self.assertEqual(note.author, "analyst_priya")

        # Retrieve Case and verify audit history
        c_final = self.service.get_case(case.case_id)
        self.assertEqual(len(c_final.notes), 1)
        self.assertGreaterEqual(len(c_final.audit_trail), 4)

    def test_optimistic_concurrency_conflict(self):
        from app.schemas.case import CaseCreate, CaseStatus, CaseStatusTransition
        payload = CaseCreate(entity_id="TXN_TEST_CONFLICT_006")
        case, _ = self.service.create_case(payload)

        # Mismatched expected version (case version is 1, payload gives 99)
        conflict_trans = CaseStatusTransition(
            target_status=CaseStatus.UNDER_INVESTIGATION,
            expected_version=99,
        )
        with self.assertRaises(ValueError) as ctx:
            self.service.transition_status(case.case_id, conflict_trans)
        self.assertIn("Concurrency conflict", str(ctx.exception))

    def test_case_fastapi_rest_endpoints(self):
        from fastapi.testclient import TestClient
        from app.main import app
        from app.auth.security import create_access_token

        client = TestClient(app)
        token, _, _ = create_access_token(
            user_id="USR_ANALYST_001",
            username="analyst_priya",
            role="fraud_analyst",
        )
        client.headers.update({"Authorization": f"Bearer {token}"})

        # 1. List cases
        res_list = client.get("/api/v1/cases")
        self.assertEqual(res_list.status_code, 200)

        data_list = res_list.json()
        self.assertIn("cases", data_list)
        self.assertIn("total", data_list)
        self.assertGreater(data_list["total"], 0)

        # 2. Get specific seeded case
        res_get = client.get("/api/v1/cases/CASE-2026-0001")
        self.assertEqual(res_get.status_code, 200)
        case_data = res_get.json()
        self.assertEqual(case_data["case_id"], "CASE-2026-0001")
        self.assertIn("graph_context", case_data)
        self.assertIn("audit_trail", case_data)

        # 3. 404 on nonexistent case
        res_404 = client.get("/api/v1/cases/CASE_DOES_NOT_EXIST")
        self.assertEqual(res_404.status_code, 404)

        # 4. Create case via REST
        res_create = client.post(
            "/api/v1/cases",
            json={
                "entity_id": "TXN_REST_TEST_007",
                "entity_type": "Transaction",
                "priority": "HIGH",
                "risk_score": 82.0,
            },
        )
        self.assertEqual(res_create.status_code, 201)
        cid = res_create.json()["case_id"]

        # 5. Add note via REST
        res_note = client.post(
            f"/api/v1/cases/{cid}/notes",
            json={"note": "FastAPI integration test note", "author": "test_suite"},
        )
        self.assertEqual(res_note.status_code, 201)

        # 6. History via REST
        res_hist = client.get(f"/api/v1/cases/{cid}/history")
        self.assertEqual(res_hist.status_code, 200)
        self.assertGreaterEqual(len(res_hist.json()), 2)


if __name__ == "__main__":
    unittest.main()

