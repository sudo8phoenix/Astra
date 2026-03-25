"""
WebSocket event schemas for real-time communication.

Defines event envelope, event types, and payload structures for:
- Chat interactions (user message → planner → assistant response)
- Real-time updates (task, calendar, email changes)
- Approval notifications
- Session/connection lifecycle
"""

from typing import Optional, Any, Literal
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class WebSocketEventType(str, Enum):
    """Standardized WebSocket event type naming (entity:action)."""
    
    # Chat flow
    CHAT_MESSAGE_RECEIVED = "chat:message_received"
    CHAT_ASSISTANT_THINKING = "chat:assistant_thinking"
    CHAT_ASSISTANT_STREAMING = "chat:assistant_streaming"
    CHAT_MESSAGE_COMPLETE = "chat:message_complete"
    CHAT_ERROR = "chat:error"
    
    # Task updates
    TASK_CREATED = "tasks:created"
    TASK_UPDATED = "tasks:updated"
    TASK_DELETED = "tasks:deleted"
    TASK_COMPLETED = "tasks:completed"
    
    # Calendar updates
    CALENDAR_EVENT_CREATED = "calendar:event_created"
    CALENDAR_EVENT_UPDATED = "calendar:event_updated"
    CALENDAR_EVENT_DELETED = "calendar:event_deleted"
    CALENDAR_FREE_SLOTS_UPDATED = "calendar:free_slots_updated"
    
    # Email updates
    EMAIL_RECEIVED = "email:received"
    EMAIL_ARCHIVED = "email:archived"
    EMAIL_DRAFTED = "email:drafted"
    EMAIL_SENT = "email:sent"
    
    # Approval workflow
    APPROVAL_REQUESTED = "approvals:requested"
    APPROVAL_APPROVED = "approvals:approved"
    APPROVAL_REJECTED = "approvals:rejected"
    APPROVAL_MODIFIED = "approvals:modified"
    APPROVAL_EXPIRED = "approvals:expired"
    
    # Session/connection
    SESSION_AUTHENTICATED = "session:authenticated"
    SESSION_HEARTBEAT = "session:heartbeat"
    SESSION_DISCONNECTED = "session:disconnected"
    SESSION_ERROR = "session:error"


class WebSocketEventEnvelope(BaseModel):
    """Standard WebSocket message envelope for all events."""
    
    type: WebSocketEventType = Field(
        ..., 
        description="Event type (entity:action)"
    )
    timestamp: datetime = Field(
        default_factory=datetime.utcnow,
        description="When event occurred (server time)"
    )
    user_id: str = Field(..., description="User receiving this event")
    trace_id: Optional[str] = Field(
        None,
        description="Trace ID for correlating requests/responses"
    )
    sequence: int = Field(
        ...,
        description="Monotonically increasing sequence for client-side ordering"
    )
    data: Any = Field(
        ...,
        description="Event-specific payload (varies by type)"
    )
    
    class Config:
        from_attributes = True


# ============================================================================
# CHAT EVENTS
# ============================================================================

class ChatMessageReceivedData(BaseModel):
    """User sent a message to AI."""
    
    message_id: str
    content: str
    message_type: Literal["text", "voice_transcription"] = "text"


class ChatAssistantThinkingData(BaseModel):
    """AI is processing (thinking)."""
    
    node: str = Field(
        ...,
        description="Current LangGraph node (planner, router, tools, response_generator)"
    )
    action: Optional[str] = Field(
        None,
        description="What is being analyzed (e.g., 'analyzing_emails', 'routing_to_calendar_tool')"
    )


class ChatAssistantStreamingData(BaseModel):
    """AI response streaming in."""
    
    message_id: str
    chunk: str = Field(..., description="Text chunk being streamed")
    is_final: bool = Field(
        default=False,
        description="Is this the final chunk?"
    )


class ChatMessageCompleteData(BaseModel):
    """AI response is complete."""
    
    message_id: str
    content: str
    trace_id: str
    tool_calls: Optional[list[dict]] = None
    approval_needed: bool = Field(
        default=False,
        description="Are approvals pending?"
    )
    approval_ids: Optional[list[str]] = Field(
        None,
        description="IDs of pending approvals (if any)"
    )


class ChatErrorData(BaseModel):
    """Error during chat processing."""
    
    error_code: str
    message: str
    user_recoverable: bool = Field(default=False)
    recovery_suggestion: Optional[str] = None
    trace_id: Optional[str] = None


# ============================================================================
# TASK EVENTS
# ============================================================================

class TaskEventData(BaseModel):
    """Base task event data."""
    
    task_id: str
    user_id: str
    title: str
    priority: Literal["high", "medium", "low"]
    status: Literal["todo", "in_progress", "completed", "cancelled"]
    due_date: Optional[datetime] = None
    ai_generated: bool = False
    trace_id: Optional[str] = None


class TaskCreatedData(TaskEventData):
    """Task was created."""
    pass


class TaskUpdatedData(TaskEventData):
    """Task was updated."""
    
    changed_fields: list[str] = Field(
        ...,
        description="Which fields changed (e.g., ['status', 'priority'])"
    )


class TaskDeletedData(BaseModel):
    """Task was deleted."""
    
    task_id: str
    user_id: str
    reason: Optional[str] = None


class TaskCompletedData(TaskEventData):
    """Task marked as complete."""
    
    completed_at: datetime


# ============================================================================
# CALENDAR EVENTS
# ============================================================================

class CalendarEventData(BaseModel):
    """Base calendar event data."""
    
    event_id: str
    user_id: str
    title: str
    start_time: datetime
    end_time: datetime
    location: Optional[str] = None
    ai_generated: bool = False
    trace_id: Optional[str] = None


class CalendarEventCreatedData(CalendarEventData):
    """Calendar event was created."""
    pass


class CalendarEventUpdatedData(CalendarEventData):
    """Calendar event was updated."""
    
    changed_fields: list[str] = Field(
        ...,
        description="Which fields changed"
    )


class CalendarEventDeletedData(BaseModel):
    """Calendar event was deleted."""
    
    event_id: str
    user_id: str
    title: str


class CalendarFreeSlotsUpdatedData(BaseModel):
    """Free time slots updated (daily or after event change)."""
    
    date: str = Field(..., description="Date (YYYY-MM-DD)")
    free_slots: list[dict] = Field(
        ...,
        description="[{'start_time': ISO8601, 'end_time': ISO8601, 'duration_minutes': int}, ...]"
    )
    total_free_minutes: int


# ============================================================================
# EMAIL EVENTS
# ============================================================================

class EmailReceivedData(BaseModel):
    """New email arrived."""
    
    email_id: str
    user_id: str
    from_address: str
    from_name: Optional[str]
    subject: str
    snippet: str = Field(..., description="First 100-200 chars")
    timestamp: datetime
    is_urgent: bool = Field(default=False)


class EmailArchivedData(BaseModel):
    """Email was archived/deleted."""
    
    email_id: str
    user_id: str
    action: Literal["archive", "delete", "spam"]


class EmailDraftedData(BaseModel):
    """AI generated email draft."""
    
    draft_id: str
    user_id: str
    thread_id: str
    to_recipient: str
    subject: Optional[str]
    body: str
    confidence: float = Field(..., ge=0.0, le=1.0)
    approval_id: str = Field(..., description="Link to approval workflow")


class EmailSentData(BaseModel):
    """Email was sent (after approval)."""
    
    message_id: str
    user_id: str
    thread_id: str
    to_recipient: str
    sent_at: datetime
    approval_id: str


# ============================================================================
# APPROVAL EVENTS
# ============================================================================

class ApprovalRequestedData(BaseModel):
    """Action requires user approval."""
    
    approval_id: str
    user_id: str
    trace_id: str
    action_type: str = Field(
        ...,
        description="send_email, create_event, create_task, etc."
    )
    summary: str = Field(
        ...,
        description="Human-readable summary for UI (e.g., 'Send email to alice@company.com')"
    )
    ai_confidence: float = Field(..., ge=0.0, le=1.0)
    expires_at: datetime
    action_preview: Optional[dict] = Field(
        None,
        description="Preview data for UI display"
    )


class ApprovalApprovedData(BaseModel):
    """User approved an action."""
    
    approval_id: str
    user_id: str
    action_type: str
    executed: bool = Field(
        default=False,
        description="Was the action executed?"
    )
    execution_result: Optional[dict] = Field(None)
    error: Optional[str] = None


class ApprovalRejectedData(BaseModel):
    """User rejected an action."""
    
    approval_id: str
    user_id: str
    action_type: str
    reason: Optional[str] = None


class ApprovalModifiedData(BaseModel):
    """User modified and approved an action."""
    
    approval_id: str
    user_id: str
    action_type: str
    changes: dict = Field(..., description="What user changed")
    executed: bool = False
    execution_result: Optional[dict] = None


class ApprovalExpiredData(BaseModel):
    """Approval request expired."""
    
    approval_id: str
    user_id: str
    action_type: str
    expires_at: datetime


# ============================================================================
# SESSION EVENTS
# ============================================================================

class SessionAuthenticatedData(BaseModel):
    """User authenticated (WebSocket connected with valid JWT)."""
    
    user_id: str
    session_id: str
    connected_at: datetime
    user_timezone: str


class SessionHeartbeatData(BaseModel):
    """Periodic heartbeat to keep connection alive."""
    
    sequence: int


class SessionDisconnectedData(BaseModel):
    """WebSocket disconnected."""
    
    reason: Literal["client_close", "idle_timeout", "auth_expired", "server_error"]
    message: Optional[str] = None


class SessionErrorData(BaseModel):
    """Session/authentication error."""
    
    error_code: str
    message: str
    recoverable: bool = False


# ============================================================================
# COMPOSITE EVENT ENVELOPE EXAMPLES
# ============================================================================

WEBSOCKET_EVENT_EXAMPLE_CHAT_MESSAGE_RECEIVED = {
    "type": "chat:message_received",
    "timestamp": "2026-03-24T10:30:00Z",
    "user_id": "user-uuid-456",
    "trace_id": "trace-uuid-workflow-1",
    "sequence": 1,
    "data": {
        "message_id": "msg-uuid-123",
        "content": "What emails do I need to respond to?",
        "message_type": "text"
    }
}

WEBSOCKET_EVENT_EXAMPLE_CHAT_ASSISTANT_THINKING = {
    "type": "chat:assistant_thinking",
    "timestamp": "2026-03-24T10:30:01Z",
    "user_id": "user-uuid-456",
    "trace_id": "trace-uuid-workflow-1",
    "sequence": 2,
    "data": {
        "node": "planner",
        "action": "analyzing_user_intent"
    }
}

WEBSOCKET_EVENT_EXAMPLE_CHAT_ASSISTANT_STREAMING = {
    "type": "chat:assistant_streaming",
    "timestamp": "2026-03-24T10:30:02Z",
    "user_id": "user-uuid-456",
    "trace_id": "trace-uuid-workflow-1",
    "sequence": 3,
    "data": {
        "message_id": "msg-uuid-124",
        "chunk": "You have 3 unread emails ",
        "is_final": False
    }
}

WEBSOCKET_EVENT_EXAMPLE_APPROVAL_REQUESTED = {
    "type": "approvals:requested",
    "timestamp": "2026-03-24T10:30:05Z",
    "user_id": "user-uuid-456",
    "trace_id": "trace-uuid-workflow-1",
    "sequence": 5,
    "data": {
        "approval_id": "approval-uuid-789",
        "user_id": "user-uuid-456",
        "trace_id": "trace-uuid-workflow-1",
        "action_type": "send_email",
        "summary": "Send email to alice@company.com",
        "ai_confidence": 0.92,
        "expires_at": "2026-03-24T10:45:00Z",
        "action_preview": {
            "to": "alice@company.com",
            "subject": "Re: Q1 Review",
            "body": "Hi Alice,\n\nThank you for your email..."
        }
    }
}

WEBSOCKET_EVENT_EXAMPLE_TASK_CREATED = {
    "type": "tasks:created",
    "timestamp": "2026-03-24T10:30:10Z",
    "user_id": "user-uuid-456",
    "trace_id": "trace-uuid-workflow-1",
    "sequence": 10,
    "data": {
        "task_id": "task-uuid-123",
        "user_id": "user-uuid-456",
        "title": "Write quarterly report",
        "priority": "high",
        "status": "todo",
        "due_date": "2026-03-31T17:00:00Z",
        "ai_generated": True,
        "trace_id": "trace-uuid-workflow-1"
    }
}

WEBSOCKET_EVENT_EXAMPLE_SESSION_AUTHENTICATED = {
    "type": "session:authenticated",
    "timestamp": "2026-03-24T10:00:00Z",
    "user_id": "user-uuid-456",
    "trace_id": None,
    "sequence": 0,
    "data": {
        "user_id": "user-uuid-456",
        "session_id": "session-uuid-xyz",
        "connected_at": "2026-03-24T10:00:00Z",
        "user_timezone": "America/New_York"
    }
}


# ============================================================================
# EVENT FLOW DIAGRAMS (Text-based documentation)
# ============================================================================

CHAT_FLOW_DESCRIPTION = """
Chat Request → Response Flow:

1. Client sends message
   Type: chat:message_received
   
2. Server acks receipt, planner starts
   Type: chat:assistant_thinking (node=planner)
   
3. Planner decides action, router starts
   Type: chat:assistant_thinking (node=router, action=routing_to_X_tool)
   
4. Tools execute
   Type: chat:assistant_thinking (node=tools)
   
5. Response generation starts
   Type: chat:assistant_thinking (node=response_generator)
   
6. Response streams in
   Type: chat:assistant_streaming (chunk increments)
   
7. Response complete
   Type: chat:message_complete (with approval_ids if needed)
   
8. If approval needed:
   Type: approvals:requested (for each pending action)

9. User approves/rejects
   Type: approvals:approved / approvals:rejected
   
10. Actions execute
    Type: email:sent / tasks:created / calendar:event_created
"""

APPROVAL_FLOW_DESCRIPTION = """
Approval Request → Decision → Execution Flow:

1. AI planner decides action needs approval
   Type: approvals:requested
   Data: action_type, summary, expires_at, action_preview
   UI: Appears in approval sidebar
   
2. User decision (approve/reject/modify)
   Client sends: ApprovalDecisionRequest (via HTTP POST /approvals/{id}/decide)
   
3. Server processes decision
   If approved:
     Type: approvals:approved
     Data: execution_result (if immediate execution)
   If rejected:
     Type: approvals:rejected
   If modified:
     Type: approvals:modified
     Data: changes, execution_result
     
4. Downstream actions execute
   Type: email:sent / tasks:created / calendar:event_created
   Data: Links back to approval_id
   
5. If approval expires
   Type: approvals:expired
   Data: expires_at, action_type
   UI: Approval removed from sidebar
"""
