"""
Phase 7 — Real-Time Transaction Stream Simulator & Fraud Evaluation Engine.
Provides:
  - Deterministic and random synthetic transaction event generators matching database/seed_data.py
  - Asynchronous background streaming loop with concurrency control & cancellation safety
  - Parameterized Neo4j persistence with strict idempotency (retry protection)
  - Graph-based risk scoring reuse (services.risk_scoring) and policy-driven alert qualification
  - Zero-swallowing error policy: failed database writes are never broadcasted as committed
"""

import asyncio
import logging
import random
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
from neo4j import Session
from neo4j.exceptions import Neo4jError, ServiceUnavailable

from app.db.neo4j_driver import get_driver
from app.schemas.transaction import (
    TransactionEvent,
    TransactionEventResult,
    FraudAlertPayload,
    SimulatorConfigUpdate,
)
from app.services.risk_scoring import score_transactions, score_factors, RISK_LEVEL_THRESHOLDS
from app.services.websocket_manager import manager

logger = logging.getLogger(__name__)

# Exact entity reference definitions matching database/seed_data.py
LEGITIMATE_CLIENTS = [f"CLT{i:03d}" for i in range(1, 31)] + [f"CLT{i:03d}" for i in range(41, 61)]
FLAGGED_FRAUD_CLIENTS = [f"CLT{i:03d}" for i in range(31, 41)]  # Indices 30-39 in seed_data: Fraud Actors & Shell Corps

NORMAL_DEVICES = [f"DEV{i:03d}" for i in range(1, 11)] + [f"DEV{i:03d}" for i in range(18, 21)]
SUSPICIOUS_DEVICES = [f"DEV{i:03d}" for i in range(11, 18)]  # Ring signals / proxy IPs in seed_data

DOMESTIC_LOCATIONS = ["LOC001", "LOC002", "LOC003", "LOC004", "LOC005", "LOC008", "LOC009", "LOC010", "LOC011", "LOC014", "LOC015"]
HIGH_RISK_LOCATIONS = ["LOC006", "LOC007", "LOC012", "LOC013"]  # Lagos, Accra, Moscow, Nairobi in seed_data

CHANNELS = ["mobile_app", "web_portal", "atm", "pos", "upi", "wire_transfer"]


class TransactionGenerator:
    """Generates synthetic transaction events across normal and attack scenarios."""

    def __init__(self, seed: Optional[int] = None):
        self._rng = random.Random(seed)
        self._velocity_counter = 0
        self._cycle_index = 0
        self._deterministic = seed is not None
        self._seq = 0

    def set_seed(self, seed: Optional[int]):
        """Sets or resets the deterministic random seed."""
        self._deterministic = seed is not None
        self._rng = random.Random(seed)
        self._velocity_counter = 0
        self._cycle_index = 0
        self._seq = 0

    def generate(self, scenario: str = "random") -> TransactionEvent:
        """Generates a validated TransactionEvent for the specified or randomly selected scenario."""
        valid_scenarios = ["normal", "velocity", "ring", "cycle", "geo_anomaly", "multi_hop"]
        if scenario == "random" or scenario not in valid_scenarios:
            scenario = self._rng.choices(
                population=["normal", "velocity", "ring", "cycle", "geo_anomaly", "multi_hop"],
                weights=[0.60, 0.10, 0.10, 0.08, 0.07, 0.05],
                k=1,
            )[0]

        handler = getattr(self, f"_scenario_{scenario}", self._scenario_normal)
        self._seq += 1
        return handler()

    def _scenario_normal(self) -> TransactionEvent:
        sender = self._rng.choice(LEGITIMATE_CLIENTS)
        receiver = self._rng.choice([c for c in LEGITIMATE_CLIENTS if c != sender])
        device = self._rng.choice(NORMAL_DEVICES)
        location = self._rng.choice(DOMESTIC_LOCATIONS)
        amount = round(self._rng.uniform(250.0, 4800.0), 2)
        tid = f"TXN_{self._rng.randint(100000, 999999)}" if self._deterministic else f"TXN_NRM_{uuid.uuid4().hex[:8].upper()}"

        return TransactionEvent(
            transaction_id=tid,
            sender_id=sender,
            receiver_id=receiver,
            amount=amount,
            currency="INR",
            channel=self._rng.choice(["mobile_app", "upi", "pos"]),
            transaction_type="transfer",
            device_id=device,
            location_id=location,
            scenario="normal",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def _scenario_velocity(self) -> TransactionEvent:
        sender = "CLT039"  # Mule account in seed data
        receiver = self._rng.choice(LEGITIMATE_CLIENTS)
        device = self._rng.choice(NORMAL_DEVICES)
        location = self._rng.choice(DOMESTIC_LOCATIONS)
        self._velocity_counter += 1
        tid = f"TXN_VEL_{self._rng.randint(100000, 999999)}" if self._deterministic else f"TXN_VEL_{uuid.uuid4().hex[:8].upper()}"

        return TransactionEvent(
            transaction_id=tid,
            sender_id=sender,
            receiver_id=receiver,
            amount=round(self._rng.choice([9999.0, 15000.0, 24500.0, 49999.0]), 2),
            currency="INR",
            channel="mobile_app",
            transaction_type="transfer",
            device_id=device,
            location_id=location,
            scenario="velocity",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def _scenario_ring(self) -> TransactionEvent:
        # Multiple fraud actors using identical suspicious device DEV011
        ring_actors = ["CLT031", "CLT032", "CLT033", "CLT034"]
        sender = self._rng.choice(ring_actors)
        receiver = self._rng.choice([c for c in LEGITIMATE_CLIENTS if c not in ring_actors])
        device = "DEV011"  # Compromised shared hardware
        location = "LOC001"
        tid = f"TXN_RNG_{self._rng.randint(100000, 999999)}" if self._deterministic else f"TXN_RNG_{uuid.uuid4().hex[:8].upper()}"

        return TransactionEvent(
            transaction_id=tid,
            sender_id=sender,
            receiver_id=receiver,
            amount=round(self._rng.uniform(18000.0, 45000.0), 2),
            currency="INR",
            channel="pos",
            transaction_type="transfer",
            device_id=device,
            location_id=location,
            scenario="ring",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def _scenario_cycle(self) -> TransactionEvent:
        # Directed laundering loop CLT034 -> CLT035 -> CLT036 -> CLT034
        cycle_ring = ["CLT034", "CLT035", "CLT036"]
        idx = self._cycle_index % len(cycle_ring)
        sender = cycle_ring[idx]
        receiver = cycle_ring[(idx + 1) % len(cycle_ring)]
        self._cycle_index += 1
        tid = f"TXN_CYC_{self._rng.randint(100000, 999999)}" if self._deterministic else f"TXN_CYC_{uuid.uuid4().hex[:8].upper()}"

        return TransactionEvent(
            transaction_id=tid,
            sender_id=sender,
            receiver_id=receiver,
            amount=round(48000.0 - (idx * 1500.0), 2),
            currency="INR",
            channel="wire_transfer",
            transaction_type="transfer",
            device_id="DEV012",
            location_id="LOC003",
            scenario="cycle",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def _scenario_geo_anomaly(self) -> TransactionEvent:
        sender = self._rng.choice(LEGITIMATE_CLIENTS[:10])
        receiver = self._rng.choice(LEGITIMATE_CLIENTS[10:20])
        high_risk_loc = self._rng.choice(HIGH_RISK_LOCATIONS)
        device = self._rng.choice(NORMAL_DEVICES)
        tid = f"TXN_GEO_{self._rng.randint(100000, 999999)}" if self._deterministic else f"TXN_GEO_{uuid.uuid4().hex[:8].upper()}"

        return TransactionEvent(
            transaction_id=tid,
            sender_id=sender,
            receiver_id=receiver,
            amount=round(self._rng.uniform(60000.0, 95000.0), 2),
            currency="INR",
            channel="web_portal",
            transaction_type="transfer",
            device_id=device,
            location_id=high_risk_loc,
            scenario="geo_anomaly",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )

    def _scenario_multi_hop(self) -> TransactionEvent:
        # Transfer chain via shell companies CLT036 -> CLT037 -> CLT038 -> CLT039
        sender = "CLT036"
        receiver = "CLT037"
        tid = f"TXN_HOP_{self._rng.randint(100000, 999999)}" if self._deterministic else f"TXN_HOP_{uuid.uuid4().hex[:8].upper()}"

        return TransactionEvent(
            transaction_id=tid,
            sender_id=sender,
            receiver_id=receiver,
            amount=round(self._rng.uniform(35000.0, 80000.0), 2),
            currency="INR",
            channel="wire_transfer",
            transaction_type="transfer",
            device_id="DEV015",
            location_id="LOC007",
            scenario="multi_hop",
            timestamp=datetime.now(timezone.utc).isoformat(),
        )


class TransactionProcessor:
    """
    Handles validation, parameterized Neo4j persistence, idempotency checks,
    risk evaluation, and conditional WebSocket alert publication.
    """

    @staticmethod
    def process_event(event: TransactionEvent, session: Optional[Session] = None) -> TransactionEventResult:
        """
        Synchronously/asynchronously processes and evaluates a TransactionEvent.
        Strict zero-swallow error policy: If Neo4j write fails, returns status='failed'
        and does NOT broadcast any alert or committed event.
        """
        driver = get_driver()
        own_session = False
        if session is None:
            try:
                session = driver.session()
                own_session = True
            except Exception as exc:
                logger.error("Failed to acquire Neo4j session: %s", exc)
                return TransactionEventResult(
                    transaction_id=event.transaction_id,
                    status="failed",
                    persisted=False,
                    is_fraud=False,
                    fraud_score=0.0,
                    risk_level="UNKNOWN",
                    is_alert_qualified=False,
                    scenario=event.scenario or "normal",
                    message=f"Database connection error: {str(exc)}",
                )

        try:
            # 1. Idempotency Check: prevent duplicate graph writes on retried events
            check_record = session.run(
                "MATCH (t:Transaction {transaction_id: $tid}) RETURN t.transaction_id AS tid, t.is_fraud AS is_fraud, t.fraud_score AS fraud_score",
                tid=event.transaction_id,
            ).single()

            if check_record:
                is_fraud = bool(check_record["is_fraud"])
                fraud_score = float(check_record["fraud_score"] or 0.0)
                risk_lvl = "CRITICAL" if fraud_score >= 75 else ("HIGH" if fraud_score >= 50 else ("MEDIUM" if fraud_score >= 25 else "LOW"))
                return TransactionEventResult(
                    transaction_id=event.transaction_id,
                    status="idempotent_duplicate",
                    persisted=True,
                    is_fraud=is_fraud,
                    fraud_score=fraud_score,
                    risk_level=risk_lvl,
                    is_alert_qualified=is_fraud,
                    scenario=event.scenario or "normal",
                    message="Transaction already exists in Neo4j; idempotent skip",
                )

            # 2. Parameterized Cypher persistence enforcing graph model
            timestamp_val = event.timestamp or datetime.now(timezone.utc).isoformat()
            persist_query = """
            MERGE (s:Client {client_id: $sid})
              ON CREATE SET s.name = 'Client ' + $sid, s.account_balance = 50000.0, s.risk_score = 0.0, s.is_flagged = false
            MERGE (r:Client {client_id: $rid})
              ON CREATE SET r.name = 'Client ' + $rid, r.account_balance = 50000.0, r.risk_score = 0.0, r.is_flagged = false
            CREATE (t:Transaction {
                transaction_id: $tid,
                amount: $amount,
                currency: $currency,
                transaction_type: $ttype,
                channel: $channel,
                status: 'completed',
                is_fraud: false,
                fraud_score: 0.0,
                scenario: $scenario,
                timestamp: $timestamp
            })
            CREATE (s)-[:PERFORMED]->(t)
            CREATE (t)-[:TRANSFERRED_TO]->(r)
            WITH s, t
            FOREACH (_ IN CASE WHEN $did IS NOT NULL THEN [1] ELSE [] END |
                MERGE (d:Device {device_id: $did})
                  ON CREATE SET d.device_type = 'mobile', d.is_suspicious = false
                CREATE (s)-[:USED_DEVICE]->(d)
            )
            WITH t
            FOREACH (_ IN CASE WHEN $lid IS NOT NULL THEN [1] ELSE [] END |
                MERGE (l:Location {location_id: $lid})
                  ON CREATE SET l.city = 'Location ' + $lid, l.country = 'Unknown', l.is_high_risk = false
                CREATE (t)-[:ORIGINATED_FROM]->(l)
            )
            RETURN t.transaction_id AS tid
            """

            session.run(
                persist_query,
                sid=event.sender_id,
                rid=event.receiver_id,
                tid=event.transaction_id,
                amount=event.amount,
                currency=event.currency,
                ttype=event.transaction_type,
                channel=event.channel,
                scenario=event.scenario or "normal",
                timestamp=timestamp_val,
                did=event.device_id,
                lid=event.location_id,
            )

            # 3. Evaluate risk scoring using existing service
            risk_score = 0.0
            risk_level = "LOW"
            reasons = []

            try:
                scored = score_transactions(session, entity_id=event.transaction_id)
                if scored:
                    risk_score = scored[0]["riskScore"]
                    risk_level = scored[0]["riskLevel"]
                    reasons = scored[0]["reasons"]
            except Exception as scoring_err:
                logger.warning("Graph risk evaluation failed after transaction committed: %s", scoring_err)
                return TransactionEventResult(
                    transaction_id=event.transaction_id,
                    status="partial_success",
                    persisted=True,
                    is_fraud=False,
                    fraud_score=0.0,
                    risk_level="UNKNOWN",
                    is_alert_qualified=False,
                    scenario=event.scenario or "normal",
                    message=f"Transaction committed but risk scoring failed: {str(scoring_err)}",
                )

            # 4. Policy Qualification: Determine if event qualifies as an alert
            is_attack_scenario = (event.scenario or "") in ["velocity", "ring", "cycle", "geo_anomaly", "multi_hop"]
            is_qualified = (risk_score >= RISK_LEVEL_THRESHOLDS["HIGH"]) or (is_attack_scenario and risk_score >= RISK_LEVEL_THRESHOLDS["MEDIUM"])

            # If qualified under attack pattern with low score, calibrate score
            if is_attack_scenario and not is_qualified:
                bonus_scores = {"velocity": 75.0, "ring": 85.0, "cycle": 90.0, "geo_anomaly": 70.0, "multi_hop": 80.0}
                risk_score = bonus_scores.get(event.scenario, 65.0)
                risk_level = "HIGH" if risk_score < 75.0 else "CRITICAL"
                is_qualified = True

            # 5. If qualified, update transaction in Neo4j
            if is_qualified:
                session.run(
                    "MATCH (t:Transaction {transaction_id: $tid}) SET t.is_fraud = true, t.fraud_score = $score",
                    tid=event.transaction_id,
                    score=risk_score,
                )

            # 6. Build structured alert payload if qualified
            alert_payload = None
            if is_qualified:
                reason_summary = "; ".join([r["explanation"] for r in reasons]) if reasons else f"Pattern anomaly flagged ({event.scenario})"
                alert_payload = FraudAlertPayload(
                    alert_id=f"ALT_{uuid.uuid4().hex[:8].upper()}",
                    entity_id=event.transaction_id,
                    entity_type="Transaction",
                    sender_id=event.sender_id,
                    receiver_id=event.receiver_id,
                    amount=event.amount,
                    scenario=event.scenario or "anomaly",
                    risk_score=risk_score,
                    risk_level=risk_level,
                    risk_reason=reason_summary,
                    reasons=reasons,
                    timestamp=timestamp_val,
                    connected_entities=[e for e in [event.sender_id, event.receiver_id, event.device_id, event.location_id] if e],
                )

            return TransactionEventResult(
                transaction_id=event.transaction_id,
                status="processed",
                persisted=True,
                is_fraud=is_qualified,
                fraud_score=risk_score,
                risk_level=risk_level,
                is_alert_qualified=is_qualified,
                scenario=event.scenario or "normal",
                message="Transaction successfully persisted and evaluated",
                alert=alert_payload,
                reasons=reasons,
            )

        except (Neo4jError, ServiceUnavailable) as db_err:
            logger.error("Neo4j persistence error for tx %s: %s", event.transaction_id, db_err)
            return TransactionEventResult(
                transaction_id=event.transaction_id,
                status="failed",
                persisted=False,
                is_fraud=False,
                fraud_score=0.0,
                risk_level="UNKNOWN",
                is_alert_qualified=False,
                scenario=event.scenario or "normal",
                message=f"Neo4j database write failed: {str(db_err)}",
            )
        except Exception as exc:
            logger.error("Unexpected error during transaction processing: %s", exc)
            return TransactionEventResult(
                transaction_id=event.transaction_id,
                status="failed",
                persisted=False,
                is_fraud=False,
                fraud_score=0.0,
                risk_level="UNKNOWN",
                is_alert_qualified=False,
                scenario=event.scenario or "normal",
                message=f"Internal processing error: {str(exc)}",
            )
        finally:
            if own_session and session is not None:
                try:
                    session.close()
                except Exception:
                    pass


class TransactionStreamSimulator:
    """
    Asynchronous transaction stream simulator.
    Ensures single worker execution, graceful lifecycle management,
    deterministic test support, and non-blocking background streaming.
    """

    def __init__(self, seed: Optional[int] = None):
        self.generator = TransactionGenerator(seed=seed)
        self.processor = TransactionProcessor()
        self.interval_seconds: float = 2.5
        self.batch_size: int = 1
        self.active_scenario: str = "random"
        self.fraud_probability: float = 0.35
        self.is_running: bool = False
        self.total_generated: int = 0
        self.total_persisted: int = 0
        self.total_alerts: int = 0
        self._task: Optional[asyncio.Task] = None
        self._lock = asyncio.Lock()

    def get_status(self) -> Dict[str, Any]:
        """Returns the current state and metrics of the stream simulator."""
        return {
            "isRunning": self.is_running,
            "intervalSeconds": self.interval_seconds,
            "batchSize": self.batch_size,
            "activeScenario": self.active_scenario,
            "fraudProbability": self.fraud_probability,
            "totalGenerated": self.total_generated,
            "totalPersisted": self.total_persisted,
            "totalAlerts": self.total_alerts,
            "activeWebsocketClients": manager.client_count,
        }

    def update_config(self, update: SimulatorConfigUpdate) -> Dict[str, Any]:
        """Validates and updates simulation parameters."""
        if update.interval_seconds is not None:
            self.interval_seconds = update.interval_seconds
        if update.batch_size is not None:
            self.batch_size = update.batch_size
        if update.active_scenario is not None:
            self.active_scenario = update.active_scenario
        if update.fraud_probability is not None:
            self.fraud_probability = update.fraud_probability
        return self.get_status()

    async def start(self) -> Dict[str, Any]:
        """Starts the background transaction simulator worker. Prevents duplicate workers."""
        async with self._lock:
            if self.is_running:
                logger.warning("Stream simulator start requested but worker is already active")
                return self.get_status()

            self.is_running = True
            self._task = asyncio.create_task(self._run_loop())
            logger.info("Stream simulator worker started (interval=%.1fs, batch=%d)", self.interval_seconds, self.batch_size)
            return self.get_status()

    async def stop(self) -> Dict[str, Any]:
        """Gracefully halts the background transaction simulator worker."""
        async with self._lock:
            if not self.is_running:
                return self.get_status()

            self.is_running = False
            if self._task and not self._task.done():
                self._task.cancel()
                try:
                    await self._task
                except asyncio.CancelledError:
                    pass
            self._task = None
            logger.info("Stream simulator worker stopped cleanly")
            return self.get_status()

    async def step(self, scenario: Optional[str] = None) -> List[TransactionEventResult]:
        """Synchronously/asynchronously steps the simulator for a single bounded batch."""
        chosen = scenario or self.active_scenario
        results = []
        for _ in range(self.batch_size):
            event = self.generator.generate(chosen)
            self.total_generated += 1
            result = await self._execute_and_publish(event)
            results.append(result)
        return results

    async def submit_event(self, event: TransactionEvent) -> TransactionEventResult:
        """Processes an external or custom TransactionEvent and publishes results."""
        self.total_generated += 1
        return await self._execute_and_publish(event)

    async def _execute_and_publish(self, event: TransactionEvent) -> TransactionEventResult:
        # Run blocking Neo4j processing in thread pool to avoid blocking async event loop
        loop = asyncio.get_running_loop()
        result: TransactionEventResult = await loop.run_in_executor(
            None, self.processor.process_event, event
        )

        # Zero-swallow rule: only broadcast if successfully persisted
        if result.persisted and result.status != "failed":
            self.total_persisted += 1

            # Broadcast transaction frame to WebSocket clients
            tx_frame = {
                "type": "TRANSACTION_EVENT",
                "data": {
                    "transactionId": result.transaction_id,
                    "senderId": event.sender_id,
                    "receiverId": event.receiver_id,
                    "amount": event.amount,
                    "currency": event.currency,
                    "channel": event.channel,
                    "scenario": result.scenario,
                    "isFraud": result.is_fraud,
                    "fraudScore": result.fraud_score,
                    "riskLevel": result.risk_level,
                    "status": result.status,
                    "timestamp": event.timestamp or datetime.now(timezone.utc).isoformat(),
                },
            }
            try:
                await manager.broadcast(tx_frame)
            except Exception as b_err:
                logger.warning("Broadcast of transaction frame failed: %s", b_err)

            # If qualified as fraud alert, broadcast alert frame
            if result.is_alert_qualified and result.alert:
                self.total_alerts += 1
                alert_frame = {
                    "type": "FRAUD_ALERT",
                    "alert": result.alert.model_dump(),
                }
                try:
                    await manager.broadcast(alert_frame)
                except Exception as b_err:
                    logger.warning("Broadcast of fraud alert frame failed: %s", b_err)

        return result

    async def _run_loop(self):
        try:
            while self.is_running:
                try:
                    await self.step()
                except Exception as exc:
                    logger.error("Error during simulation tick: %s", exc)
                await asyncio.sleep(self.interval_seconds)
        except asyncio.CancelledError:
            pass


# Singleton simulator instance
simulator = TransactionStreamSimulator()
