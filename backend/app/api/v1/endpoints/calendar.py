"""Calendar management endpoints for Google Calendar integration."""

import logging
import uuid
from datetime import datetime, timedelta, date
from typing import Optional
import pytz

from fastapi import APIRouter, Depends, HTTPException, status, Query, Request
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.auth import get_current_user, TokenPayload, JWTManager
from app.core.auth_extended import GoogleOAuthTokens
from app.db.config import get_db
from app.db.models import User, CalendarEvent, Approval
from app.repositories.repositories import (
    CalendarEventRepository,
    UserRepository,
)
from app.schemas.calendar import (
    CalendarEventCreateRequest,
    CalendarEventUpdateRequest,
    CalendarDayScheduleRequest,
    CalendarDayScheduleResponse,
    FreeBusyRequest,
    FreeBusyResponse,
    FreeBusySlot,
    CalendarEvent as CalendarEventSchema,
    CalendarEventListResponse,
    EventStatus,
)
from app.schemas.common import ApiResponse, ApiErrorResponse
from app.services.calendar import GoogleCalendarService

router = APIRouter(prefix="/calendar", tags=["calendar"])
logger = logging.getLogger(__name__)

# Initialize Google Calendar service
calendar_service = GoogleCalendarService()


def _is_missing_table_error(error: Exception) -> bool:
    """Best-effort detection for missing DB table errors across DB drivers."""
    message = str(error)
    if "UndefinedTable" in message:
        return True

    original = getattr(error, "orig", None)
    if getattr(original, "pgcode", None) == "42P01":
        return True
    if getattr(original, "sqlstate", None) == "42P01":
        return True

    lowered = message.lower()
    return ("does not exist" in lowered) and (
        "relation" in lowered or "table" in lowered
    )


def _parse_oauth_expiry(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            return parsed.astimezone(pytz.UTC).replace(tzinfo=None)
        return parsed
    except Exception:
        return None


async def _resolve_calendar_access_token(user: User, db: Session) -> str:
    if not user.preferences:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google Calendar not connected. Please authorize first.",
        )

    preferences = dict(user.preferences or {})
    tokens_data = dict(preferences.get("calendar_oauth_tokens") or {})
    access_token = tokens_data.get("access_token")
    refresh_token = tokens_data.get("refresh_token")
    expires_at = _parse_oauth_expiry(tokens_data.get("expires_at"))

    if access_token and (not expires_at or expires_at > datetime.utcnow() + timedelta(minutes=2)):
        return access_token

    if not refresh_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Calendar access token expired and no refresh token is available. Please reconnect Google Calendar.",
        )

    try:
        refreshed = await calendar_service.refresh_access_token(refresh_token)
        tokens_data["access_token"] = refreshed["access_token"]
        tokens_data["expires_at"] = (
            datetime.utcnow() + timedelta(seconds=int(refreshed.get("expires_in", 3600)))
        ).isoformat()
        preferences["calendar_oauth_tokens"] = tokens_data
        preferences["calendar_connected"] = True
        user.preferences = preferences
        db.add(user)
        db.commit()
        db.refresh(user)
        return tokens_data["access_token"]
    except Exception:
        logger.warning(
            "calendar.oauth.refresh_failed user=%s",
            user.id,
            exc_info=True,
        )
        tokens_data["access_token"] = None
        preferences["calendar_oauth_tokens"] = tokens_data
        preferences["calendar_connected"] = False
        user.preferences = preferences
        db.add(user)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Google Calendar session expired. Please reconnect Google Calendar.",
        )


def _to_calendar_event_schema(
    parsed_event: dict,
    user_id: str,
    timezone: str,
) -> CalendarEventSchema:
    """Build response schema from Google event payload without DB persistence."""
    try:
        status = EventStatus(parsed_event.get("status", "confirmed"))
    except ValueError:
        status = EventStatus.CONFIRMED

    now = datetime.utcnow()
    attendees_raw = parsed_event.get("attendees") or []
    attendees: list[str] = []
    for attendee in attendees_raw:
        if isinstance(attendee, str):
            value = attendee.strip()
            if value:
                attendees.append(value)
            continue
        if isinstance(attendee, dict):
            value = str(attendee.get("email") or "").strip()
            if value:
                attendees.append(value)

    metadata = {
        "all_day": bool(parsed_event.get("all_day")),
        "html_link": parsed_event.get("html_link"),
        "hangout_link": parsed_event.get("hangout_link"),
        "conference_link": parsed_event.get("conference_link"),
        "organizer": parsed_event.get("organizer"),
        "attendee_statuses": parsed_event.get("attendee_statuses") or {},
        "reminders": parsed_event.get("reminders") or [],
    }

    return CalendarEventSchema(
        id=str(uuid.uuid4()),
        user_id=user_id,
        google_event_id=parsed_event.get("google_event_id"),
        title=parsed_event.get("title", "Untitled Event"),
        description=parsed_event.get("description"),
        start_time=parsed_event["start_time"],
        end_time=parsed_event["end_time"],
        timezone=timezone,
        location=parsed_event.get("location"),
        attendees=attendees,
        status=status,
        recurrence=None,
        color=parsed_event.get("color_id"),
        ai_generated=False,
        metadata=metadata,
        created_at=now,
        updated_at=now,
        trace_id=None,
    )


def _db_event_to_calendar_event_schema(event: CalendarEvent, timezone: str) -> CalendarEventSchema:
    """Build response schema from persisted CalendarEvent row."""
    attendees_raw = event.attendees or []
    attendees: list[str] = []
    for attendee in attendees_raw:
        if isinstance(attendee, str):
            value = attendee.strip()
            if value:
                attendees.append(value)
            continue
        if isinstance(attendee, dict):
            value = str(attendee.get("email") or "").strip()
            if value:
                attendees.append(value)

    attendee_statuses: dict[str, str] = {}
    for attendee in attendees_raw:
        if isinstance(attendee, dict):
            email = str(attendee.get("email") or "").strip()
            status_value = str(attendee.get("status") or "needsAction").strip()
            if email:
                attendee_statuses[email] = status_value

    metadata = {
        "all_day": bool(event.all_day),
        "attendee_statuses": attendee_statuses,
        "reminders": event.reminders or [],
    }

    return CalendarEventSchema(
        id=event.id,
        user_id=event.user_id,
        google_event_id=event.google_event_id,
        title=event.title,
        description=event.description,
        start_time=event.start_time,
        end_time=event.end_time,
        timezone=timezone,
        location=event.location,
        attendees=attendees,
        status=EventStatus(event.status.value if hasattr(event.status, "value") else str(event.status).lower()),
        recurrence=None,
        color=event.color_id,
        ai_generated=False,
        metadata=metadata,
        created_at=event.created_at,
        updated_at=event.updated_at,
        trace_id=None,
    )


async def get_current_user_from_db(
    current_token: TokenPayload = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> User:
    """Resolve authenticated token payload to full User model."""
    user = db.query(User).filter(User.id == current_token.sub).first()
    if not user:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found")
    return user


# ============================================================================
# OAUTH CALLBACK & TOKEN MANAGEMENT
# ============================================================================


@router.get("/oauth-authorize")
async def initiate_oauth_flow(
    state: Optional[str] = Query(None, description="Optional state parameter for OAuth round-trip"),
) -> dict:
    """
    Initiate Google Calendar OAuth flow.

    Generates authorization URL for user to connect their Google Calendar.
    This endpoint is called from the login page, so no auth required.

    Returns:
        Dictionary with oauth_url for redirection
    """
    try:
        state = state or str(uuid.uuid4())

        # Store state in session/cache for verification in callback
        # In production, store in Redis or session

        auth_url = calendar_service.get_authorization_url(state)

        return {"oauth_url": auth_url, "state": state}
    except Exception as e:
        logger.error(f"OAuth flow initiation failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to initiate OAuth flow",
        )


@router.post("/oauth-callback")
async def handle_oauth_callback(
    code: str = Query(..., description="Authorization code from Google"),
    state: Optional[str] = Query(None, description="State parameter for CSRF protection"),
    token: Optional[str] = Query(None, description="JWT token for authenticated user"),
    db: Session = Depends(get_db),
) -> ApiResponse:
    """
    Handle Google Calendar OAuth callback.

    Exchanges authorization code for access tokens and stores them.
    Works for both authenticated users (linking calendar) and new users (first login).

    Args:
        code: Authorization code from Google OAuth flow
        state: State parameter for CSRF validation (optional)
        token: JWT token if user is already authenticated (optional)
        db: Database session

    Returns:
        Success message with user info and auth token
    """
    try:
        # In production, verify state parameter against stored value

        # Exchange code for tokens
        tokens = await calendar_service.exchange_code_for_tokens(code)

        # Determine which user to link calendar to
        user = None
        current_user_id = None

        # If JWT token provided, use authenticated user
        if token:
            try:
                token_payload = JWTManager.verify_token(token)
                user = db.query(User).filter(User.id == token_payload.sub).first()
                current_user_id = token_payload.sub
            except Exception:
                user = None

        # If no authenticated user, create or get user from dev email
        if not user:
            demo_email = "demo.user@local.dev"
            user = db.query(User).filter(User.email == demo_email).first()
            if not user:
                user = User(
                    email=demo_email,
                    name="OAuth User",
                    timezone="UTC",
                    is_active=True,
                )
                db.add(user)
                db.commit()
                db.refresh(user)
            current_user_id = user.id

        # Store OAuth tokens in user preferences
        preferences = dict(user.preferences or {})
        existing_tokens = dict(preferences.get("calendar_oauth_tokens") or {})
        preferences["calendar_oauth_tokens"] = {
            "access_token": tokens["access_token"],
            "refresh_token": tokens.get("refresh_token") or existing_tokens.get("refresh_token"),
            "expires_at": (
                datetime.utcnow() + timedelta(seconds=tokens["expires_in"])
            ).isoformat(),
        }
        preferences["calendar_connected"] = True
        user.preferences = preferences
        user.oauth_provider = "google"
        db.add(user)
        db.commit()

        logger.info(f"User {current_user_id} connected Google Calendar")

        # If this is a new login (no token provided), generate JWT for them
        access_token = token
        if not token:
            access_token = JWTManager.create_access_token(
                user_id=user.id,
                email=user.email,
                scopes=["read", "write"],
            )

        return ApiResponse(
            data={
                "connected": True,
                "user_id": user.id,
                "email": user.email,
                "token": access_token,
            },
            message="Google Calendar connected successfully",
        )

    except ValueError as e:
        logger.error(f"Token exchange failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid authorization code"
        )
    except Exception as e:
        logger.error(f"OAuth callback failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process OAuth callback",
        )


# ============================================================================
# DAILY SCHEDULE & VISUALIZATION
# ============================================================================


@router.post("/daily-schedule", response_model=CalendarDayScheduleResponse)
async def get_daily_schedule(
    request: Request,
    payload: CalendarDayScheduleRequest,
    current_user: User = Depends(get_current_user_from_db),
    db: Session = Depends(get_db),
) -> CalendarDayScheduleResponse:
    """
    Fetch daily calendar schedule for a specific date.

    Retrieves all events for the day, ordered chronologically.

    Args:
        payload: Request with date and timezone
        current_user: Authenticated user
        db: Database session

    Returns:
        Daily schedule with events and current time for UI highlighting
    """
    try:
        trace_id = request.headers.get("x-trace-id", str(uuid.uuid4()))

        # Parse timezone
        tz = pytz.timezone(payload.timezone)
        date_in_tz = tz.localize(datetime.combine(payload.date, datetime.min.time()))

        # Get user's Google tokens
        user_repo = UserRepository(db)
        user = user_repo.get_by_id(current_user.id)

        if not user or not user.preferences or "calendar_oauth_tokens" not in user.preferences:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Google Calendar not connected. Please authorize first.",
            )

        access_token = await _resolve_calendar_access_token(user, db)

        # Fetch events from Google Calendar for this day
        day_start = date_in_tz.replace(hour=0, minute=0, second=0, microsecond=0)
        day_end = day_start + timedelta(days=1)

        google_events = await calendar_service.fetch_user_events(
            access_token, day_start, day_end, max_results=100
        )

        # Convert Google events to internal format and store in DB
        calendar_event_repo = CalendarEventRepository(db)
        parsed_google_events: list[dict] = []
        sync_failed = False
        try:
            for google_event in google_events:
                parsed_event = calendar_service.parse_google_event_to_dict(google_event)
                parsed_google_events.append(parsed_event)

                try:
                    # Check if event already exists
                    existing = calendar_event_repo.get_by_google_event_id(
                        parsed_event["google_event_id"]
                    )

                    if not existing:
                        # Create new event in DB
                        calendar_event_repo.create(
                            id=str(uuid.uuid4()),
                            user_id=current_user.id,
                            google_event_id=parsed_event["google_event_id"],
                            title=parsed_event["title"],
                            description=parsed_event["description"],
                            start_time=parsed_event["start_time"],
                            end_time=parsed_event["end_time"],
                            all_day=parsed_event["all_day"],
                            location=parsed_event["location"],
                            attendees=parsed_event["attendees"],
                            color_id=parsed_event["color_id"],
                            reminders=parsed_event.get("reminders"),
                            status=parsed_event["status"],
                        )
                    else:
                        calendar_event_repo.update(
                            existing.id,
                            title=parsed_event["title"],
                            description=parsed_event["description"],
                            start_time=parsed_event["start_time"],
                            end_time=parsed_event["end_time"],
                            location=parsed_event["location"],
                            attendees=parsed_event["attendees"],
                            color_id=parsed_event["color_id"],
                            reminders=parsed_event.get("reminders"),
                            status=parsed_event["status"],
                        )
                except Exception as event_sync_error:
                    db.rollback()
                    sync_failed = True
                    logger.warning(
                        "calendar.daily_schedule.event_sync_skipped user=%s google_event_id=%s error=%s",
                        current_user.id,
                        parsed_event.get("google_event_id"),
                        str(event_sync_error),
                    )
                    continue

            db.commit()

            # Get events from DB for this day
            db_events = calendar_event_repo.get_user_events_by_date_range(
                current_user.id, day_start, day_end
            )

            # Convert to schema
            events_schema = [
                _db_event_to_calendar_event_schema(event, payload.timezone)
                for event in db_events
            ]

            # Prefer direct Google payload conversion when DB sync is partial,
            # so the UI receives complete event coverage for the selected day.
            if sync_failed or len(events_schema) < len(parsed_google_events):
                events_schema = [
                    _to_calendar_event_schema(parsed_event, current_user.id, payload.timezone)
                    for parsed_event in parsed_google_events
                ]
        except Exception as db_error:
            db.rollback()
            if not _is_missing_table_error(db_error):
                raise
            logger.warning(
                "calendar.daily_schedule.db_unavailable_fallback user=%s error=%s",
                current_user.id,
                str(db_error),
            )
            events_schema = [
                _to_calendar_event_schema(
                    calendar_service.parse_google_event_to_dict(event),
                    current_user.id,
                    payload.timezone,
                )
                for event in google_events
            ]

        # Get current time in user's timezone
        current_time = datetime.now(tz).replace(tzinfo=None)

        return CalendarDayScheduleResponse(
            date=payload.date,
            events=events_schema,
            current_time=current_time,
            timezone=payload.timezone,
        )

    except pytz.UnknownTimeZoneError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid timezone",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to fetch daily schedule: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch calendar schedule",
        )


# ============================================================================
# FREE SLOT DETECTION
# ============================================================================


@router.post("/free-slots", response_model=FreeBusyResponse)
async def find_free_slots(
    request: Request,
    payload: FreeBusyRequest,
    current_user: User = Depends(get_current_user_from_db),
    db: Session = Depends(get_db),
) -> FreeBusyResponse:
    """
    Find free time slots on a given day.

    Uses calendar events to find available meeting slots within working hours.

    Args:
        payload: Request with date and working hours preferences
        current_user: Authenticated user
        db: Database session

    Returns:
        List of available time slots
    """
    try:
        trace_id = request.headers.get("x-trace-id", str(uuid.uuid4()))

        # Parse working hours
        work_start_hour, work_start_min = map(
            int, payload.working_hours_start.split(":")
        )
        work_end_hour, work_end_min = map(int, payload.working_hours_end.split(":"))

        # Calculate the work day window in user timezone
        tz = pytz.timezone(payload.timezone)
        day_start = tz.localize(datetime.combine(payload.date, datetime.min.time()))
        day_end = day_start + timedelta(days=1)
        work_day_start = tz.localize(
            datetime.combine(
                payload.date,
                datetime.min.time().replace(hour=work_start_hour, minute=work_start_min),
            )
        )
        work_day_end = tz.localize(
            datetime.combine(
                payload.date,
                datetime.min.time().replace(hour=work_end_hour, minute=work_end_min),
            )
        )

        # Collect busy windows from DB first, then fall back to Google events
        event_windows: list[tuple[datetime, datetime]] = []

        def _normalize_to_tz(dt: datetime) -> datetime:
            if dt.tzinfo is None:
                return tz.localize(dt)
            return dt.astimezone(tz)

        calendar_event_repo = CalendarEventRepository(db)
        try:
            events = calendar_event_repo.get_user_events_by_date_range(
                current_user.id, day_start, day_end
            )
            event_windows = [
                (_normalize_to_tz(event.start_time), _normalize_to_tz(event.end_time))
                for event in events
            ]
        except Exception as db_error:
            db.rollback()
            if not _is_missing_table_error(db_error):
                raise

            logger.warning(
                "calendar.free_slots.db_unavailable_fallback user=%s error=%s",
                current_user.id,
                str(db_error),
            )

            access_token = await _resolve_calendar_access_token(current_user, db)
            if access_token:
                google_events = await calendar_service.fetch_user_events(
                    access_token, day_start, day_end, max_results=100
                )
                for google_event in google_events:
                    parsed = calendar_service.parse_google_event_to_dict(google_event)
                    event_windows.append(
                        (
                            _normalize_to_tz(parsed["start_time"]),
                            _normalize_to_tz(parsed["end_time"]),
                        )
                    )

        free_slots = []
        total_free_minutes = 0

        # Sort events by start time
        sorted_events = sorted(event_windows, key=lambda e: e[0])

        if not sorted_events:
            # Entire work day is free
            duration = (work_day_end - work_day_start).total_seconds() / 60
            if duration >= payload.min_duration_minutes:
                free_slots.append(
                    FreeBusySlot(
                        start_time=work_day_start,
                        end_time=work_day_end,
                        duration_minutes=int(duration),
                    )
                )
                total_free_minutes = int(duration)
        else:
            # Check gap before first event
            if sorted_events[0][0] > work_day_start:
                gap_start = work_day_start
                gap_end = sorted_events[0][0]
                duration = (gap_end - gap_start).total_seconds() / 60
                if duration >= payload.min_duration_minutes:
                    free_slots.append(
                        FreeBusySlot(
                            start_time=gap_start,
                            end_time=gap_end,
                            duration_minutes=int(duration),
                        )
                    )
                    total_free_minutes += int(duration)

            # Check gaps between events
            for i in range(len(sorted_events) - 1):
                gap_start = sorted_events[i][1]
                gap_end = sorted_events[i + 1][0]
                duration = (gap_end - gap_start).total_seconds() / 60
                if duration >= payload.min_duration_minutes:
                    free_slots.append(
                        FreeBusySlot(
                            start_time=gap_start,
                            end_time=gap_end,
                            duration_minutes=int(duration),
                        )
                    )
                    total_free_minutes += int(duration)

            # Check gap after last event
            if sorted_events[-1][1] < work_day_end:
                gap_start = sorted_events[-1][1]
                gap_end = work_day_end
                duration = (gap_end - gap_start).total_seconds() / 60
                if duration >= payload.min_duration_minutes:
                    free_slots.append(
                        FreeBusySlot(
                            start_time=gap_start,
                            end_time=gap_end,
                            duration_minutes=int(duration),
                        )
                    )
                    total_free_minutes += int(duration)

        return FreeBusyResponse(
            date=payload.date,
            free_slots=free_slots,
            timezone=payload.timezone,
            total_free_minutes=total_free_minutes,
        )

    except ValueError as e:
        logger.error(f"Invalid time format: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid time format"
        )
    except pytz.UnknownTimeZoneError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid timezone",
        )
    except Exception as e:
        logger.error(f"Failed to find free slots: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to find free slots",
        )


# ============================================================================
# EVENT MANAGEMENT WITH APPROVALS
# ============================================================================


@router.post("/events", response_model=ApiResponse)
async def create_calendar_event(
    request: Request,
    payload: CalendarEventCreateRequest,
    current_user: User = Depends(get_current_user_from_db),
    db: Session = Depends(get_db),
) -> ApiResponse:
    """
    Create a new calendar event.

    Creates a calendar event and requires approval before syncing to Google Calendar.

    Args:
        payload: Event details
        current_user: Authenticated user
        db: Database session

    Returns:
        Created event with approval status
    """
    try:
        trace_id = request.headers.get("x-trace-id", str(uuid.uuid4()))

        approval = Approval(
            id=str(uuid.uuid4()),
            user_id=current_user.id,
            approval_type=Approval.ApprovalType.CREATE_EVENT,
            status=Approval.ApprovalStatus.PENDING,
            action_description=f"Create calendar event: {payload.title}",
            action_payload={
                "title": payload.title,
                "description": payload.description,
                "start_time": payload.start_time.isoformat(),
                "end_time": payload.end_time.isoformat(),
                "timezone": payload.timezone,
                "location": payload.location,
                "attendees": payload.attendees,
                "color": payload.color,
                "ai_generated": payload.ai_generated,
                "metadata": payload.metadata,
            },
            ai_reasoning="User requested event creation through chat",
            confidence_score=1.0 if not payload.ai_generated else 0.9,
            expires_at=datetime.utcnow() + timedelta(hours=24),
        )

        db.add(approval)
        try:
            db.commit()
        except Exception as db_error:
            db.rollback()
            if not _is_missing_table_error(db_error):
                raise
            logger.warning(
                "calendar.create_event.approval_table_unavailable_fallback user=%s error=%s",
                current_user.id,
                str(db_error),
            )
            return ApiResponse(
                data={
                    "approval_id": None,
                    "status": "PENDING",
                    "action": "pending_approval_fallback",
                    "event_preview": {
                        "title": payload.title,
                        "start_time": payload.start_time,
                        "end_time": payload.end_time,
                        "attendees": payload.attendees,
                    },
                },
                message="Event creation request accepted (approval persistence unavailable in this environment)",
            )

        return ApiResponse(
            data={
                "approval_id": approval.id,
                "status": approval.status,
                "action": "pending_approval",
                "event_preview": {
                    "title": payload.title,
                    "start_time": payload.start_time,
                    "end_time": payload.end_time,
                    "attendees": payload.attendees,
                },
            },
            message="Event creation pending approval",
        )

    except Exception as e:
        logger.error(f"Failed to create event: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create event",
        )


@router.put("/events/{event_id}", response_model=ApiResponse)
async def update_calendar_event(
    event_id: str,
    request: Request,
    payload: CalendarEventUpdateRequest,
    current_user: User = Depends(get_current_user_from_db),
    db: Session = Depends(get_db),
) -> ApiResponse:
    """
    Update an existing calendar event.

    Updates event details and requires approval before syncing to Google Calendar.

    Args:
        event_id: Calendar event ID
        payload: Updated event details
        current_user: Authenticated user
        db: Database session

    Returns:
        Updated event with approval status
    """
    try:
        trace_id = request.headers.get("x-trace-id", str(uuid.uuid4()))

        # Get existing event
        calendar_event_repo = CalendarEventRepository(db)
        event = calendar_event_repo.get_by_id(event_id)

        if not event or event.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Event not found"
            )

        # Prepare updated data
        updated_data = {}
        if payload.title:
            updated_data["title"] = payload.title
        if payload.description is not None:
            updated_data["description"] = payload.description
        if payload.start_time:
            updated_data["start_time"] = payload.start_time.isoformat()
        if payload.end_time:
            updated_data["end_time"] = payload.end_time.isoformat()
        if payload.location:
            updated_data["location"] = payload.location
        if payload.attendees:
            updated_data["attendees"] = payload.attendees
        if payload.status:
            updated_data["status"] = payload.status.value

        approval = Approval(
            id=str(uuid.uuid4()),
            user_id=current_user.id,
            approval_type=Approval.ApprovalType.UPDATE_EVENT,
            status=Approval.ApprovalStatus.PENDING,
            action_description=f"Update calendar event: {event.title}",
            action_payload={
                "event_id": event_id,
                "updates": updated_data,
            },
            ai_reasoning="User requested event update through chat",
            confidence_score=1.0,
            expires_at=datetime.utcnow() + timedelta(hours=24),
        )

        db.add(approval)
        db.commit()

        return ApiResponse(
            data={
                "approval_id": approval.id,
                "status": approval.status,
                "action": "pending_approval",
                "event_id": event_id,
            },
            message="Event update pending approval",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to update event: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update event",
        )


@router.delete("/events/{event_id}", response_model=ApiResponse)
async def delete_calendar_event(
    event_id: str,
    request: Request,
    current_user: User = Depends(get_current_user_from_db),
    db: Session = Depends(get_db),
) -> ApiResponse:
    """
    Delete a calendar event.

    Creates an approval request for deletion before removing event.

    Args:
        event_id: Calendar event ID
        current_user: Authenticated user
        db: Database session

    Returns:
        Deletion status with approval
    """
    try:
        trace_id = request.headers.get("x-trace-id", str(uuid.uuid4()))

        # Get existing event
        calendar_event_repo = CalendarEventRepository(db)
        event = calendar_event_repo.get_by_id(event_id)

        if not event or event.user_id != current_user.id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="Event not found"
            )

        approval = Approval(
            id=str(uuid.uuid4()),
            user_id=current_user.id,
            approval_type=Approval.ApprovalType.DELETE_EVENT,
            status=Approval.ApprovalStatus.PENDING,
            action_description=f"Delete calendar event: {event.title}",
            action_payload={
                "event_id": event_id,
                "title": event.title,
                "google_event_id": event.google_event_id,
            },
            ai_reasoning="User requested event deletion through chat",
            confidence_score=1.0,
            expires_at=datetime.utcnow() + timedelta(hours=24),
        )

        db.add(approval)
        db.commit()

        return ApiResponse(
            data={
                "approval_id": approval.id,
                "status": approval.status,
                "action": "pending_approval",
                "event_id": event_id,
            },
            message="Event deletion pending approval",
        )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to delete event: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to delete event",
        )


# ============================================================================
# CURRENT TIME HIGHLIGHT (FOR UI)
# ============================================================================


@router.get("/current-time")
async def get_current_time_info(
    timezone: str = Query(default="UTC", description="User's timezone"),
    current_user: User = Depends(get_current_user),
) -> ApiResponse:
    """
    Get current time information in user's timezone.

    Used by frontend to display current time highlight on calendar.

    Args:
        timezone: IANA timezone string
        current_user: Authenticated user

    Returns:
        Current time and timezone information
    """
    try:
        tz = pytz.timezone(timezone)
        current_time = datetime.now(tz)

        return ApiResponse(
            data={
                "current_time": current_time.isoformat(),
                "timestamp": current_time.timestamp(),
                "timezone": timezone,
                "offset_hours": current_time.utcoffset().total_seconds() / 3600,
            },
            message="Current time retrieved",
        )

    except pytz.exceptions.UnknownTimeZoneError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid timezone",
        )
    except Exception as e:
        logger.error(f"Failed to get current time: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to get current time",
        )


# ============================================================================
# EVENT LISTING
# ============================================================================


@router.get("/events", response_model=CalendarEventListResponse)
async def list_calendar_events(
    current_user: User = Depends(get_current_user_from_db),
    db: Session = Depends(get_db),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    status: Optional[str] = Query(None, description="Filter by event status"),
) -> CalendarEventListResponse:
    """
    List calendar events for authenticated user.

    Args:
        current_user: Authenticated user
        db: Database session
        skip: Number of events to skip
        limit: Maximum events to return
        status: Filter by event status

    Returns:
        List of calendar events
    """
    try:
        calendar_event_repo = CalendarEventRepository(db)

        # Build query
        query = db.query(CalendarEvent).filter(CalendarEvent.user_id == current_user.id)

        if status:
            try:
                event_status = EventStatus[status.upper()]
                query = query.filter(CalendarEvent.status == event_status.value)
            except KeyError:
                pass

        total_count = query.count()
        events = (
            query.order_by(CalendarEvent.start_time)
            .offset(skip)
            .limit(limit)
            .all()
        )

        events_schema = [CalendarEventSchema.model_validate(event) for event in events]

        return CalendarEventListResponse(
            events=events_schema,
            total_count=total_count,
            offset=skip,
            limit=limit,
            has_more=(skip + limit) < total_count,
        )

    except Exception as e:
        logger.error(f"Failed to list events: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to list events",
        )
