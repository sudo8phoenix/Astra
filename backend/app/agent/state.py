"""
LangGraph Shared State Object for multi-agent orchestration.

This module defines the complete state schema that flows through:
- Planner node (decision making)
- Router node (tool selection)
- Tool nodes (execution)
- Response generator node (final output)

State persists in Redis with TTL for resumability and observability.
"""

from typing import Optional, Any, Literal
from datetime import datetime, timedelta
from enum import Enum

from pydantic import BaseModel, Field


class InputTriggerType(str, Enum):
    """How the workflow was triggered."""
    USER_CHAT = "user_chat"
    MORNING_ROUTINE = "morning_routine"
    END_OF_DAY_ROUTINE = "end_of_day_routine"
    CALENDAR_ALERT = "calendar_alert"
    EMAIL_ALERT = "email_alert"
    SCHEDULED = "scheduled"
    API = "api"


class PlannerDecision(str, Enum):
    """High-level action type from planner."""
    CHAT_RESPONSE = "chat_response"
    EMAIL_DRAFT = "email_draft"
    CREATE_TASK = "create_task"
    UPDATE_TASK = "update_task"
    CREATE_EVENT = "create_event"
    UPDATE_EVENT = "update_event"
    EMAIL_SUMMARY = "email_summary"
    TASK_LIST = "task_list"
    DAILY_PLAN = "daily_plan"
    FREE_SLOTS_CHECK = "free_slots_check"
    TASK_ROLLOVER = "task_rollover"
    NONE = "none"


# ============================================================================
# INPUT & CONTEXT SECTION
# ============================================================================

class UserInput(BaseModel):
    """User input (chat message or trigger)."""
    
    type: InputTriggerType
    content: Optional[str] = Field(
        None,
        description="Chat message text or trigger description"
    )
    context: Optional[dict] = Field(
        None,
        description="Contextual metadata (e.g., {'message_type': 'text'})"
    )


class EmailSnapshot(BaseModel):
    """Cached email for context."""
    
    id: str
    from_address: str
    subject: str
    timestamp: datetime
    is_unread: bool
    urgency_level: Optional[str] = None


class CalendarEventSnapshot(BaseModel):
    """Cached calendar event for context."""
    
    id: str
    title: str
    start_time: datetime
    end_time: datetime
    is_all_day: bool


class TaskSnapshot(BaseModel):
    """Cached task for context."""
    
    id: str
    title: str
    priority: str
    status: str
    due_date: Optional[datetime] = None


class ContextBlock(BaseModel):
    """Current context for planning decision."""
    
    current_time: datetime = Field(
        ...,
        description="Current server time in user timezone"
    )
    current_date: str = Field(..., description="Current date YYYY-MM-DD")
    user_timezone: str
    
    # Real-time snapshots
    recent_emails: list[EmailSnapshot] = Field(
        default_factory=list,
        description="Last N unread/recent emails"
    )
    today_schedule: list[CalendarEventSnapshot] = Field(
        default_factory=list,
        description="Today's calendar events"
    )
    open_tasks: list[TaskSnapshot] = Field(
        default_factory=list,
        description="Incomplete tasks (sorted by due date)"
    )
    
    # User preferences
    user_preferences: Optional[dict] = Field(
        default=None,
        description="User preferences (working hours, tone, etc.)"
    )
    
    # Metadata
    context_collection_time: datetime = Field(
        default_factory=datetime.utcnow,
        description="When this context was collected"
    )


# ============================================================================
# PLANNER OUTPUT
# ============================================================================

class ToolRequirement(BaseModel):
    """A tool that planner says should be executed."""
    
    tool_name: str = Field(
        ...,
        description="fetch_emails, fetch_calendar, create_task, send_email_draft, etc."
    )
    parameters: dict = Field(
        ...,
        description="Tool-specific parameters"
    )
    required: bool = Field(
        default=True,
        description="Is this tool required or optional?"
    )


class PlannerOutput(BaseModel):
    """Decision output from planner node."""
    
    action_type: PlannerDecision = Field(
        ...,
        description="High-level action decision"
    )
    reasoning: str = Field(
        ...,
        description="Why planner chose this action"
    )
    tools_required: list[ToolRequirement] = Field(
        default_factory=list,
        description="Tools to execute"
    )
    requires_approval: bool = Field(
        default=False,
        description="Does final action need user approval?"
    )
    approval_reason: Optional[str] = Field(
        None,
        description="Why approval is needed"
    )
    confidence: float = Field(
        default=0.8,
        ge=0.0,
        le=1.0,
        description="Planner's confidence in this decision"
    )
    estimated_duration_seconds: Optional[float] = Field(
        None,
        description="Estimated time to execute this plan"
    )


# ============================================================================
# TOOL EXECUTION RESULTS
# ============================================================================

class ToolExecutionResult(BaseModel):
    """Single tool execution result."""
    
    tool_name: str
    success: bool
    result: Optional[Any] = Field(None)
    error: Optional[str] = Field(None)
    execution_time_ms: float
    tokens_used: Optional[int] = Field(None)


# ============================================================================
# PENDING APPROVAL
# ============================================================================

class PendingApproval(BaseModel):
    """Action awaiting user approval."""
    
    approval_id: str
    action_type: str = Field(
        ...,
        description="send_email, create_event, create_task, etc."
    )
    action_payload: Any = Field(
        ...,
        description="Full action data (draft email, event details, task, etc.)"
    )
    reason: str = Field(..., description="Why approval needed")
    created_at: datetime
    expires_at: datetime
    ai_confidence: float = Field(ge=0.0, le=1.0)


# ============================================================================
# RESPONSE GENERATION
# ============================================================================

class ActionCard(BaseModel):
    """UI action card for chat bubble."""
    
    id: str
    label: str = Field(..., max_length=50)
    action: str = Field(..., description="approve, reject, modify, dismiss")
    payload: Optional[dict] = None


class ResponseUpdate(BaseModel):
    """State mutation for frontend to apply."""
    
    entity_type: str = Field(
        ...,
        description="task, event, email, etc."
    )
    operation: Literal["create", "update", "delete", "refresh"] = Field(...)
    data: Any


class ResponseContent(BaseModel):
    """Final response to user."""
    
    message: str = Field(
        ...,
        description="Main response text"
    )
    action_cards: list[ActionCard] = Field(
        default_factory=list,
        description="UI cards for approval/actions"
    )
    updates_to_apply: list[ResponseUpdate] = Field(
        default_factory=list,
        description="Frontend state mutations"
    )
    suggested_follow_ups: list[str] = Field(
        default_factory=list,
        description="Quick prompt suggestions"
    )


# ============================================================================
# METADATA & OBSERVABILITY
# ============================================================================

class WorkflowMetadata(BaseModel):
    """Workflow execution metadata."""
    
    start_time: datetime
    end_time: Optional[datetime] = None
    execution_time_ms: Optional[float] = None
    nodes_executed: list[str] = Field(
        default_factory=list,
        description="Which LangGraph nodes ran"
    )
    total_llm_calls: int = Field(default=0)
    total_tokens: int = Field(default=0)
    estimated_cost_usd: Optional[float] = Field(None)
    errors: list[dict] = Field(
        default_factory=list,
        description="Errors that occurred during execution"
    )
    warnings: list[str] = Field(
        default_factory=list,
        description="Non-fatal warnings"
    )


# ============================================================================
# FULL STATE GRAPH
# ============================================================================

class AgentState(BaseModel):
    """Complete LangGraph state object.
    
    This flows through: Planner → Router → Tools → ResponseGenerator
    
    Persisted to Redis with key: f"state:{user_id}:{trace_id}"
    TTL: 24 hours from creation
    """
    
    # Session & tracing
    user_id: str = Field(..., description="User UUID")
    trace_id: str = Field(..., description="Workflow trace UUID")
    session_id: str = Field(..., description="User session UUID")
    
    # Input
    user_input: UserInput
    
    # Context (populated early in planner)
    context: Optional[ContextBlock] = Field(default=None)
    
    # Planner decision
    plan: Optional[PlannerOutput] = Field(default=None)
    
    # Router output (which tools to execute)
    router_decision: Optional[list[str]] = Field(
        None,
        description="Which tool names to invoke"
    )
    
    # Tool results
    tool_results: list[ToolExecutionResult] = Field(
        default_factory=list,
        description="Results from each tool execution"
    )
    
    # Approval (if needed)
    pending_approval: Optional[PendingApproval] = Field(
        None,
        description="If not None, workflow is awaiting approval"
    )
    approval_decision: Optional[Literal["approve", "reject", "modify"]] = Field(
        None,
        description="User's approval decision"
    )
    approval_user_input: Optional[str] = Field(
        None,
        description="If modified, user's customization"
    )
    
    # Response
    response: Optional[ResponseContent] = Field(default=None)
    
    # Metadata
    metadata: WorkflowMetadata
    
    # State machine
    current_node: str = Field(
        default="input",
        description="Current LangGraph node"
    )
    completed_nodes: list[str] = Field(
        default_factory=list,
        description="Nodes that have completed"
    )
    
    class Config:
        from_attributes = True
    
    def to_redis_dict(self) -> dict:
        """Serialize state for Redis storage."""
        return self.model_dump(exclude_none=False)
    
    @classmethod
    def from_redis_dict(cls, data: dict) -> "AgentState":
        """Deserialize state from Redis."""
        return cls(**data)


# ============================================================================
# STATE BUILDER UTILITIES
# ============================================================================

class StateBuilder:
    """Utility to build and hydrate AgentState."""
    
    @staticmethod
    def create_initial_state(
        user_id: str,
        trace_id: str,
        session_id: str,
        user_input: UserInput,
    ) -> AgentState:
        """Create initial state from user input."""
        return AgentState(
            user_id=user_id,
            trace_id=trace_id,
            session_id=session_id,
            user_input=user_input,
            metadata=WorkflowMetadata(start_time=datetime.utcnow()),
            current_node="input",
        )
    
    @staticmethod
    def hydrate_context(
        state: AgentState,
        emails: Optional[list[EmailSnapshot]] = None,
        events: Optional[list[CalendarEventSnapshot]] = None,
        tasks: Optional[list[TaskSnapshot]] = None,
        user_prefs: Optional[dict] = None,
    ) -> AgentState:
        """Populate context block with real data."""
        state.context = ContextBlock(
            current_time=datetime.utcnow(),
            current_date=datetime.utcnow().strftime("%Y-%m-%d"),
            user_timezone=user_prefs.get("timezone", "UTC") if user_prefs else "UTC",
            recent_emails=emails or [],
            today_schedule=events or [],
            open_tasks=tasks or [],
            user_preferences=user_prefs,
        )
        return state
    
    @staticmethod
    def transition_to_node(state: AgentState, node_name: str) -> AgentState:
        """Mark transition to next node."""
        state.current_node = node_name
        if node_name not in state.completed_nodes:
            state.completed_nodes.append(node_name)
        return state


# ============================================================================
# STATE EXAMPLES (for documentation)
# ============================================================================

STATE_EXAMPLE_INITIAL = {
    "user_id": "user-uuid-456",
    "trace_id": "trace-uuid-workflow-1",
    "session_id": "session-uuid-xyz",
    "user_input": {
        "type": "user_chat",
        "content": "What emails do I need to respond to?",
        "context": None
    },
    "context": None,
    "plan": None,
    "router_decision": None,
    "tool_results": [],
    "pending_approval": None,
    "approval_decision": None,
    "approval_user_input": None,
    "response": None,
    "metadata": {
        "start_time": "2026-03-24T10:30:00Z",
        "end_time": None,
        "execution_time_ms": None,
        "nodes_executed": [],
        "total_llm_calls": 0,
        "total_tokens": 0,
        "estimated_cost_usd": None,
        "errors": [],
        "warnings": []
    },
    "current_node": "input",
    "completed_nodes": []
}

STATE_EXAMPLE_AFTER_PLANNER = {
    **STATE_EXAMPLE_INITIAL,
    "context": {
        "current_time": "2026-03-24T10:30:00Z",
        "current_date": "2026-03-24",
        "user_timezone": "America/New_York",
        "recent_emails": [
            {
                "id": "email-uuid-123",
                "from_address": "alice@company.com",
                "subject": "Q1 Review Timeline",
                "timestamp": "2026-03-24T14:30:00Z",
                "is_unread": True,
                "urgency_level": "high"
            }
        ],
        "today_schedule": [
            {
                "id": "event-uuid-123",
                "title": "Team Standup",
                "start_time": "2026-03-24T09:30:00Z",
                "end_time": "2026-03-24T09:45:00Z",
                "is_all_day": False
            }
        ],
        "open_tasks": [
            {
                "id": "task-uuid-123",
                "title": "Write quarterly report",
                "priority": "high",
                "status": "todo",
                "due_date": "2026-03-31T17:00:00Z"
            }
        ],
        "user_preferences": {
            "timezone": "America/New_York",
            "tone": "professional"
        },
        "context_collection_time": "2026-03-24T10:30:00Z"
    },
    "plan": {
        "action_type": "email_summary",
        "reasoning": "User asked about emails to respond to. Planner will fetch recent unread emails and generate summary.",
        "tools_required": [
            {
                "tool_name": "fetch_emails",
                "parameters": {"limit": 10, "unread_only": True},
                "required": True
            }
        ],
        "requires_approval": False,
        "confidence": 0.95,
        "estimated_duration_seconds": 2.5
    },
    "current_node": "planner",
    "completed_nodes": ["input"]
}

STATE_EXAMPLE_AFTER_TOOLS = {
    **STATE_EXAMPLE_AFTER_PLANNER,
    "router_decision": ["fetch_emails"],
    "tool_results": [
        {
            "tool_name": "fetch_emails",
            "success": True,
            "result": {
                "emails": [
                    {
                        "id": "email-uuid-123",
                        "from_address": "alice@company.com",
                        "subject": "Q1 Review Timeline",
                        "snippet": "Could you please provide feedback..."
                    }
                ],
                "total_count": 3
            },
            "error": None,
            "execution_time_ms": 850,
            "tokens_used": 150
        }
    ],
    "current_node": "tools",
    "completed_nodes": ["input", "planner", "router"]
}

STATE_EXAMPLE_WITH_PENDING_APPROVAL = {
    "user_id": "user-uuid-456",
    "trace_id": "trace-uuid-workflow-2",
    "session_id": "session-uuid-xyz",
    "user_input": {
        "type": "user_chat",
        "content": "Draft a response to Alice.",
        "context": {"email_id": "email-uuid-123"}
    },
    "context": {
        "current_time": "2026-03-24T10:35:00Z",
        "current_date": "2026-03-24",
        "user_timezone": "America/New_York",
        "recent_emails": [],
        "today_schedule": [],
        "open_tasks": [],
        "user_preferences": {"timezone": "America/New_York"},
        "context_collection_time": "2026-03-24T10:35:00Z"
    },
    "plan": {
        "action_type": "email_draft",
        "reasoning": "User requested draft reply. Planner will generate email draft and request approval.",
        "tools_required": [
            {
                "tool_name": "generate_email_draft",
                "parameters": {"email_id": "email-uuid-123", "tone": "professional"},
                "required": True
            }
        ],
        "requires_approval": True,
        "approval_reason": "Email drafts always require user approval before sending.",
        "confidence": 0.88
    },
    "router_decision": ["generate_email_draft"],
    "tool_results": [
        {
            "tool_name": "generate_email_draft",
            "success": True,
            "result": {
                "draft_id": "draft-uuid-456",
                "body": "Hi Alice,\n\nThank you for your email. I'll have feedback by Friday.\n\nBest regards"
            },
            "execution_time_ms": 1200,
            "tokens_used": 350
        }
    ],
    "pending_approval": {
        "approval_id": "approval-uuid-789",
        "action_type": "send_email",
        "action_payload": {
            "draft_id": "draft-uuid-456",
            "to_recipient": "alice@company.com",
            "body": "Hi Alice,\n\nThank you for your email. I'll have feedback by Friday.\n\nBest regards"
        },
        "reason": "User requested email draft. All outbound emails require approval.",
        "created_at": "2026-03-24T10:35:05Z",
        "expires_at": "2026-03-24T10:50:05Z",
        "ai_confidence": 0.88
    },
    "approval_decision": None,
    "response": None,
    "metadata": {
        "start_time": "2026-03-24T10:35:00Z",
        "end_time": None,
        "execution_time_ms": 5500,
        "nodes_executed": ["input", "planner", "router", "tools"],
        "total_llm_calls": 2,
        "total_tokens": 500,
        "estimated_cost_usd": 0.001,
        "errors": [],
        "warnings": []
    },
    "current_node": "awaiting_approval",
    "completed_nodes": ["input", "planner", "router", "tools"]
}

STATE_EXAMPLE_FINAL = {
    **STATE_EXAMPLE_WITH_PENDING_APPROVAL,
    "approval_decision": "approve",
    "response": {
        "message": "I've drafted a response to Alice. Your approval allowed me to send it.",
        "action_cards": [],
        "updates_to_apply": [
            {
                "entity_type": "email",
                "operation": "create",
                "data": {
                    "id": "email-uuid-sent-123",
                    "thread_id": "thread-uuid-123",
                    "to_recipient": "alice@company.com",
                    "status": "sent",
                    "sent_at": "2026-03-24T10:35:10Z"
                }
            }
        ],
        "suggested_follow_ups": [
            "Show my tasks for today",
            "What's my schedule?",
            "Any urgent emails?"
        ]
    },
    "current_node": "response_generator",
    "completed_nodes": ["input", "planner", "router", "tools", "awaiting_approval", "response_generator"]
}
