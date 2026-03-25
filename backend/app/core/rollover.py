"""End-of-day rollover service for moving incomplete tasks to next day."""

from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy.orm import Session
import logging

from app.db.models import Task as TaskModel, CalendarEvent
from app.repositories.repositories import TaskRepository, CalendarEventRepository

logger = logging.getLogger(__name__)


class EndOfDayRolloverService:
    """Service for end-of-day task rollover and carryover operations."""

    def __init__(self, db_session: Session):
        """Initialize with database session."""
        self.db = db_session
        self.task_repo = TaskRepository(db_session)
        self.calendar_repo = CalendarEventRepository(db_session)

    def perform_end_of_day_rollover(
        self,
        user_id: str,
        from_date: Optional[datetime] = None,
        to_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Perform end-of-day rollover for incomplete tasks.

        Moves all incomplete tasks from 'from_date' to 'to_date' (next day by default).
        Optionally reschedules based on calendar availability.

        Args:
            user_id: User ID
            from_date: Date to collect incomplete tasks (defaults to today UTC)
            to_date: Target date for rollover (defaults to tomorrow UTC)

        Returns:
            Rollover result with moved tasks and statistics
        """
        if from_date is None:
            from_date = datetime.utcnow()
        if to_date is None:
            to_date = from_date + timedelta(days=1)

        # Normalize dates
        from_date = from_date.replace(hour=0, minute=0, second=0, microsecond=0)
        from_next = from_date + timedelta(days=1)
        to_date = to_date.replace(hour=0, minute=0, second=0, microsecond=0)

        # Fetch incomplete tasks from the date
        tasks_from_date = self.task_repo.get_tasks_due_in_date_range(
            user_id, from_date, from_next
        )

        incomplete_tasks = [
            t for t in tasks_from_date
            if t.status in [TaskModel.TaskStatus.TODO, TaskModel.TaskStatus.IN_PROGRESS]
        ]

        if not incomplete_tasks:
            logger.info(f"No incomplete tasks for user {user_id} on {from_date.date()}")
            return {
                "from_date": from_date.isoformat(),
                "to_date": to_date.isoformat(),
                "rolled_over_count": 0,
                "rolled_over_tasks": [],
                "high_priority_count": 0,
                "medium_priority_count": 0,
                "low_priority_count": 0,
            }

        # Separate by priority
        high_priority = [t for t in incomplete_tasks if t.priority == TaskModel.PriorityLevel.HIGH]
        medium_priority = [t for t in incomplete_tasks if t.priority == TaskModel.PriorityLevel.MEDIUM]
        low_priority = [t for t in incomplete_tasks if t.priority == TaskModel.PriorityLevel.LOW]

        # Get next day's calendar to help with reschedule suggestions
        next_day_events = self.calendar_repo.get_user_today_events(user_id) if to_date.date() == datetime.utcnow().date() else []
        next_day_free_slots = self.calendar_repo.get_user_free_slots(user_id, to_date)

        # Move tasks to next day
        rolled_over = []
        for task in incomplete_tasks:
            task.due_date = to_date
            rolled_over.append(task)
            logger.info(f"Rolled over task {task.id} to {to_date.date()}")

        # Commit changes
        self.db.commit()

        # Generate rollover details
        rollover_details = [
            {
                "id": t.id,
                "title": t.title,
                "description": t.description,
                "priority": t.priority.value,
                "original_due": from_date.isoformat(),
                "new_due": to_date.isoformat(),
                "status": t.status.value,
                "estimated_minutes": self._estimate_minutes(t.priority),
                "suggested_time_slot": self._find_suitable_time_slot(
                    t.priority,
                    next_day_free_slots,
                ),
            }
            for t in rolled_over
        ]

        return {
            "from_date": from_date.isoformat(),
            "to_date": to_date.isoformat(),
            "rolled_over_count": len(rolled_over),
            "rolled_over_tasks": rollover_details,
            "high_priority_count": len(high_priority),
            "medium_priority_count": len(medium_priority),
            "low_priority_count": len(low_priority),
            "total_estimated_minutes": sum(
                self._estimate_minutes(t.priority) for t in rolled_over
            ),
            "available_time_next_day": sum(
                int((slot["end"] - slot["start"]).total_seconds() / 60)
                for slot in next_day_free_slots
            ),
        }

    def suggest_reschedule(
        self,
        user_id: str,
        from_date: Optional[datetime] = None,
        num_days_ahead: int = 3,
    ) -> Dict[str, Any]:
        """
        Suggest reschedule plan for incomplete tasks.

        Analyzes incomplete tasks and suggests spreading them across available days.

        Args:
            user_id: User ID
            from_date: Starting date for analysis (defaults to today UTC)
            num_days_ahead: Number of days to look ahead for scheduling

        Returns:
            Suggested reschedule plan
        """
        if from_date is None:
            from_date = datetime.utcnow()

        from_date = from_date.replace(hour=0, minute=0, second=0, microsecond=0)

        # Fetch incomplete tasks
        incomplete_tasks = self.task_repo.get_user_incomplete_tasks(user_id)

        # Separate by priority
        high_priority = [t for t in incomplete_tasks if t.priority == TaskModel.PriorityLevel.HIGH]
        medium_priority = [t for t in incomplete_tasks if t.priority == TaskModel.PriorityLevel.MEDIUM]
        low_priority = [t for t in incomplete_tasks if t.priority == TaskModel.PriorityLevel.LOW]

        # Build daily capacity map
        daily_capacity = {}
        for i in range(num_days_ahead):
            day = from_date + timedelta(days=i)
            free_slots = self.calendar_repo.get_user_free_slots(user_id, day)
            available_minutes = sum(
                int((slot["end"] - slot["start"]).total_seconds() / 60)
                for slot in free_slots
            )
            daily_capacity[day.date().isoformat()] = {
                "available_minutes": available_minutes,
                "day": day.strftime("%A"),
            }

        # Suggest schedule
        suggestions = {
            "high_priority": self._suggest_task_dates(high_priority, daily_capacity, 45),
            "medium_priority": self._suggest_task_dates(medium_priority, daily_capacity, 30),
            "low_priority": self._suggest_task_dates(low_priority, daily_capacity, 20),
        }

        return {
            "from_date": from_date.isoformat(),
            "forecast_days": num_days_ahead,
            "daily_capacity": daily_capacity,
            "suggestions": suggestions,
            "total_tasks_to_reschedule": len(incomplete_tasks),
        }

    def estimate_day_capacity(
        self,
        user_id: str,
        target_date: Optional[datetime] = None,
    ) -> Dict[str, Any]:
        """
        Estimate the capacity for a given day.

        Returns available time, scheduled commitments, and task fit estimate.

        Args:
            user_id: User ID
            target_date: Target date (defaults to today UTC)

        Returns:
            Capacity estimation dictionary
        """
        if target_date is None:
            target_date = datetime.utcnow()

        target_date = target_date.replace(hour=0, minute=0, second=0, microsecond=0)

        # Fetch calendar events
        events = self.calendar_repo.get_user_today_events(user_id)

        # Calculate event time
        event_minutes = sum(
            int((e.end_time - e.start_time).total_seconds() / 60)
            for e in events
        )

        # Get free slots
        free_slots = self.calendar_repo.get_user_free_slots(user_id, target_date)
        free_minutes = sum(
            int((slot["end"] - slot["start"]).total_seconds() / 60)
            for slot in free_slots
        )

        # Fetch tasks for this day
        next_day = target_date + timedelta(days=1)
        day_tasks = self.task_repo.get_tasks_due_in_date_range(
            user_id, target_date, next_day
        )
        incomplete_tasks = [
            t for t in day_tasks
            if t.status in [TaskModel.TaskStatus.TODO, TaskModel.TaskStatus.IN_PROGRESS]
        ]

        # Estimate task time
        task_minutes = sum(
            self._estimate_minutes(t.priority) for t in incomplete_tasks
        )

        # Determine capacity level
        if free_minutes == 0:
            capacity_level = "fully_booked"
            utilization = 100.0
        elif task_minutes <= free_minutes * 0.6:
            capacity_level = "comfortable"
            utilization = (task_minutes / free_minutes) * 100
        elif task_minutes <= free_minutes:
            capacity_level = "tight"
            utilization = (task_minutes / free_minutes) * 100
        else:
            capacity_level = "overloaded"
            utilization = (task_minutes / free_minutes) * 100

        return {
            "date": target_date.isoformat(),
            "calendar": {
                "event_count": len(events),
                "event_minutes": event_minutes,
                "events": [
                    {
                        "title": e.title,
                        "start": e.start_time.isoformat(),
                        "end": e.end_time.isoformat(),
                        "duration_minutes": int((e.end_time - e.start_time).total_seconds() / 60),
                    }
                    for e in sorted(events, key=lambda e: e.start_time)[:5]
                ],
            },
            "availability": {
                "free_minutes": free_minutes,
                "free_slots_count": len(free_slots),
            },
            "tasks": {
                "incomplete_count": len(incomplete_tasks),
                "estimated_minutes": task_minutes,
            },
            "capacity": {
                "level": capacity_level,  # fully_booked, comfortable, tight, overloaded
                "utilization_percent": round(utilization, 1),
                "can_fit_all_tasks": task_minutes <= free_minutes,
            },
            "recommendations": self._generate_capacity_recommendations(
                capacity_level,
                incomplete_tasks,
                free_minutes,
                task_minutes,
            ),
        }

    def _estimate_minutes(self, priority: TaskModel.PriorityLevel) -> int:
        """Estimate minutes for a task based on priority."""
        estimates = {
            TaskModel.PriorityLevel.HIGH: 45,
            TaskModel.PriorityLevel.MEDIUM: 30,
            TaskModel.PriorityLevel.LOW: 20,
        }
        return estimates.get(priority, 30)

    def _find_suitable_time_slot(
        self,
        priority: TaskModel.PriorityLevel,
        free_slots: List[Dict[str, Any]],
    ) -> Optional[Dict[str, str]]:
        """Find a suitable time slot for a task based on priority."""
        if not free_slots:
            return None

        # High priority tasks should get earlier slots
        if priority == TaskModel.PriorityLevel.HIGH:
            slot = free_slots[0]
        elif priority == TaskModel.PriorityLevel.MEDIUM and len(free_slots) > 1:
            slot = free_slots[len(free_slots) // 2]
        else:
            slot = free_slots[-1]

        return {
            "start": slot["start"].isoformat(),
            "end": slot["end"].isoformat(),
            "duration_minutes": int((slot["end"] - slot["start"]).total_seconds() / 60),
        }

    def _suggest_task_dates(
        self,
        tasks: List[TaskModel],
        daily_capacity: Dict[str, Any],
        minutes_per_task: int,
    ) -> List[Dict[str, Any]]:
        """Suggest dates for tasks based on daily capacity."""
        suggestions = []
        current_day_idx = 0

        for task in sorted(tasks, key=lambda t: t.created_at, reverse=True):
            # Find a day with enough capacity
            while current_day_idx < len(daily_capacity) and \
                  daily_capacity[list(daily_capacity.keys())[current_day_idx]]["available_minutes"] < minutes_per_task:
                current_day_idx += 1

            if current_day_idx < len(daily_capacity):
                suggested_date = list(daily_capacity.keys())[current_day_idx]
                suggestions.append({
                    "task_id": task.id,
                    "task_title": task.title,
                    "suggested_date": suggested_date,
                    "day": daily_capacity[suggested_date]["day"],
                    "estimated_minutes": minutes_per_task,
                })
                # Reduce available capacity
                daily_capacity[suggested_date]["available_minutes"] -= minutes_per_task

        return suggestions

    def _generate_capacity_recommendations(
        self,
        capacity_level: str,
        tasks: List[TaskModel],
        available_minutes: int,
        needed_minutes: int,
    ) -> List[str]:
        """Generate recommendations based on day capacity."""
        recommendations = []

        if capacity_level == "fully_booked":
            recommendations.append(
                "📅 This day is fully booked with calendar events. Consider rescheduling tasks."
            )
        elif capacity_level == "overloaded":
            deficit = needed_minutes - available_minutes
            recommendations.append(
                f"⚠️ You're overloaded by {deficit} minutes. Suggest deferring {(deficit // 30) + 1} task(s) to another day."
            )
            high_priority = [t for t in tasks if t.priority == TaskModel.PriorityLevel.HIGH]
            if len(high_priority) == 0:
                recommendations.append("💡 Try deferring low or medium priority tasks.")
        elif capacity_level == "tight":
            recommendations.append(
                "🎯 Tight schedule—focus on high-priority tasks and batch-process emails."
            )
        elif capacity_level == "comfortable":
            recommendations.append(
                "✅ Good capacity available. You can handle all tasks while staying balanced."
            )

        return recommendations
