"""Summary trigger service for morning and end-of-day summaries."""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from sqlalchemy.orm import Session
import logging

from app.db.models import Task as TaskModel, CalendarEvent, Email
from app.repositories.repositories import TaskRepository, CalendarEventRepository, EmailRepository

logger = logging.getLogger(__name__)


class SummaryTriggerService:
    """Service for generating triggered summaries (morning and end-of-day)."""

    def __init__(self, db_session: Session):
        """Initialize with database session."""
        self.db = db_session
        self.task_repo = TaskRepository(db_session)
        self.calendar_repo = CalendarEventRepository(db_session)
        self.email_repo = EmailRepository(db_session)

    def generate_morning_summary(
        self,
        user_id: str,
        target_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Generate morning summary for user.

        Includes:
        - Number of tasks due today (by priority)
        - Calendar events scheduled for today
        - Urgent emails requiring attention
        - Recommended focus areas

        Args:
            user_id: User ID
            target_date: Target date (defaults to today UTC)

        Returns:
            Morning summary dictionary
        """
        if target_date is None:
            target_date = datetime.utcnow()

        target_date = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        next_day = target_date + timedelta(days=1)

        # Fetch today's tasks
        today_tasks = self.task_repo.get_tasks_due_in_date_range(
            user_id, target_date, next_day
        )

        # Separate by priority
        high_priority_tasks = [
            t for t in today_tasks
            if t.priority == TaskModel.PriorityLevel.HIGH
            and t.status in [TaskModel.TaskStatus.TODO, TaskModel.TaskStatus.IN_PROGRESS]
        ]
        medium_priority_tasks = [
            t for t in today_tasks
            if t.priority == TaskModel.PriorityLevel.MEDIUM
            and t.status in [TaskModel.TaskStatus.TODO, TaskModel.TaskStatus.IN_PROGRESS]
        ]
        low_priority_tasks = [
            t for t in today_tasks
            if t.priority == TaskModel.PriorityLevel.LOW
            and t.status in [TaskModel.TaskStatus.TODO, TaskModel.TaskStatus.IN_PROGRESS]
        ]

        # Fetch calendar events
        calendar_events = self.calendar_repo.get_user_today_events(user_id)
        calendar_events = sorted(calendar_events, key=lambda e: e.start_time)

        # Fetch urgent emails from last 24 hours
        recent_emails = self.email_repo.get_user_recent_emails(user_id, hours=24, limit=20)
        urgent_emails = [e for e in recent_emails if e.is_urgent]

        # Fetch unreviewed emails
        unreviewed_emails = [
            e for e in recent_emails
            if e.status == Email.EmailStatus.MARKED_FOR_REVIEW
        ]

        # Compile summary
        summary = {
            "timestamp": datetime.utcnow().isoformat(),
            "date": target_date.isoformat(),
            "greeting": self._get_morning_greeting(),
            "tasks": {
                "high_priority": {
                    "count": len(high_priority_tasks),
                    "items": [
                        {
                            "id": t.id,
                            "title": t.title,
                            "description": t.description,
                        }
                        for t in high_priority_tasks[:3]
                    ],
                    "sample": True if len(high_priority_tasks) > 3 else False,
                },
                "medium_priority": {
                    "count": len(medium_priority_tasks),
                },
                "low_priority": {
                    "count": len(low_priority_tasks),
                },
                "total_tasks": len(high_priority_tasks) + len(medium_priority_tasks) + len(low_priority_tasks),
            },
            "calendar": {
                "events_today": len(calendar_events),
                "upcoming_events": [
                    {
                        "title": e.title,
                        "start": e.start_time.isoformat(),
                        "end": e.end_time.isoformat(),
                        "duration_minutes": int((e.end_time - e.start_time).total_seconds() / 60),
                    }
                    for e in calendar_events[:3]
                ],
                "has_conflicts": self._check_task_calendar_conflicts(
                    high_priority_tasks, calendar_events
                ),
            },
            "emails": {
                "urgent_count": len(urgent_emails),
                "unreviewed_count": len(unreviewed_emails),
                "urgent_senders": list(set(e.sender for e in urgent_emails[:3]))
                if urgent_emails else [],
            },
            "focus_areas": self._generate_morning_focus_areas(
                high_priority_tasks,
                urgent_emails,
                unreviewed_emails,
            ),
            "weather_insight": "Check weather for outdoor tasks if any",  # Placeholder
        }

        return summary

    def generate_end_of_day_summary(
        self,
        user_id: str,
        target_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Generate end-of-day summary for user.

        Includes:
        - Tasks completed today
        - Tasks that were rolled over to tomorrow
        - Emails processed
        - Calendar events attended
        - Productivity metrics

        Args:
            user_id: User ID
            target_date: Target date (defaults to today UTC)

        Returns:
            End-of-day summary dictionary
        """
        if target_date is None:
            target_date = datetime.utcnow()

        target_date = target_date.replace(hour=0, minute=0, second=0, microsecond=0)
        next_day = target_date + timedelta(days=1)

        # Fetch tasks completed today
        completed_tasks = self.task_repo.get_completed_tasks_today(user_id)

        # Fetch incomplete tasks (to be rolled over)
        incomplete_tasks = self.task_repo.get_user_incomplete_tasks(user_id)
        incomplete_today = [
            t for t in incomplete_tasks
            if t.due_date and target_date <= t.due_date < next_day
        ]

        # Fetch emails processed today
        today_emails = self.email_repo.get_user_recent_emails(user_id, hours=24, limit=100)
        processed_emails = [
            e for e in today_emails
            if e.status != Email.EmailStatus.MARKED_FOR_REVIEW
        ]

        # Calculate metrics
        high_priority_completed = len(
            [t for t in completed_tasks if t.priority == TaskModel.PriorityLevel.HIGH]
        )
        medium_completed = len(
            [t for t in completed_tasks if t.priority == TaskModel.PriorityLevel.MEDIUM]
        )
        low_completed = len(
            [t for t in completed_tasks if t.priority == TaskModel.PriorityLevel.LOW]
        )

        # Productivity score (0-100)
        total_tasks_today = len(completed_tasks) + len(incomplete_today)
        completion_rate = (len(completed_tasks) / total_tasks_today * 100) if total_tasks_today > 0 else 0

        # Compile summary
        summary = {
            "timestamp": datetime.utcnow().isoformat(),
            "date": target_date.isoformat(),
            "greeting": "Great work today! Here's a summary of what you accomplished.",
            "completion": {
                "total_completed": len(completed_tasks),
                "high_priority": high_priority_completed,
                "medium_priority": medium_completed,
                "low_priority": low_completed,
                "completion_rate": round(completion_rate, 1),
            },
            "incomplete": {
                "total_incomplete": len(incomplete_today),
                "rolled_over": len(incomplete_today),
                "items": [
                    {
                        "id": t.id,
                        "title": t.title,
                        "priority": t.priority.value,
                    }
                    for t in incomplete_today[:5]
                ],
                "sample": True if len(incomplete_today) > 5 else False,
            },
            "emails": {
                "processed": len(processed_emails),
                "still_unreviewed": len(
                    [e for e in today_emails if e.status == Email.EmailStatus.MARKED_FOR_REVIEW]
                ),
            },
            "insights": self._generate_end_of_day_insights(
                completed_tasks,
                incomplete_today,
                completion_rate,
            ),
            "recommendations": self._generate_end_of_day_recommendations(
                incomplete_today,
                completion_rate,
            ),
        }

        return summary

    def generate_weekly_summary(
        self,
        user_id: str,
        target_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Generate weekly summary for user.

        Includes:
        - Total tasks completed this week
        - Task completion trends
        - Most productive day
        - Most common task categories
        - Weekly insights and recommendations

        Args:
            user_id: User ID
            target_date: Reference date in the week (defaults to today UTC)

        Returns:
            Weekly summary dictionary
        """
        if target_date is None:
            target_date = datetime.utcnow()

        # Get start and end of week (Monday-Sunday)
        start_of_week = target_date - timedelta(days=target_date.weekday())
        start_of_week = start_of_week.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_week = start_of_week + timedelta(days=7)

        # Fetch week's tasks
        week_tasks = self.task_repo.get_tasks_due_in_date_range(
            user_id, start_of_week, end_of_week
        )

        # Separate completed and incomplete
        completed_this_week = [
            t for t in week_tasks
            if t.status == TaskModel.TaskStatus.COMPLETED
        ]
        incomplete_this_week = [
            t for t in week_tasks
            if t.status in [TaskModel.TaskStatus.TODO, TaskModel.TaskStatus.IN_PROGRESS]
        ]

        # Calculate daily breakdown
        daily_completed = {}
        for i in range(7):
            day = (start_of_week + timedelta(days=i)).date()
            day_completed = len(
                [
                    t for t in completed_this_week
                    if t.completed_at and t.completed_at.date() == day
                ]
            )
            daily_completed[day.isoformat()] = day_completed

        most_productive_day = max(daily_completed.items(), key=lambda x: x[1])[0]

        # Compile summary
        summary = {
            "timestamp": datetime.utcnow().isoformat(),
            "week_of": start_of_week.isoformat(),
            "completion": {
                "total_completed": len(completed_this_week),
                "total_incomplete": len(incomplete_this_week),
                "completion_rate": round(
                    len(completed_this_week) / (len(completed_this_week) + len(incomplete_this_week)) * 100
                    if (len(completed_this_week) + len(incomplete_this_week)) > 0
                    else 0,
                    1
                ),
            },
            "daily_breakdown": daily_completed,
            "most_productive_day": most_productive_day,
            "priority_distribution": {
                "high": len([t for t in completed_this_week if t.priority == TaskModel.PriorityLevel.HIGH]),
                "medium": len([t for t in completed_this_week if t.priority == TaskModel.PriorityLevel.MEDIUM]),
                "low": len([t for t in completed_this_week if t.priority == TaskModel.PriorityLevel.LOW]),
            },
            "ai_generated_tasks": len([t for t in completed_this_week if t.ai_generated]),
        }

        return summary

    def _get_morning_greeting(self) -> str:
        """Get a motivational morning greeting."""
        greetings = [
            "🌅 Good morning! Let's make today count.",
            "☀️ Rise and shine! Here's your day ahead.",
            "🚀 Morning energy! Ready to tackle today's goals?",
            "💪 Let's get after it! Here's what's on your plate.",
        ]
        import random
        return random.choice(greetings)

    def _check_task_calendar_conflicts(
        self,
        tasks: List[TaskModel],
        events: List[CalendarEvent],
    ) -> bool:
        """Check if there are potential conflicts between tasks and calendar."""
        # Simple heuristic: if combined duration exceeds available time
        task_minutes = len(tasks) * 30
        event_minutes = sum(
            int((e.end_time - e.start_time).total_seconds() / 60) for e in events
        )
        working_hours = 8 * 60
        return (task_minutes + event_minutes) > working_hours

    def _generate_morning_focus_areas(
        self,
        high_priority: List[TaskModel],
        urgent_emails: List[Email],
        unreviewed_emails: List[Email],
    ) -> List[str]:
        """Generate morning focus areas."""
        areas = []

        if high_priority:
            areas.append(f"🎯 {len(high_priority)} high-priority tasks to tackle")

        if urgent_emails:
            areas.append(f"⚠️ {len(urgent_emails)} urgent emails need your attention")

        if unreviewed_emails:
            areas.append(f"📧 {len(unreviewed_emails)} emails to review")

        if not areas:
            areas.append("✨ Clear day ahead - great time for deep work")

        return areas

    def _generate_end_of_day_insights(
        self,
        completed: List[TaskModel],
        incomplete: List[TaskModel],
        completion_rate: float,
    ) -> List[str]:
        """Generate end-of-day insights."""
        insights = []

        if completion_rate >= 80:
            insights.append(f"🌟 Excellent work! You completed {completion_rate:.0f}% of your tasks.")
        elif completion_rate >= 60:
            insights.append(f"👍 Good progress today! {completion_rate:.0f}% tasks completed.")
        elif completion_rate >= 30:
            insights.append(f"💡 {completion_rate:.0f}% of tasks completed. Some days are harder than others!")
        else:
            insights.append("📝 Challenging day. No worries—tomorrow is a fresh start.")

        if len(completed) > 5:
            insights.append(f"⚡ You powered through {len(completed)} tasks!")

        if len(incomplete) > 10:
            insights.append("🎯 Lots on your plate tomorrow. Prioritize what matters most.")

        return insights

    def _generate_end_of_day_recommendations(
        self,
        incomplete: List[TaskModel],
        completion_rate: float,
    ) -> List[str]:
        """Generate end-of-day recommendations."""
        recommendations = []

        if incomplete:
            high_priority_incomplete = len(
                [t for t in incomplete if t.priority == TaskModel.PriorityLevel.HIGH]
            )
            if high_priority_incomplete > 0:
                recommendations.append(
                    f"🔴 {high_priority_incomplete} high-priority task(s) rolled to tomorrow. Start with these."
                )

        if completion_rate < 50:
            recommendations.append(
                "📌 Consider breaking tasks into smaller chunks for tomorrow's planning."
            )

        if len(incomplete) == 0:
            recommendations.append(
                "🎉 Perfect day! You completed everything. Well done!"
            )

        return recommendations
