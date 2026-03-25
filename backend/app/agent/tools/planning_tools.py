"""LangGraph tools for daily planning workflows."""

from __future__ import annotations

import logging
from datetime import datetime
from time import perf_counter
from typing import Any, Dict, Optional

from sqlalchemy.orm import Session

from app.core.logging_config import get_trace_id
from app.core.metrics import metrics_collector
from app.core.planning import DailyPlanService

logger = logging.getLogger(__name__)


def create_planning_tools(db: Session):
    """Create planning tools for LangGraph agent."""

    service = DailyPlanService(db)

    def generate_daily_plan(user_id: str, date: Optional[str] = None) -> Dict[str, Any]:
        start = perf_counter()
        trace_id = get_trace_id() or "N/A"

        try:
            target_date = datetime.fromisoformat(date) if date else None
            plan = service.generate_daily_plan(user_id=user_id, target_date=target_date)

            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_agent_step("tool.generate_daily_plan", "success", duration_ms)
            logger.info(
                "tool.generate_daily_plan.success",
                extra={
                    "trace_id": trace_id,
                    "user_id": user_id,
                    "duration_ms": round(duration_ms, 2),
                    "total_tasks": plan.get("summary", {}).get("total_tasks", 0),
                },
            )
            return {"status": "success", "plan": plan}

        except Exception as exc:
            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_agent_step("tool.generate_daily_plan", "error", duration_ms)
            logger.error(
                "tool.generate_daily_plan.error",
                extra={"trace_id": trace_id, "user_id": user_id, "duration_ms": round(duration_ms, 2)},
                exc_info=True,
            )
            return {"status": "failed", "error": str(exc)}

    return {
        "generate_daily_plan": generate_daily_plan,
    }
