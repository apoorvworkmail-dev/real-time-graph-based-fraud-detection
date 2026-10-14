from pydantic import BaseModel, EmailStr, ConfigDict, Field
from typing import Optional
from datetime import datetime


class ClientCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={
        "example": {"name": "Aarav Shah", "email": "aarav.shah@example.com", "phone": "+91-9876543210",
                    "account_type": "savings", "account_balance": 25000.0, "kyc_verified": True}
    })
    client_id: Optional[str] = None
    name: str = Field(min_length=1, max_length=200)
    email: EmailStr
    phone: Optional[str] = None
    account_type: str = "savings"
    account_balance: float = Field(default=0.0, ge=0)
    kyc_verified: bool = True

class ClientUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    account_type: Optional[str] = None
    account_balance: Optional[float] = None
    risk_score: Optional[float] = None
    is_flagged: Optional[bool] = None
    kyc_verified: Optional[bool] = None


class ClientOut(BaseModel):
    client_id: str
    name: str
    email: str
    phone: Optional[str] = None
    account_type: str = "savings"
    account_balance: float = 0.0
    risk_score: Optional[float] = None
    is_flagged: Optional[bool] = None
    kyc_verified: Optional[bool] = None
    created_at: Optional[str] = None
