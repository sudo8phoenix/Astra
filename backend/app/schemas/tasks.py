"""
Task management schemas for CRUD operations, listing, and status tracking.

Supports task creation, updates, completion, priority levels, and filtering.
"""

from typing import Optional, Literal
from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class TaskPriority(str, Enum):
    """Task priority level."""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TaskStatus(str, Enum):
    """Task status in lifecycle."""
    TODO = "todo"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class TaskCreateRequest(BaseModel):
    """Create a new task."""
    
    title: str = Field(
        ..., 
        min_length=1, 
        max_length=255,
        description="Task title"
    )
    description: Optional[str] = Field(
        None,
        max_length=2000,
        description="Detailed task description"
    )
    priority: TaskPriority = Field(
        default=TaskPriority.MEDIUM,
        description="Task priority"
    )
    due_date: Optional[datetime] = Field(
        None,
        description="When task is due (ISO 8601)"
    )
    ai_generated: bool = Field(
        default=False,
        description="Was this task AI-generated?"
    )
    metadata: Optional[dict] = Field(
        default=None,
        description="AI metadata (reasoning, confidence)"
    )


class TaskUpdateRequest(BaseModel):
    """Update an existing task."""
    
    title: Optional[str] = Field(
        None, 
        min_length=1, 
        max_length=255
    )
    description: Optional[str] = Field(None, max_length=2000)
    priority: Optional[TaskPriority] = None
    status: Optional[TaskStatus] = None
    due_date: Optional[datetime] = None
    metadata: Optional[dict] = None


class Task(BaseModel):
    """Full task object."""
    
    id: str = Field(..., description="Task UUID")
    user_id: str
    title: str
    description: Optional[str]
    priority: TaskPriority
    status: TaskStatus
    due_date: Optional[datetime]
    ai_generated: bool
    ai_metadata: Optional[dict]
    created_at: datetime
    updated_at: datetime
    completed_at: Optional[datetime] = Field(
        None,
        description="When task was marked complete"
    )
    trace_id: Optional[str] = Field(
        None,
        description="If created by AI agent, trace ID of workflow"
    )
    
    class Config:
        from_attributes = True


class TaskListRequest(BaseModel):
    """Request to list tasks with filtering."""
    
    status: Optional[TaskStatus] = Field(
        None,
        description="Filter by status"
    )
    priority: Optional[TaskPriority] = Field(
        None,
        description="Filter by priority"
    )
    due_date_range: Optional[dict] = Field(
        None,
        description="Filter by due date range {'start': ISO8601, 'end': ISO8601}"
    )
    ai_generated_only: bool = Field(
        default=False,
        description="Show only AI-generated tasks"
    )
    limit: int = Field(
        default=50,
        ge=1,
        le=200,
        description="Page size"
    )
    offset: int = Field(
        default=0,
        ge=0,
        description="Pagination offset"
    )
    sort_by: Literal["created", "due_date", "priority"] = Field(
        default="due_date",
        description="Sort key"
    )
    order: Literal["asc", "desc"] = Field(
        default="asc",
        description="Sort order"
    )


class TaskListResponse(BaseModel):
    """List of tasks with pagination."""
    
    tasks: list[Task]
    total_count: int
    offset: int
    limit: int
    has_more: bool
    summary: Optional[dict] = Field(
        None,
        description="Aggregated stats {'completed': 3, 'high_priority': 2, ...}"
    )


class TaskResponse(BaseModel):
    """Single task response."""
    
    task: Task
    trace_id: Optional[str] = None


class TaskBulkUpdateRequest(BaseModel):
    """Update multiple tasks at once (e.g., end-of-day rollover)."""
    
    task_ids: list[str]
    update: TaskUpdateRequest


class TaskRolloverRequest(BaseModel):
    """End-of-day rollover: move incomplete tasks to next day."""
    
    from_date: datetime = Field(..., description="Date to collect incomplete tasks")
    to_date: datetime = Field(..., description="Target date for rollover")
    include_cancelled: bool = Field(default=False)


class TaskRolloverResponse(BaseModel):
    """Result of rollover operation."""
    
    moved_count: int
    rolled_over_tasks: list[Task]
    trace_id: Optional[str] = None


# Example JSON payloads

TASK_CREATE_REQUEST_EXAMPLE = {
    "title": "Write quarterly report",
    "description": "Complete Q1 performance review and submit to manager",
    "priority": "high",
    "due_date": "2026-03-31T17:00:00Z",
    "ai_generated": True,
    "metadata": {
        "reasoning": "Extracted from email from manager dated 2026-03-20",
        "confidence": 0.95
    }
}

TASK_RESPONSE_EXAMPLE = {
    "task": {
        "id": "task-uuid-123",
        "user_id": "user-uuid-456",
        "title": "Write quarterly report",
        "description": "Complete Q1 performance review and submit to manager",
        "priority": "high",
        "status": "todo",
        "due_date": "2026-03-31T17:00:00Z",
        "ai_generated": True,
        "ai_metadata": {
            "reasoning": "Extracted from email from manager dated 2026-03-20",
            "confidence": 0.95
        },
        "created_at": "2026-03-24T10:30:00Z",
        "updated_at": "2026-03-24T10:30:00Z",
        "completed_at": None,
        "trace_id": "trace-uuid-789"
    },
    "trace_id": "trace-uuid-789"
}

TASK_LIST_RESPONSE_EXAMPLE = {
    "tasks": [
        {
            "id": "task-uuid-123",
            "user_id": "user-uuid-456",
            "title": "Write quarterly report",
            "description": "Complete Q1 performance review and submit to manager",
            "priority": "high",
            "status": "todo",
            "due_date": "2026-03-31T17:00:00Z",
            "ai_generated": True,
            "ai_metadata": {"reasoning": "...", "confidence": 0.95},
            "created_at": "2026-03-24T10:30:00Z",
            "updated_at": "2026-03-24T10:30:00Z",
            "completed_at": None,
            "trace_id": "trace-uuid-789"
        },
        {
            "id": "task-uuid-124",
            "user_id": "user-uuid-456",
            "title": "Review pull requests",
            "description": None,
            "priority": "medium",
            "status": "in_progress",
            "due_date": "2026-03-25T12:00:00Z",
            "ai_generated": False,
            "ai_metadata": None,
            "created_at": "2026-03-23T14:00:00Z",
            "updated_at": "2026-03-24T09:15:00Z",
            "completed_at": None,
            "trace_id": None
        }
    ],
    "total_count": 2,
    "offset": 0,
    "limit": 50,
    "has_more": False,
    "summary": {
        "completed": 0,
        "in_progress": 1,
        "todo": 1,
        "high_priority": 1,
        "medium_priority": 1,
        "low_priority": 0
    }
}
