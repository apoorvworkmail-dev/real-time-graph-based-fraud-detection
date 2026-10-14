from fastapi import APIRouter, Depends, HTTPException, Query, status
from neo4j import Session
from app.db.neo4j_driver import get_session
from app.schemas.device import LocationCreate, LocationUpdate
from app.schemas.auth import UserOut
from app.auth.dependencies import require_permission
from typing import Optional
import uuid

router = APIRouter()


@router.get("/", summary="List all locations")
def list_locations(
    is_high_risk: Optional[bool] = Query(None, description="Filter by high-risk flag"),
    session: Session = Depends(get_session),
    current_user: UserOut = Depends(require_permission("graph:read")),
):
    where = "WHERE l.is_high_risk = $flag" if is_high_risk is not None else ""
    params = {}
    if is_high_risk is not None:
        params["flag"] = is_high_risk
    result = session.run(f"MATCH (l:Location) {where} RETURN l ORDER BY l.country", **params)
    return [dict(r["l"]) for r in result]


@router.get("/{location_id}", summary="Get location by ID")
def get_location(
    location_id: str,
    session: Session = Depends(get_session),
    current_user: UserOut = Depends(require_permission("graph:read")),
):
    result = session.run("""
        MATCH (l:Location {location_id: $lid})
        OPTIONAL MATCH (t:Transaction)-[:ORIGINATED_FROM]->(l)
        RETURN l, count(t) as transaction_count,
               sum(CASE WHEN t.is_fraud THEN 1 ELSE 0 END) as fraud_count
    """, lid=location_id).single()
    if not result:
        raise HTTPException(status_code=404, detail=f"Location {location_id} not found")
    data = dict(result["l"])
    data["transaction_count"] = result["transaction_count"]
    data["fraud_count"] = result["fraud_count"]
    return data


@router.post("/", status_code=status.HTTP_201_CREATED, summary="Create a location")
def create_location(
    body: LocationCreate,
    session: Session = Depends(get_session),
    current_user: UserOut = Depends(require_permission("entities:write")),
):
    """Create a Location node. (Admin only)"""
    lid = body.location_id or f"LOC{str(uuid.uuid4())[:6].upper()}"
    exists = session.run("MATCH (l:Location {location_id:$lid}) RETURN l", lid=lid).single()
    if exists:
        raise HTTPException(status_code=409, detail=f"Location {lid} already exists")
    props = body.model_dump()
    props["location_id"] = lid
    session.run("CREATE (l:Location $props)", props=props)
    return {"message": "Location created", "location_id": lid}


@router.put("/{location_id}", summary="Update a location")
def update_location(
    location_id: str,
    body: LocationUpdate,
    session: Session = Depends(get_session),
    current_user: UserOut = Depends(require_permission("entities:write")),
):
    """Update a Location node. (Admin only)"""
    exists = session.run("MATCH (l:Location {location_id:$lid}) RETURN l", lid=location_id).single()
    if not exists:
        raise HTTPException(status_code=404, detail=f"Location {location_id} not found")
    updates = {k: v for k, v in body.model_dump().items() if v is not None}
    if not updates:
        raise HTTPException(status_code=400, detail="No fields to update")
    set_clause = ", ".join([f"l.{k} = ${k}" for k in updates])
    session.run(f"MATCH (l:Location {{location_id:$lid}}) SET {set_clause}", lid=location_id, **updates)
    return {"message": "Location updated", "location_id": location_id}


@router.delete("/{location_id}", summary="Delete a location")
def delete_location(
    location_id: str,
    session: Session = Depends(get_session),
    current_user: UserOut = Depends(require_permission("entities:write")),
):
    """Delete a Location node. (Admin only)"""
    exists = session.run("MATCH (l:Location {location_id:$lid}) RETURN l", lid=location_id).single()
    if not exists:
        raise HTTPException(status_code=404, detail=f"Location {location_id} not found")
    session.run("MATCH (l:Location {location_id:$lid}) DETACH DELETE l", lid=location_id)
    return {"message": f"Location {location_id} deleted"}
