"""LangGraph tools for calendar queries and approval-gated event actions."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from time import perf_counter
from typing import Any, Dict, Optional
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.logging_config import get_trace_id
from app.core.metrics import metrics_collector
from app.db.models import Approval, CalendarEvent
from app.repositories.repositories import CalendarEventRepository

logger = logging.getLogger(__name__)


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def _event_to_dict(event: CalendarEvent) -> dict:
    return {
        "id": event.id,
        "title": event.title,
        "description": event.description,
        "start_time": event.start_time.isoformat(),
        "end_time": event.end_time.isoformat(),
        "status": event.status.value if hasattr(event.status, "value") else str(event.status),
        "location": event.location,
        "attendees": event.attendees or [],
    }


def create_calendar_tools(db: Session):
    """Create calendar tools for LangGraph agent."""

    repo = CalendarEventRepository(db)

    def list_free_slots(
        user_id: str,
        date: Optional[str] = None,
        min_duration_minutes: int = 30,
    ) -> Dict[str, Any]:
        start = perf_counter()
        trace_id = get_trace_id() or "N/A"

        try:
            date_value = _parse_datetime(f"{date}T00:00:00") if date else datetime.utcnow()
            slots = repo.get_user_free_slots(user_id, date_value, min_duration_minutes=min_duration_minutes)
            response = {
                "status": "success",
                "count": len(slots),
                "free_slots": [
                    {
                        "start_time": slot["start"].isoformat(),
                        "end_time": slot["end"].isoformat(),
                    }
                    for slot in slots
                ],
            }

            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_agent_step("tool.list_free_slots", "success", duration_ms)
            logger.info(
                "tool.list_free_slots.success",
                extra={"trace_id": trace_id, "user_id": user_id, "count": len(slots), "duration_ms": round(duration_ms, 2)},
            )
            return response

        except Exception as exc:
            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_agent_step("tool.list_free_slots", "error", duration_ms)
            logger.error(
                "tool.list_free_slots.error",
                extra={"trace_id": trace_id, "user_id": user_id, "duration_ms": round(duration_ms, 2)},
                exc_info=True,
            )
            return {"status": "failed", "error": str(exc)}

    def check_conflicts(user_id: str, start_time: str, end_time: str) -> Dict[str, Any]:
        start = perf_counter()
        trace_id = get_trace_id() or "N/A"

        try:
            start_dt = _parse_datetime(start_time)
            end_dt = _parse_datetime(end_time)
            events = repo.get_user_events_by_date_range(user_id, start_dt, end_dt)

            conflicts = []
            for event in events:
                overlaps = event.start_time < end_dt and event.end_time > start_dt
                if overlaps:
                    conflicts.append(_event_to_dict(event))

            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_agent_step("tool.check_conflicts", "success", duration_ms)
            logger.info(
                "tool.check_conflicts.success",
                extra={"trace_id": trace_id, "user_id": user_id, "conflicts": len(conflicts), "duration_ms": round(duration_ms, 2)},
            )
            return {"status": "success", "has_conflicts": len(conflicts) > 0, "conflicts": conflicts}

        except Exception as exc:
            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_agent_step("tool.check_conflicts", "error", duration_ms)
            logger.error(
                "tool.check_conflicts.error",
                extra={"trace_id": trace_id, "user_id": user_id, "duration_ms": round(duration_ms, 2)},
                exc_info=True,
            )
            return {"status": "failed", "error": str(exc)}

    def find_best_slot(
        user_id: str,
        date: Optional[str] = None,
        duration_minutes: int = 30,
    ) -> Dict[str, Any]:
        start = perf_counter()
        trace_id = get_trace_id() or "N/A"

        try:
            slot_result = list_free_slots(user_id=user_id, date=date, min_duration_minutes=duration_minutes)
            slots = slot_result.get("free_slots", [])
            best = slots[0] if slots else None

            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_agent_step("tool.find_best_slot", "success", duration_ms)
            logger.info(
                "tool.find_best_slot.success",
                extra={"trace_id": trace_id, "user_id": user_id, "duration_ms": round(duration_ms, 2), "found": bool(best)},
            )
            return {"status": "success", "best_slot": best, "candidate_count": len(slots)}

        except Exception as exc:
            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_agent_step("tool.find_best_slot", "error", duration_ms)
            logger.error(
                "tool.find_best_slot.error",
                extra={"trace_id": trace_id, "user_id": user_id, "duration_ms": round(duration_ms, 2)},
                exc_info=True,
            )
            return {"status": "failed", "error": str(exc)}

    def create_event(
        user_id: str,
        title: str,
        start_time: str,
        end_time: str,
        description: Optional[str] = None,
        location: Optional[str] = None,
        attendees: Optional[list[str]] = None,
        require_approval: bool = True,
    ) -> Dict[str, Any]:
        start = perf_counter()
        trace_id = get_trace_id() or "N/A"

        try:
            start_dt = _parse_datetime(start_time)
            end_dt = _parse_datetime(end_time)

            if require_approval:
                approval = Approval(
                    id=str(uuid4()),
                    user_id=user_id,
                    approval_type=Approval.ApprovalType.CREATE_EVENT,
                    status=Approval.ApprovalStatus.PENDING,
                    action_description=f"Create calendar event: {title}",
                    action_payload={
                        "title": title,
                        "description": description,
                        "start_time": start_dt.isoformat(),
                        "end_time": end_dt.isoformat(),
                        "location": location,
                        "attendees": attendees or [],
                    },
                    ai_reasoning="AI requested calendar event creation",
                    confidence_score=0.9,
                    expires_at=datetime.utcnow() + timedelta(minutes=15),
                )

                db.add(approval)
                db.commit()

                response = {
                    "status": "success",
                    "requires_approval": True,
                    "approval_id": approval.id,
                    "action_type": "create_event",
                    "event_preview": {
                        "title": title,
                        "start_time": start_dt.isoformat(),
                        "end_time": end_dt.isoformat(),
                        "location": location,
                    },
                }
            else:
                event = repo.create(
                    user_id=user_id,
                    title=title,
                    description=description,
                    start_time=start_dt,
                    end_time=end_dt,
                    location=location,
                    attendees=attendees or [],
                    status=CalendarEvent.EventStatus.SCHEDULED,
                )
                db.commit()
                response = {"status": "success", "requires_approval": False, "event": _event_to_dict(event)}

            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_agent_step("tool.create_event", "success", duration_ms)
            logger.info(
                "tool.create_event.success",
                extra={"trace_id": trace_id, "user_id": user_id, "duration_ms": round(duration_ms, 2)},
            )
            return response

        except Exception as exc:
            db.rollback()
            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_agent_step("tool.create_event", "error", duration_ms)
            logger.error(
                "tool.create_event.error",
                extra={"trace_id": trace_id, "user_id": user_id, "duration_ms": round(duration_ms, 2)},
                exc_info=True,
            )
            return {"status": "failed", "error": str(exc)}

    return {
        "list_free_slots": list_free_slots,
        "check_conflicts": check_conflicts,
        "find_best_slot": find_best_slot,
        "create_event": create_event,
    }
