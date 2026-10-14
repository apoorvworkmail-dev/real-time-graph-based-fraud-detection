"""CRUD endpoints for the public /api resource paths."""
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, status
from neo4j import Session

from app.db.neo4j_driver import get_session
from app.schemas.client import ClientCreate, ClientUpdate
from app.schemas.device import DeviceCreate, DeviceUpdate, LocationCreate, LocationUpdate
from app.schemas.transaction import TransactionCreate, TransactionUpdate

router = APIRouter()


def _one(session: Session, query: str, **params: Any):
    return session.run(query, **params).single()


def _props(record, key: str):
    return dict(record[key])


@router.post("/clients", status_code=status.HTTP_201_CREATED, tags=["Clients"])
def create_client(body: ClientCreate, session: Session = Depends(get_session)):
    cid = body.client_id or f"CLT{uuid4().hex[:8].upper()}"
    if _one(session, "MATCH (n:Client {client_id:$id}) RETURN n", id=cid):
        raise HTTPException(409, "Client already exists")
    props = body.model_dump(exclude={"client_id"}) | {
        "client_id": cid, "risk_score": 5.0, "is_flagged": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _one(session, "CREATE (n:Client $props) RETURN n", props=props)
    return props


@router.get("/clients", tags=["Clients"])
def list_clients(skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=500), session: Session = Depends(get_session)):
    return [_props(r, "n") for r in session.run(
        "MATCH (n:Client) RETURN n ORDER BY n.client_id SKIP $skip LIMIT $limit", skip=skip, limit=limit
    )]


@router.get("/clients/{clientId}", tags=["Clients"])
def get_client(clientId: str, session: Session = Depends(get_session)):
    r = _one(session, "MATCH (n:Client {client_id:$id}) RETURN n", id=clientId)
    if not r:
        raise HTTPException(404, "Client not found")
    return _props(r, "n")


@router.put("/clients/{clientId}", tags=["Clients"])
def update_client(clientId: str, body: ClientUpdate, session: Session = Depends(get_session)):
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(400, "At least one field is required")
    r = _one(session, "MATCH (n:Client {client_id:$id}) SET n += $updates RETURN n", id=clientId, updates=updates)
    if not r:
        raise HTTPException(404, "Client not found")
    return _props(r, "n")


@router.delete("/clients/{clientId}", status_code=status.HTTP_204_NO_CONTENT, tags=["Clients"])
def delete_client(clientId: str, session: Session = Depends(get_session)):
    r = _one(session, "MATCH (n:Client {client_id:$id}) DETACH DELETE n RETURN count(n) AS deleted", id=clientId)
    if not r or r["deleted"] == 0:
        raise HTTPException(404, "Client not found")


@router.post("/transactions", status_code=status.HTTP_201_CREATED, tags=["Transactions"])
def create_transaction(body: TransactionCreate, session: Session = Depends(get_session)):
    tid = body.transaction_id or f"TXN{uuid4().hex[:8].upper()}"
    references = (
        (body.sender_id, "MATCH (n:Client {client_id:$id}) RETURN n", "Client"),
        (body.receiver_id, "MATCH (n:Client {client_id:$id}) RETURN n", "Client"),
        (body.device_id, "MATCH (n:Device {device_id:$id}) RETURN n", "Device"),
        (body.location_id, "MATCH (n:Location {location_id:$id}) RETURN n", "Location"),
    )
    for value, query, label in references:
        if value and not _one(session, query, id=value):
            raise HTTPException(404, f"{label} {value} not found")
    if _one(session, "MATCH (t:Transaction {transaction_id:$id}) RETURN t", id=tid):
        raise HTTPException(409, "Transaction already exists")
    props = {"transaction_id": tid, "amount": body.amount, "currency": body.currency,
             "transaction_type": body.transaction_type, "channel": body.channel, "status": "pending",
             "is_fraud": False, "fraud_score": 0.0, "timestamp": datetime.now(timezone.utc).isoformat()}
    q = """MATCH (s:Client {client_id:$sender}) MATCH (r:Client {client_id:$receiver})
             CREATE (t:Transaction $props) CREATE (s)-[:PERFORMED]->(t) CREATE (t)-[:TRANSFERRED_TO]->(r)"""
    if body.device_id:
        q += " WITH s,t MATCH (d:Device {device_id:$device}) CREATE (s)-[:USED_DEVICE]->(d)"
    if body.location_id:
        q += " WITH t MATCH (l:Location {location_id:$location}) CREATE (t)-[:ORIGINATED_FROM]->(l)"
    q += " RETURN t"
    params = {"sender": body.sender_id, "receiver": body.receiver_id, "props": props,
              "device": body.device_id, "location": body.location_id}
    r = _one(session, q, **params)
    if not r:
        raise HTTPException(404, "Sender or receiver not found")
    return _props(r, "t")


@router.get("/transactions", tags=["Transactions"])
def list_transactions(skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=500), session: Session = Depends(get_session)):
    return [_props(r, "n") for r in session.run(
        "MATCH (n:Transaction) RETURN n ORDER BY n.transaction_id SKIP $skip LIMIT $limit", skip=skip, limit=limit
    )]


@router.get("/transactions/{txId}", tags=["Transactions"])
def get_transaction(txId: str, session: Session = Depends(get_session)):
    r = _one(session, "MATCH (n:Transaction {transaction_id:$id}) RETURN n", id=txId)
    if not r:
        raise HTTPException(404, "Transaction not found")
    return _props(r, "n")


@router.put("/transactions/{txId}", tags=["Transactions"])
def update_transaction(txId: str, body: TransactionUpdate, session: Session = Depends(get_session)):
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(400, "At least one field is required")
    r = _one(session, "MATCH (n:Transaction {transaction_id:$id}) SET n += $updates RETURN n", id=txId, updates=updates)
    if not r:
        raise HTTPException(404, "Transaction not found")
    return _props(r, "n")


@router.delete("/transactions/{txId}", status_code=status.HTTP_204_NO_CONTENT, tags=["Transactions"])
def delete_transaction(txId: str, session: Session = Depends(get_session)):
    r = _one(session, "MATCH (n:Transaction {transaction_id:$id}) DETACH DELETE n RETURN count(n) AS deleted", id=txId)
    if not r or r["deleted"] == 0:
        raise HTTPException(404, "Transaction not found")


@router.post("/devices", status_code=status.HTTP_201_CREATED, tags=["Devices"])
def create_device(body: DeviceCreate, session: Session = Depends(get_session)):
    did = body.device_id or f"DEV{uuid4().hex[:8].upper()}"
    if _one(session, "MATCH (n:Device {device_id:$id}) RETURN n", id=did):
        raise HTTPException(409, "Device already exists")
    props = body.model_dump(exclude={"device_id"}) | {"device_id": did}
    _one(session, "CREATE (n:Device $props) RETURN n", props=props)
    return props


@router.get("/devices", tags=["Devices"])
def list_devices(skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=500), session: Session = Depends(get_session)):
    return [_props(r, "n") for r in session.run(
        "MATCH (n:Device) RETURN n ORDER BY n.device_id SKIP $skip LIMIT $limit", skip=skip, limit=limit
    )]


@router.get("/devices/{deviceId}", tags=["Devices"])
def get_device(deviceId: str, session: Session = Depends(get_session)):
    r = _one(session, "MATCH (n:Device {device_id:$id}) RETURN n", id=deviceId)
    if not r:
        raise HTTPException(404, "Device not found")
    return _props(r, "n")


@router.put("/devices/{deviceId}", tags=["Devices"])
def update_device(deviceId: str, body: DeviceUpdate, session: Session = Depends(get_session)):
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(400, "At least one field is required")
    r = _one(session, "MATCH (n:Device {device_id:$id}) SET n += $updates RETURN n", id=deviceId, updates=updates)
    if not r:
        raise HTTPException(404, "Device not found")
    return _props(r, "n")


@router.delete("/devices/{deviceId}", status_code=status.HTTP_204_NO_CONTENT, tags=["Devices"])
def delete_device(deviceId: str, session: Session = Depends(get_session)):
    r = _one(session, "MATCH (n:Device {device_id:$id}) DETACH DELETE n RETURN count(n) AS deleted", id=deviceId)
    if not r or r["deleted"] == 0:
        raise HTTPException(404, "Device not found")


@router.post("/locations", status_code=status.HTTP_201_CREATED, tags=["Locations"])
def create_location(body: LocationCreate, session: Session = Depends(get_session)):
    ip = body.ip_address
    if _one(session, "MATCH (n:Location {ip_address:$ip}) RETURN n", ip=ip):
        raise HTTPException(409, "Location already exists")
    props = body.model_dump() | {"location_id": body.location_id or f"LOC{uuid4().hex[:8].upper()}"}
    _one(session, "CREATE (n:Location $props) RETURN n", props=props)
    return props


@router.get("/locations", tags=["Locations"])
def list_locations(skip: int = Query(0, ge=0), limit: int = Query(50, ge=1, le=500), session: Session = Depends(get_session)):
    return [_props(r, "n") for r in session.run(
        "MATCH (n:Location) RETURN n ORDER BY n.location_id SKIP $skip LIMIT $limit", skip=skip, limit=limit
    )]


@router.get("/locations/{ipAddress}", tags=["Locations"])
def get_location(ipAddress: str, session: Session = Depends(get_session)):
    r = _one(session, "MATCH (n:Location {ip_address:$ip}) RETURN n", ip=ipAddress)
    if not r:
        raise HTTPException(404, "Location not found")
    return _props(r, "n")


@router.put("/locations/{ipAddress}", tags=["Locations"])
def update_location(ipAddress: str, body: LocationUpdate, session: Session = Depends(get_session)):
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(400, "At least one field is required")
    r = _one(session, "MATCH (n:Location {ip_address:$ip}) SET n += $updates RETURN n", ip=ipAddress, updates=updates)
    if not r:
        raise HTTPException(404, "Location not found")
    return _props(r, "n")


@router.delete("/locations/{ipAddress}", status_code=status.HTTP_204_NO_CONTENT, tags=["Locations"])
def delete_location(ipAddress: str, session: Session = Depends(get_session)):
    r = _one(session, "MATCH (n:Location {ip_address:$ip}) DETACH DELETE n RETURN count(n) AS deleted", ip=ipAddress)
    if not r or r["deleted"] == 0:
        raise HTTPException(404, "Location not found")
