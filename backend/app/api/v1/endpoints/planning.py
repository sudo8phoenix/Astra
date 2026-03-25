"""Daily planning and summary endpoints for task management and insights."""

from datetime import datetime, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Path, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.db.config import get_db
from app.db.models import User
from app.core.planning import DailyPlanService
from app.core.summaries import SummaryTriggerService
from app.core.rollover import EndOfDayRolloverService
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/planning", tags=["planning"])


# ============================================================================
# DAILY PLANNING ENDPOINTS
# ============================================================================


@router.get(
    "/daily-plan",
    summary="Get daily plan",
    description="Generate an optimized daily plan based on tasks, calendar, and emails."
)
async def get_daily_plan(
    date: Optional[str] = Query(None, description="Target date (ISO 8601, defaults to today)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get an optimized daily plan."""
    try:
        target_date = None
        if date:
            target_date = datetime.fromisoformat(date)
        
        service = DailyPlanService(db)
        plan = service.generate_daily_plan(current_user.id, target_date)
        
        return ApiResponse(
            success=True,
            message="Daily plan generated successfully",
            data=plan,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/daily-summary",
    summary="Get today's task summary",
    description="Quick summary of today's incomplete tasks in priority order."
)
async def get_daily_summary(
    date: Optional[str] = Query(None, description="Target date (ISO 8601, defaults to today)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get a quick task summary for today."""
    try:
        target_date = None
        if date:
            target_date = datetime.fromisoformat(date)
        
        service = DailyPlanService(db)
        summary = service.get_tasks_summary(current_user.id, target_date)
        
        return ApiResponse(
            success=True,
            message="Task summary retrieved",
            data=summary,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/workload-estimate",
    summary="Estimate daily workload",
    description="Estimate the time needed for tasks and available working time."
)
async def get_workload_estimate(
    date: Optional[str] = Query(None, description="Target date (ISO 8601, defaults to today)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get workload estimation."""
    try:
        target_date = None
        if date:
            target_date = datetime.fromisoformat(date)
        
        service = DailyPlanService(db)
        estimate = service.estimate_daily_workload(current_user.id, target_date)
        
        return ApiResponse(
            success=True,
            message="Workload estimated",
            data=estimate,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# SUMMARY TRIGGER ENDPOINTS
# ============================================================================


@router.get(
    "/morning-summary",
    summary="Generate morning summary",
    description="Get morning dashboard summary with today's tasks, calendar, and emails."
)
async def get_morning_summary(
    date: Optional[str] = Query(None, description="Target date (ISO 8601, defaults to today)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get morning summary."""
    try:
        target_date = None
        if date:
            target_date = datetime.fromisoformat(date)
        
        service = SummaryTriggerService(db)
        summary = service.generate_morning_summary(current_user.id, target_date)
        
        return ApiResponse(
            success=True,
            message="Morning summary generated",
            data=summary,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/end-of-day-summary",
    summary="Generate end-of-day summary",
    description="Get end-of-day summary with completed tasks, rollover items, and insights."
)
async def get_end_of_day_summary(
    date: Optional[str] = Query(None, description="Target date (ISO 8601, defaults to today)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get end-of-day summary."""
    try:
        target_date = None
        if date:
            target_date = datetime.fromisoformat(date)
        
        service = SummaryTriggerService(db)
        summary = service.generate_end_of_day_summary(current_user.id, target_date)
        
        return ApiResponse(
            success=True,
            message="End-of-day summary generated",
            data=summary,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/weekly-summary",
    summary="Generate weekly summary",
    description="Get weekly summary with completion trends and insights."
)
async def get_weekly_summary(
    date: Optional[str] = Query(None, description="Reference date in the target week (ISO 8601, defaults to today)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get weekly summary."""
    try:
        target_date = None
        if date:
            target_date = datetime.fromisoformat(date)
        
        service = SummaryTriggerService(db)
        summary = service.generate_weekly_summary(current_user.id, target_date)
        
        return ApiResponse(
            success=True,
            message="Weekly summary generated",
            data=summary,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ============================================================================
# END-OF-DAY ROLLOVER ENDPOINTS
# ============================================================================


@router.post(
    "/rollover/execute",
    summary="Execute end-of-day rollover",
    description="Move incomplete tasks to the next day."
)
async def execute_rollover(
    from_date: Optional[str] = Query(None, description="Date to collect incomplete tasks (ISO 8601, defaults to today)"),
    to_date: Optional[str] = Query(None, description="Target date for rollover (ISO 8601, defaults to tomorrow)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Execute end-of-day rollover."""
    try:
        from_dt = None
        to_dt = None
        
        if from_date:
            from_dt = datetime.fromisoformat(from_date)
        if to_date:
            to_dt = datetime.fromisoformat(to_date)
        
        service = EndOfDayRolloverService(db)
        result = service.perform_end_of_day_rollover(current_user.id, from_dt, to_dt)
        
        return ApiResponse(
            success=True,
            message="End-of-day rollover completed",
            data=result,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/rollover/suggest",
    summary="Suggest reschedule plan",
    description="Suggest how to reschedule incomplete tasks across upcoming days."
)
async def suggest_reschedule(
    from_date: Optional[str] = Query(None, description="Starting date (ISO 8601, defaults to today)"),
    days_ahead: int = Query(3, ge=1, le=30, description="Number of days to look ahead"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get reschedule suggestions."""
    try:
        from_dt = None
        if from_date:
            from_dt = datetime.fromisoformat(from_date)
        
        service = EndOfDayRolloverService(db)
        suggestions = service.suggest_reschedule(current_user.id, from_dt, days_ahead)
        
        return ApiResponse(
            success=True,
            message="Reschedule suggestions generated",
            data=suggestions,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get(
    "/capacity/{date}",
    summary="Estimate day capacity",
    description="Get capacity estimate for a specific day."
)
async def get_day_capacity(
    date: str = Path(..., description="Target date (ISO 8601)"),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """Get day capacity estimate."""
    try:
        target_date = datetime.fromisoformat(date)
        
        service = EndOfDayRolloverService(db)
        capacity = service.estimate_day_capacity(current_user.id, target_date)
        
        return ApiResponse(
            success=True,
            message="Day capacity estimated",
            data=capacity,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
