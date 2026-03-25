"""
Calendar event management schemas for Google Calendar integration.

Handles event CRUD, free-busy queries, and recurrence rules.
"""

from typing import Optional, Literal
from datetime import datetime, date as DateType
from enum import Enum

from pydantic import BaseModel, Field


class RecurrenceFrequency(str, Enum):
    """RRULE frequency."""
    DAILY = "daily"
    WEEKLY = "weekly"
    MONTHLY = "monthly"
    YEARLY = "yearly"


class EventStatus(str, Enum):
    """Event status in calendar."""
    SCHEDULED = "scheduled"
    CONFIRMED = "confirmed"
    TENTATIVE = "tentative"
    CANCELLED = "cancelled"


class RecurrenceRule(BaseModel):
    """iCalendar RRULE representation."""
    
    frequency: RecurrenceFrequency
    count: Optional[int] = Field(
        None,
        description="Number of occurrences"
    )
    until: Optional[datetime] = Field(
        None,
        description="Until date for recurrence"
    )
    interval: int = Field(
        default=1,
        ge=1,
        description="Interval between occurrences"
    )
    by_day: Optional[list[str]] = Field(
        None,
        description="Days of week (MO, TU, etc.)"
    )
    by_month_day: Optional[list[int]] = Field(
        None,
        description="Days of month"
    )


class CalendarEventCreateRequest(BaseModel):
    """Create a calendar event."""
    
    title: str = Field(
        ..., 
        min_length=1, 
        max_length=255,
        description="Event title"
    )
    description: Optional[str] = Field(
        None,
        max_length=2000,
        description="Event description"
    )
    start_time: datetime = Field(..., description="Event start (ISO 8601)")
    end_time: datetime = Field(..., description="Event end (ISO 8601)")
    timezone: str = Field(
        default="UTC",
        description="IANA timezone (e.g., 'America/New_York')"
    )
    location: Optional[str] = Field(
        None,
        max_length=500,
        description="Physical or Zoom location"
    )
    attendees: Optional[list[str]] = Field(
        None,
        description="Email addresses of attendees"
    )
    recurrence: Optional[RecurrenceRule] = Field(
        None,
        description="Recurrence pattern"
    )
    color: Optional[str] = Field(
        None,
        description="Color ID from Google Calendar"
    )
    ai_generated: bool = Field(
        default=False,
        description="Was this event AI-generated?"
    )
    metadata: Optional[dict] = None


class CalendarEventUpdateRequest(BaseModel):
    """Update an existing calendar event."""
    
    title: Optional[str] = Field(None, min_length=1, max_length=255)
    description: Optional[str] = Field(None, max_length=2000)
    start_time: Optional[datetime] = None
    end_time: Optional[datetime] = None
    location: Optional[str] = Field(None, max_length=500)
    attendees: Optional[list[str]] = None
    recurrence: Optional[RecurrenceRule] = None
    color: Optional[str] = None
    status: Optional[EventStatus] = None
    metadata: Optional[dict] = None


class CalendarEvent(BaseModel):
    """Full calendar event object."""
    
    id: str = Field(..., description="Event UUID")
    user_id: str
    google_event_id: Optional[str] = Field(
        None,
        description="Google Calendar event ID (for sync)"
    )
    title: str
    description: Optional[str]
    start_time: datetime
    end_time: datetime
    timezone: str
    location: Optional[str]
    attendees: Optional[list[str]]
    status: EventStatus
    recurrence: Optional[RecurrenceRule]
    color: Optional[str]
    ai_generated: bool
    metadata: Optional[dict]
    created_at: datetime
    updated_at: datetime
    trace_id: Optional[str] = Field(
        None,
        description="If created by AI agent, trace ID of workflow"
    )
    
    class Config:
        from_attributes = True


class CalendarDayScheduleRequest(BaseModel):
    """Request schedule for a specific day."""
    
    date: DateType = Field(..., description="Target date")
    timezone: str = Field(default="UTC")
    include_all_day: bool = Field(
        default=True,
        description="Include all-day events"
    )


class CalendarDayScheduleResponse(BaseModel):
    """Daily schedule response."""
    
    date: DateType
    events: list[CalendarEvent]
    current_time: Optional[datetime] = Field(
        None,
        description="Current time in user's timezone (for UI highlighting)"
    )
    timezone: str


class FreeBusySlot(BaseModel):
    """A free time slot in calendar."""
    
    start_time: datetime
    end_time: datetime
    duration_minutes: int = Field(
        ...,
        description="Slot duration in minutes",
        ge=15,
        le=480
    )


class FreeBusyRequest(BaseModel):
    """Query for free time slots."""
    
    date: DateType = Field(..., description="Target date")
    min_duration_minutes: int = Field(
        default=30,
        ge=15,
        description="Minimum slot duration"
    )
    working_hours_start: str = Field(
        default="09:00",
        description="Work day start (HH:MM)"
    )
    working_hours_end: str = Field(
        default="17:00",
        description="Work day end (HH:MM)"
    )
    timezone: str = Field(default="UTC")


class FreeBusyResponse(BaseModel):
    """Free time slots response."""
    
    date: DateType
    free_slots: list[FreeBusySlot]
    timezone: str
    total_free_minutes: int


class CalendarEventListRequest(BaseModel):
    """Request to list calendar events."""
    
    date_range: Optional[dict] = Field(
        None,
        description="Date range {'start': ISO8601, 'end': ISO8601}"
    )
    status: Optional[EventStatus] = None
    ai_generated_only: bool = Field(default=False)
    limit: int = Field(default=50, ge=1, le=200)
    offset: int = Field(default=0, ge=0)
    sort_by: Literal["start_time", "created"] = Field(default="start_time")
    order: Literal["asc", "desc"] = Field(default="asc")


class CalendarEventListResponse(BaseModel):
    """List of calendar events."""
    
    events: list[CalendarEvent]
    total_count: int
    offset: int
    limit: int
    has_more: bool


class CalendarEventResponse(BaseModel):
    """Single calendar event response."""
    
    event: CalendarEvent
    trace_id: Optional[str] = None


# Example JSON payloads

CALENDAR_EVENT_CREATE_REQUEST_EXAMPLE = {
    "title": "Team Standup",
    "description": "Daily 15-minute sync",
    "start_time": "2026-03-25T09:30:00Z",
    "end_time": "2026-03-25T09:45:00Z",
    "timezone": "America/New_York",
    "location": "Zoom: zoom.us/j/123456",
    "attendees": ["alice@company.com", "bob@company.com"],
    "recurrence": {
        "frequency": "daily",
        "until": "2026-12-31T23:59:59Z",
        "interval": 1
    },
    "color": "1",
    "ai_generated": False
}

CALENDAR_EVENT_RESPONSE_EXAMPLE = {
    "event": {
        "id": "event-uuid-123",
        "user_id": "user-uuid-456",
        "google_event_id": "abc123xyz@google.com",
        "title": "Team Standup",
        "description": "Daily 15-minute sync",
        "start_time": "2026-03-25T09:30:00Z",
        "end_time": "2026-03-25T09:45:00Z",
        "timezone": "America/New_York",
        "location": "Zoom: zoom.us/j/123456",
        "attendees": ["alice@company.com", "bob@company.com"],
        "status": "confirmed",
        "recurrence": {
            "frequency": "daily",
            "until": "2026-12-31T23:59:59Z",
            "interval": 1
        },
        "color": "1",
        "ai_generated": False,
        "metadata": None,
        "created_at": "2026-03-24T10:00:00Z",
        "updated_at": "2026-03-24T10:00:00Z",
        "trace_id": None
    },
    "trace_id": None
}

FREE_BUSY_RESPONSE_EXAMPLE = {
    "date": "2026-03-25",
    "free_slots": [
        {
            "start_time": "2026-03-25T10:00:00Z",
            "end_time": "2026-03-25T11:00:00Z",
            "duration_minutes": 60
        },
        {
            "start_time": "2026-03-25T14:00:00Z",
            "end_time": "2026-03-25T16:30:00Z",
            "duration_minutes": 150
        }
    ],
    "timezone": "America/New_York",
    "total_free_minutes": 210
}

CALENDAR_DAY_SCHEDULE_RESPONSE_EXAMPLE = {
    "date": "2026-03-25",
    "events": [
        {
            "id": "event-uuid-123",
            "user_id": "user-uuid-456",
            "google_event_id": "abc123xyz@google.com",
            "title": "Team Standup",
            "description": "Daily 15-minute sync",
            "start_time": "2026-03-25T09:30:00Z",
            "end_time": "2026-03-25T09:45:00Z",
            "timezone": "America/New_York",
            "location": "Zoom: zoom.us/j/123456",
            "attendees": ["alice@company.com", "bob@company.com"],
            "status": "confirmed",
            "recurrence": None,
            "color": "1",
            "ai_generated": False,
            "metadata": None,
            "created_at": "2026-03-24T10:00:00Z",
            "updated_at": "2026-03-24T10:00:00Z",
            "trace_id": None
        }
    ],
    "current_time": "2026-03-25T10:15:00Z",
    "timezone": "America/New_York"
}
