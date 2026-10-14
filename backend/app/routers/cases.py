"""
Phase 9 & 10 — Fraud Investigation & Case Management API Endpoints with RBAC.
Provides:
  - Case listing and multi-criteria filtering (cases:read)
  - Single case retrieval with rich graph neighborhood context (cases:read)
  - Idempotent case creation from alerts or manual investigation (cases:create)
  - Analyst assignment & priority management (cases:assign, cases:priority)
  - Strict lifecycle state transitions with resolution rationale validation (cases:transition, cases:reopen)
  - Concurrency checks via version tracking
  - Timestamped analyst observations and append-only audit trail (cases:notes, cases:audit)
  - Enforced actor identity preservation from authenticated JWT claims.
"""

from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.dependencies import require_permission
from app.schemas.auth import UserOut
from app.schemas.case import (
    CaseAuditRecord,
    CaseCreate,
    CaseListResponse,
    CaseNote,
    CaseNoteCreate,
    CasePriority,
    CaseStatus,
    CaseStatusTransition,
    CaseUpdateAssignment,
    CaseUpdatePriority,
    FraudCase,
)
from app.services.case_service import case_service

router = APIRouter(prefix="/cases", tags=["Case Management"])


@router.get("", response_model=CaseListResponse, summary="List and filter fraud cases")
def list_cases(
    status: Optional[CaseStatus] = Query(None, description="Filter by case status"),
    priority: Optional[CasePriority] = Query(None, description="Filter by severity priority"),
    analyst: Optional[str] = Query(None, description="Filter by assigned analyst"),
    entity_type: Optional[str] = Query(None, description="Filter by entity type (Transaction, Client)"),
    search: Optional[str] = Query(None, description="Search term for case ID, entity ID, or title"),
    limit: int = Query(50, ge=1, le=200, description="Page limit"),
    skip: int = Query(0, ge=0, description="Offset for pagination"),
    current_user: UserOut = Depends(require_permission("cases:read")),
):
    cases, total = case_service.list_cases(
        status=status,
        priority=priority,
        assigned_analyst=analyst,
        entity_type=entity_type,
        search=search,
        limit=limit,
        skip=skip,
    )
    return CaseListResponse(total=total, cases=cases)


@router.get("/{case_id}", response_model=FraudCase, summary="Retrieve a case with graph context and audit history")
def get_case(
    case_id: str,
    current_user: UserOut = Depends(require_permission("cases:read")),
):
    case = case_service.get_case(case_id)
    if not case:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Fraud case '{case_id}' does not exist.",
        )
    return case


@router.post("", response_model=FraudCase, status_code=status.HTTP_201_CREATED, summary="Create a new fraud investigation case")
def create_case(
    payload: CaseCreate,
    current_user: UserOut = Depends(require_permission("cases:create")),
):
    try:
        case, created = case_service.create_case(payload, actor=current_user.username)
        return case
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.patch("/{case_id}/assign", response_model=FraudCase, summary="Assign or reassign an analyst")
def assign_analyst(
    case_id: str,
    payload: CaseUpdateAssignment,
    current_user: UserOut = Depends(require_permission("cases:assign")),
):
    try:
        # Enforce authentic actor identity from token
        return case_service.update_assignment(case_id, payload.assigned_analyst, actor=current_user.username)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Case '{case_id}' not found.")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.patch("/{case_id}/priority", response_model=FraudCase, summary="Update case severity/priority")
def update_priority(
    case_id: str,
    payload: CaseUpdatePriority,
    current_user: UserOut = Depends(require_permission("cases:priority")),
):
    try:
        # Enforce authentic actor identity from token
        return case_service.update_priority(case_id, payload.priority, actor=current_user.username)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Case '{case_id}' not found.")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/{case_id}/transition", response_model=FraudCase, summary="Transition case lifecycle status")
def transition_case_status(
    case_id: str,
    payload: CaseStatusTransition,
    current_user: UserOut = Depends(require_permission("cases:transition")),
):
    # Specialized permission check: resolving cases requires cases:resolve
    if payload.target_status in (CaseStatus.CONFIRMED_FRAUD, CaseStatus.DISMISSED_FALSE_POSITIVE):
        if "cases:resolve" not in current_user.permissions and "admin:all" not in current_user.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: Resolving cases requires 'cases:resolve' permission (Compliance Officer or Admin).",
            )

    # Specialized permission check: reopening resolved cases requires cases:reopen
    if payload.target_status == CaseStatus.REOPENED:
        if "cases:reopen" not in current_user.permissions and "admin:all" not in current_user.permissions:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Forbidden: Reopening resolved cases requires 'cases:reopen' permission (Compliance Officer or Admin).",
            )

    try:
        # Overwrite payload actor with verified user identity
        payload_with_actor = payload.model_copy(update={"actor": current_user.username})
        return case_service.transition_status(case_id, payload_with_actor)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Case '{case_id}' not found.")
    except ValueError as val_err:
        err_msg = str(val_err)
        if "Concurrency conflict" in err_msg:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=err_msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err_msg)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.post("/{case_id}/notes", response_model=CaseNote, status_code=status.HTTP_201_CREATED, summary="Add an analyst observation note")
def add_case_note(
    case_id: str,
    payload: CaseNoteCreate,
    current_user: UserOut = Depends(require_permission("cases:notes")),
):
    try:
        # Overwrite author with verified user identity
        payload_with_actor = payload.model_copy(update={"author": current_user.username})
        return case_service.add_note(case_id, payload_with_actor)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Case '{case_id}' not found.")
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))


@router.get("/{case_id}/history", response_model=List[CaseAuditRecord], summary="Retrieve chronological append-only audit trail")
def get_case_history(
    case_id: str,
    current_user: UserOut = Depends(require_permission("cases:audit")),
):
    try:
        return case_service.get_audit_history(case_id)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"Case '{case_id}' not found.")
