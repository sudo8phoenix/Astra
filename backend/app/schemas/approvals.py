"""
Approval workflow schemas for sensitive actions.

Handles approval requests, user decisions, and execution of approved actions.
Implements the gate that NO external action happens without explicit user approval.
"""

from typing import Optional, Any, Literal
from datetime import datetime, timedelta
from enum import Enum

from pydantic import BaseModel, Field


class ApprovalActionType(str, Enum):
    """Type of action requiring approval."""
    SEND_EMAIL = "send_email"
    CREATE_EVENT = "create_event"
    UPDATE_EVENT = "update_event"
    DELETE_EVENT = "delete_event"
    CREATE_TASK = "create_task"
    UPDATE_TASK = "update_task"
    DELETE_TASK = "delete_task"
    SEND_MESSAGE = "send_message"  # WhatsApp (post-MVP)


class ApprovalStatus(str, Enum):
    """Status of approval request."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    MODIFIED = "modified"  # User approved with modifications
    EXPIRED = "expired"


class ApprovalRequestPayload(BaseModel):
    """Generic payload for any approvable action."""
    
    action_type: ApprovalActionType
    action_data: Any = Field(
        ...,
        description="Action-specific data (email draft, event, task, etc.)"
    )
    reason: str = Field(
        ...,
        description="Why AI is requesting approval (e.g., 'high-risk action', 'low confidence')"
    )
    ai_confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="AI confidence in this action (0-1). Lower = more caution needed."
    )


class ApprovalRequest(BaseModel):
    """Approval request record."""
    
    id: str = Field(..., description="Approval UUID")
    user_id: str
    trace_id: str = Field(
        ...,
        description="LangGraph workflow trace ID"
    )
    action_type: ApprovalActionType
    action_payload: ApprovalRequestPayload
    status: ApprovalStatus = Field(
        default=ApprovalStatus.PENDING
    )
    created_at: datetime
    expires_at: datetime = Field(
        ...,
        description="When approval expires (default 15 min)"
    )
    decision_at: Optional[datetime] = Field(
        None,
        description="When user made decision"
    )
    decision_user_input: Optional[str] = Field(
        None,
        description="User feedback/modifications if status=modified"
    )
    
    class Config:
        from_attributes = True


class ApprovalResponse(BaseModel):
    """Response with approval request."""
    
    approval: ApprovalRequest
    ui_hints: Optional[dict] = Field(
        None,
        description="Hints for approval sidebar UI (priority, icon, color, etc.)"
    )


class ApprovalListRequest(BaseModel):
    """Request to list pending/recent approvals."""
    
    status: Optional[ApprovalStatus] = Field(
        None,
        description="Filter by status (typically 'pending')"
    )
    action_type: Optional[ApprovalActionType] = None
    days: int = Field(
        default=7,
        ge=1,
        le=30,
        description="Show approvals from last N days"
    )
    limit: int = Field(
        default=20,
        ge=1,
        le=100
    )
    offset: int = Field(default=0, ge=0)


class ApprovalListResponse(BaseModel):
    """List of approval requests."""
    
    approvals: list[ApprovalRequest]
    total_count: int
    pending_count: int = Field(
        ...,
        description="Number of pending approvals"
    )
    offset: int
    limit: int
    has_more: bool


class ApprovalDecisionRequest(BaseModel):
    """User decision on approval request."""
    
    approval_id: str = Field(..., description="Which approval to decide")
    decision: Literal["approve", "reject", "modify"] = Field(
        ...,
        description="User's decision"
    )
    user_input: Optional[str] = Field(
        None,
        description="If decision=modify or reject, user's explanation/changes"
    )
    override_ai_confidence: bool = Field(
        default=False,
        description="Acknowledge overriding AI confidence threshold"
    )


class ApprovalDecisionResponse(BaseModel):
    """Result of approval decision."""
    
    approval_id: str
    decision: Literal["approve", "reject", "modify"]
    status: ApprovalStatus
    executed: bool = Field(
        default=False,
        description="If approved, was action executed?"
    )
    execution_result: Optional[dict] = Field(
        None,
        description="Result of execution (e.g., email_message_id, event_id)"
    )
    error: Optional[str] = Field(
        None,
        description="If execution failed"
    )
    trace_id: Optional[str] = None


class ModifiedApprovalRequest(BaseModel):
    """User modified approval with updated action data."""
    
    approval_id: str
    modified_action_data: Any = Field(
        ...,
        description="Updated action data (e.g., modified email draft)"
    )
    user_explanation: str = Field(
        ...,
        description="Why user modified this action"
    )


class ApprovalTokenRequest(BaseModel):
    """Request a temporary approval token (for time-sensitive actions)."""
    
    approval_id: str
    duration_seconds: int = Field(
        default=900,  # 15 minutes
        ge=60,
        le=3600,
        description="How long token is valid"
    )


class ApprovalTokenResponse(BaseModel):
    """Approval token for headless/API execution."""
    
    token: str = Field(
        ...,
        description="Short-lived JWT containing approval decision"
    )
    expires_at: datetime
    approval_id: str


class ApprovalStats(BaseModel):
    """User's approval statistics."""
    
    total_approvals: int
    approved_count: int
    rejected_count: int
    modified_count: int
    avg_decision_time_seconds: float
    approval_rate: float = Field(
        ...,
        description="Percentage of approvals approved (0-1)"
    )
    most_common_action_type: Optional[ApprovalActionType] = None


class ApprovalStatsResponse(BaseModel):
    """Response with approval stats."""
    
    stats: ApprovalStats
    time_period: str = Field(default="all_time")


# Approval UI Hints (for sidebar presentation)

APPROVAL_UI_HINT_EMAIL = {
    "icon": "email",
    "color": "blue",
    "priority": "medium",
    "display_template": "Send email to {to_recipient}?",
    "show_preview": True
}

APPROVAL_UI_HINT_EVENT = {
    "icon": "calendar",
    "color": "purple",
    "priority": "medium",
    "display_template": "Create event: {title}?",
    "show_preview": True
}

APPROVAL_UI_HINT_TASK = {
    "icon": "check-circle",
    "color": "green",
    "priority": "low",
    "display_template": "Create task: {title}?",
    "show_preview": False
}

APPROVAL_UI_HINTS: dict[ApprovalActionType, dict] = {
    ApprovalActionType.SEND_EMAIL: APPROVAL_UI_HINT_EMAIL,
    ApprovalActionType.CREATE_EVENT: APPROVAL_UI_HINT_EVENT,
    ApprovalActionType.UPDATE_EVENT: {
        "icon": "calendar",
        "color": "purple",
        "priority": "medium",
        "display_template": "Update event: {title}?",
        "show_preview": True
    },
    ApprovalActionType.DELETE_EVENT: {
        "icon": "calendar",
        "color": "red",
        "priority": "high",
        "display_template": "Delete event: {title}?",
        "show_preview": True
    },
    ApprovalActionType.CREATE_TASK: APPROVAL_UI_HINT_TASK,
    ApprovalActionType.UPDATE_TASK: {
        "icon": "check-circle",
        "color": "green",
        "priority": "low",
        "display_template": "Update task: {title}?",
        "show_preview": False
    },
    ApprovalActionType.DELETE_TASK: {
        "icon": "check-circle",
        "color": "red",
        "priority": "medium",
        "display_template": "Delete task: {title}?",
        "show_preview": False
    },
}


# Example JSON payloads

APPROVAL_REQUEST_EXAMPLE = {
    "id": "approval-uuid-789",
    "user_id": "user-uuid-456",
    "trace_id": "trace-uuid-workflow-1",
    "action_type": "send_email",
    "action_payload": {
        "action_type": "send_email",
        "action_data": {
            "draft_id": "draft-uuid-456",
            "thread_id": "thread-uuid-123",
            "to_recipient": "alice@company.com",
            "subject": None,
            "body": "Hi Alice,\n\nThank you for your email. I appreciate the heads-up on the Q1 timeline. I'll have feedback ready by Friday.\n\nBest regards"
        },
        "reason": "Email draft generated by AI planner. Requires explicit approval before sending.",
        "ai_confidence": 0.92
    },
    "status": "pending",
    "created_at": "2026-03-24T15:00:00Z",
    "expires_at": "2026-03-24T15:15:00Z",
    "decision_at": None,
    "decision_user_input": None
}

APPROVAL_DECISION_REQUEST_EXAMPLE = {
    "approval_id": "approval-uuid-789",
    "decision": "approve",
    "user_input": None,
    "override_ai_confidence": False
}

APPROVAL_DECISION_RESPONSE_EXAMPLE = {
    "approval_id": "approval-uuid-789",
    "decision": "approve",
    "status": "approved",
    "executed": True,
    "execution_result": {
        "message_id": "gmail-msg-xyz123",
        "sent_at": "2026-03-24T15:01:00Z",
        "thread_id": "thread-uuid-123"
    },
    "error": None,
    "trace_id": "trace-uuid-workflow-1"
}

APPROVAL_LIST_RESPONSE_EXAMPLE = {
    "approvals": [
        {
            "id": "approval-uuid-789",
            "user_id": "user-uuid-456",
            "trace_id": "trace-uuid-workflow-1",
            "action_type": "send_email",
            "action_payload": {
                "action_type": "send_email",
                "action_data": {
                    "draft_id": "draft-uuid-456",
                    "to_recipient": "alice@company.com",
                    "body": "Hi Alice,\n\nThank you for your email..."
                },
                "reason": "Email draft generated by AI planner.",
                "ai_confidence": 0.92
            },
            "status": "pending",
            "created_at": "2026-03-24T15:00:00Z",
            "expires_at": "2026-03-24T15:15:00Z",
            "decision_at": None,
            "decision_user_input": None
        }
    ],
    "total_count": 1,
    "pending_count": 1,
    "offset": 0,
    "limit": 20,
    "has_more": False
}
