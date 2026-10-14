from pydantic import BaseModel, ConfigDict, Field, field_validator
from typing import Optional, List, Dict, Any
from datetime import datetime


class TransactionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={
        "example": {
            "amount": 5000.0,
            "currency": "INR",
            "transaction_type": "transfer",
            "channel": "mobile_app",
            "sender_id": "CLT001",
            "receiver_id": "CLT002",
            "device_id": "DEV001",
            "location_id": "LOC001",
        }
    })
    transaction_id: Optional[str] = None
    amount: float = Field(gt=0)
    currency: str = "INR"
    transaction_type: str = "transfer"
    channel: str = "mobile_app"
    sender_id: str
    receiver_id: str
    device_id: Optional[str] = None
    location_id: Optional[str] = None


class TransactionUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Optional[str] = None
    is_fraud: Optional[bool] = None
    fraud_score: Optional[float] = None


class TransactionOut(BaseModel):
    transaction_id: str
    amount: float
    currency: str = "INR"
    status: Optional[str] = None
    transaction_type: Optional[str] = None
    timestamp: Optional[str] = None
    is_fraud: Optional[bool] = False
    fraud_score: Optional[float] = None
    channel: Optional[str] = None


# ── Phase 7 Event Contracts ──────────────────────────────────────────

class TransactionEvent(BaseModel):
    """
    Validated transaction event schema for real-time ingestion and simulation.
    Enforces strict field boundaries, valid IDs, non-identical counterparties,
    and ISO-8601 timestamps.
    """
    model_config = ConfigDict(extra="forbid", json_schema_extra={
        "example": {
            "transaction_id": "TXN_SIM_A1B2C3D4",
            "sender_id": "CLT001",
            "receiver_id": "CLT002",
            "amount": 4500.0,
            "currency": "INR",
            "channel": "mobile_app",
            "transaction_type": "transfer",
            "device_id": "DEV001",
            "location_id": "LOC001",
            "scenario": "normal",
            "timestamp": "2026-10-12T23:30:00Z"
        }
    })

    transaction_id: str = Field(..., min_length=4, max_length=64, description="Unique transaction/event ID")
    sender_id: str = Field(..., min_length=3, max_length=32, description="Sender client ID")
    receiver_id: str = Field(..., min_length=3, max_length=32, description="Receiver client ID")
    amount: float = Field(..., gt=0, le=10_000_000.0, description="Transaction amount (0 < amount <= 10,000,000)")
    currency: str = Field(default="INR", max_length=10)
    transaction_type: str = Field(default="transfer", max_length=32)
    channel: str = Field(default="mobile_app", max_length=32)
    device_id: Optional[str] = Field(default=None, max_length=32)
    location_id: Optional[str] = Field(default=None, max_length=32)
    scenario: Optional[str] = Field(default="normal", max_length=32)
    timestamp: Optional[str] = Field(default=None, description="ISO-8601 UTC timestamp")

    @field_validator("sender_id", "receiver_id")
    @classmethod
    def validate_client_ids(cls, v: str) -> str:
        val = v.strip()
        if not val:
            raise ValueError("Client ID must not be empty or whitespace")
        return val

    @field_validator("receiver_id")
    @classmethod
    def validate_distinct_counterparties(cls, v: str, info) -> str:
        sender = info.data.get("sender_id")
        if sender and sender == v:
            raise ValueError("Sender and receiver client IDs cannot be identical")
        return v

    @field_validator("timestamp")
    @classmethod
    def validate_iso_timestamp(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return None
        clean = v.replace("Z", "+00:00")
        try:
            datetime.fromisoformat(clean)
        except Exception:
            raise ValueError("timestamp must be a valid ISO-8601 formatted date string")
        return v


class FraudAlertPayload(BaseModel):
    """Standardized schema for qualified fraud alerts published via WebSockets."""
    alert_id: str
    entity_id: str
    entity_type: str = "Transaction"
    sender_id: str
    receiver_id: str
    amount: float
    scenario: str
    risk_score: float
    risk_level: str
    risk_reason: str
    reasons: List[Dict[str, Any]] = []
    timestamp: str
    connected_entities: List[str] = []


class TransactionEventResult(BaseModel):
    """Structured processing outcome for a submitted or generated transaction event."""
    transaction_id: str
    status: str  # "processed", "idempotent_duplicate", "failed", "partial_success"
    persisted: bool
    is_fraud: bool
    fraud_score: float
    risk_level: str
    is_alert_qualified: bool
    scenario: str
    message: str
    alert: Optional[FraudAlertPayload] = None
    reasons: List[Dict[str, Any]] = []


class SimulatorConfigUpdate(BaseModel):
    """Permitted configuration parameters for the stream simulator."""
    model_config = ConfigDict(extra="forbid")
    interval_seconds: Optional[float] = Field(None, ge=0.5, le=30.0, description="Delay between events (0.5s - 30.0s)")
    batch_size: Optional[int] = Field(None, ge=1, le=50, description="Events processed per tick (1 - 50)")
    active_scenario: Optional[str] = Field(None, description="Scenario or pattern to generate")
    fraud_probability: Optional[float] = Field(None, ge=0.0, le=1.0, description="Ratio of suspicious vs normal events")
