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

    return {
        "success": True,
        "message": state.response.message if state.response else "",
        "response": state.response.model_dump(mode="json") if state.response else None,
        "trace_id": state.trace_id,
        "conversation_id": session_id,
        "approval_required": state.pending_approval is not None,
        "approval_id": state.pending_approval.approval_id if state.pending_approval else None,
        "tool_results": [item.model_dump(mode="json") for item in state.tool_results],
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
