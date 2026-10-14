from pydantic import BaseModel, ConfigDict, Field
from typing import Optional


class DeviceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={
        "example": {"device_type": "mobile", "os": "Android", "ip_address": "192.168.1.10", "is_suspicious": False}
    })
    device_id: Optional[str] = None
    device_type: str
    os: str
    ip_address: str
    is_suspicious: bool = False

class DeviceUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    device_type: Optional[str] = None
    os: Optional[str] = None
    ip_address: Optional[str] = None
    is_suspicious: Optional[bool] = None


class DeviceOut(BaseModel):
    device_id: str
    device_type: str
    os: str
    ip_address: str
    is_suspicious: Optional[bool] = False


class LocationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", json_schema_extra={
        "example": {"city": "Mumbai", "country": "India",
                    "latitude": 19.076, "longitude": 72.8777, "ip_address": "103.21.244.1", "is_high_risk": False}
    })
    location_id: Optional[str] = None
    city: str
    country: str
    latitude: float
    longitude: float
    ip_address: Optional[str] = None
    is_high_risk: bool = False

class LocationUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    city: Optional[str] = None
    country: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    ip_address: Optional[str] = None
    is_high_risk: Optional[bool] = None


class LocationOut(BaseModel):
    location_id: str
    city: str
    country: str
    latitude: float
    longitude: float
    ip_address: Optional[str] = None
    is_high_risk: Optional[bool] = False
