"""LangGraph tools for task management."""

from __future__ import annotations

import logging
from datetime import datetime
from time import perf_counter
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.core.logging_config import get_trace_id
from app.core.metrics import metrics_collector
from app.db.models import Task
from app.repositories.repositories import TaskRepository

logger = logging.getLogger(__name__)


def _to_task_dict(task: Task) -> dict:
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "priority": task.priority.value if hasattr(task.priority, "value") else str(task.priority),
        "status": task.status.value if hasattr(task.status, "value") else str(task.status),
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "created_at": task.created_at.isoformat() if task.created_at else None,
        "updated_at": task.updated_at.isoformat() if task.updated_at else None,
    }


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    text = value.replace("Z", "+00:00")
    return datetime.fromisoformat(text)


def create_task_tools(db: Session):
    """Create task tools for LangGraph agent."""

    repo = TaskRepository(db)

    def list_tasks(
        user_id: str,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        limit: int = 20,
    ) -> Dict[str, Any]:
        start = perf_counter()
        trace_id = get_trace_id() or "N/A"

        try:
            tasks = repo.get_user_tasks(user_id, limit=min(max(limit, 1), 100))
            if status:
                tasks = [t for t in tasks if str(t.status.value).lower() == status.lower()]
            if priority:
                tasks = [t for t in tasks if str(t.priority.value).lower() == priority.lower()]

            response = {
                "status": "success",
                "count": len(tasks),
                "tasks": [_to_task_dict(task) for task in tasks],
            }

            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_agent_step("tool.list_tasks", "success", duration_ms)
            logger.info(
                "tool.list_tasks.success",
                extra={"trace_id": trace_id, "user_id": user_id, "count": len(tasks), "duration_ms": round(duration_ms, 2)},
            )
            return response

        except Exception as exc:
            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_agent_step("tool.list_tasks", "error", duration_ms)
            logger.error(
                "tool.list_tasks.error",
                extra={"trace_id": trace_id, "user_id": user_id, "duration_ms": round(duration_ms, 2)},
                exc_info=True,
            )
            return {"status": "failed", "error": str(exc)}

    def create_task(
        user_id: str,
        title: str,
        description: Optional[str] = None,
        priority: str = "medium",
        due_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        start = perf_counter()
        trace_id = get_trace_id() or "N/A"

        try:
            priority_value = priority.lower()
            if priority_value == "high":
                model_priority = Task.PriorityLevel.HIGH
            elif priority_value == "low":
                model_priority = Task.PriorityLevel.LOW
            else:
                model_priority = Task.PriorityLevel.MEDIUM

            task = repo.create(
                user_id=user_id,
                title=title,
                description=description,
                priority=model_priority,
                status=Task.TaskStatus.TODO,
                due_date=_parse_datetime(due_date),
                ai_generated=True,
                ai_metadata={"source": "chat_orchestration"},
            )
            db.commit()

            response = {"status": "success", "task": _to_task_dict(task)}
            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_agent_step("tool.create_task", "success", duration_ms)
            logger.info(
                "tool.create_task.success",
                extra={"trace_id": trace_id, "user_id": user_id, "task_id": task.id, "duration_ms": round(duration_ms, 2)},
            )
            return response

        except Exception as exc:
            db.rollback()
            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_agent_step("tool.create_task", "error", duration_ms)
            logger.error(
                "tool.create_task.error",
                extra={"trace_id": trace_id, "user_id": user_id, "duration_ms": round(duration_ms, 2)},
                exc_info=True,
            )
            return {"status": "failed", "error": str(exc)}

    def update_task(
        user_id: str,
        task_id: str,
        title: Optional[str] = None,
        description: Optional[str] = None,
        status: Optional[str] = None,
        priority: Optional[str] = None,
        due_date: Optional[str] = None,
    ) -> Dict[str, Any]:
        start = perf_counter()
        trace_id = get_trace_id() or "N/A"

        try:
            task = repo.get_by_id(task_id)
            if not task or task.user_id != user_id:
                return {"status": "failed", "error": "Task not found"}

            updates: Dict[str, Any] = {}
            if title is not None:
                updates["title"] = title
            if description is not None:
                updates["description"] = description
            if due_date is not None:
                updates["due_date"] = _parse_datetime(due_date)
            if status is not None:
                status_text = status.lower()
                if status_text == "completed":
                    updates["status"] = Task.TaskStatus.COMPLETED
                    updates["completed_at"] = datetime.utcnow()
                elif status_text == "in_progress":
                    updates["status"] = Task.TaskStatus.IN_PROGRESS
                elif status_text == "cancelled":
                    updates["status"] = Task.TaskStatus.CANCELLED
                else:
                    updates["status"] = Task.TaskStatus.TODO
            if priority is not None:
                priority_text = priority.lower()
                if priority_text == "high":
                    updates["priority"] = Task.PriorityLevel.HIGH
                elif priority_text == "low":
                    updates["priority"] = Task.PriorityLevel.LOW
                else:
                    updates["priority"] = Task.PriorityLevel.MEDIUM

            updated = repo.update(task_id, **updates)
            db.commit()
            response = {"status": "success", "task": _to_task_dict(updated)}

            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_agent_step("tool.update_task", "success", duration_ms)
            logger.info(
                "tool.update_task.success",
                extra={"trace_id": trace_id, "user_id": user_id, "task_id": task_id, "duration_ms": round(duration_ms, 2)},
            )
            return response

        except Exception as exc:
            db.rollback()
            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_agent_step("tool.update_task", "error", duration_ms)
            logger.error(
                "tool.update_task.error",
                extra={"trace_id": trace_id, "user_id": user_id, "task_id": task_id, "duration_ms": round(duration_ms, 2)},
                exc_info=True,
            )
            return {"status": "failed", "error": str(exc)}

    def delete_task(user_id: str, task_id: str) -> Dict[str, Any]:
        start = perf_counter()
        trace_id = get_trace_id() or "N/A"

        try:
            task = repo.get_by_id(task_id)
            if not task or task.user_id != user_id:
                return {"status": "failed", "error": "Task not found"}

            repo.delete(task_id)
            db.commit()

            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_agent_step("tool.delete_task", "success", duration_ms)
            logger.info(
                "tool.delete_task.success",
                extra={"trace_id": trace_id, "user_id": user_id, "task_id": task_id, "duration_ms": round(duration_ms, 2)},
            )
            return {"status": "success", "task_id": task_id}

        except Exception as exc:
            db.rollback()
            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_agent_step("tool.delete_task", "error", duration_ms)
            logger.error(
                "tool.delete_task.error",
                extra={"trace_id": trace_id, "user_id": user_id, "task_id": task_id, "duration_ms": round(duration_ms, 2)},
                exc_info=True,
            )
            return {"status": "failed", "error": str(exc)}

    def move_task(user_id: str, task_id: str, due_date: str) -> Dict[str, Any]:
        return update_task(user_id=user_id, task_id=task_id, due_date=due_date)

    return {
        "list_tasks": list_tasks,
        "create_task": create_task,
        "update_task": update_task,
        "delete_task": delete_task,
        "move_task": move_task,
    }
