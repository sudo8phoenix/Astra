"""
Chat and Conversation schemas for user ↔ AI interaction.

Handles user messages, AI responses, chat history, and suggested prompts.
"""

from typing import Optional, Literal
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class ChatMessageRole(str, Enum):
    """Message sender role."""
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"


class ChatMessageRequest(BaseModel):
    """User message to AI."""
    
    content: str = Field(
        ..., 
        min_length=1, 
        max_length=5000,
        description="User message text"
    )
    message_type: Literal["text", "voice_transcription"] = Field(
        default="text",
        description="Type of user input"
    )
    metadata: Optional[dict] = Field(
        default=None,
        description="Additional context (e.g., voice confidence, language detection)"
    )


class ChatMessage(BaseModel):
    """Single chat message (user or assistant)."""
    
    id: str = Field(..., description="Message UUID")
    role: ChatMessageRole
    content: str
    timestamp: datetime
    user_id: str = Field(..., description="User who sent/received message")
    trace_id: Optional[str] = Field(
        None, 
        description="Trace ID for observability"
    )
    tool_calls: Optional[list[dict]] = Field(
        default=None,
        description="LLM tool calls made during this turn (assistant only)"
    )
    approval_required: bool = Field(
        default=False,
        description="If true, message is awaiting user approval (e.g., draft email)"
    )
    approval_id: Optional[str] = Field(
        None,
        description="Reference to Approval record if approval_required=true"
    )
    metadata: Optional[dict] = Field(default=None)
    
    class Config:
        from_attributes = True


class ChatMessageResponse(BaseModel):
    """Response containing new chat message (stream or complete)."""
    
    message: ChatMessage
    typing_indicator: Optional[dict] = Field(
        None,
        description="For streaming: {'is_typing': bool}"
    )


class ChatHistoryRequest(BaseModel):
    """Request to fetch chat history."""
    
    limit: int = Field(
        default=50, 
        ge=1, 
        le=200,
        description="Number of messages to fetch"
    )
    offset: int = Field(
        default=0, 
        ge=0,
        description="Pagination offset"
    )
    order: Literal["asc", "desc"] = Field(
        default="desc",
        description="Chronological order (newest first or oldest first)"
    )


class ChatHistoryResponse(BaseModel):
    """Chat history response with pagination."""
    
    messages: list[ChatMessage]
    total_count: int
    offset: int
    limit: int
    has_more: bool


class SuggestedPrompt(BaseModel):
    """Quick-action prompt suggestion."""
    
    id: str
    label: str = Field(
        ..., 
        max_length=50,
        description="Display label (e.g., 'Summarize emails')"
    )
    prompt: str = Field(
        ...,
        description="Full prompt to inject into chat input"
    )
    category: Literal["email", "calendar", "tasks", "planning", "general"] = Field(
        default="general"
    )
    emoji: Optional[str] = Field(None)


class SuggestedPromptsResponse(BaseModel):
    """Suggested prompts for current context."""
    
    prompts: list[SuggestedPrompt]
    context: str = Field(
        ...,
        description="Context when prompts were generated (e.g., 'morning', 'during_meeting')"
    )


class ChatTypingIndicator(BaseModel):
    """Real-time typing indicator (AI thinking)."""
    
    is_typing: bool
    node: Optional[str] = Field(
        None,
        description="Current LangGraph node (e.g., 'planner', 'router', 'tools')"
    )
    timestamp: datetime


class ChatErrorResponse(BaseModel):
    """Error during chat processing."""
    
    error_code: str
    message: str
    user_recoverable: bool = Field(
        default=False,
        description="Can user retry or is it a permanent error?"
    )
    recovery_suggestion: Optional[str] = None
    trace_id: Optional[str] = None


# Example JSON payloads for documentation

CHAT_MESSAGE_REQUEST_EXAMPLE = {
    "content": "What emails do I need to respond to?",
    "message_type": "text",
    "metadata": None
}

CHAT_MESSAGE_RESPONSE_EXAMPLE = {
    "message": {
        "id": "msg-uuid-123",
        "role": "assistant",
        "content": "You have 3 unread emails from Sarah, John, and the team. I've drafted responses for each. Would you like me to send them?",
        "timestamp": "2026-03-24T10:30:00Z",
        "user_id": "user-uuid-456",
        "trace_id": "trace-uuid-789",
        "tool_calls": [
            {
                "tool": "fetch_emails",
                "args": {"limit": 10},
                "result": "3 emails retrieved"
            }
        ],
        "approval_required": False,
        "approval_id": None,
        "metadata": None
    },
    "typing_indicator": None
}

CHAT_HISTORY_RESPONSE_EXAMPLE = {
    "messages": [
        {
            "id": "msg-uuid-001",
            "role": "user",
            "content": "Good morning! What's my schedule?",
            "timestamp": "2026-03-24T09:00:00Z",
            "user_id": "user-uuid-456",
            "trace_id": None,
            "tool_calls": None,
            "approval_required": False,
            "approval_id": None,
            "metadata": None
        },
        {
            "id": "msg-uuid-002",
            "role": "assistant",
            "content": "Good morning! You have 5 events today...",
            "timestamp": "2026-03-24T09:01:00Z",
            "user_id": "user-uuid-456",
            "trace_id": "trace-uuid-789",
            "tool_calls": [
                {
                    "tool": "fetch_calendar_events",
                    "args": {"date": "2026-03-24"},
                    "result": "5 events retrieved"
                }
            ],
            "approval_required": False,
            "approval_id": None,
            "metadata": None
        }
    ],
    "total_count": 2,
    "offset": 0,
    "limit": 50,
    "has_more": False
}

SUGGESTED_PROMPTS_RESPONSE_EXAMPLE = {
    "prompts": [
        {
            "id": "prompt-1",
            "label": "Summarize emails",
            "prompt": "Please summarize my inbox and highlight urgent items.",
            "category": "email",
            "emoji": "📧"
        },
        {
            "id": "prompt-2",
            "label": "Plan my day",
            "prompt": "Based on my calendar and tasks, create an optimal daily plan.",
            "category": "planning",
            "emoji": "📅"
        },
        {
            "id": "prompt-3",
            "label": "Show my tasks",
            "prompt": "What are my open tasks for today?",
            "category": "tasks",
            "emoji": "✅"
        }
    ],
    "context": "morning"
}
