"""
Email management schemas for Gmail integration.

Handles email listing, summarization, draft generation, and approval workflows.
"""

from typing import Optional, Literal
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class EmailLabel(str, Enum):
    """Gmail label categories."""
    INBOX = "INBOX"
    SENT = "SENT"
    DRAFT = "DRAFT"
    SPAM = "SPAM"
    TRASH = "TRASH"
    STARRED = "STARRED"


class EmailRange(str, Enum):
    """Time range for email queries."""
    TODAY = "today"
    WEEK = "week"
    MONTH = "month"
    ALL = "all"


class EmailListRequest(BaseModel):
    """Request to list emails."""
    
    label: EmailLabel = Field(
        default=EmailLabel.INBOX,
        description="Gmail label to fetch from"
    )
    limit: int = Field(
        default=20,
        ge=1,
        le=100,
        description="Number of emails to fetch"
    )
    offset: int = Field(
        default=0,
        ge=0,
        description="Pagination offset"
    )
    unread_only: bool = Field(
        default=False,
        description="Only fetch unread emails"
    )
    time_range: EmailRange = Field(
        default=EmailRange.WEEK,
        description="Limit to emails from this time range"
    )
    sort_by: Literal["date", "sender", "subject"] = Field(
        default="date"
    )
    order: Literal["asc", "desc"] = Field(
        default="desc"
    )


class EmailMetadata(BaseModel):
    """Email metadata without full body (for lists)."""
    
    id: str = Field(..., description="Gmail message ID")
    thread_id: str = Field(..., description="Gmail thread ID")
    from_address: str = Field(..., description="Sender email")
    from_name: Optional[str]
    to_addresses: list[str]
    subject: str
    snippet: str = Field(
        ...,
        description="First 100-200 chars of body"
    )
    labels: list[str]
    timestamp: datetime = Field(..., description="When email was received")
    is_unread: bool
    is_starred: bool
    has_attachments: bool


class Email(BaseModel):
    """Full email object with body."""
    
    id: str = Field(..., description="Gmail message ID")
    thread_id: str
    from_address: str
    from_name: Optional[str]
    to_addresses: list[str]
    cc_addresses: Optional[list[str]]
    bcc_addresses: Optional[list[str]]
    subject: str
    body: str = Field(..., description="Full email body (HTML or plain text)")
    body_plain: Optional[str] = Field(None, description="Plain text fallback")
    labels: list[str]
    timestamp: datetime
    is_unread: bool
    is_starred: bool
    has_attachments: bool
    attachments: Optional[list[dict]] = Field(
        None,
        description="Attachment metadata [{name, mime_type, size}]"
    )
    user_id: str
    trace_id: Optional[str] = Field(
        None,
        description="If processed by AI agent"
    )
    
    class Config:
        from_attributes = True


class EmailListResponse(BaseModel):
    """List of emails with pagination."""
    
    emails: list[EmailMetadata]
    total_count: int
    offset: int
    limit: int
    has_more: bool


class EmailResponse(BaseModel):
    """Single full email response."""
    
    email: Email
    trace_id: Optional[str] = None


class EmailSummaryRequest(BaseModel):
    """Request to summarize inbox."""
    
    limit: int = Field(
        default=10,
        ge=1,
        le=50,
        description="Number of emails to summarize"
    )
    time_range: EmailRange = Field(
        default=EmailRange.TODAY,
        description="Summarize emails from this range"
    )
    include_urgent_only: bool = Field(
        default=False,
        description="Highlight urgent emails"
    )


class EmailSummary(BaseModel):
    """AI-generated email summary."""
    
    total_count: int
    unread_count: int
    urgent_emails: Optional[list[EmailMetadata]] = None
    summary_text: str = Field(
        ...,
        description="AI-generated summary of key emails"
    )
    key_senders: list[str] = Field(
        ...,
        description="Top senders by count"
    )
    action_items: Optional[list[str]] = Field(
        None,
        description="Extracted action items from emails"
    )
    trace_id: str = Field(
        ...,
        description="Trace ID of summarization workflow"
    )


class EmailSummaryResponse(BaseModel):
    """Email summary response."""
    
    summary: EmailSummary


class EmailDraftRequest(BaseModel):
    """Request to generate email draft reply."""
    
    email_id: str = Field(..., description="Email to reply to")
    thread_id: str = Field(...)
    recipient: str = Field(..., description="Email recipient (usually from_address)")
    context: Optional[str] = Field(
        None,
        description="Additional context for draft (e.g., 'be concise', 'technical tone')"
    )
    tone: Literal["professional", "casual", "formal", "friendly"] = Field(
        default="professional"
    )


class EmailDraft(BaseModel):
    """AI-generated email draft."""
    
    id: str = Field(..., description="Draft UUID")
    thread_id: str
    to_recipient: str
    subject: Optional[str] = Field(
        None,
        description="Reply subject (may be empty for re: format)"
    )
    body: str = Field(..., description="Generated draft body")
    tone: str
    ai_generated: bool = Field(default=True)
    confidence: float = Field(
        ...,
        ge=0.0,
        le=1.0,
        description="AI confidence in draft quality"
    )
    metadata: Optional[dict] = Field(
        None,
        description="Reasoning, suggestions, etc."
    )
    created_at: datetime
    
    class Config:
        from_attributes = True


class EmailDraftResponse(BaseModel):
    """Email draft response (pending approval)."""
    
    draft: EmailDraft
    approval_required: bool = Field(
        default=True,
        description="User must approve before sending"
    )
    approval_id: Optional[str] = Field(
        None,
        description="Link to approval workflow"
    )
    trace_id: Optional[str] = None


class EmailSendRequest(BaseModel):
    """Request to send an email (requires approval)."""
    
    approval_id: str = Field(
        ...,
        description="Approval workflow ID"
    )
    draft_id: str = Field(
        ...,
        description="Email draft ID"
    )
    override_ai_confidence: bool = Field(
        default=False,
        description="Acknowledge sending low-confidence draft"
    )


class EmailSendResponse(BaseModel):
    """Email send result."""
    
    success: bool
    message_id: Optional[str] = Field(
        None,
        description="Gmail message ID if sent"
    )
    thread_id: str
    sent_at: Optional[datetime] = None
    error: Optional[str] = None
    trace_id: Optional[str] = None


class EmailUrgencyClassification(BaseModel):
    """Urgency classification for email."""
    
    email_id: str
    urgency_level: Literal["low", "medium", "high", "critical"]
    reason: str = Field(
        ...,
        description="Why this email is urgent"
    )
    suggested_action: Optional[str] = Field(
        None,
        description="Recommended action (e.g., 'reply immediately')"
    )


# Example JSON payloads

EMAIL_LIST_RESPONSE_EXAMPLE = {
    "emails": [
        {
            "id": "email-uuid-123",
            "thread_id": "thread-uuid-123",
            "from_address": "alice@company.com",
            "from_name": "Alice Smith",
            "to_addresses": ["user@company.com"],
            "subject": "Q1 Review Timeline",
            "snippet": "Hi, Could you please provide your feedback on the proposed Q1 review timeline by Friday? It's...",
            "labels": ["INBOX"],
            "timestamp": "2026-03-24T14:30:00Z",
            "is_unread": True,
            "is_starred": False,
            "has_attachments": False
        }
    ],
    "total_count": 1,
    "offset": 0,
    "limit": 20,
    "has_more": False
}

EMAIL_SUMMARY_RESPONSE_EXAMPLE = {
    "summary": {
        "total_count": 5,
        "unread_count": 3,
        "urgent_emails": [
            {
                "id": "email-uuid-123",
                "thread_id": "thread-uuid-123",
                "from_address": "manager@company.com",
                "from_name": "Manager",
                "to_addresses": ["user@company.com"],
                "subject": "URGENT: Q1 Review Timeline",
                "snippet": "Could you please provide feedback by Friday...",
                "labels": ["INBOX"],
                "timestamp": "2026-03-24T14:30:00Z",
                "is_unread": True,
                "is_starred": True,
                "has_attachments": False
            }
        ],
        "summary_text": "You have 5 unread emails. The most urgent is from your manager about Q1 review feedback due Friday. Alice also sent a decision request about project resource allocation.",
        "key_senders": ["manager@company.com", "alice@company.com", "bob@company.com"],
        "action_items": [
            "Provide Q1 review feedback to manager by Friday",
            "Approve project resource allocation with Alice"
        ],
        "trace_id": "trace-uuid-789"
    }
}

EMAIL_DRAFT_RESPONSE_EXAMPLE = {
    "draft": {
        "id": "draft-uuid-456",
        "thread_id": "thread-uuid-123",
        "to_recipient": "alice@company.com",
        "subject": None,
        "body": "Hi Alice,\n\nThank you for your email. I appreciate the heads-up on the Q1 timeline. I'll have feedback ready by Friday.\n\nBest regards",
        "tone": "professional",
        "ai_generated": True,
        "confidence": 0.92,
        "metadata": {
            "reasoning": "Polite, committal response. Acknowledges urgency.",
            "suggestions": ["Consider adding specific items you'll review"]
        },
        "created_at": "2026-03-24T15:00:00Z"
    },
    "approval_required": True,
    "approval_id": "approval-uuid-789",
    "trace_id": "trace-uuid-789"
}
