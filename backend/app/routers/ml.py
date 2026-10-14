"""
Phase 8 — Machine Learning & Graph Analytics Router.
Exposes endpoints for model metadata & evaluation metrics,
account-level fraud predictions, and graph community/ring analytics.
"""

from typing import List, Dict, Any, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel

from app.services.ml_service import ml_service
from app.db.neo4j_driver import get_session
from app.auth.dependencies import require_permission

router = APIRouter(dependencies=[Depends(require_permission("ml:read"))])


@router.get("/info", summary="Get ML model metadata and evaluation scorecard")
def get_model_information():
    """
    Returns model version, architecture, train/test evaluation metrics
    (Precision, Recall, F1, ROC-AUC, PR-AUC, Confusion Matrix),
    feature importances, and known synthetic dataset limitations.
    """
    info = ml_service.get_model_info()
    if "error" in info:
        raise HTTPException(status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=info["error"])
    return info


@router.get("/predict/client/{client_id}", summary="Predict fraud probability for an account")
def predict_client_fraud(client_id: str, session=Depends(get_session)):
    """
    Extracts leakage-safe topological graph features and generates
    ML fraud probability, prediction classification, contributing factors,
    and a comparison with the deterministic rule-based score.
    """
    try:
        res = ml_service.predict_client(client_id, session=session)
        if "error" in res:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=res["error"])
        return res
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get("/communities", summary="Detect suspicious graph rings and communities")
def get_graph_communities(session=Depends(get_session)):
    """
    Identifies tightly coupled graph clusters, physical device-sharing rings,
    and circular fund layering chains across accounts.
    """
    try:
        communities = ml_service.get_graph_communities(session=session)
        return {"totalCommunities": len(communities), "communities": communities}
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))
