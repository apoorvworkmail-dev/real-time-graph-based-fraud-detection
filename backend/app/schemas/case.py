"""
Phase 9 — Fraud Investigation & Case Management Pydantic Schemas.
Defines models for:
  - Case entity, statuses, and priorities
  - State machine transitions & validation
  - Analyst notes and assignment
  - Append-only audit history records
  - Graph contextual entities (clients, devices, locations)
"""

from enum import Enum
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, ConfigDict, Field, field_validator


class CaseStatus(str, Enum):
    NEW_ALERT = "NEW_ALERT"
    UNDER_INVESTIGATION = "UNDER_INVESTIGATION"
    CONFIRMED_FRAUD = "CONFIRMED_FRAUD"
    DISMISSED_FALSE_POSITIVE = "DISMISSED_FALSE_POSITIVE"
    ESCALATED = "ESCALATED"
    REOPENED = "REOPENED"


class CasePriority(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class ResolutionCategory(str, Enum):
    TRUE_POSITIVE_FRAUD = "TRUE_POSITIVE_FRAUD"
    FALSE_POSITIVE_NORMAL_ACTIVITY = "FALSE_POSITIVE_NORMAL_ACTIVITY"
    CUSTOMER_DISPUTE = "CUSTOMER_DISPUTE"
    UNRESOLVED_ESCALATED = "UNRESOLVED_ESCALATED"
    OTHER = "OTHER"


VALID_TRANSITIONS: Dict[CaseStatus, set[CaseStatus]] = {
    CaseStatus.NEW_ALERT: {
        CaseStatus.UNDER_INVESTIGATION,
        CaseStatus.DISMISSED_FALSE_POSITIVE,
        CaseStatus.ESCALATED,
    },
    CaseStatus.UNDER_INVESTIGATION: {
        CaseStatus.CONFIRMED_FRAUD,
        CaseStatus.DISMISSED_FALSE_POSITIVE,
        CaseStatus.ESCALATED,
    },
    CaseStatus.ESCALATED: {
        CaseStatus.UNDER_INVESTIGATION,
        CaseStatus.CONFIRMED_FRAUD,
        CaseStatus.DISMISSED_FALSE_POSITIVE,
    },
    CaseStatus.CONFIRMED_FRAUD: {
        CaseStatus.REOPENED,
    },
    CaseStatus.DISMISSED_FALSE_POSITIVE: {
        CaseStatus.REOPENED,
    },
    CaseStatus.REOPENED: {
        CaseStatus.UNDER_INVESTIGATION,
        CaseStatus.CONFIRMED_FRAUD,
        CaseStatus.DISMISSED_FALSE_POSITIVE,
        CaseStatus.ESCALATED,
    },
}


class CaseCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    entity_id: str = Field(..., min_length=1, description="Primary ID being investigated (Transaction, Client, etc.)")
    entity_type: str = Field("Transaction", description="Entity type: Transaction, Client, Device, Location, Cluster")
    alert_id: Optional[str] = Field(None, description="Optional associated alert reference ID")
    title: Optional[str] = Field(None, description="Optional brief title for the case")
    summary: Optional[str] = Field(None, description="Optional case summary or background")
    priority: CasePriority = Field(CasePriority.MEDIUM, description="Initial investigation priority")
    assigned_analyst: Optional[str] = Field("unassigned", description="Assigned analyst username")
    risk_score: Optional[float] = Field(0.0, ge=0.0, le=100.0, description="Associated initial risk score")


class CaseUpdateAssignment(BaseModel):
    model_config = ConfigDict(extra="forbid")
    assigned_analyst: str = Field(..., min_length=1, description="Analyst identifier")
    actor: str = Field("analyst", description="Actor performing the reassignment")


class CaseUpdatePriority(BaseModel):
    model_config = ConfigDict(extra="forbid")
    priority: CasePriority = Field(..., description="New priority level")
    actor: str = Field("analyst", description="Actor performing the priority update")


class CaseStatusTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    target_status: CaseStatus = Field(..., description="Target status for transition")
    actor: str = Field("analyst", description="Actor performing the state change")
    reason: Optional[str] = Field(None, description="Optional general reason for transition")
    resolution_category: Optional[ResolutionCategory] = Field(None, description="Required when resolving case")
    resolution_explanation: Optional[str] = Field(None, description="Required when resolving or reopening case")
    expected_version: Optional[int] = Field(None, description="Optimistic concurrency control version")


class CaseNoteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note: str = Field(..., min_length=1, max_length=5000, description="Analyst observation or note")
    author: str = Field("analyst", description="Author of the note")


class CaseNote(BaseModel):
    note_id: str
    case_id: str
    author: str
    note: str
    created_at: str


class CaseAuditRecord(BaseModel):
    audit_id: str
    case_id: str
    action_type: str
    actor: str
    timestamp: str
    previous_value: Optional[Any] = None
    new_value: Optional[Any] = None
    reason: Optional[str] = None


class CaseGraphContext(BaseModel):
    case_id: str
    entity_id: str
    entity_type: str
    primary_node: Dict[str, Any] = {}
    counterparties: List[Dict[str, Any]] = []
    devices: List[Dict[str, Any]] = []
    locations: List[Dict[str, Any]] = []
    transactions: List[Dict[str, Any]] = []


class FraudCase(BaseModel):
    case_id: str
    entity_id: str
    entity_type: str
    alert_id: Optional[str] = None
    title: str
    summary: str
    status: CaseStatus
    priority: CasePriority
    assigned_analyst: str
    risk_score: float
    resolution_category: Optional[str] = None
    resolution_explanation: Optional[str] = None
    created_at: str
    updated_at: str
    version: int = 1
    notes_count: int = 0
    notes: List[CaseNote] = []
    audit_trail: List[CaseAuditRecord] = []
    graph_context: Optional[CaseGraphContext] = None


class CaseListResponse(BaseModel):
    total: int
    cases: List[FraudCase]
