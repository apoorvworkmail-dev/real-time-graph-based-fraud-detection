from fastapi import APIRouter, Depends, HTTPException, status
from neo4j import Session
from app.db.neo4j_driver import get_session
from app.schemas.transaction import TransactionCreate, TransactionUpdate
from app.schemas.auth import UserOut
from app.auth.dependencies import require_permission
from typing import List, Optional
import uuid
from datetime import datetime

router = APIRouter()


@router.get("/", summary="List all transactions")
def list_transactions(
    skip: int = 0,
    limit: int = 50,
    is_fraud: Optional[bool] = None,
    min_amount: Optional[float] = None,
    session: Session = Depends(get_session),
    current_user: UserOut = Depends(require_permission("graph:read")),
):
    """Paginated list of transactions with optional fraud/amount filters."""
    conditions = []
    params: dict = {"skip": skip, "limit": limit}
    if is_fraud is not None:
        conditions.append("t.is_fraud = $is_fraud")
        params["is_fraud"] = is_fraud
    if min_amount is not None:
        conditions.append("t.amount >= $min_amount")
        params["min_amount"] = min_amount
    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""
    query = f"""
        MATCH (s:Client)-[:PERFORMED]->(t:Transaction)
        OPTIONAL MATCH (t)-[:TRANSFERRED_TO]->(r:Client)
        OPTIONAL MATCH (t)-[:ORIGINATED_FROM]->(loc:Location)
        {where}
        RETURN t, s.name as sender_name, r.name as receiver_name, loc.city as location
        ORDER BY t.timestamp DESC SKIP $skip LIMIT $limit
    """
    result = session.run(query, **params)
    rows = []
    for rec in result:
        d = dict(rec["t"])
        d["sender_name"] = rec["sender_name"]
        d["receiver_name"] = rec["receiver_name"]
        d["location"] = rec["location"]
        rows.append(d)
    return rows


@router.get("/stats", summary="Transaction statistics")
def transaction_stats(
    session: Session = Depends(get_session),
    current_user: UserOut = Depends(require_permission("graph:read")),
):
    r = session.run("""
        MATCH (t:Transaction)
        RETURN count(t) as total,
               sum(CASE WHEN t.is_fraud THEN 1 ELSE 0 END) as fraud_count,
               round(sum(t.amount), 2) as total_volume,
               round(avg(t.amount), 2) as avg_amount,
               round(avg(t.fraud_score), 2) as avg_fraud_score
    """).single()
    return dict(r)


@router.get("/{transaction_id}", summary="Get transaction by ID")
def get_transaction(
    transaction_id: str,
    session: Session = Depends(get_session),
    current_user: UserOut = Depends(require_permission("graph:read")),
):
    result = session.run("""
        MATCH (s:Client)-[:PERFORMED]->(t:Transaction {transaction_id: $tid})
        OPTIONAL MATCH (t)-[:TRANSFERRED_TO]->(r:Client)
        OPTIONAL MATCH (t)-[:ORIGINATED_FROM]->(loc:Location)
        OPTIONAL MATCH (s)-[:USED_DEVICE]->(d:Device)
        RETURN t, s.name as sender_name, s.client_id as sender_id,
               r.name as receiver_name, r.client_id as receiver_id,
               loc as location, d as device
    """, tid=transaction_id).single()
    if not result:
        raise HTTPException(status_code=404, detail=f"Transaction {transaction_id} not found")
    d = dict(result["t"])
    d["sender"]   = {"id": result["sender_id"],   "name": result["sender_name"]}
    d["receiver"] = {"id": result["receiver_id"],  "name": result["receiver_name"]}
    d["location"] = dict(result["location"]) if result["location"] else None
    d["device"]   = dict(result["device"])   if result["device"]   else None
    return d


@router.post("/", status_code=status.HTTP_201_CREATED, summary="Create a transaction")
def create_transaction(
    body: TransactionCreate,
    session: Session = Depends(get_session),
    current_user: UserOut = Depends(require_permission("entities:write")),
):
    """Create a Transaction node with PERFORMED, TRANSFERRED_TO, USED_DEVICE, ORIGINATED_FROM edges. (Admin only)"""
    tid = body.transaction_id or f"TXN{str(uuid.uuid4())[:6].upper()}"
    # Validate sender/receiver exist
    for cid in [body.sender_id, body.receiver_id]:
        if not session.run("MATCH (c:Client {client_id:$cid}) RETURN c", cid=cid).single():
            raise HTTPException(status_code=404, detail=f"Client {cid} not found")
    props = {
        "transaction_id": tid,
        "amount": body.amount,
        "currency": body.currency,
        "transaction_type": body.transaction_type,
        "channel": body.channel,
        "status": "pending",
        "is_fraud": False,
        "fraud_score": 0.0,
        "timestamp": datetime.utcnow().isoformat() + "Z",
    }
    cypher = """
        MATCH (s:Client {client_id: $sid})
        MATCH (r:Client {client_id: $rid})
        CREATE (t:Transaction $props)
        CREATE (s)-[:PERFORMED]->(t)
        CREATE (t)-[:TRANSFERRED_TO]->(r)
    """
    params = {"sid": body.sender_id, "rid": body.receiver_id, "props": props}
    if body.device_id:
        cypher += " WITH s,t MATCH (d:Device {device_id:$did}) CREATE (s)-[:USED_DEVICE]->(d)"
        params["did"] = body.device_id
    if body.location_id:
        cypher += " WITH t MATCH (l:Location {location_id:$lid}) CREATE (t)-[:ORIGINATED_FROM]->(l)"
        params["lid"] = body.location_id
    session.run(cypher, **params)
    return {"message": "Transaction created", "transaction_id": tid, "data": props}


@router.put("/{transaction_id}", summary="Update a transaction")
def update_transaction(
    transaction_id: str,
    body: TransactionUpdate,
    session: Session = Depends(get_session),
    current_user: UserOut = Depends(require_permission("entities:write")),
):
    """Update mutable fields of a transaction. (Admin only)"""
    exists = session.run("MATCH (t:Transaction {transaction_id:$tid}) RETURN t", tid=transaction_id).single()
    if not exists:
        raise HTTPException(status_code=404, detail=f"Transaction {transaction_id} not found")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    set_clause = ", ".join([f"t.{k} = ${k}" for k in updates])
    session.run(f"MATCH (t:Transaction {{transaction_id:$tid}}) SET {set_clause}", tid=transaction_id, **updates)
    return {"message": "Transaction updated", "transaction_id": transaction_id}


@router.delete("/{transaction_id}", summary="Delete a transaction")
def delete_transaction(
    transaction_id: str,
    session: Session = Depends(get_session),
    current_user: UserOut = Depends(require_permission("entities:write")),
):
    """Delete a transaction node. (Admin only)"""
    exists = session.run("MATCH (t:Transaction {transaction_id:$tid}) RETURN t", tid=transaction_id).single()
    if not exists:
        raise HTTPException(status_code=404, detail=f"Transaction {transaction_id} not found")
    session.run("MATCH (t:Transaction {transaction_id:$tid}) DETACH DELETE t", tid=transaction_id)
    return {"message": f"Transaction {transaction_id} deleted"}
