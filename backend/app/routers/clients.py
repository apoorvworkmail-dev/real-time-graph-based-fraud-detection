from fastapi import APIRouter, Depends, HTTPException, status
from neo4j import Session
from app.db.neo4j_driver import get_session
from app.schemas.client import ClientCreate, ClientUpdate, ClientOut
from app.schemas.auth import UserOut
from app.auth.dependencies import require_permission
from typing import List, Optional
import uuid
from datetime import datetime

router = APIRouter()


@router.get("/", response_model=List[dict], summary="List all clients")
def list_clients(
    skip: int = 0,
    limit: int = 50,
    is_flagged: Optional[bool] = None,
    session: Session = Depends(get_session),
    current_user: UserOut = Depends(require_permission("graph:read")),
):
    """Retrieve a paginated list of clients. Optionally filter by fraud flag."""
    where = "WHERE c.is_flagged = $flag" if is_flagged is not None else ""
    query = f"MATCH (c:Client) {where} RETURN c ORDER BY c.risk_score DESC SKIP $skip LIMIT $limit"
    params = {"skip": skip, "limit": limit}
    if is_flagged is not None:
        params["flag"] = is_flagged
    result = session.run(query, **params)
    return [dict(r["c"]) for r in result]


@router.get("/stats", summary="Get client statistics")
def client_stats(
    session: Session = Depends(get_session),
    current_user: UserOut = Depends(require_permission("graph:read")),
):
    """Returns total count, flagged count, avg risk score."""
    r = session.run("""
        MATCH (c:Client)
        RETURN count(c) as total,
               sum(CASE WHEN c.is_flagged THEN 1 ELSE 0 END) as flagged,
               round(avg(c.risk_score), 2) as avg_risk
    """).single()
    return dict(r)


@router.get("/{client_id}", summary="Get client by ID")
def get_client(
    client_id: str,
    session: Session = Depends(get_session),
    current_user: UserOut = Depends(require_permission("graph:read")),
):
    """Retrieve a single client node with their transaction count."""
    result = session.run("""
        MATCH (c:Client {client_id: $cid})
        OPTIONAL MATCH (c)-[:PERFORMED]->(t:Transaction)
        OPTIONAL MATCH (c)-[:USED_DEVICE]->(d:Device)
        RETURN c,
               count(DISTINCT t) as transaction_count,
               count(DISTINCT d) as device_count
    """, cid=client_id).single()
    if not result:
        raise HTTPException(status_code=404, detail=f"Client {client_id} not found")
    data = dict(result["c"])
    data["transaction_count"] = result["transaction_count"]
    data["device_count"] = result["device_count"]
    return data


@router.post("/", status_code=status.HTTP_201_CREATED, summary="Create a new client")
def create_client(
    body: ClientCreate,
    session: Session = Depends(get_session),
    current_user: UserOut = Depends(require_permission("entities:write")),
):
    """Create a new Client node. (Admin only)"""
    cid = body.client_id or f"CLT{str(uuid.uuid4())[:6].upper()}"
    exists = session.run("MATCH (c:Client {client_id:$cid}) RETURN c", cid=cid).single()
    if exists:
        raise HTTPException(status_code=409, detail=f"Client {cid} already exists")
    props = body.model_dump()
    props["client_id"] = cid
    props["risk_score"] = 5.0
    props["is_flagged"] = False
    props["created_at"] = datetime.utcnow().isoformat() + "Z"
    session.run("CREATE (c:Client $props)", props=props)
    return {"message": "Client created", "client_id": cid, "data": props}


@router.put("/{client_id}", summary="Update a client")
def update_client(
    client_id: str,
    body: ClientUpdate,
    session: Session = Depends(get_session),
    current_user: UserOut = Depends(require_permission("entities:write")),
):
    """Update mutable fields of a Client node. (Admin only)"""
    exists = session.run("MATCH (c:Client {client_id:$cid}) RETURN c", cid=client_id).single()
    if not exists:
        raise HTTPException(status_code=404, detail=f"Client {client_id} not found")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    set_clause = ", ".join([f"c.{k} = ${k}" for k in updates])
    session.run(f"MATCH (c:Client {{client_id:$cid}}) SET {set_clause}", cid=client_id, **updates)
    return {"message": "Client updated", "client_id": client_id, "updated_fields": list(updates.keys())}


@router.delete("/{client_id}", summary="Delete a client")
def delete_client(
    client_id: str,
    session: Session = Depends(get_session),
    current_user: UserOut = Depends(require_permission("entities:write")),
):
    """Delete a Client node and all its relationships. (Admin only)"""
    exists = session.run("MATCH (c:Client {client_id:$cid}) RETURN c", cid=client_id).single()
    if not exists:
        raise HTTPException(status_code=404, detail=f"Client {client_id} not found")
    session.run("MATCH (c:Client {client_id:$cid}) DETACH DELETE c", cid=client_id)
    return {"message": f"Client {client_id} deleted"}


@router.get("/{client_id}/transactions", summary="Get client's transactions")
def get_client_transactions(
    client_id: str,
    session: Session = Depends(get_session),
    current_user: UserOut = Depends(require_permission("graph:read")),
):
    """List all transactions performed by this client."""
    result = session.run("""
        MATCH (c:Client {client_id: $cid})-[:PERFORMED]->(t:Transaction)
        OPTIONAL MATCH (t)-[:TRANSFERRED_TO]->(receiver:Client)
        OPTIONAL MATCH (t)-[:ORIGINATED_FROM]->(loc:Location)
        RETURN t, receiver.name as receiver_name, loc.city as location
        ORDER BY t.timestamp DESC LIMIT 50
    """, cid=client_id)
    rows = []
    for r in result:
        d = dict(r["t"])
        d["receiver_name"] = r["receiver_name"]
        d["location"] = r["location"]
        rows.append(d)
    return rows
