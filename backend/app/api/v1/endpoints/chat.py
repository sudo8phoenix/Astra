"""Chat API endpoint backed by agent orchestration."""

from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.agent.orchestration import AgentOrchestrator
from app.core.auth import TokenPayload, get_current_user
from app.db.config import get_db
from app.db.models import User

router = APIRouter(prefix="/chat", tags=["chat"])


def _parse_iso_datetime(value: Any) -> datetime | None:
    if not value or not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            return parsed.replace(tzinfo=None)
        return parsed
    except Exception:
        return None


def _provider_status(user: User) -> dict[str, Any]:
    preferences = user.preferences or {}

    gmail_connected = bool(preferences.get("gmail_connected") and preferences.get("gmail_access_token"))
    gmail_expiry = preferences.get("gmail_token_expires_at")
    gmail_status = "connected"
    if not gmail_connected:
        gmail_status = "disconnected"
    elif isinstance(gmail_expiry, (int, float)) and datetime.utcfromtimestamp(gmail_expiry) <= datetime.utcnow():
        gmail_status = "expired"

    calendar_tokens = preferences.get("calendar_oauth_tokens") or {}
    calendar_access_token = calendar_tokens.get("access_token")
    calendar_expiry = _parse_iso_datetime(calendar_tokens.get("expires_at"))
    calendar_status = "connected"
    if not calendar_access_token:
        calendar_status = "disconnected"
    elif calendar_expiry and calendar_expiry <= datetime.utcnow():
        calendar_status = "expired"

    return {
        "gmail": {
            "connected": gmail_status == "connected",
            "status": gmail_status,
            "connect_path": "/api/v1/emails/oauth/authorize-url",
        },
        "calendar": {
            "connected": calendar_status == "connected",
            "status": calendar_status,
            "connect_path": "/api/v1/calendar/oauth-authorize",
        },
    }


async def get_current_user_from_db(
    current_token: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    user = db.query(User).filter(User.id == current_token.sub).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


@router.post("/messages", summary="Process a chat message")
async def process_chat_message(
    payload: dict[str, Any] = Body(...),
    current_user: User = Depends(get_current_user_from_db),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """Route a chat message through planner, router and tool execution."""

    content = payload.get("message") or payload.get("content")
    if not content or not str(content).strip():
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Message cannot be empty")

    session_id = payload.get("conversation_id") or payload.get("session_id") or str(uuid4())

    orchestrator = AgentOrchestrator(db)
    state = orchestrator.execute_chat(
        user=current_user,
        message=str(content),
        session_id=session_id,
    )

    provider_status = _provider_status(current_user)
    response_message = state.response.message if state.response else ""
    failed_errors = " ".join((item.error or "").lower() for item in state.tool_results if not item.success)
    auth_failure_detected = any(term in failed_errors for term in ["gmail", "calendar", "token", "oauth", "expired"])
    provider_problem = any(
        status in {"disconnected", "expired"}
        for status in [provider_status["gmail"]["status"], provider_status["calendar"]["status"]]
    )
    if auth_failure_detected and provider_problem:
        response_message = (
            f"{response_message}\n\n"
            f"Connection status -> Gmail: {provider_status['gmail']['status']}, "
            f"Calendar: {provider_status['calendar']['status']}."
        )

    return {
        "success": True,
        "message": response_message,
        "response": state.response.model_dump(mode="json") if state.response else None,
        "trace_id": state.trace_id,
        "conversation_id": session_id,
        "approval_required": state.pending_approval is not None,
        "approval_id": state.pending_approval.approval_id if state.pending_approval else None,
        "tool_results": [item.model_dump(mode="json") for item in state.tool_results],
        "provider_status": provider_status,
        "timestamp": datetime.utcnow().isoformat(),
    }


@router.get("/messages", summary="Get chat history")
async def get_chat_messages(
    current_user: User = Depends(get_current_user_from_db),
) -> dict[str, Any]:
    """Return a minimal history placeholder until persistent chat history is wired."""
    return {
        "messages": [],
        "total_count": 0,
        "offset": 0,
        "limit": 50,
        "has_more": False,
        "user_id": current_user.id,
    }
