"""SQLAlchemy ORM models for AI Assistant."""

from sqlalchemy import (
    Column, String, Integer, Text, DateTime, Boolean, Float, DECIMAL,
    ForeignKey, Enum, JSON, Index, UniqueConstraint, CheckConstraint,
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from datetime import datetime
import enum
import uuid
from app.db.config import Base


class User(Base):
    """User account and profile data."""

    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    timezone = Column(String(50), nullable=False, default="UTC")
    oauth_provider = Column(String(50), nullable=True)  # "google", "github", etc.
    oauth_id = Column(String(255), nullable=True, unique=True)
    
    # Preferences
    preferences = Column(JSON, nullable=True, default={})  # {"language": "en", "notifications": true}
    
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)

    # Relationships
    tasks = relationship("Task", back_populates="user", cascade="all, delete-orphan")
    calendar_events = relationship("CalendarEvent", back_populates="user", cascade="all, delete-orphan")
    emails = relationship("Email", back_populates="user", cascade="all, delete-orphan")
    messages = relationship("Message", back_populates="user", cascade="all, delete-orphan")
    approvals = relationship("Approval", back_populates="user", cascade="all, delete-orphan")
    agent_runs = relationship("AgentRun", back_populates="user", cascade="all, delete-orphan")

    __table_args__ = (
        Index("idx_user_email", "email"),
        Index("idx_user_oauth", "oauth_provider", "oauth_id"),
    )


class Task(Base):
    """User tasks with priorities and status."""

    __tablename__ = "tasks"

    class PriorityLevel(str, enum.Enum):
        HIGH = "high"
        MEDIUM = "medium"
        LOW = "low"

    class TaskStatus(str, enum.Enum):
        TODO = "todo"
        IN_PROGRESS = "in_progress"
        COMPLETED = "completed"
        CANCELLED = "cancelled"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    priority = Column(
        Enum(
            PriorityLevel,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=PriorityLevel.MEDIUM,
    )
    status = Column(
        Enum(
            TaskStatus,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=TaskStatus.TODO,
    )
    
    # Scheduling
    due_date = Column(DateTime, nullable=True)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)
    completed_at = Column(DateTime, nullable=True)
    
    # AI Generated
    ai_generated = Column(Boolean, nullable=False, default=False)
    ai_metadata = Column(JSON, nullable=True)  # {"reasoning": "...", "confidence": 0.95}

    # Relationships
    user = relationship("User", back_populates="tasks")

    __table_args__ = (
        Index("idx_task_user_status", "user_id", "status"),
        Index("idx_task_user_due", "user_id", "due_date"),
        CheckConstraint("completed_at IS NULL OR status = 'completed'"),
    )


class CalendarEvent(Base):
    """Google Calendar events."""

    __tablename__ = "calendar_events"

    class EventStatus(str, enum.Enum):
        SCHEDULED = "scheduled"
        CONFIRMED = "confirmed"
        TENTATIVE = "tentative"
        CANCELLED = "cancelled"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    google_event_id = Column(String(255), nullable=True, unique=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    title = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    status = Column(
        Enum(
            EventStatus,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=EventStatus.SCHEDULED,
    )
    
    # Time
    start_time = Column(DateTime, nullable=False)
    end_time = Column(DateTime, nullable=False)
    all_day = Column(Boolean, nullable=False, default=False)
    
    # Location & participants
    location = Column(String(255), nullable=True)
    attendees = Column(JSON, nullable=True)  # [{"email": "...", "status": "accepted"}]
    
    # Metadata
    color_id = Column(String(50), nullable=True)
    reminders = Column(JSON, nullable=True)
    
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="calendar_events")

    __table_args__ = (
        Index("idx_calendar_user_start", "user_id", "start_time"),
        CheckConstraint("start_time < end_time"),
    )


class Email(Base):
    """Gmail emails with processing state."""

    __tablename__ = "emails"

    class EmailStatus(str, enum.Enum):
        RECEIVED = "received"
        DRAFT = "draft"
        SENT = "sent"
        MARKED_FOR_REVIEW = "marked_for_review"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    gmail_message_id = Column(String(255), nullable=True, unique=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    subject = Column(String(500), nullable=False)
    sender = Column(String(255), nullable=True)
    recipients = Column(JSON, nullable=False)  # ["email1@example.com", "email2@example.com"]
    body = Column(Text, nullable=True)
    
    # AI Generated content
    summary = Column(Text, nullable=True)
    draft_reply = Column(Text, nullable=True)
    is_urgent = Column(Boolean, nullable=False, default=False)
    
    status = Column(
        Enum(
            EmailStatus,
            name="emailstatus",
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
        ),
        nullable=False,
        default=EmailStatus.RECEIVED,
    )
    
    # Metadata
    labels = Column(JSON, nullable=True)  # ["important", "work", "follow-up"]
    has_attachments = Column(Boolean, nullable=False, default=False)
    thread_id = Column(String(255), nullable=True, index=True)
    
    received_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="emails")

    __table_args__ = (
        Index("idx_email_user_received", "user_id", "received_at"),
        Index("idx_email_thread", "thread_id"),
    )


class Message(Base):
    """WhatsApp and other messages."""

    __tablename__ = "messages"

    class MessageType(str, enum.Enum):
        WHATSAPP = "whatsapp"
        SMS = "sms"
        OTHER = "other"

    class MessageDirection(str, enum.Enum):
        INBOUND = "inbound"
        OUTBOUND = "outbound"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    external_id = Column(String(255), nullable=True, unique=True, index=True)
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    message_type = Column(Enum(MessageType), nullable=False)
    direction = Column(Enum(MessageDirection), nullable=False)
    
    sender_phone = Column(String(50), nullable=False)
    recipient_phone = Column(String(50), nullable=False)
    
    body = Column(Text, nullable=False)
    
    # AI Generated
    suggested_reply = Column(Text, nullable=True)
    reply_confidence = Column(Float, nullable=True)  # 0.0 to 1.0
    
    received_at = Column(DateTime, nullable=False)
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), nullable=False)

    # Relationships
    user = relationship("User", back_populates="messages")

    __table_args__ = (
        Index("idx_message_user_received", "user_id", "received_at"),
        Index("idx_message_phone", "sender_phone", "recipient_phone"),
    )


class Approval(Base):
    """Outbound action approvals (send email, create event, etc)."""

    __tablename__ = "approvals"

    class ApprovalType(str, enum.Enum):
        SEND_EMAIL = "send_email"
        SEND_MESSAGE = "send_message"
        CREATE_EVENT = "create_event"
        UPDATE_EVENT = "update_event"
        DELETE_EVENT = "delete_event"
        MARK_COMPLETE = "mark_complete"
        SCHEDULE_TASK = "schedule_task"
        OTHER = "other"

    class ApprovalStatus(str, enum.Enum):
        PENDING = "pending"
        APPROVED = "approved"
        REJECTED = "rejected"
        EXPIRED = "expired"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    approval_type = Column(
        Enum(
            ApprovalType,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
            name="approvaltype",
        ),
        nullable=False,
    )
    status = Column(
        Enum(
            ApprovalStatus,
            values_callable=lambda enum_cls: [member.value for member in enum_cls],
            name="approvalstatus",
        ),
        nullable=False,
        default=ApprovalStatus.PENDING,
    )
    
    # What is being approved
    action_description = Column(String(500), nullable=False)
    action_payload = Column(JSON, nullable=False)  # Full data needed to execute action
    
    # AI Context
    ai_reasoning = Column(Text, nullable=True)
    confidence_score = Column(Float, nullable=True)
    
    # Approval Decision
    approved_by = Column(String(36), nullable=True)  # User ID or "auto"
    approved_at = Column(DateTime, nullable=True)
    rejection_reason = Column(Text, nullable=True)
    
    # Expiry
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    expires_at = Column(DateTime, nullable=False)  # TTL for approval

    # Relationships
    user = relationship("User", back_populates="approvals")

    __table_args__ = (
        Index("idx_approval_user_status", "user_id", "status"),
        Index("idx_approval_expires", "expires_at"),
    )


class AgentRun(Base):
    """Agent execution history and state."""

    __tablename__ = "agent_runs"

    class RunStatus(str, enum.Enum):
        STARTED = "started"
        PLANNING = "planning"
        EXECUTING = "executing"
        COMPLETED = "completed"
        FAILED = "failed"
        CANCELLED = "cancelled"

    class RunType(str, enum.Enum):
        MORNING_ROUTINE = "morning_routine"
        END_OF_DAY = "end_of_day"
        USER_QUERY = "user_query"
        SCHEDULED = "scheduled"
        EMAIL_RECEIVED = "email_received"
        MESSAGE_RECEIVED = "message_received"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    
    run_type = Column(Enum(RunType), nullable=False)
    status = Column(Enum(RunStatus), nullable=False, default=RunStatus.STARTED)
    
    # Input & Trigger
    trigger_data = Column(JSON, nullable=True)  # What triggered the run
    
    # Execution
    planner_input = Column(JSON, nullable=True)  # Input to planner node
    planner_output = Column(JSON, nullable=True)  # Decision from planner
    router_decisions = Column(JSON, nullable=True)  # [{tool: "email", action: "..."}]
    tool_results = Column(JSON, nullable=True)  # Results from tool executions
    
    # Final output
    final_response = Column(Text, nullable=True)  # Response to user/summary
    approvals_required = Column(JSON, nullable=True)  # [approval_id1, approval_id2, ...]
    
    # Metrics
    total_tokens_used = Column(Integer, nullable=True)
    llm_cost = Column(DECIMAL(10, 6), nullable=True)  # LLM usage cost
    execution_time_ms = Column(Integer, nullable=True)
    
    # Errors
    error_message = Column(Text, nullable=True)
    error_traceback = Column(Text, nullable=True)
    
    created_at = Column(DateTime, server_default=func.now(), nullable=False)
    started_at = Column(DateTime, nullable=True)
    completed_at = Column(DateTime, nullable=True)

    # Relationships
    user = relationship("User", back_populates="agent_runs")

    __table_args__ = (
        Index("idx_agentrun_user_type", "user_id", "run_type"),
        Index("idx_agentrun_user_created", "user_id", "created_at"),
        Index("idx_agentrun_status", "status"),
    )
