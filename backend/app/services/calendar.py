"""Google Calendar API integration service with OAuth 2.0 support."""

import logging
from datetime import datetime, timedelta
from time import perf_counter
from typing import Optional, List, Dict, Any
import httpx
import json

from app.core.config import settings
from app.core.logging_config import get_trace_id
from app.core.metrics import metrics_collector
from app.core.retry import RetryExhaustedError, retry_async, retry_sync
from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials
from google_auth_oauthlib.flow import Flow
from google.auth.exceptions import RefreshError
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

logger = logging.getLogger(__name__)


class GoogleCalendarService:
    """Google Calendar OAuth and API integration."""

    SCOPES = [
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/calendar.events",
    ]

    def __init__(self):
        """Initialize Google Calendar service."""
        self.client_id = settings.google_oauth_client_id
        self.client_secret = settings.google_oauth_client_secret
        self.redirect_uri = settings.google_oauth_redirect_uri

    @staticmethod
    def _should_retry_google_http_error(error: HttpError) -> bool:
        status = getattr(error.resp, "status", None)
        return status in (429, 500, 502, 503, 504)

    def _execute_google_call(self, operation: str, fn):
        start = perf_counter()
        trace_id = get_trace_id() or "N/A"
        attempts = 1
        try:
            result, attempts = retry_sync(
                operation=fn,
                exceptions=(HttpError,),
                max_attempts=3,
                base_delay=0.4,
                backoff_factor=2.0,
            )
            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_external_call(
                service="google_calendar",
                operation=operation,
                status="success",
                duration_ms=duration_ms,
                attempts=attempts,
            )
            logger.info(
                "calendar.external_call.success",
                extra={
                    "trace_id": trace_id,
                    "operation": operation,
                    "duration_ms": round(duration_ms, 2),
                    "attempts": attempts,
                },
            )
            return result
        except RetryExhaustedError:
            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_external_call(
                service="google_calendar",
                operation=operation,
                status="error",
                duration_ms=duration_ms,
                attempts=attempts,
            )
            logger.error(
                "calendar.external_call.retry_exhausted",
                extra={
                    "trace_id": trace_id,
                    "operation": operation,
                    "duration_ms": round(duration_ms, 2),
                },
                exc_info=True,
            )
            raise

    def get_oauth_flow(self) -> Flow:
        """Create OAuth 2.0 flow for authorization."""
        flow = Flow.from_client_config(
            {
                "installed": {
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "redirect_uris": [self.redirect_uri],
                    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                    "token_uri": "https://oauth2.googleapis.com/token",
                }
            },
            scopes=self.SCOPES,
            redirect_uri=self.redirect_uri,
        )
        return flow

    def get_authorization_url(self, state: str) -> str:
        """
        Generate OAuth 2.0 authorization URL.

        Args:
            state: CSRF protection state parameter

        Returns:
            Authorization URL for user to visit
        """
        flow = self.get_oauth_flow()
        auth_url, _ = flow.authorization_url(state=state, access_type="offline")
        return auth_url

    async def exchange_code_for_tokens(
        self, code: str, redirect_uri: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Exchange authorization code for access and refresh tokens.

        Args:
            code: Authorization code from OAuth callback
            redirect_uri: Must match registered redirect_uri

        Returns:
            Dict with access_token, refresh_token, expires_in, etc.
        """
        trace_id = get_trace_id() or "N/A"
        try:
            flow = self.get_oauth_flow()
            if redirect_uri:
                flow.redirect_uri = redirect_uri

            # Exchange code for tokens
            self._execute_google_call("exchange_code_for_tokens", lambda: flow.fetch_token(code=code))

            token = flow.credentials.token
            refresh_token = flow.credentials.refresh_token
            expires_in = 3600  # Default Google token expiry

            return {
                "access_token": token,
                "refresh_token": refresh_token,
                "expires_in": expires_in,
                "token_type": "Bearer",
                "scope": " ".join(self.SCOPES),
            }
        except Exception as e:
            logger.error(
                "calendar.oauth_exchange.failed",
                extra={"trace_id": trace_id},
                exc_info=True,
            )
            raise

    async def refresh_access_token(self, refresh_token: str) -> Dict[str, Any]:
        """
        Refresh expired access token using refresh token.

        Args:
            refresh_token: Previously issued refresh token

        Returns:
            Dict with new access_token and expires_in
        """
        start = perf_counter()
        trace_id = get_trace_id() or "N/A"
        attempts = 1
        try:
            async def _do_refresh() -> httpx.Response:
                async with httpx.AsyncClient() as client:
                    response = await client.post(
                        "https://oauth2.googleapis.com/token",
                        data={
                            "client_id": self.client_id,
                            "client_secret": self.client_secret,
                            "refresh_token": refresh_token,
                            "grant_type": "refresh_token",
                        },
                        timeout=10.0,
                    )
                    if response.status_code != 200:
                        raise ValueError(f"Token refresh failed: {response.text}")
                    return response

            response, attempts = await retry_async(
                operation=_do_refresh,
                exceptions=(httpx.RequestError, httpx.TimeoutException, ValueError),
                max_attempts=3,
                base_delay=0.4,
                backoff_factor=2.0,
            )

            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_external_call(
                service="google_calendar",
                operation="refresh_access_token",
                status="success",
                duration_ms=duration_ms,
                attempts=attempts,
            )

            data = response.json()
            return {
                "access_token": data["access_token"],
                "expires_in": data.get("expires_in", 3600),
                "token_type": data.get("token_type", "Bearer"),
            }
        except Exception as e:
            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_external_call(
                service="google_calendar",
                operation="refresh_access_token",
                status="error",
                duration_ms=duration_ms,
                attempts=attempts,
            )
            logger.error(
                "calendar.refresh_token.failed",
                extra={"trace_id": trace_id, "duration_ms": round(duration_ms, 2)},
                exc_info=True,
            )
            raise

    def build_calendar_service(self, access_token: str):
        """
        Build Google Calendar API service client.

        Args:
            access_token: Valid OAuth access token

        Returns:
            Google Calendar API service object
        """
        try:
            from google.oauth2.credentials import Credentials

            credentials = Credentials(token=access_token)
            service = build("calendar", "v3", credentials=credentials, cache_discovery=False)
            return service
        except Exception as e:
            logger.error(f"Failed to build calendar service: {str(e)}")
            raise

    async def fetch_user_events(
        self,
        access_token: str,
        time_min: datetime,
        time_max: datetime,
        max_results: int = 50,
    ) -> List[Dict[str, Any]]:
        """
        Fetch user's calendar events for a date range.

        Args:
            access_token: Valid OAuth access token
            time_min: Start of time range (UTC)
            time_max: End of time range (UTC)
            max_results: Maximum number of events to return

        Returns:
            List of calendar events
        """
        trace_id = get_trace_id() or "N/A"
        try:
            service = self.build_calendar_service(access_token)

            events: List[Dict[str, Any]] = []
            page_token: Optional[str] = None
            while True:
                events_result = self._execute_google_call(
                    "fetch_user_events",
                    lambda: service.events().list(
                        calendarId="primary",
                        timeMin=time_min.isoformat().replace("+00:00", "Z"),
                        timeMax=time_max.isoformat().replace("+00:00", "Z"),
                        maxResults=max_results,
                        singleEvents=True,
                        orderBy="startTime",
                        pageToken=page_token,
                    ).execute(),
                )

                items = events_result.get("items", [])
                if items:
                    events.extend(items)
                page_token = events_result.get("nextPageToken")
                if not page_token:
                    break

            logger.info(f"Fetched {len(events)} events from primary calendar")
            return events

        except HttpError as e:
            if e.resp.status == 401:
                logger.warning("Access token expired, need refresh")
                raise ValueError("Access token expired")
            logger.error("calendar.fetch_user_events.failed", extra={"trace_id": trace_id}, exc_info=True)
            raise

    async def create_event(
        self,
        access_token: str,
        event_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Create a new calendar event.

        Args:
            access_token: Valid OAuth access token
            event_data: Event details {title, start, end, description, attendees, etc.}

        Returns:
            Created event details including Google event ID
        """
        trace_id = get_trace_id() or "N/A"
        try:
            service = self.build_calendar_service(access_token)

            body = {
                "summary": event_data.get("title", "Event"),
                "description": event_data.get("description"),
                "location": event_data.get("location"),
                "start": {
                    "dateTime": event_data["start_time"].isoformat(),
                    "timeZone": event_data.get("timezone", "UTC"),
                },
                "end": {
                    "dateTime": event_data["end_time"].isoformat(),
                    "timeZone": event_data.get("timezone", "UTC"),
                },
            }

            if event_data.get("attendees"):
                body["attendees"] = [
                    {"email": email} for email in event_data["attendees"]
                ]

            if event_data.get("color_id"):
                body["colorId"] = event_data["color_id"]

            if event_data.get("reminders"):
                body["reminders"] = {
                    "useDefault": False,
                    "overrides": event_data["reminders"],
                }

            if event_data.get("recurrence"):
                body["recurrence"] = [event_data["recurrence"]]

            event = self._execute_google_call(
                "create_event",
                lambda: service.events().insert(
                    calendarId="primary",
                    body=body,
                    sendNotifications=True,
                ).execute(),
            )

            logger.info(f"Created event {event['id']}")
            return event

        except HttpError as e:
            logger.error("calendar.create_event.failed", extra={"trace_id": trace_id}, exc_info=True)
            raise

    async def update_event(
        self,
        access_token: str,
        google_event_id: str,
        event_data: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Update an existing calendar event.

        Args:
            access_token: Valid OAuth access token
            google_event_id: Google Calendar event ID
            event_data: Updated event details

        Returns:
            Updated event details
        """
        trace_id = get_trace_id() or "N/A"
        try:
            service = self.build_calendar_service(access_token)

            # Get existing event
            event = self._execute_google_call(
                "get_event_for_update",
                lambda: service.events().get(calendarId="primary", eventId=google_event_id).execute(),
            )

            # Update fields
            if "title" in event_data:
                event["summary"] = event_data["title"]
            if "description" in event_data:
                event["description"] = event_data["description"]
            if "location" in event_data:
                event["location"] = event_data["location"]
            if "start_time" in event_data:
                event["start"] = {
                    "dateTime": event_data["start_time"].isoformat(),
                    "timeZone": event_data.get("timezone", "UTC"),
                }
            if "end_time" in event_data:
                event["end"] = {
                    "dateTime": event_data["end_time"].isoformat(),
                    "timeZone": event_data.get("timezone", "UTC"),
                }

            updated_event = self._execute_google_call(
                "update_event",
                lambda: service.events().update(calendarId="primary", eventId=google_event_id, body=event).execute(),
            )

            logger.info(f"Updated event {google_event_id}")
            return updated_event

        except HttpError as e:
            logger.error("calendar.update_event.failed", extra={"trace_id": trace_id}, exc_info=True)
            raise

    async def delete_event(
        self,
        access_token: str,
        google_event_id: str,
    ) -> bool:
        """
        Delete a calendar event.

        Args:
            access_token: Valid OAuth access token
            google_event_id: Google Calendar event ID

        Returns:
            True if deleted successfully
        """
        trace_id = get_trace_id() or "N/A"
        try:
            service = self.build_calendar_service(access_token)
            self._execute_google_call(
                "delete_event",
                lambda: service.events().delete(
                    calendarId="primary",
                    eventId=google_event_id,
                    sendNotifications=True,
                ).execute(),
            )

            logger.info(f"Deleted event {google_event_id}")
            return True

        except HttpError as e:
            logger.error("calendar.delete_event.failed", extra={"trace_id": trace_id}, exc_info=True)
            raise

    async def get_freebusy(
        self,
        access_token: str,
        time_min: datetime,
        time_max: datetime,
    ) -> Dict[str, Any]:
        """
        Get freebusy information for user's calendar.

        Args:
            access_token: Valid OAuth access token
            time_min: Start of time range (UTC)
            time_max: End of time range (UTC)

        Returns:
            Freebusy data with busy and free slots
        """
        trace_id = get_trace_id() or "N/A"
        try:
            service = self.build_calendar_service(access_token)

            body = {
                "timeMin": time_min.isoformat() + "Z",
                "timeMax": time_max.isoformat() + "Z",
                "items": [{"id": "primary"}],
            }

            freebusy = self._execute_google_call(
                "get_freebusy",
                lambda: service.freebusy().query(body=body).execute(),
            )

            logger.info("Retrieved freebusy information")
            return freebusy

        except HttpError as e:
            logger.error("calendar.get_freebusy.failed", extra={"trace_id": trace_id}, exc_info=True)
            raise

    def parse_google_event_to_dict(
        self, google_event: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Convert Google Calendar API event to internal format.

        Args:
            google_event: Event from Google Calendar API

        Returns:
            Normalized event dictionary
        """
        start = google_event.get("start", {})
        end = google_event.get("end", {})

        # Handle all-day events vs timed events
        start_time = start.get("dateTime") or start.get("date")
        end_time = end.get("dateTime") or end.get("date")
        is_all_day = "dateTime" not in start

        # Parse datetimes
        parsed_start = datetime.fromisoformat(start_time.replace("Z", "+00:00"))
        parsed_end = datetime.fromisoformat(end_time.replace("Z", "+00:00"))

        # Keep Google all-day semantics (exclusive end boundary at next day start).
        # This preserves start_time < end_time for one-day all-day events.
        if is_all_day and parsed_end <= parsed_start:
            parsed_end = parsed_start + timedelta(days=1)

        return {
            "google_event_id": google_event.get("id"),
            "title": google_event.get("summary", "Untitled"),
            "description": google_event.get("description"),
            "start_time": parsed_start,
            "end_time": parsed_end,
            "location": google_event.get("location"),
            "all_day": is_all_day,
            "color_id": google_event.get("colorId"),
            "status": google_event.get("status", "confirmed").lower(),
            "attendees": [
                {"email": att.get("email"), "status": att.get("responseStatus")}
                for att in google_event.get("attendees", [])
            ],
            "reminders": google_event.get("reminders", {}).get("overrides", []),
            "html_link": google_event.get("htmlLink"),
            "hangout_link": google_event.get("hangoutLink"),
            "conference_link": ((google_event.get("conferenceData") or {}).get("entryPoints") or [{}])[0].get("uri"),
            "organizer": (google_event.get("organizer") or {}).get("email"),
            "attendee_statuses": {
                str(att.get("email") or ""): str(att.get("responseStatus") or "needsAction")
                for att in google_event.get("attendees", [])
                if att.get("email")
            },
        }
