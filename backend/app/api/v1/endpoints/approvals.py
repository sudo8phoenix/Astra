"""Approval workflow API endpoints with idempotency and trace ID support."""

import logging
import json
from typing import Optional
from datetime import datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status, Query, Header
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, TokenPayload
from app.core.config import settings
from app.db.config import get_db
from app.db.models import User, Approval
from app.schemas.approvals import (
    ApprovalRequest,
    ApprovalResponse,
    ApprovalListRequest,
    ApprovalStatus,
)
from app.cache.config import get_redis
from app.repositories.repositories import ApprovalRepository

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/approvals", tags=["approvals"])


# ============================================================================
# HELPER FUNCTIONS
# ============================================================================

def extract_trace_id(request_headers: dict) -> str:
    """Extract trace_id from request headers or generate new one."""
    return request_headers.get("x-trace-id", str(uuid4()))


async def check_idempotency(
    redis_client,
    idempotency_key: str,
) -> Optional[dict]:
    """
    Check if request was already processed.
    Returns cached result if found, None otherwise.
    """
    if not idempotency_key:
        return None
    
    cache_key = f"idempotency:{idempotency_key}"
    cached_result = redis_client.get(cache_key)
    
    if cached_result:
        logger.info(
            f"Idempotent request cache hit",
            extra={"trace_id": "N/A", "key": idempotency_key},
        )
        return json.loads(cached_result)
    
    return None


async def cache_idempotent_result(
    redis_client,
    idempotency_key: str,
    result: dict,
):
    """Cache result for future idempotent requests (24h TTL)."""
    if not idempotency_key:
        return
    
    cache_key = f"idempotency:{idempotency_key}"
    redis_client.setex(
        cache_key,
        86400,  # 24 hours
        json.dumps(result),
    )


async def broadcast_approval_event(
    redis_client,
    user_id: str,
    event_type: str,
    approval_id: str,
    data: dict,
    trace_id: str,
):
    """
    Broadcast approval state change via WebSocket.
    Publishes to Redis pub/sub for WebSocket handler to relay.
    """
    event_payload = {
        "type": event_type,
        "approval_id": approval_id,
        "user_id": user_id,
        "timestamp": datetime.utcnow().isoformat(),
        "trace_id": trace_id,
        "data": data,
    }
    
    channel = f"ws:approvals:{user_id}"
    redis_client.publish(channel, json.dumps(event_payload))
    
    logger.info(
        f"Published approval event",
        extra={
            "trace_id": trace_id,
            "user_id": user_id,
            "event_type": event_type,
            "approval_id": approval_id,
        }
    )


async def execute_approved_action(
    db: Session,
    redis_client,
    approval: Approval,
    trace_id: str,
) -> dict:
    """
    Execute the action contained in the approval.
    
    This is a hook point for tool execution. Currently returns
    placeholder execution result. In full implementation, would
    call appropriate tool based on approval.approval_type.
    """
    action_payload = approval.action_payload
    action_type = approval.approval_type
    
    logger.info(
        f"Executing approved action",
        extra={
            "trace_id": trace_id,
            "action_type": action_type,
            "approval_id": approval.id,
            "user_id": approval.user_id,
        }
    )
    
    # TODO: Route to actual tool execution based on action_type
    # For now, return placeholder
    execution_result = {
        "action_type": action_type,
        "status": "executed",
        "executed_at": datetime.utcnow().isoformat(),
        "trace_id": trace_id,
    }
    
    # In production, would also update related records
    # (send email, create task, etc. based on action_type)
    
    return execution_result


async def expire_stale_user_approvals(
    db: Session,
    redis_client,
    user_id: str,
    trace_id: str,
) -> int:
    """Mark stale pending approvals as expired for this user and emit events."""
    stale = db.query(Approval).filter(
        Approval.user_id == user_id,
        Approval.status == Approval.ApprovalStatus.PENDING,
        Approval.expires_at <= datetime.utcnow(),
    ).all()

    if not stale:
        return 0

    expired_ids: list[str] = []
    for approval in stale:
        approval.status = Approval.ApprovalStatus.EXPIRED
        expired_ids.append(approval.id)

    db.commit()

    for approval_id in expired_ids:
        try:
            await broadcast_approval_event(
                redis_client,
                user_id,
                "approvals:expired",
                approval_id,
                {"reason": "approval_ttl_elapsed"},
                trace_id,
            )
        except Exception:
            logger.warning(
                "Failed to broadcast approval expiry event",
                extra={"trace_id": trace_id, "approval_id": approval_id, "user_id": user_id},
            )

    logger.info(
        "Expired stale pending approvals",
        extra={"trace_id": trace_id, "user_id": user_id, "expired_count": len(expired_ids)},
    )
    return len(expired_ids)



async def get_current_user_from_db(
    current_token: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Get current user object from database using token payload."""
    user = db.query(User).filter(User.id == current_token.sub).first()
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found",
        )
    return user


@router.get("/pending", summary="List pending approvals")
async def list_pending_approvals(
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
    current_user: User = Depends(get_current_user_from_db),
    db: Session = Depends(get_db),
) -> dict:
    """
    Get list of pending approvals for current user.
    
    Returns approvals that are awaiting user decision.
    """
    trace_id = str(uuid4())
    await expire_stale_user_approvals(db=db, redis_client=get_redis(), user_id=current_user.id, trace_id=trace_id)

    approvals = db.query(Approval).filter(
        Approval.user_id == current_user.id,
        Approval.status == Approval.ApprovalStatus.PENDING,
        Approval.expires_at > datetime.utcnow(),
    ).order_by(Approval.created_at.desc()).offset(offset).limit(limit).all()
    
    approval_list = []
    for approval in approvals:
        approval_list.append({
            "id": approval.id,
            "type": approval.approval_type,
            "description": approval.action_description,
            "created_at": approval.created_at.isoformat(),
            "expires_at": approval.expires_at.isoformat(),
            "confidence": approval.confidence_score or 0.0,
            "reasoning": approval.ai_reasoning,
        })
    
    return {
        "approvals": approval_list,
        "total_count": len(approvals),
        "offset": offset,
        "limit": limit,
    }


@router.get("/{approval_id}", summary="Get approval details")
async def get_approval(
    approval_id: str,
    current_user: User = Depends(get_current_user_from_db),
    db: Session = Depends(get_db),
) -> dict:
    """Get full details of an approval request."""
    trace_id = str(uuid4())
    await expire_stale_user_approvals(db=db, redis_client=get_redis(), user_id=current_user.id, trace_id=trace_id)

    approval = db.query(Approval).filter(
        Approval.id == approval_id,
        Approval.user_id == current_user.id,
    ).first()
    
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval not found",
        )
    
    return {
        "id": approval.id,
        "type": approval.approval_type,
        "description": approval.action_description,
        "status": approval.status,
        "payload": approval.action_payload,
        "confidence": approval.confidence_score,
        "reasoning": approval.ai_reasoning,
        "created_at": approval.created_at.isoformat(),
        "expires_at": approval.expires_at.isoformat(),
    }


@router.post("/{approval_id}/approve", summary="Approve action")
async def approve_action(
    approval_id: str,
    current_user: User = Depends(get_current_user_from_db),
    db: Session = Depends(get_db),
) -> dict:
    """
    Approve a pending action.
    
    After approval, the action tool can be executed.
    """
    trace_id = str(uuid4())
    await expire_stale_user_approvals(db=db, redis_client=get_redis(), user_id=current_user.id, trace_id=trace_id)

    approval = db.query(Approval).filter(
        Approval.id == approval_id,
        Approval.user_id == current_user.id,
    ).first()
    
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval not found",
        )
    
    if approval.status != Approval.ApprovalStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Approval is already {approval.status}",
        )
    
    if approval.expires_at < datetime.utcnow():
        approval.status = Approval.ApprovalStatus.EXPIRED
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Approval has expired",
        )
    
    # Approve the action
    approval.status = Approval.ApprovalStatus.APPROVED
    approval.approved_by = current_user.id
    approval.approved_at = datetime.utcnow()
    db.commit()
    
    return {
        "success": True,
        "approval_id": approval_id,
        "status": "approved",
        "message": "Action approved and ready for execution",
    }


@router.post("/{approval_id}/reject", summary="Reject action")
async def reject_action(
    approval_id: str,
    reason: str = Query(..., min_length=1, max_length=500),
    current_user: User = Depends(get_current_user_from_db),
    db: Session = Depends(get_db),
) -> dict:
    """
    Reject a pending approval.
    
    Prevents the action from being executed.
    """
    trace_id = str(uuid4())
    await expire_stale_user_approvals(db=db, redis_client=get_redis(), user_id=current_user.id, trace_id=trace_id)

    approval = db.query(Approval).filter(
        Approval.id == approval_id,
        Approval.user_id == current_user.id,
    ).first()
    
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval not found",
        )
    
    if approval.status != Approval.ApprovalStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Approval is already {approval.status}",
        )
    
    # Reject the action
    approval.status = Approval.ApprovalStatus.REJECTED
    approval.approved_by = current_user.id
    approval.approved_at = datetime.utcnow()
    approval.rejection_reason = reason
    db.commit()
    
    return {
        "success": True,
        "approval_id": approval_id,
        "status": "rejected",
        "message": "Action has been rejected",
    }


@router.get("/recent", summary="Get recent approvals")
async def get_recent_approvals(
    limit: int = Query(10, ge=1, le=50),
    current_user: User = Depends(get_current_user_from_db),
    db: Session = Depends(get_db),
) -> dict:
    """Get recently decided approvals (approved/rejected)."""
    approvals = db.query(Approval).filter(
        Approval.user_id == current_user.id,
        Approval.status.in_([
            Approval.ApprovalStatus.APPROVED,
            Approval.ApprovalStatus.REJECTED,
        ]),
    ).order_by(Approval.approved_at.desc()).limit(limit).all()
    
    approval_list = []
    for approval in approvals:
        approval_list.append({
            "id": approval.id,
            "type": approval.approval_type,
            "description": approval.action_description,
            "status": approval.status,
            "decided_at": approval.approved_at.isoformat() if approval.approved_at else None,
            "rejection_reason": approval.rejection_reason,
        })
    
    return {
        "approvals": approval_list,
        "total_count": len(approvals),
    }


# ============================================================================
# UNIFIED DECISION ENDPOINT (NEW - Integration Gate 1)
# ============================================================================

@router.post("/{approval_id}/decide", summary="Approve, reject, or modify an action")
async def decide_approval(
    approval_id: str,
    decision: str = Query("approve", regex="^(approve|reject|modify)$"),
    reason: Optional[str] = Query(None, max_length=500),
    modified_payload: Optional[dict] = None,
    x_idempotency_key: Optional[str] = Header(None, description="Idempotency key for deduplication"),
    x_trace_id: Optional[str] = Header(None, description="Trace ID for request tracking"),
    current_user: User = Depends(get_current_user_from_db),
    db: Session = Depends(get_db),
    redis_client = Depends(get_redis),
) -> dict:
    """
    Unified approval decision endpoint.
    
    Handles approve, reject, or modify with idempotency and trace ID support.
    
    - **decision**: "approve", "reject", or "modify"
    - **reason**: Optional rejection reason
    - **modified_payload**: For modify decision, the new action payload
    - **x-idempotency-key**: For idempotent request handling
    - **x-trace-id**: For end-to-end request tracing
    
    Returns:
        - 200: Idempotent duplicate (cached result)
        - 201: First successful execution
        - 400: Invalid state or expired approval
        - 404: Approval not found
    """
    # Extract trace ID
    trace_id = extract_trace_id({"x-trace-id": x_trace_id})

    await expire_stale_user_approvals(db=db, redis_client=redis_client, user_id=current_user.id, trace_id=trace_id)
    
    # Check idempotency cache
    if x_idempotency_key:
        cached = await check_idempotency(redis_client, x_idempotency_key)
        if cached:
            return {
                "success": True,
                "cached": True,
                "approval_id": approval_id,
                "decision": decision,
                "trace_id": trace_id,
                **cached,
            }
    
    # Fetch approval
    approval = db.query(Approval).filter(
        Approval.id == approval_id,
        Approval.user_id == current_user.id,
    ).first()
    
    if not approval:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Approval not found",
        )
    
    # Check status
    if approval.status != Approval.ApprovalStatus.PENDING:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Approval is already {approval.status}. Cannot change status.",
        )
    
    # Check expiration
    if approval.expires_at < datetime.utcnow():
        approval.status = Approval.ApprovalStatus.EXPIRED
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Approval has expired (15 minute timeout)",
        )
    
    # Process decision
    execution_result = None
    
    if decision == "approve":
        approval.status = Approval.ApprovalStatus.APPROVED
        approval.approved_by = current_user.id
        approval.approved_at = datetime.utcnow()
        
        # Execute the approved action
        execution_result = await execute_approved_action(
            db, redis_client, approval, trace_id
        )
        
        db.commit()
        
        # Broadcast approval event
        await broadcast_approval_event(
            redis_client,
            current_user.id,
            "approvals:approved",
            approval_id,
            {
                "execution_result": execution_result,
                "action_type": approval.approval_type,
            },
            trace_id,
        )
        
        logger.info(
            f"Approval decision: APPROVED",
            extra={
                "trace_id": trace_id,
                "user_id": current_user.id,
                "approval_id": approval_id,
                "action_type": approval.approval_type,
            },
        )
        
    elif decision == "reject":
        if not reason:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Rejection reason is required",
            )
        
        approval.status = Approval.ApprovalStatus.REJECTED
        approval.approved_by = current_user.id
        approval.approved_at = datetime.utcnow()
        approval.rejection_reason = reason
        db.commit()
        
        # Broadcast rejection event
        await broadcast_approval_event(
            redis_client,
            current_user.id,
            "approvals:rejected",
            approval_id,
            {
                "reason": reason,
                "action_type": approval.approval_type,
            },
            trace_id,
        )
        
        logger.info(
            f"Approval decision: REJECTED",
            extra={
                "trace_id": trace_id,
                "user_id": current_user.id,
                "approval_id": approval_id,
                "rejection_reason": reason,
            },
        )
        
    elif decision == "modify":
        if not modified_payload:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Modified payload is required for modify decision",
            )
        
        # Update approval with modified payload
        approval.action_payload = modified_payload
        approval.status = Approval.ApprovalStatus.APPROVED
        approval.approved_by = current_user.id
        approval.approved_at = datetime.utcnow()
        
        # Execute with modified payload
        execution_result = await execute_approved_action(
            db, redis_client, approval, trace_id
        )
        
        db.commit()
        
        # Broadcast modification event
        await broadcast_approval_event(
            redis_client,
            current_user.id,
            "approvals:modified",
            approval_id,
            {
                "modified_payload": modified_payload,
                "execution_result": execution_result,
                "action_type": approval.approval_type,
            },
            trace_id,
        )
        
        logger.info(
            f"Approval decision: MODIFIED & APPROVED",
            extra={
                "trace_id": trace_id,
                "user_id": current_user.id,
                "approval_id": approval_id,
                "action_type": approval.approval_type,
            },
        )
    
    # Prepare response
    response_data = {
        "success": True,
        "approval_id": approval_id,
        "decision": decision,
        "status": approval.status,
        "decided_at": approval.approved_at.isoformat() if approval.approved_at else None,
        "trace_id": trace_id,
    }
    
    if execution_result:
        response_data["execution_result"] = execution_result
    
    # Cache idempotent result
    await cache_idempotent_result(redis_client, x_idempotency_key, response_data)
    
    return response_data

