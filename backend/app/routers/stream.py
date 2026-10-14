"""
Phase 7 & 10 — Real-Time Transaction Stream & Secure WebSocket Alert Routers.
Enforces:
- RBAC permissions on simulation controls (Admin only for start/stop/config/step).
- Authenticated transaction event ingestion.
- Secure multi-layered WebSocket authentication (HttpOnly cookie, single-use ticket, or first-frame auth)
  WITHOUT exposing reusable bearer tokens in query strings.
"""

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, status

from app.auth.dependencies import require_permission
from app.auth.security import consume_ws_ticket, decode_token
from app.schemas.auth import UserOut, UserRole
from app.schemas.transaction import (
    SimulatorConfigUpdate,
    TransactionEvent,
    TransactionEventResult,
)
from app.services.simulator import simulator
from app.services.user_service import user_service
from app.services.websocket_manager import manager
import jwt

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/status", summary="Check transaction stream status")
def get_stream_status(current_user: UserOut = Depends(require_permission("stream:read"))):
    """Returns simulator running state, generation metrics, and active WebSocket client count."""
    return simulator.get_status()


@router.post("/start", summary="Start background transaction stream")
async def start_stream(current_user: UserOut = Depends(require_permission("stream:control"))):
    """Starts the asynchronous real-time transaction streaming background worker. (Admin only)"""
    return await simulator.start()


@router.post("/stop", summary="Stop background transaction stream")
async def stop_stream(current_user: UserOut = Depends(require_permission("stream:control"))):
    """Gracefully halts the background transaction streaming worker. (Admin only)"""
    return await simulator.stop()


@router.post("/config", summary="Configure simulator parameters")
def update_stream_config(
    config: SimulatorConfigUpdate,
    current_user: UserOut = Depends(require_permission("stream:control")),
):
    """Updates permitted simulation parameters. (Admin only)"""
    return simulator.update_config(config)


@router.post("/transactions", response_model=TransactionEventResult, status_code=status.HTTP_201_CREATED, summary="Submit a transaction event")
async def submit_transaction_event(
    event: TransactionEvent,
    current_user: UserOut = Depends(require_permission("stream:write")),
):
    """Submits a single validated transaction event for Neo4j persistence and graph fraud evaluation."""
    result = await simulator.submit_event(event)
    if result.status == "failed":
        raise HTTPException(status_code=status.HTTP_502_BAD_GATEWAY, detail=result.message)
    return result


@router.post("/step", summary="Trigger a single synthetic transaction step")
async def step_stream(
    scenario: Optional[str] = Query(None, description="Optional scenario override"),
    current_user: UserOut = Depends(require_permission("stream:control")),
):
    """Generates, persists, and evaluates a single synthetic transaction batch on demand. (Admin only)"""
    results = await simulator.step(scenario=scenario)
    return {
        "results": [r.model_dump() for r in results],
        "status": simulator.get_status(),
    }


async def _authenticate_websocket(websocket: WebSocket) -> Optional[dict]:
    """
    Authenticates WebSocket connection using:
    1. HttpOnly 'access_token' cookie sent with handshake.
    2. One-time temporary ticket via query param '?ticket=...'.
    3. In-band first frame authentication: {"type": "AUTH", "token": "..."} within 5s.
    Returns user dict on success, None on failure.
    """
    # 1. Check HttpOnly cookie
    token = websocket.cookies.get("access_token")
    if token:
        try:
            payload = decode_token(token, expected_type="access")
            user = user_service.get_by_id(payload.get("sub"))
            if user and user.get("is_active", True):
                return user
        except Exception:
            pass

    # 2. Check one-time ticket query parameter
    ticket = websocket.query_params.get("ticket")
    if ticket:
        user_id = consume_ws_ticket(ticket)
        if user_id:
            user = user_service.get_by_id(user_id)
            if user and user.get("is_active", True):
                return user

    # 3. In-band first-message authentication (accept temporary connection to receive auth frame)
    await websocket.accept()
    try:
        raw_msg = await asyncio.wait_for(websocket.receive_text(), timeout=5.0)
        data = json.loads(raw_msg)
        if data.get("type", "").upper() == "AUTH" and data.get("token"):
            payload = decode_token(data["token"], expected_type="access")
            user = user_service.get_by_id(payload.get("sub"))
            if user and user.get("is_active", True):
                return user
    except Exception as exc:
        logger.debug("WebSocket in-band authentication failed: %s", exc)

    return None


@router.websocket("/ws/alerts")
async def websocket_alerts_endpoint(websocket: WebSocket):
    """
    Secure WebSocket endpoint for real-time transaction events and instant fraud alerts.
    Authenticates via HttpOnly cookie, short-lived ticket, or initial auth message.
    """
    user = None
    # If connection was already accepted in _authenticate_websocket, user is returned or connection closed
    # Check if handshake already accepted
    token_or_ticket = websocket.cookies.get("access_token") or websocket.query_params.get("ticket")
    if token_or_ticket:
        user = await _authenticate_websocket(websocket)
        if not user:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized")
            return
        await manager.connect(websocket)
    else:
        # Needs in-band auth frame
        user = await _authenticate_websocket(websocket)
        if not user:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION, reason="Unauthorized")
            return
        manager.active_connections.append(websocket)

    try:
        # Handshake frame
        await websocket.send_json({
            "type": "HANDSHAKE",
            "message": "Connected to FraudGraph Secure Real-Time Alert Stream",
            "authenticated_as": user.get("username"),
            "role": user.get("role"),
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "simulator": simulator.get_status(),
        })

        while True:
            raw = await websocket.receive_text()
            try:
                frame = json.loads(raw)
                frame_type = frame.get("type", "").upper()
            except Exception:
                frame_type = raw.strip().upper()

            if frame_type in ["PING", '"PING"']:
                await websocket.send_json({
                    "type": "PONG",
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                })
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as exc:
        logger.debug("WebSocket connection closed: %s", exc)
        manager.disconnect(websocket)
