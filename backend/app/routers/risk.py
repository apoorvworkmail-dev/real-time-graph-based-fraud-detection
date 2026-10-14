from fastapi import APIRouter, Depends, HTTPException, Query
from neo4j import Session

from app.db.neo4j_driver import get_session
from app.auth.dependencies import require_permission
from app.services.risk_scoring import (
    RISK_LEVEL_THRESHOLDS,
    score_clients,
    score_transactions,
)

router = APIRouter(dependencies=[Depends(require_permission("risk:read"))])


@router.get("/client/{clientId}", summary="Graph-Based Risk Score for a client")
def client_risk(clientId: str, session: Session = Depends(get_session)):
    scores = score_clients(session, clientId)
    if not scores:
        raise HTTPException(status_code=404, detail=f"Client {clientId} not found")
    return scores[0]


@router.get("/transaction/{txId}", summary="Graph-Based Risk Score for a transaction")
def transaction_risk(txId: str, session: Session = Depends(get_session)):
    scores = score_transactions(session, txId)
    if not scores:
        raise HTTPException(status_code=404, detail=f"Transaction {txId} not found")
    return scores[0]


@router.get("/high-risk", summary="List entities with high Graph-Based Risk Scores")
def high_risk_entities(
    min_score: float = Query(RISK_LEVEL_THRESHOLDS["HIGH"], ge=0, le=100),
    limit: int = Query(100, ge=1, le=500),
    session: Session = Depends(get_session),
):
    # Both sets come from one Neo4j graph query apiece; scoring and ordering are deterministic.
    scores = score_clients(session) + score_transactions(session)
    high_risk = [item for item in scores if item["riskScore"] >= min_score]
    high_risk.sort(key=lambda item: (-item["riskScore"], item["entityId"]))
    return high_risk[:limit]
