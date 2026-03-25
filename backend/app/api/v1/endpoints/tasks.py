"""Task management endpoints for CRUD operations and lifecycle management."""

from typing import Optional
from datetime import datetime, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.auth import get_current_user, TokenPayload
from app.db.config import get_db
from app.db.models import User, Task as TaskModel
from app.repositories.repositories import TaskRepository
from app.schemas.tasks import (
    TaskCreateRequest,
    TaskUpdateRequest,
    Task,
    TaskListRequest,
    TaskListResponse,
    TaskResponse,
    TaskBulkUpdateRequest,
    TaskRolloverRequest,
    TaskRolloverResponse,
    TaskStatus,
    TaskPriority,
)
from app.schemas.common import ApiResponse

router = APIRouter(prefix="/tasks", tags=["tasks"])


async def get_current_user_from_db(
    current_token: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Resolve authenticated token payload to a full User model."""
    user = db.query(User).filter(User.id == current_token.sub).first()
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user


# ============================================================================
# TASK CRUD ENDPOINTS
# ============================================================================


@router.post(
    "",
    response_model=TaskResponse,
    status_code=201,
    summary="Create a new task",
    description="Create a new task for the authenticated user."
)
async def create_task(
    request: TaskCreateRequest,
    current_user: User = Depends(get_current_user_from_db),
    db: Session = Depends(get_db),
) -> TaskResponse:
    """Create a new task for the user."""
    repo = TaskRepository(db)
    
    task = repo.create(
        user_id=current_user.id,
        title=request.title,
        description=request.description,
        priority=request.priority,
        due_date=request.due_date,
        ai_generated=request.ai_generated,
        ai_metadata=request.metadata,
        status=TaskModel.TaskStatus.TODO,
    )
    
    db.commit()
    
    return TaskResponse(
        task=Task.model_validate(task),
        trace_id=None,
    )


@router.get(
    "/{task_id}",
    response_model=TaskResponse,
    summary="Get task by ID",
    description="Retrieve a specific task by its ID."
)
async def get_task(
    task_id: str,
    current_user: User = Depends(get_current_user_from_db),
    db: Session = Depends(get_db),
) -> TaskResponse:
    """Get a specific task by ID."""
    repo = TaskRepository(db)
    task = repo.get_by_id(task_id)
    
    if not task or task.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Task not found")
    
    return TaskResponse(task=Task.model_validate(task))


@router.put(
    "/{task_id}",
    response_model=TaskResponse,
    summary="Update a task",
    description="Update an existing task by its ID."
)
async def update_task(
    task_id: str,
    request: TaskUpdateRequest,
    current_user: User = Depends(get_current_user_from_db),
    db: Session = Depends(get_db),
) -> TaskResponse:
    """Update a task."""
    repo = TaskRepository(db)
    task = repo.get_by_id(task_id)
    
    if not task or task.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Task not found")
    
    # Prepare update dict (only include provided fields)
    update_data = {}
    if request.title is not None:
        update_data["title"] = request.title
    if request.description is not None:
        update_data["description"] = request.description
    if request.priority is not None:
        update_data["priority"] = request.priority
    if request.status is not None:
        update_data["status"] = request.status
        # If marking as completed, set completed_at
        if request.status == TaskStatus.COMPLETED:
            update_data["completed_at"] = datetime.utcnow()
    if request.due_date is not None:
        update_data["due_date"] = request.due_date
    if request.metadata is not None:
        update_data["ai_metadata"] = request.metadata
    
    updated_task = repo.update(task_id, **update_data)
    db.commit()
    
    return TaskResponse(task=Task.model_validate(updated_task))


@router.delete(
    "/{task_id}",
    status_code=204,
    summary="Delete a task",
    description="Delete a task by its ID."
)
async def delete_task(
    task_id: str,
    current_user: User = Depends(get_current_user_from_db),
    db: Session = Depends(get_db),
) -> None:
    """Delete a task."""
    repo = TaskRepository(db)
    task = repo.get_by_id(task_id)
    
    if not task or task.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Task not found")
    
    repo.delete(task_id)
    db.commit()


# ============================================================================
# TASK LISTING AND FILTERING
# ============================================================================


@router.get(
    "",
    response_model=TaskListResponse,
    summary="List user tasks",
    description="List all tasks for the authenticated user with filtering and pagination."
)
async def list_tasks(
    status: Optional[TaskStatus] = Query(None, description="Filter by status"),
    priority: Optional[TaskPriority] = Query(None, description="Filter by priority"),
    skip: int = Query(0, ge=0, description="Pagination offset"),
    limit: int = Query(50, ge=1, le=200, description="Page size"),
    sort_by: str = Query("due_date", description="Sort key: created, due_date, priority"),
    order: str = Query("asc", description="Sort order: asc, desc"),
    current_user: User = Depends(get_current_user_from_db),
    db: Session = Depends(get_db),
) -> TaskListResponse:
    """List user tasks with filtering and pagination."""
    repo = TaskRepository(db)
    
    # Get filtered tasks
    if status and priority:
        all_tasks = repo.find(user_id=current_user.id, status=status, priority=priority)
    elif status:
        all_tasks = repo.get_user_tasks_by_status(current_user.id, status)
    elif priority:
        all_tasks = repo.find(user_id=current_user.id, priority=priority)
    else:
        all_tasks = repo.get_user_tasks(current_user.id)
    
    # Sort
    if sort_by == "priority":
        priority_order = {TaskModel.PriorityLevel.HIGH: 0, TaskModel.PriorityLevel.MEDIUM: 1, TaskModel.PriorityLevel.LOW: 2}
        all_tasks = sorted(all_tasks, key=lambda t: priority_order[t.priority], reverse=(order == "desc"))
    elif sort_by == "created":
        all_tasks = sorted(all_tasks, key=lambda t: t.created_at, reverse=(order == "desc"))
    else:  # due_date
        all_tasks = sorted(all_tasks, key=lambda t: t.due_date or datetime.max, reverse=(order == "desc"))
    
    # Paginate
    total_count = len(all_tasks)
    paginated_tasks = all_tasks[skip:skip + limit]
    
    # Compute summary
    summary = {
        "total": total_count,
        "completed": len([t for t in all_tasks if t.status == TaskModel.TaskStatus.COMPLETED]),
        "incomplete": len([t for t in all_tasks if t.status != TaskModel.TaskStatus.COMPLETED]),
        "high_priority": len([t for t in all_tasks if t.priority == TaskModel.PriorityLevel.HIGH]),
        "overdue": len([t for t in all_tasks if t.due_date and t.due_date < datetime.utcnow() and t.status != TaskModel.TaskStatus.COMPLETED]),
    }
    
    return TaskListResponse(
        tasks=[Task.model_validate(t) for t in paginated_tasks],
        total_count=total_count,
        offset=skip,
        limit=limit,
        has_more=(skip + limit) < total_count,
        summary=summary,
    )


@router.get(
    "/daily/today",
    response_model=TaskListResponse,
    summary="Get today's tasks",
    description="Get all tasks due today for the authenticated user."
)
async def get_today_tasks(
    current_user: User = Depends(get_current_user_from_db),
    db: Session = Depends(get_db),
) -> TaskListResponse:
    """Get tasks due today."""
    repo = TaskRepository(db)
    tasks = repo.get_user_tasks_due_today(current_user.id)
    
    # Sort by priority
    tasks = repo.get_user_tasks_by_priority_and_status(current_user.id, None)
    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    tomorrow = today + timedelta(days=1)
    tasks = [t for t in tasks if t.due_date and today <= t.due_date < tomorrow]
    
    return TaskListResponse(
        tasks=[Task.model_validate(t) for t in tasks],
        total_count=len(tasks),
        offset=0,
        limit=len(tasks),
        has_more=False,
        summary={
            "total": len(tasks),
            "high_priority": len([t for t in tasks if t.priority == TaskModel.PriorityLevel.HIGH]),
        }
    )


@router.get(
    "/incomplete/all",
    response_model=TaskListResponse,
    summary="Get incomplete tasks",
    description="Get all incomplete (TODO/IN_PROGRESS) tasks for the authenticated user."
)
async def get_incomplete_tasks(
    current_user: User = Depends(get_current_user_from_db),
    db: Session = Depends(get_db),
) -> TaskListResponse:
    """Get incomplete tasks."""
    repo = TaskRepository(db)
    tasks = repo.get_user_incomplete_tasks(current_user.id)
    
    # Sort by priority
    priority_order = {TaskModel.PriorityLevel.HIGH: 0, TaskModel.PriorityLevel.MEDIUM: 1, TaskModel.PriorityLevel.LOW: 2}
    tasks = sorted(tasks, key=lambda t: (priority_order[t.priority], t.created_at))
    
    return TaskListResponse(
        tasks=[Task.model_validate(t) for t in tasks],
        total_count=len(tasks),
        offset=0,
        limit=len(tasks),
        has_more=False,
        summary={
            "total": len(tasks),
            "high_priority": len([t for t in tasks if t.priority == TaskModel.PriorityLevel.HIGH]),
        }
    )


@router.get(
    "/overdue/all",
    response_model=TaskListResponse,
    summary="Get overdue tasks",
    description="Get all overdue and incomplete tasks for the authenticated user."
)
async def get_overdue_tasks(
    current_user: User = Depends(get_current_user_from_db),
    db: Session = Depends(get_db),
) -> TaskListResponse:
    """Get overdue tasks."""
    repo = TaskRepository(db)
    tasks = repo.get_user_overdue_tasks(current_user.id)
    
    # Sort by due_date (earliest first)
    tasks = sorted(tasks, key=lambda t: t.due_date or datetime.max)
    
    return TaskListResponse(
        tasks=[Task.model_validate(t) for t in tasks],
        total_count=len(tasks),
        offset=0,
        limit=len(tasks),
        has_more=False,
        summary={
            "total": len(tasks),
            "high_priority": len([t for t in tasks if t.priority == TaskModel.PriorityLevel.HIGH]),
        }
    )


# ============================================================================
# TASK LIFECYCLE OPERATIONS
# ============================================================================


@router.post(
    "/{task_id}/complete",
    response_model=TaskResponse,
    summary="Mark task as completed",
    description="Mark a task as completed."
)
async def complete_task(
    task_id: str,
    current_user: User = Depends(get_current_user_from_db),
    db: Session = Depends(get_db),
) -> TaskResponse:
    """Mark a task as completed."""
    repo = TaskRepository(db)
    task = repo.get_by_id(task_id)
    
    if not task or task.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Task not found")
    
    completed = repo.mark_task_completed(task_id)
    db.commit()
    
    return TaskResponse(task=Task.model_validate(completed))


@router.post(
    "/bulk/update",
    response_model=TaskListResponse,
    summary="Bulk update tasks",
    description="Update multiple tasks at once."
)
async def bulk_update_tasks(
    request: TaskBulkUpdateRequest,
    current_user: User = Depends(get_current_user_from_db),
    db: Session = Depends(get_db),
) -> TaskListResponse:
    """Bulk update multiple tasks."""
    repo = TaskRepository(db)
    updated_tasks = []
    
    for task_id in request.task_ids:
        task = repo.get_by_id(task_id)
        
        if not task or task.user_id != current_user.id:
            continue
        
        # Prepare update dict
        update_data = {}
        if request.update.title is not None:
            update_data["title"] = request.update.title
        if request.update.description is not None:
            update_data["description"] = request.update.description
        if request.update.priority is not None:
            update_data["priority"] = request.update.priority
        if request.update.status is not None:
            update_data["status"] = request.update.status
            if request.update.status == TaskStatus.COMPLETED:
                update_data["completed_at"] = datetime.utcnow()
        if request.update.due_date is not None:
            update_data["due_date"] = request.update.due_date
        if request.update.metadata is not None:
            update_data["ai_metadata"] = request.update.metadata
        
        updated_task = repo.update(task_id, **update_data)
        if updated_task:
            updated_tasks.append(updated_task)
    
    db.commit()
    
    return TaskListResponse(
        tasks=[Task.model_validate(t) for t in updated_tasks],
        total_count=len(updated_tasks),
        offset=0,
        limit=len(updated_tasks),
        has_more=False,
        summary={"updated": len(updated_tasks)}
    )


@router.post(
    "/rollover/end-of-day",
    response_model=TaskRolloverResponse,
    status_code=200,
    summary="End-of-day task rollover",
    description="Move incomplete tasks to the next day."
)
async def rollover_tasks(
    current_user: User = Depends(get_current_user_from_db),
    db: Session = Depends(get_db),
) -> TaskRolloverResponse:
    """Roll over incomplete tasks to the next day."""
    repo = TaskRepository(db)
    
    # Get incomplete tasks
    incomplete_tasks = repo.get_user_incomplete_tasks(current_user.id)
    
    # Move to next day
    next_day = datetime.utcnow() + timedelta(days=1)
    rolled_over = []
    for task in incomplete_tasks:
        task.due_date = next_day
        rolled_over.append(task)
    
    db.commit()
    
    return TaskRolloverResponse(
        moved_count=len(rolled_over),
        rolled_over_tasks=[Task.model_validate(t) for t in rolled_over],
        trace_id=None,
    )
