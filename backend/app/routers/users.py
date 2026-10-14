"""
Phase 10 — Administrative User Management Endpoints.
Accessible strictly to users with the 'admin' role or 'users:manage' permission.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.auth.dependencies import require_permission
from app.schemas.auth import UserCreate, UserOut, UserUpdate
from app.services.user_service import user_service

router = APIRouter(prefix="/users", tags=["User Administration"])


@router.get("", response_model=List[UserOut], summary="List all platform users (Admin only)")
def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    current_user: UserOut = Depends(require_permission("users:manage")),
):
    users, _ = user_service.list_users(skip=skip, limit=limit)
    return users


@router.post("", response_model=UserOut, status_code=status.HTTP_201_CREATED, summary="Create a new user (Admin only)")
def create_user(
    payload: UserCreate,
    current_user: UserOut = Depends(require_permission("users:manage")),
):
    try:
        return user_service.create_user(payload)
    except ValueError as val_err:
        err_msg = str(val_err)
        if "already registered" in err_msg:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=err_msg)
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=err_msg)
    except Exception as exc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(exc))


@router.get("/{user_id}", response_model=UserOut, summary="Get user details by ID (Admin only)")
def get_user(
    user_id: str,
    current_user: UserOut = Depends(require_permission("users:manage")),
):
    user = user_service.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User '{user_id}' not found.")
    return user_service.to_out(user)


@router.patch("/{user_id}", response_model=UserOut, summary="Update user role, status, or details (Admin only)")
def update_user(
    user_id: str,
    payload: UserUpdate,
    current_user: UserOut = Depends(require_permission("users:manage")),
):
    try:
        return user_service.update_user(user_id, payload)
    except KeyError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User '{user_id}' not found.")
    except ValueError as val_err:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(val_err))


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete a user (Admin only)")
def delete_user(
    user_id: str,
    current_user: UserOut = Depends(require_permission("users:manage")),
):
    if user_id == current_user.user_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Administrators cannot delete their own account.")
    deleted = user_service.delete_user(user_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=f"User '{user_id}' not found.")
