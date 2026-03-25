"""Daily planning service for generating optimized daily plans from tasks, calendar, and emails."""

from datetime import datetime, timedelta
from time import perf_counter
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
import logging

from app.core.logging_config import get_trace_id
from app.core.metrics import metrics_collector
from app.db.models import Task as TaskModel, CalendarEvent, Email, User
from app.repositories.repositories import TaskRepository, CalendarEventRepository, EmailRepository

logger = logging.getLogger(__name__)


class DailyPlanService:
    """Service for generating and managing daily plans."""

    def __init__(self, db_session: Session):
        """Initialize with database session."""
        self.db = db_session
        self.task_repo = TaskRepository(db_session)
        self.calendar_repo = CalendarEventRepository(db_session)
        self.email_repo = EmailRepository(db_session)

    def generate_daily_plan(
        self,
        user_id: str,
        target_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Generate an optimized daily plan for the user.

        Plan includes:
        - High-priority tasks due today
        - Calendar events with free slots
        - Urgent emails requiring attention
        - Recommended task order based on calendar availability

        Args:
            user_id: User ID
            target_date: Target date (defaults to today UTC)

        Returns:
            Daily plan dictionary with tasks, events, free slots, and recommendations
        """
        trace_id = get_trace_id() or "N/A"
        start = perf_counter()
        if target_date is None:
            target_date = datetime.utcnow()

        target_date = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        next_day = target_date + timedelta(days=1)

        # Fetch user's tasks for today
        today_tasks = self.task_repo.get_tasks_due_in_date_range(
            user_id, target_date, next_day
        )

        # Separate by priority and status
        high_priority = [
            t for t in today_tasks
            if t.priority == TaskModel.PriorityLevel.HIGH
            and t.status in [TaskModel.TaskStatus.TODO, TaskModel.TaskStatus.IN_PROGRESS]
        ]
        medium_priority = [
            t for t in today_tasks
            if t.priority == TaskModel.PriorityLevel.MEDIUM
            and t.status in [TaskModel.TaskStatus.TODO, TaskModel.TaskStatus.IN_PROGRESS]
        ]
        low_priority = [
            t for t in today_tasks
            if t.priority == TaskModel.PriorityLevel.LOW
            and t.status in [TaskModel.TaskStatus.TODO, TaskModel.TaskStatus.IN_PROGRESS]
        ]
        completed_today = [
            t for t in today_tasks
            if t.status == TaskModel.TaskStatus.COMPLETED
        ]

        # Fetch user's calendar events for today
        calendar_events = self.calendar_repo.get_user_today_events(user_id)
        calendar_events = sorted(calendar_events, key=lambda e: e.start_time)

        # Find free slots
        free_slots = self.calendar_repo.get_user_free_slots(user_id, target_date)

        # Fetch urgent emails
        urgent_emails = self.email_repo.get_user_urgent_emails(user_id)[:5]

        # Fetch recent unreviewed emails (last 24 hours)
        recent_emails = self.email_repo.get_recent_emails(user_id, hours=24, limit=10)
        unreviewed_emails = [
            e for e in recent_emails
            if e.status == Email.EmailStatus.MARKED_FOR_REVIEW
        ]

        # Calculate task estimation (assume 30 min per task)
        estimated_task_minutes = (
            len(high_priority) * 45 +
            len(medium_priority) * 30 +
            len(low_priority) * 20
        )

        # Estimate available working minutes
        total_free_minutes = sum(
            (slot["end"] - slot["start"]).total_seconds() / 60
            for slot in free_slots
        )

        # Determine if all tasks can fit
        all_tasks_fit = estimated_task_minutes <= total_free_minutes

        response = {
            "date": target_date.isoformat(),
            "summary": {
                "total_tasks": len(today_tasks),
                "high_priority_tasks": len(high_priority),
                "medium_priority_tasks": len(medium_priority),
                "low_priority_tasks": len(low_priority),
                "completed_tasks": len(completed_today),
                "estimated_minutes_needed": estimated_task_minutes,
                "available_minutes": int(total_free_minutes),
                "all_tasks_fit": all_tasks_fit,
                "urgent_emails": len(urgent_emails),
                "unreviewed_emails": len(unreviewed_emails),
            },
            "schedule": {
                "calendar_events": [
                    {
                        "id": e.id,
                        "title": e.title,
                        "start_time": e.start_time.isoformat(),
                        "end_time": e.end_time.isoformat(),
                        "location": e.location,
                        "duration_minutes": int((e.end_time - e.start_time).total_seconds() / 60),
                    }
                    for e in calendar_events
                ],
                "free_slots": [
                    {
                        "start": slot["start"].isoformat(),
                        "end": slot["end"].isoformat(),
                        "duration_minutes": int((slot["end"] - slot["start"]).total_seconds() / 60),
                    }
                    for slot in free_slots
                ],
            },
            "tasks_by_priority": {
                "high": [
                    {
                        "id": t.id,
                        "title": t.title,
                        "description": t.description,
                        "priority": t.priority.value,
                        "due_date": t.due_date.isoformat() if t.due_date else None,
                        "status": t.status.value,
                        "ai_generated": t.ai_generated,
                        "estimated_minutes": 45,
                    }
                    for t in high_priority
                ],
                "medium": [
                    {
                        "id": t.id,
                        "title": t.title,
                        "description": t.description,
                        "priority": t.priority.value,
                        "due_date": t.due_date.isoformat() if t.due_date else None,
                        "status": t.status.value,
                        "ai_generated": t.ai_generated,
                        "estimated_minutes": 30,
                    }
                    for t in medium_priority
                ],
                "low": [
                    {
                        "id": t.id,
                        "title": t.title,
                        "description": t.description,
                        "priority": t.priority.value,
                        "due_date": t.due_date.isoformat() if t.due_date else None,
                        "status": t.status.value,
                        "ai_generated": t.ai_generated,
                        "estimated_minutes": 20,
                    }
                    for t in low_priority
                ],
            },
            "emails": {
                "urgent": [
                    {
                        "id": e.id,
                        "subject": e.subject,
                        "sender": e.sender,
                        "summary": e.summary,
                        "is_urgent": e.is_urgent,
                        "received_at": e.received_at.isoformat(),
                    }
                    for e in urgent_emails[:3]
                ],
                "unreviewed_count": len(unreviewed_emails),
            },
            "recommendations": self._generate_recommendations(
                high_priority,
                medium_priority,
                low_priority,
                all_tasks_fit,
                urgent_emails,
                len(unreviewed_emails),
            ),
        }

        duration_ms = (perf_counter() - start) * 1000
        metrics_collector.record_agent_step(
            step="planning.generate_daily_plan",
            status="success",
            duration_ms=duration_ms,
        )
        logger.info(
            "planning.daily_plan.generated",
            extra={
                "trace_id": trace_id,
                "user_id": user_id,
                "duration_ms": round(duration_ms, 2),
                "task_count": len(today_tasks),
                "event_count": len(calendar_events),
                "urgent_email_count": len(urgent_emails),
            },
        )
        return response

    def _generate_recommendations(
        self,
        high_priority: List[TaskModel],
        medium_priority: List[TaskModel],
        low_priority: List[TaskModel],
        all_fit: bool,
        urgent_emails: List[Email],
        unreviewed_count: int,
    ) -> List[str]:
        """Generate actionable recommendations for the day."""
        recommendations = []

        # Email recommendations
        if len(urgent_emails) > 0:
            recommendations.append(
                f"⚠️ Respond to {len(urgent_emails)} urgent email(s) first thing"
            )
        if unreviewed_count > 0:
            recommendations.append(
                f"📧 Review {unreviewed_count} unread email(s) during breaks"
            )

        # Priority recommendations
        if len(high_priority) > 3:
            recommendations.append(
                f"🎯 Focus on {len(high_priority)} high-priority tasks - consider delegating or deferring lower priority work"
            )
        elif len(high_priority) > 0:
            recommendations.append(
                f"🎯 Prioritize {len(high_priority)} high-priority task(s) first"
            )

        # Capacity recommendations
        if not all_fit:
            recommendations.append(
                "⏰ Everything won't fit today - suggest deferring low-priority or medium-priority tasks"
            )
        else:
            recommendations.append(
                "✅ You can complete all tasks today if you stay focused"
            )

        # Overload recommendations
        if len(high_priority) + len(medium_priority) > 8:
            recommendations.append(
                "💡 Consider batch-processing emails to reclaim focus time for tasks"
            )

        # Default if no specific recommendations
        if not recommendations:
            recommendations.append(
                "📋 Your day looks manageable - great opportunity for deep work"
            )

        return recommendations

    def get_tasks_summary(
        self,
        user_id: str,
        target_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Get a quick summary of today's tasks (lightweight version).

        Args:
            user_id: User ID
            target_date: Target date (defaults to today UTC)

        Returns:
            Task summary dictionary
        """
        trace_id = get_trace_id() or "N/A"
        start = perf_counter()
        if target_date is None:
            target_date = datetime.utcnow()

        target_date = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        next_day = target_date + timedelta(days=1)

        # Fetch today's tasks
        today_tasks = self.task_repo.get_tasks_due_in_date_range(
            user_id, target_date, next_day
        )

        incomplete_tasks = [
            t for t in today_tasks
            if t.status in [TaskModel.TaskStatus.TODO, TaskModel.TaskStatus.IN_PROGRESS]
        ]

        high_priority = [
            t for t in incomplete_tasks
            if t.priority == TaskModel.PriorityLevel.HIGH
        ]

        response = {
            "date": target_date.isoformat(),
            "total_tasks": len(incomplete_tasks),
            "high_priority": len(high_priority),
            "tasks": [
                {
                    "id": t.id,
                    "title": t.title,
                    "priority": t.priority.value,
                    "status": t.status.value,
                }
                for t in sorted(
                    incomplete_tasks,
                    key=lambda t: (
                        {"high": 0, "medium": 1, "low": 2}[t.priority.value],
                        t.created_at
                    )
                )
            ],
        }
        duration_ms = (perf_counter() - start) * 1000
        metrics_collector.record_agent_step(
            step="planning.get_tasks_summary",
            status="success",
            duration_ms=duration_ms,
        )
        logger.info(
            "planning.task_summary.generated",
            extra={
                "trace_id": trace_id,
                "user_id": user_id,
                "duration_ms": round(duration_ms, 2),
                "total_tasks": len(incomplete_tasks),
            },
        )
        return response

    def estimate_daily_workload(
        self,
        user_id: str,
        target_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Estimate the workload for the day.

        Returns estimated minutes needed for all tasks and available free time.

        Args:
            user_id: User ID
            target_date: Target date (defaults to today UTC)

        Returns:
            Workload estimation dictionary
        """
        if target_date is None:
            target_date = datetime.utcnow()

        target_date = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        next_day = target_date + timedelta(days=1)

        # Fetch data
        today_tasks = self.task_repo.get_tasks_due_in_date_range(
            user_id, target_date, next_day
        )
        free_slots = self.calendar_repo.get_user_free_slots(user_id, target_date)

        # Filter incomplete tasks
        incomplete_tasks = [
            t for t in today_tasks
            if t.status in [TaskModel.TaskStatus.TODO, TaskModel.TaskStatus.IN_PROGRESS]
        ]

        # Estimate minutes (configurable per priority)
        estimates = {
            TaskModel.PriorityLevel.HIGH: 45,
            TaskModel.PriorityLevel.MEDIUM: 30,
            TaskModel.PriorityLevel.LOW: 20,
        }

        total_estimated_minutes = sum(
            estimates.get(t.priority, 30) for t in incomplete_tasks
        )

        available_minutes = sum(
            int((slot["end"] - slot["start"]).total_seconds() / 60)
            for slot in free_slots
        )

        return {
            "estimated_minutes": total_estimated_minutes,
            "available_minutes": available_minutes,
            "can_fit": total_estimated_minutes <= available_minutes,
            "surplus_deficit_minutes": available_minutes - total_estimated_minutes,
            "task_count": len(incomplete_tasks),
            "high_priority_count": len(
                [t for t in incomplete_tasks if t.priority == TaskModel.PriorityLevel.HIGH]
            ),
            "free_slots_count": len(free_slots),
        }
