"""Concrete repository implementations for each entity."""

from sqlalchemy.orm import Session
from sqlalchemy import desc, and_, or_
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
import logging

from app.db.models import User, Task, CalendarEvent, Email, Message, Approval, AgentRun
from app.repositories.base import BaseRepository

logger = logging.getLogger(__name__)


class UserRepository(BaseRepository[User]):
    """Repository for User entity."""

    def __init__(self, session: Session):
        super().__init__(session, User)

    def get_by_email(self, email: str) -> Optional[User]:
        """Get user by email address."""
        return self.find_one(email=email)

    def get_by_oauth(self, oauth_provider: str, oauth_id: str) -> Optional[User]:
        """Get user by OAuth provider and ID."""
        return self.find_one(oauth_provider=oauth_provider, oauth_id=oauth_id)

    def get_active_users(self, skip: int = 0, limit: int = 100) -> List[User]:
        """Get all active users."""
        return self.session.query(self.model_class).filter(
            self.model_class.is_active == True
        ).offset(skip).limit(limit).all()

    def email_exists(self, email: str) -> bool:
        """Check if email already registered."""
        return self.session.query(self.model_class).filter(
            self.model_class.email == email
        ).first() is not None


class TaskRepository(BaseRepository[Task]):
    """Repository for Task entity."""

    def __init__(self, session: Session):
        super().__init__(session, Task)

    def get_user_tasks(self, user_id: str, skip: int = 0, limit: int = 100) -> List[Task]:
        """Get all tasks for a user."""
        return self.session.query(self.model_class).filter(
            self.model_class.user_id == user_id
        ).offset(skip).limit(limit).all()

    def get_user_tasks_by_status(self, user_id: str, status: Task.TaskStatus) -> List[Task]:
        """Get user tasks filtered by status."""
        return self.find(user_id=user_id, status=status)

    def get_user_overdue_tasks(self, user_id: str) -> List[Task]:
        """Get user tasks that are overdue (past due_date, not completed)."""
        return self.session.query(self.model_class).filter(
            and_(
                self.model_class.user_id == user_id,
                self.model_class.due_date < datetime.utcnow(),
                self.model_class.status != Task.TaskStatus.COMPLETED,
            )
        ).all()

    def get_user_high_priority_tasks(self, user_id: str) -> List[Task]:
        """Get user's high priority tasks."""
        return self.find(user_id=user_id, priority=Task.PriorityLevel.HIGH)

    def get_user_tasks_due_today(self, user_id: str) -> List[Task]:
        """Get user tasks due today."""
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)
        return self.session.query(self.model_class).filter(
            and_(
                self.model_class.user_id == user_id,
                self.model_class.due_date >= today,
                self.model_class.due_date < tomorrow,
            )
        ).all()

    def get_ai_generated_tasks(self, user_id: str) -> List[Task]:
        """Get AI-generated tasks for user."""
        return self.find(user_id=user_id, ai_generated=True)

    def mark_incomplete_tasks_as_carried_over(self, user_id: str) -> int:
        """Mark incomplete tasks as carried over with updated due date."""
        incomplete_tasks = self.session.query(self.model_class).filter(
            and_(
                self.model_class.user_id == user_id,
                self.model_class.status != Task.TaskStatus.COMPLETED,
            )
        ).all()
        
        next_day = datetime.utcnow() + timedelta(days=1)
        for task in incomplete_tasks:
            task.due_date = next_day
        
        self.session.flush()
        return len(incomplete_tasks)

    def get_user_incomplete_tasks(self, user_id: str) -> List[Task]:
        """Get all incomplete tasks for a user."""
        return self.session.query(self.model_class).filter(
            and_(
                self.model_class.user_id == user_id,
                self.model_class.status.in_([
                    Task.TaskStatus.TODO,
                    Task.TaskStatus.IN_PROGRESS,
                ])
            )
        ).all()

    def get_user_tasks_by_priority_and_status(
        self, user_id: str, status: Optional[Task.TaskStatus] = None
    ) -> List[Task]:
        """Get user tasks sorted by priority (HIGH -> MEDIUM -> LOW)."""
        query = self.session.query(self.model_class).filter(
            self.model_class.user_id == user_id
        )
        if status:
            query = query.filter(self.model_class.status == status)
        
        # Sort by priority order
        priority_order = {
            Task.PriorityLevel.HIGH: 0,
            Task.PriorityLevel.MEDIUM: 1,
            Task.PriorityLevel.LOW: 2,
        }
        return sorted(
            query.all(),
            key=lambda t: (priority_order[t.priority], t.created_at)
        )

    def mark_task_completed(self, task_id: str) -> Optional[Task]:
        """Mark a task as completed."""
        task = self.get_by_id(task_id)
        if task:
            task.status = Task.TaskStatus.COMPLETED
            task.completed_at = datetime.utcnow()
            self.session.flush()
        return task

    def get_tasks_due_in_date_range(
        self, user_id: str, start_date: datetime, end_date: datetime
    ) -> List[Task]:
        """Get user tasks due within a date range."""
        return self.session.query(self.model_class).filter(
            and_(
                self.model_class.user_id == user_id,
                self.model_class.due_date >= start_date,
                self.model_class.due_date <= end_date,
            )
        ).order_by(self.model_class.due_date).all()

    def get_completed_tasks_today(self, user_id: str) -> List[Task]:
        """Get tasks completed today by a user."""
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)
        return self.session.query(self.model_class).filter(
            and_(
                self.model_class.user_id == user_id,
                self.model_class.status == Task.TaskStatus.COMPLETED,
                self.model_class.completed_at >= today,
                self.model_class.completed_at < tomorrow,
            )
        ).all()


class CalendarEventRepository(BaseRepository[CalendarEvent]):
    """Repository for CalendarEvent entity."""

    def __init__(self, session: Session):
        super().__init__(session, CalendarEvent)

    def get_user_events(self, user_id: str, skip: int = 0, limit: int = 100) -> List[CalendarEvent]:
        """Get all events for a user."""
        return self.session.query(self.model_class).filter(
            self.model_class.user_id == user_id
        ).order_by(self.model_class.start_time).offset(skip).limit(limit).all()

    def get_user_events_by_date_range(self, user_id: str, start_date: datetime, end_date: datetime) -> List[CalendarEvent]:
        """Get user events within a date range."""
        return self.session.query(self.model_class).filter(
            and_(
                self.model_class.user_id == user_id,
                self.model_class.start_time >= start_date,
                self.model_class.end_time <= end_date,
            )
        ).order_by(self.model_class.start_time).all()

    def get_user_today_events(self, user_id: str) -> List[CalendarEvent]:
        """Get user's events for today."""
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow = today + timedelta(days=1)
        return self.get_user_events_by_date_range(user_id, today, tomorrow)

    def get_user_free_slots(self, user_id: str, date: datetime, min_duration_minutes: int = 30) -> List[Dict[str, datetime]]:
        """Find free time slots for user on a given date."""
        day_events = self.session.query(self.model_class).filter(
            and_(
                self.model_class.user_id == user_id,
                self.model_class.start_time >= date.replace(hour=0, minute=0, second=0),
                self.model_class.end_time <= date.replace(hour=23, minute=59, second=59),
            )
        ).order_by(self.model_class.start_time).all()

        # Calculate free slots between events
        free_slots = []
        day_start = date.replace(hour=9, minute=0)
        day_end = date.replace(hour=18, minute=0)

        if not day_events:
            free_slots.append({"start": day_start, "end": day_end})
        else:
            # Check slot before first event
            if day_events[0].start_time > day_start:
                duration = (day_events[0].start_time - day_start).total_seconds() / 60
                if duration >= min_duration_minutes:
                    free_slots.append({"start": day_start, "end": day_events[0].start_time})

            # Check slots between events
            for i in range(len(day_events) - 1):
                gap_start = day_events[i].end_time
                gap_end = day_events[i + 1].start_time
                duration = (gap_end - gap_start).total_seconds() / 60
                if duration >= min_duration_minutes:
                    free_slots.append({"start": gap_start, "end": gap_end})

            # Check slot after last event
            if day_events[-1].end_time < day_end:
                duration = (day_end - day_events[-1].end_time).total_seconds() / 60
                if duration >= min_duration_minutes:
                    free_slots.append({"start": day_events[-1].end_time, "end": day_end})

        return free_slots

    def get_by_google_event_id(self, google_event_id: str) -> Optional[CalendarEvent]:
        """Get event by Google Calendar event ID."""
        return self.find_one(google_event_id=google_event_id)


class EmailRepository(BaseRepository[Email]):
    """Repository for Email entity."""

    def __init__(self, session: Session):
        super().__init__(session, Email)

    def get_user_emails(self, user_id: str, skip: int = 0, limit: int = 100) -> List[Email]:
        """Get all emails for a user."""
        return self.session.query(self.model_class).filter(
            self.model_class.user_id == user_id
        ).order_by(desc(self.model_class.received_at)).offset(skip).limit(limit).all()

    def get_user_emails_by_status(self, user_id: str, status: Email.EmailStatus) -> List[Email]:
        """Get user emails filtered by status."""
        return self.find(user_id=user_id, status=status)

    def get_user_urgent_emails(self, user_id: str, limit: int = 20) -> List[Email]:
        """Get urgent emails for user."""
        return self.session.query(self.model_class).filter(
            and_(
                self.model_class.user_id == user_id,
                self.model_class.is_urgent == True,
            )
        ).order_by(desc(self.model_class.received_at)).limit(limit).all()

    def get_user_unread_emails(self, user_id: str) -> List[Email]:
        """Get unread emails (marked_for_review status)."""
        return self.find(user_id=user_id, status=Email.EmailStatus.MARKED_FOR_REVIEW)

    def get_user_recent_emails(self, user_id: str, hours: int = 24, limit: int = 50) -> List[Email]:
        """Get recent emails received within last N hours."""
        since = datetime.utcnow() - timedelta(hours=hours)
        return self.session.query(self.model_class).filter(
            and_(
                self.model_class.user_id == user_id,
                self.model_class.received_at >= since,
            )
        ).order_by(desc(self.model_class.received_at)).limit(limit).all()

    def get_by_gmail_message_id(self, gmail_message_id: str) -> Optional[Email]:
        """Get email by Gmail message ID."""
        return self.find_one(gmail_message_id=gmail_message_id)

    def get_thread_emails(self, thread_id: str) -> List[Email]:
        """Get all emails in a thread."""
        return self.find(thread_id=thread_id)


class MessageRepository(BaseRepository[Message]):
    """Repository for Message entity."""

    def __init__(self, session: Session):
        super().__init__(session, Message)

    def get_user_messages(self, user_id: str, skip: int = 0, limit: int = 100) -> List[Message]:
        """Get all messages for a user."""
        return self.session.query(self.model_class).filter(
            self.model_class.user_id == user_id
        ).order_by(desc(self.model_class.received_at)).offset(skip).limit(limit).all()

    def get_conversation(self, user_id: str, phone_number: str, limit: int = 50) -> List[Message]:
        """Get conversation history with a specific phone number."""
        return self.session.query(self.model_class).filter(
            and_(
                self.model_class.user_id == user_id,
                or_(
                    self.model_class.sender_phone == phone_number,
                    self.model_class.recipient_phone == phone_number,
                )
            )
        ).order_by(desc(self.model_class.received_at)).limit(limit).all()

    def get_inbound_messages(self, user_id: str) -> List[Message]:
        """Get all inbound messages for user."""
        return self.find(user_id=user_id, direction=Message.MessageDirection.INBOUND)

    def get_outbound_messages(self, user_id: str) -> List[Message]:
        """Get all outbound messages sent by user."""
        return self.find(user_id=user_id, direction=Message.MessageDirection.OUTBOUND)

    def get_by_external_id(self, external_id: str) -> Optional[Message]:
        """Get message by external provider ID."""
        return self.find_one(external_id=external_id)


class ApprovalRepository(BaseRepository[Approval]):
    """Repository for Approval entity."""

    def __init__(self, session: Session):
        super().__init__(session, Approval)

    def get_user_approvals(self, user_id: str, skip: int = 0, limit: int = 100) -> List[Approval]:
        """Get all approvals for a user."""
        return self.session.query(self.model_class).filter(
            self.model_class.user_id == user_id
        ).order_by(desc(self.model_class.created_at)).offset(skip).limit(limit).all()

    def get_pending_approvals(self, user_id: str) -> List[Approval]:
        """Get all pending approvals for user."""
        return self.session.query(self.model_class).filter(
            and_(
                self.model_class.user_id == user_id,
                self.model_class.status == Approval.ApprovalStatus.PENDING,
                self.model_class.expires_at > datetime.utcnow(),
            )
        ).order_by(self.model_class.created_at).all()

    def get_expired_approvals(self) -> List[Approval]:
        """Get all expired approvals across all users."""
        return self.session.query(self.model_class).filter(
            and_(
                self.model_class.status == Approval.ApprovalStatus.PENDING,
                self.model_class.expires_at <= datetime.utcnow(),
            )
        ).all()

    def expire_pending_approvals(self) -> int:
        """Mark all expired approvals as expired."""
        expired = self.get_expired_approvals()
        for approval in expired:
            approval.status = Approval.ApprovalStatus.EXPIRED
        self.session.flush()
        return len(expired)

    def get_user_approvals_by_type(self, user_id: str, approval_type: Approval.ApprovalType) -> List[Approval]:
        """Get user approvals filtered by type."""
        return self.find(user_id=user_id, approval_type=approval_type)


class AgentRunRepository(BaseRepository[AgentRun]):
    """Repository for AgentRun entity."""

    def __init__(self, session: Session):
        super().__init__(session, AgentRun)

    def get_user_runs(self, user_id: str, skip: int = 0, limit: int = 100) -> List[AgentRun]:
        """Get all agent runs for a user."""
        return self.session.query(self.model_class).filter(
            self.model_class.user_id == user_id
        ).order_by(desc(self.model_class.created_at)).offset(skip).limit(limit).all()

    def get_user_runs_by_type(self, user_id: str, run_type: AgentRun.RunType, limit: int = 50) -> List[AgentRun]:
        """Get user runs filtered by type."""
        return self.session.query(self.model_class).filter(
            and_(
                self.model_class.user_id == user_id,
                self.model_class.run_type == run_type,
            )
        ).order_by(desc(self.model_class.created_at)).limit(limit).all()

    def get_user_active_run(self, user_id: str) -> Optional[AgentRun]:
        """Get currently active (in-progress) run for user."""
        return self.session.query(self.model_class).filter(
            and_(
                self.model_class.user_id == user_id,
                self.model_class.status.in_([AgentRun.RunStatus.STARTED, AgentRun.RunStatus.PLANNING, AgentRun.RunStatus.EXECUTING]),
            )
        ).order_by(desc(self.model_class.created_at)).first()

    def get_failed_runs(self, hours: int = 24) -> List[AgentRun]:
        """Get failed runs from last N hours."""
        since = datetime.utcnow() - timedelta(hours=hours)
        return self.session.query(self.model_class).filter(
            and_(
                self.model_class.status == AgentRun.RunStatus.FAILED,
                self.model_class.created_at >= since,
            )
        ).order_by(desc(self.model_class.created_at)).all()

    def get_user_today_runs(self, user_id: str) -> List[AgentRun]:
        """Get all agent runs for user today."""
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        return self.session.query(self.model_class).filter(
            and_(
                self.model_class.user_id == user_id,
                self.model_class.created_at >= today,
            )
        ).order_by(desc(self.model_class.created_at)).all()

    def get_total_tokens_used(self, user_id: str, hours: int = 24) -> int:
        """Get total LLM tokens used by user in last N hours."""
        since = datetime.utcnow() - timedelta(hours=hours)
        result = self.session.query(
            self.model_class.total_tokens_used
        ).filter(
            and_(
                self.model_class.user_id == user_id,
                self.model_class.created_at >= since,
                self.model_class.total_tokens_used.isnot(None),
            )
        ).all()
        return sum([r[0] for r in result if r[0]])

    def get_total_cost(self, user_id: str, hours: int = 24) -> float:
        """Get total LLM cost for user in last N hours."""
        since = datetime.utcnow() - timedelta(hours=hours)
        result = self.session.query(
            self.model_class.llm_cost
        ).filter(
            and_(
                self.model_class.user_id == user_id,
                self.model_class.created_at >= since,
                self.model_class.llm_cost.isnot(None),
            )
        ).all()
        return float(sum([float(r[0]) for r in result if r[0]]))


class EmailRepository(BaseRepository[Email]):
    """Repository for Email entity."""

    def __init__(self, session: Session):
        super().__init__(session, Email)

    def get_user_emails(self, user_id: str, skip: int = 0, limit: int = 100) -> List[Email]:
        """Get all emails for a user."""
        return self.session.query(self.model_class).filter(
            self.model_class.user_id == user_id
        ).order_by(desc(self.model_class.received_at)).offset(skip).limit(limit).all()

    def get_user_unread_emails(self, user_id: str) -> List[Email]:
        """Get unread emails for user."""
        return self.session.query(self.model_class).filter(
            and_(
                self.model_class.user_id == user_id,
                self.model_class.status == Email.EmailStatus.RECEIVED,
            )
        ).order_by(desc(self.model_class.received_at)).all()

    def get_user_urgent_emails(self, user_id: str) -> List[Email]:
        """Get urgent/flagged emails for user."""
        return self.session.query(self.model_class).filter(
            and_(
                self.model_class.user_id == user_id,
                self.model_class.is_urgent == True,
            )
        ).order_by(desc(self.model_class.received_at)).all()

    def get_emails_by_sender(self, user_id: str, sender: str) -> List[Email]:
        """Get emails from a specific sender."""
        return self.session.query(self.model_class).filter(
            and_(
                self.model_class.user_id == user_id,
                self.model_class.sender == sender,
            )
        ).order_by(desc(self.model_class.received_at)).all()

    def get_emails_in_thread(self, thread_id: str, user_id: str) -> List[Email]:
        """Get all emails in a thread."""
        return self.session.query(self.model_class).filter(
            and_(
                self.model_class.user_id == user_id,
                self.model_class.thread_id == thread_id,
            )
        ).order_by(self.model_class.received_at).all()

    def get_emails_by_label(self, user_id: str, label: str) -> List[Email]:
        """Get emails with a specific label."""
        return self.session.query(self.model_class).filter(
            and_(
                self.model_class.user_id == user_id,
            )
        ).all()  # Filter by label in memory since it's a JSON field

    def get_recent_emails(self, user_id: str, hours: int = 24, limit: int = 20) -> List[Email]:
        """Get recent emails from last N hours."""
        since = datetime.utcnow() - timedelta(hours=hours)
        return self.session.query(self.model_class).filter(
            and_(
                self.model_class.user_id == user_id,
                self.model_class.received_at >= since,
            )
        ).order_by(desc(self.model_class.received_at)).limit(limit).all()

    def mark_as_urgent(self, email_id: str) -> bool:
        """Mark email as urgent."""
        email = self.get_by_id(email_id)
        if email:
            email.is_urgent = True
            self.session.flush()
            return True
        return False

    def get_emails_with_attachments(self, user_id: str) -> List[Email]:
        """Get emails with attachments."""
        return self.session.query(self.model_class).filter(
            and_(
                self.model_class.user_id == user_id,
                self.model_class.has_attachments == True,
            )
        ).order_by(desc(self.model_class.received_at)).all()

    def get_email_by_gmail_id(self, gmail_message_id: str) -> Optional[Email]:
        """Get email by Gmail message ID."""
        return self.find_one(gmail_message_id=gmail_message_id)
