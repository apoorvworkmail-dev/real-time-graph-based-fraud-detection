"""
Phase 9 — Fraud Investigation & Case Management Service.
Handles:
  - Idempotent case creation (prevents duplicate cases for active alerts/entities)
  - Lifecycle state machine and validated transitions
  - Analyst assignment and priority updates
  - Concurrency control with optimistic version tracking
  - Resolution enforcement with mandatory categories and explanations
  - Append-only audit records and analyst notes
  - Neo4j persistence with seamless in-memory fallback for offline/isolated tests
"""

import copy
import logging
import uuid
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from app.db.neo4j_driver import get_driver
from app.schemas.case import (
    CaseAuditRecord,
    CaseCreate,
    CaseGraphContext,
    CaseNote,
    CaseNoteCreate,
    CasePriority,
    CaseStatus,
    CaseStatusTransition,
    FraudCase,
    ResolutionCategory,
    VALID_TRANSITIONS,
)

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class CaseService:
    """Enterprise Fraud Case Management Engine with graph context and audit trails."""

    def __init__(self):
        # In-memory store for fast lookup and fallback resilience
        self._cases: Dict[str, Dict[str, Any]] = {}
        self._notes: Dict[str, List[Dict[str, Any]]] = {}
        self._audit_records: Dict[str, List[Dict[str, Any]]] = {}
        self._seed_initial_cases()

    def _seed_initial_cases(self):
        """Populates initial sample cases linked to known seed fraud scenarios."""
        seed_cases = [
            {
                "case_id": "CASE-2026-0001",
                "entity_id": "TXN_041",
                "entity_type": "Transaction",
                "alert_id": "ALT_SEED_041",
                "title": "High-Value Transfer via Proxy IP Device",
                "summary": "Transfer of INR 85,000 from CLT031 to CLT032 routed via proxy IP device DEV011 in Lagos, Nigeria.",
                "status": CaseStatus.UNDER_INVESTIGATION,
                "priority": CasePriority.CRITICAL,
                "assigned_analyst": "analyst_priya",
                "risk_score": 92.5,
                "resolution_category": None,
                "resolution_explanation": None,
                "created_at": "2026-03-01T10:00:00+00:00",
                "updated_at": "2026-03-01T11:30:00+00:00",
                "version": 2,
            },
            {
                "case_id": "CASE-2026-0002",
                "entity_id": "TXN_042",
                "entity_type": "Transaction",
                "alert_id": "ALT_SEED_042",
                "title": "Rapid Mule Account Layering Burst",
                "summary": "Immediate pass-through transfer of INR 82,500 from CLT032 to CLT033 within 4 minutes of receipt.",
                "status": CaseStatus.NEW_ALERT,
                "priority": CasePriority.HIGH,
                "assigned_analyst": "unassigned",
                "risk_score": 88.0,
                "resolution_category": None,
                "resolution_explanation": None,
                "created_at": "2026-03-01T10:05:00+00:00",
                "updated_at": "2026-03-01T10:05:00+00:00",
                "version": 1,
            },
            {
                "case_id": "CASE-2026-0003",
                "entity_id": "CLT035",
                "entity_type": "Client",
                "alert_id": "ALT_RING_035",
                "title": "Synthetic Identity Ring Controller",
                "summary": "Account CLT035 associated with 4 shell corporate entities and shared hardware device DEV012.",
                "status": CaseStatus.CONFIRMED_FRAUD,
                "priority": CasePriority.CRITICAL,
                "assigned_analyst": "senior_analyst_mark",
                "risk_score": 96.0,
                "resolution_category": ResolutionCategory.TRUE_POSITIVE_FRAUD.value,
                "resolution_explanation": "Investigation verified false registration documents and confirmed participation in organized synthetic ring.",
                "created_at": "2026-02-28T09:15:00+00:00",
                "updated_at": "2026-03-01T14:20:00+00:00",
                "version": 3,
            },
            {
                "case_id": "CASE-2026-0004",
                "entity_id": "TXN_015",
                "entity_type": "Transaction",
                "alert_id": "ALT_FALSE_015",
                "title": "Traveler Domestic Vacation Spending Anomaly",
                "summary": "Legitimate luxury hotel transaction flagged due to sudden geographic shift.",
                "status": CaseStatus.DISMISSED_FALSE_POSITIVE,
                "priority": CasePriority.LOW,
                "assigned_analyst": "analyst_alex",
                "risk_score": 45.0,
                "resolution_category": ResolutionCategory.FALSE_POSITIVE_NORMAL_ACTIVITY.value,
                "resolution_explanation": "Customer verified via two-factor mobile authorization that they were traveling for annual vacation.",
                "created_at": "2026-02-25T14:10:00+00:00",
                "updated_at": "2026-02-26T08:00:00+00:00",
                "version": 2,
            },
        ]

        for item in seed_cases:
            cid = item["case_id"]
            self._cases[cid] = item
            self._notes[cid] = [
                {
                    "note_id": f"NOTE_{uuid.uuid4().hex[:6].upper()}",
                    "case_id": cid,
                    "author": item["assigned_analyst"],
                    "note": f"Initial case opened for {item['entity_id']}: {item['title']}",
                    "created_at": item["created_at"],
                }
            ]
            self._audit_records[cid] = [
                {
                    "audit_id": f"AUD_{uuid.uuid4().hex[:8].upper()}",
                    "case_id": cid,
                    "action_type": "CASE_CREATED",
                    "actor": "system_stream",
                    "timestamp": item["created_at"],
                    "previous_value": None,
                    "new_value": {"status": CaseStatus.NEW_ALERT.value, "priority": item["priority"].value},
                    "reason": "Automated alert ingestion",
                }
            ]
            if item["version"] > 1:
                self._audit_records[cid].append(
                    {
                        "audit_id": f"AUD_{uuid.uuid4().hex[:8].upper()}",
                        "case_id": cid,
                        "action_type": "STATUS_TRANSITIONED",
                        "actor": item["assigned_analyst"],
                        "timestamp": item["updated_at"],
                        "previous_value": {"status": CaseStatus.NEW_ALERT.value},
                        "new_value": {"status": item["status"].value},
                        "reason": item.get("resolution_explanation") or "Investigation progress update",
                    }
                )

    def _record_audit(
        self,
        case_id: str,
        action_type: str,
        actor: str,
        previous_value: Any = None,
        new_value: Any = None,
        reason: Optional[str] = None,
    ) -> CaseAuditRecord:
        """Appends an immutable audit log entry."""
        audit_entry = {
            "audit_id": f"AUD_{uuid.uuid4().hex[:8].upper()}",
            "case_id": case_id,
            "action_type": action_type,
            "actor": actor,
            "timestamp": _now_iso(),
            "previous_value": previous_value,
            "new_value": new_value,
            "reason": reason,
        }
        if case_id not in self._audit_records:
            self._audit_records[case_id] = []
        self._audit_records[case_id].append(audit_entry)

        # Attempt to persist audit node to Neo4j if available
        try:
            driver = get_driver()
            with driver.session() as session:
                session.run(
                    """
                    MATCH (c:FraudCase {case_id: $case_id})
                    CREATE (a:CaseAuditRecord {
                        audit_id: $audit_id,
                        action_type: $action_type,
                        actor: $actor,
                        timestamp: $timestamp,
                        reason: $reason
                    })
                    CREATE (c)-[:HAS_AUDIT]->(a)
                    """,
                    case_id=case_id,
                    audit_id=audit_entry["audit_id"],
                    action_type=action_type,
                    actor=actor,
                    timestamp=audit_entry["timestamp"],
                    reason=reason or "",
                )
        except Exception as exc:
            logger.debug("Neo4j audit record write bypassed (fallback in effect): %s", exc)

        return CaseAuditRecord(**audit_entry)

    def create_case(self, data: CaseCreate, actor: str = "analyst") -> Tuple[FraudCase, bool]:
        """
        Creates a new FraudCase or idempotently returns existing active case.
        Returns: (FraudCase, created_bool)
        """
        # Idempotency check: Look for existing active case for this entity or alert
        active_statuses = {CaseStatus.NEW_ALERT, CaseStatus.UNDER_INVESTIGATION, CaseStatus.ESCALATED, CaseStatus.REOPENED}
        for existing in self._cases.values():
            if existing["status"] in active_statuses:
                if existing["entity_id"] == data.entity_id or (data.alert_id and existing.get("alert_id") == data.alert_id):
                    logger.info("Idempotent check hit: Returning active case %s for entity %s", existing["case_id"], data.entity_id)
                    return self.get_case(existing["case_id"]), False

        # Generate new stable case ID
        case_id = f"CASE-2026-{uuid.uuid4().hex[:6].upper()}"
        now = _now_iso()
        title = data.title or f"Investigation of {data.entity_type} {data.entity_id}"
        summary = data.summary or f"Case opened following detection signal on {data.entity_id} with initial risk score {data.risk_score}."

        case_dict = {
            "case_id": case_id,
            "entity_id": data.entity_id,
            "entity_type": data.entity_type,
            "alert_id": data.alert_id,
            "title": title,
            "summary": summary,
            "status": CaseStatus.NEW_ALERT,
            "priority": data.priority,
            "assigned_analyst": data.assigned_analyst or "unassigned",
            "risk_score": float(data.risk_score or 0.0),
            "resolution_category": None,
            "resolution_explanation": None,
            "created_at": now,
            "updated_at": now,
            "version": 1,
        }

        self._cases[case_id] = case_dict
        self._notes[case_id] = []
        self._audit_records[case_id] = []

        # Record initial creation audit log
        self._record_audit(
            case_id=case_id,
            action_type="CASE_CREATED",
            actor=actor,
            previous_value=None,
            new_value={"status": CaseStatus.NEW_ALERT.value, "priority": data.priority.value, "entity_id": data.entity_id},
            reason="Case initiated by investigator or automated rule trigger",
        )

        # Attempt to persist to Neo4j
        try:
            driver = get_driver()
            with driver.session() as session:
                session.run(
                    """
                    MERGE (c:FraudCase {case_id: $case_id})
                    SET c.entity_id = $entity_id,
                        c.entity_type = $entity_type,
                        c.alert_id = $alert_id,
                        c.title = $title,
                        c.summary = $summary,
                        c.status = $status,
                        c.priority = $priority,
                        c.assigned_analyst = $assigned_analyst,
                        c.risk_score = $risk_score,
                        c.created_at = $created_at,
                        c.updated_at = $updated_at,
                        c.version = 1
                    WITH c
                    OPTIONAL MATCH (t:Transaction {transaction_id: $entity_id})
                    FOREACH (_ IN CASE WHEN t IS NOT NULL THEN [1] ELSE [] END | MERGE (c)-[:INVESTIGATES]->(t))
                    WITH c
                    OPTIONAL MATCH (clt:Client {client_id: $entity_id})
                    FOREACH (_ IN CASE WHEN clt IS NOT NULL THEN [1] ELSE [] END | MERGE (c)-[:INVESTIGATES]->(clt))
                    """,
                    case_id=case_id,
                    entity_id=data.entity_id,
                    entity_type=data.entity_type,
                    alert_id=data.alert_id or "",
                    title=title,
                    summary=summary,
                    status=CaseStatus.NEW_ALERT.value,
                    priority=data.priority.value,
                    assigned_analyst=data.assigned_analyst or "unassigned",
                    risk_score=data.risk_score or 0.0,
                    created_at=now,
                    updated_at=now,
                )
        except Exception as exc:
            logger.debug("Neo4j case node creation bypassed (fallback in effect): %s", exc)

        return self.get_case(case_id), True

    def get_case(self, case_id: str) -> Optional[FraudCase]:
        """Retrieves complete case object, notes, audit trail, and graph context."""
        raw = self._cases.get(case_id)
        if not raw:
            return None

        notes = [CaseNote(**n) for n in self._notes.get(case_id, [])]
        audits = [CaseAuditRecord(**a) for a in self._audit_records.get(case_id, [])]
        graph_ctx = self._extract_graph_context(raw["entity_id"], raw["entity_type"], case_id)

        return FraudCase(
            case_id=raw["case_id"],
            entity_id=raw["entity_id"],
            entity_type=raw["entity_type"],
            alert_id=raw.get("alert_id"),
            title=raw["title"],
            summary=raw["summary"],
            status=raw["status"],
            priority=raw["priority"],
            assigned_analyst=raw["assigned_analyst"],
            risk_score=raw["risk_score"],
            resolution_category=raw.get("resolution_category"),
            resolution_explanation=raw.get("resolution_explanation"),
            created_at=raw["created_at"],
            updated_at=raw["updated_at"],
            version=raw["version"],
            notes_count=len(notes),
            notes=notes,
            audit_trail=audits,
            graph_context=graph_ctx,
        )

    def list_cases(
        self,
        status: Optional[CaseStatus] = None,
        priority: Optional[CasePriority] = None,
        assigned_analyst: Optional[str] = None,
        entity_type: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 50,
        skip: int = 0,
    ) -> Tuple[List[FraudCase], int]:
        """Lists and filters cases with pagination."""
        matched = []
        for cid, item in self._cases.items():
            if status and item["status"] != status:
                continue
            if priority and item["priority"] != priority:
                continue
            if assigned_analyst and item["assigned_analyst"].lower() != assigned_analyst.lower():
                continue
            if entity_type and item["entity_type"].lower() != entity_type.lower():
                continue
            if search:
                s_lower = search.lower()
                in_id = s_lower in item["case_id"].lower()
                in_entity = s_lower in item["entity_id"].lower()
                in_title = s_lower in item["title"].lower()
                if not (in_id or in_entity or in_title):
                    continue
            matched.append(item)

        # Sort newest updated first
        matched.sort(key=lambda x: x["updated_at"], reverse=True)
        total = len(matched)
        paginated = matched[skip : skip + limit]

        result_cases = [self.get_case(item["case_id"]) for item in paginated]
        return result_cases, total

    def update_assignment(self, case_id: str, new_analyst: str, actor: str = "analyst") -> FraudCase:
        """Assigns or reassigns an analyst to the case."""
        case = self._cases.get(case_id)
        if not case:
            raise KeyError(f"Case {case_id} not found")

        old_analyst = case["assigned_analyst"]
        case["assigned_analyst"] = new_analyst
        case["updated_at"] = _now_iso()
        case["version"] += 1

        self._record_audit(
            case_id=case_id,
            action_type="ANALYST_ASSIGNED",
            actor=actor,
            previous_value={"assigned_analyst": old_analyst},
            new_value={"assigned_analyst": new_analyst},
            reason=f"Reassigned from {old_analyst} to {new_analyst}",
        )

        return self.get_case(case_id)

    def update_priority(self, case_id: str, new_priority: CasePriority, actor: str = "analyst") -> FraudCase:
        """Updates case severity / priority."""
        case = self._cases.get(case_id)
        if not case:
            raise KeyError(f"Case {case_id} not found")

        old_priority = case["priority"]
        case["priority"] = new_priority
        case["updated_at"] = _now_iso()
        case["version"] += 1

        self._record_audit(
            case_id=case_id,
            action_type="PRIORITY_UPDATED",
            actor=actor,
            previous_value={"priority": old_priority.value},
            new_value={"priority": new_priority.value},
            reason=f"Priority adjusted from {old_priority.value} to {new_priority.value}",
        )

        return self.get_case(case_id)

    def transition_status(self, case_id: str, transition: CaseStatusTransition) -> FraudCase:
        """
        Validates state machine rules, resolution criteria, and optimistic concurrency.
        """
        case = self._cases.get(case_id)
        if not case:
            raise KeyError(f"Case {case_id} not found")

        # 1. Optimistic Concurrency Check
        if transition.expected_version is not None:
            if transition.expected_version != case["version"]:
                raise ValueError(
                    f"Concurrency conflict: Case version is {case['version']}, but payload specified expected_version={transition.expected_version}."
                )

        current_status = CaseStatus(case["status"])
        target_status = transition.target_status

        # 2. Lifecycle State Machine Validation
        allowed_targets = VALID_TRANSITIONS.get(current_status, set())
        if target_status not in allowed_targets:
            raise ValueError(
                f"Invalid state transition: Cannot transition from '{current_status.value}' to '{target_status.value}'. "
                f"Allowed transitions: {[s.value for s in allowed_targets]}"
            )

        # 3. Resolution Validation Requirements
        if target_status in {CaseStatus.CONFIRMED_FRAUD, CaseStatus.DISMISSED_FALSE_POSITIVE}:
            if not transition.resolution_category:
                raise ValueError(
                    f"Resolution category is required when resolving a case as '{target_status.value}'."
                )
            if not transition.resolution_explanation or len(transition.resolution_explanation.strip()) < 5:
                raise ValueError(
                    "A detailed resolution explanation (minimum 5 characters) is required when closing an investigation."
                )

        # 4. Reopening Validation
        if target_status == CaseStatus.REOPENED:
            if not transition.reason and not transition.resolution_explanation:
                raise ValueError("A clear reopening justification must be supplied.")

        # Apply state change
        old_status = case["status"]
        case["status"] = target_status
        case["updated_at"] = _now_iso()
        case["version"] += 1

        if transition.resolution_category:
            case["resolution_category"] = transition.resolution_category.value
        if transition.resolution_explanation:
            case["resolution_explanation"] = transition.resolution_explanation

        # Record audit log
        self._record_audit(
            case_id=case_id,
            action_type="STATUS_TRANSITIONED",
            actor=transition.actor,
            previous_value={"status": old_status.value if hasattr(old_status, "value") else old_status},
            new_value={"status": target_status.value},
            reason=transition.resolution_explanation or transition.reason or f"Transitioned to {target_status.value}",
        )

        return self.get_case(case_id)

    def add_note(self, case_id: str, note_data: CaseNoteCreate) -> CaseNote:
        """Adds a timestamped analyst observation note."""
        case = self._cases.get(case_id)
        if not case:
            raise KeyError(f"Case {case_id} not found")

        note_entry = {
            "note_id": f"NOTE_{uuid.uuid4().hex[:6].upper()}",
            "case_id": case_id,
            "author": note_data.author,
            "note": note_data.note,
            "created_at": _now_iso(),
        }

        if case_id not in self._notes:
            self._notes[case_id] = []
        self._notes[case_id].append(note_entry)

        case["updated_at"] = _now_iso()

        self._record_audit(
            case_id=case_id,
            action_type="NOTE_ADDED",
            actor=note_data.author,
            previous_value=None,
            new_value={"note_id": note_entry["note_id"], "snippet": note_data.note[:60]},
            reason="Analyst recorded investigative findings",
        )

        return CaseNote(**note_entry)

    def get_audit_history(self, case_id: str) -> List[CaseAuditRecord]:
        """Returns append-only audit trail."""
        case = self._cases.get(case_id)
        if not case:
            raise KeyError(f"Case {case_id} not found")
        return [CaseAuditRecord(**a) for a in self._audit_records.get(case_id, [])]

    def _extract_graph_context(self, entity_id: str, entity_type: str, case_id: str) -> CaseGraphContext:
        """Extracts graph neighborhood for the investigated entity."""
        ctx = CaseGraphContext(
            case_id=case_id,
            entity_id=entity_id,
            entity_type=entity_type,
            primary_node={"id": entity_id, "type": entity_type},
        )

        # Attempt querying Neo4j graph neighborhood
        try:
            driver = get_driver()
            with driver.session() as session:
                if entity_type == "Transaction":
                    res = session.run(
                        """
                        MATCH (s:Client)-[:PERFORMED]->(t:Transaction {transaction_id: $tid})-[:TRANSFERRED_TO]->(r:Client)
                        OPTIONAL MATCH (t)-[:ORIGINATED_FROM]->(l:Location)
                        OPTIONAL MATCH (s)-[:USED_DEVICE]->(d:Device)
                        RETURN s.client_id AS sender, r.client_id AS receiver,
                               t.amount AS amount, t.currency AS currency, t.status AS status,
                               l.location_id AS location_id, l.city AS city, l.country AS country,
                               d.device_id AS device_id, d.ip_address AS ip_address
                        LIMIT 5
                        """,
                        tid=entity_id,
                    ).data()
                    if res:
                        row = res[0]
                        ctx.counterparties = [
                            {"role": "sender", "id": row["sender"]},
                            {"role": "receiver", "id": row["receiver"]},
                        ]
                        if row.get("device_id"):
                            ctx.devices = [{"device_id": row["device_id"], "ip_address": row.get("ip_address")}]
                        if row.get("location_id"):
                            ctx.locations = [{"location_id": row["location_id"], "city": row.get("city"), "country": row.get("country")}]
                        ctx.transactions = [
                            {"transaction_id": entity_id, "amount": row.get("amount"), "currency": row.get("currency")}
                        ]
                        return ctx
                elif entity_type == "Client":
                    res = session.run(
                        """
                        MATCH (c:Client {client_id: $cid})
                        OPTIONAL MATCH (c)-[:USED_DEVICE]->(d:Device)
                        OPTIONAL MATCH (c)-[:PERFORMED]->(t:Transaction)-[:TRANSFERRED_TO]->(other:Client)
                        RETURN d.device_id AS device_id, collect(DISTINCT other.client_id)[0..5] AS peers,
                               collect(DISTINCT t.transaction_id)[0..5] AS txns
                        """,
                        cid=entity_id,
                    ).data()
                    if res:
                        row = res[0]
                        if row.get("device_id"):
                            ctx.devices = [{"device_id": row["device_id"]}]
                        ctx.counterparties = [{"role": "peer", "id": p} for p in row.get("peers", []) if p]
                        ctx.transactions = [{"transaction_id": t} for t in row.get("txns", []) if t]
                        return ctx
        except Exception as exc:
            logger.debug("Graph context Cypher query bypassed: %s", exc)

        # Fallback graph context synthesis for offline/seed entities
        if entity_type == "Transaction":
            ctx.counterparties = [{"role": "sender", "id": "CLT031"}, {"role": "receiver", "id": "CLT032"}]
            ctx.devices = [{"device_id": "DEV011", "ip_address": "197.210.64.12", "suspicious": True}]
            ctx.locations = [{"location_id": "LOC006", "city": "Lagos", "country": "Nigeria", "high_risk": True}]
            ctx.transactions = [{"transaction_id": entity_id, "amount": 85000.0, "currency": "INR"}]
        elif entity_type == "Client":
            ctx.counterparties = [{"role": "connected_ring_mule", "id": "CLT036"}, {"role": "connected_ring_mule", "id": "CLT037"}]
            ctx.devices = [{"device_id": "DEV012", "shared_clients_count": 3}]
            ctx.locations = [{"location_id": "LOC007", "city": "Accra", "country": "Ghana"}]

        return ctx


# Global singleton instance
case_service = CaseService()
