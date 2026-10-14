from fastapi import APIRouter, Depends, HTTPException, status
from neo4j import Session
from app.db.neo4j_driver import get_session
from app.schemas.device import DeviceCreate, DeviceUpdate
from app.schemas.auth import UserOut
from app.auth.dependencies import require_permission
from typing import List, Optional
import uuid

router = APIRouter()


@router.get("/", summary="List all devices")
def list_devices(
    is_suspicious: Optional[bool] = None,
    session: Session = Depends(get_session),
    current_user: UserOut = Depends(require_permission("graph:read")),
):
    where = "WHERE d.is_suspicious = $flag" if is_suspicious is not None else ""
    params = {}
    if is_suspicious is not None:
        params["flag"] = is_suspicious
    result = session.run(f"MATCH (d:Device) {where} RETURN d ORDER BY d.device_id", **params)
    return [dict(r["d"]) for r in result]


@router.get("/{device_id}", summary="Get device by ID")
def get_device(
    device_id: str,
    session: Session = Depends(get_session),
    current_user: UserOut = Depends(require_permission("graph:read")),
):
    result = session.run("""
        MATCH (d:Device {device_id: $did})
        OPTIONAL MATCH (c:Client)-[:USED_DEVICE]->(d)
        RETURN d, collect(c.client_id) as users
    """, did=device_id).single()
    if not result:
        raise HTTPException(status_code=404, detail=f"Device {device_id} not found")
    data = dict(result["d"])
    data["used_by_clients"] = result["users"]
    data["shared_by_count"] = len(result["users"])
    return data


@router.post("/", status_code=status.HTTP_201_CREATED, summary="Create a device")
def create_device(
    body: DeviceCreate,
    session: Session = Depends(get_session),
    current_user: UserOut = Depends(require_permission("entities:write")),
):
    """Create a Device node. (Admin only)"""
    did = body.device_id or f"DEV{str(uuid.uuid4())[:6].upper()}"
    exists = session.run("MATCH (d:Device {device_id:$did}) RETURN d", did=did).single()
    if exists:
        raise HTTPException(status_code=409, detail=f"Device {did} already exists")
    props = body.model_dump()
    props["device_id"] = did
    session.run("CREATE (d:Device $props)", props=props)
    return {"message": "Device created", "device_id": did}


@router.put("/{device_id}", summary="Update a device")
def update_device(
    device_id: str,
    body: DeviceUpdate,
    session: Session = Depends(get_session),
    current_user: UserOut = Depends(require_permission("entities:write")),
):
    """Update a Device node. (Admin only)"""
    exists = session.run("MATCH (d:Device {device_id:$did}) RETURN d", did=device_id).single()
    if not exists:
        raise HTTPException(status_code=404, detail=f"Device {device_id} not found")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    set_clause = ", ".join([f"d.{k} = ${k}" for k in updates])
    session.run(f"MATCH (d:Device {{device_id:$did}}) SET {set_clause}", did=device_id, **updates)
    return {"message": "Device updated", "device_id": device_id}


@router.delete("/{device_id}", summary="Delete a device")
def delete_device(
    device_id: str,
    session: Session = Depends(get_session),
    current_user: UserOut = Depends(require_permission("entities:write")),
):
    """Delete a Device node. (Admin only)"""
    exists = session.run("MATCH (d:Device {device_id:$did}) RETURN d", did=device_id).single()
    if not exists:
        raise HTTPException(status_code=404, detail=f"Device {device_id} not found")
    session.run("MATCH (d:Device {device_id:$did}) DETACH DELETE d", did=device_id)
    return {"message": f"Device {device_id} deleted"}
