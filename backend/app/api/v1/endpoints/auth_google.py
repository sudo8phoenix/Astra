"""Google OAuth callback bridge endpoints for Gmail and Calendar connections."""

import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.core.auth import JWTManager
from app.db.config import get_db
from app.db.models import User
from app.repositories.repositories import UserRepository
from app.schemas.common import ApiResponse
from app.services.calendar import GoogleCalendarService
from app.services.email_service import EmailService

router = APIRouter(prefix="/auth/google", tags=["auth"])
logger = logging.getLogger(__name__)


def _extract_bearer_token(request: Request) -> Optional[str]:
    """Return bearer token if present in Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    return auth_header.replace("Bearer ", "", 1).strip()


@router.get("/callback", response_model=ApiResponse)
async def google_oauth_callback_bridge(
    request: Request,
    code: str = Query(..., description="Google OAuth authorization code"),
    state: Optional[str] = Query(None, description="OAuth state (can carry JWT token)"),
    token: Optional[str] = Query(None, description="JWT token for user identification"),
    provider: Optional[str] = Query(None, description="Target integration: email or calendar"),
    scope: Optional[str] = Query(None, description="OAuth scopes returned by Google"),
    db: Session = Depends(get_db),
) -> ApiResponse:
    """
    Complete Google OAuth callback and link either Gmail or Calendar to the user.

    The endpoint accepts JWT token via `token` query, Authorization header,
    or `state` as a fallback for local/manual OAuth testing.
    """
    jwt_token = token or _extract_bearer_token(request) or state
    if not jwt_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing JWT token. Pass token query param, bearer header, or state.",
        )

    token_payload = JWTManager.verify_token(jwt_token)
    user_repo = UserRepository(db)
    user = user_repo.get_by_id(token_payload.sub)

    if not user:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="User not found",
        )

    selected_provider = provider.lower().strip() if provider else ""
    if not selected_provider:
        normalized_scope = (scope or "").lower()
        # Prefer Gmail when both Gmail and Calendar scopes are present.
        # Gmail authorize URL uses include_granted_scopes=true, so Google can
        # return previously granted calendar scopes in the callback as well.
        if "gmail" in normalized_scope or "mail.google.com" in normalized_scope:
            selected_provider = "email"
        elif "calendar" in normalized_scope:
            selected_provider = "calendar"
        else:
            selected_provider = "email"

    if selected_provider in {"email", "gmail"}:
        email_service = EmailService(db)
        try:
            success = email_service.connect_gmail_account(user, code)
        except Exception as exc:
            logger.warning(
                "gmail.oauth.callback.exchange_failed user=%s error=%s",
                user.id,
                str(exc),
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Failed to exchange Google authorization code for Gmail. "
                    "Use a fresh authorize URL and complete consent immediately."
                ),
            )

        if not success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Failed to connect Gmail account",
            )

        logger.info("Google Gmail connected for user %s", user.id)
        return ApiResponse(
            data={"connected": True, "provider": "email", "user_id": user.id},
            message="Gmail account connected successfully",
        )

    if selected_provider == "calendar":
        calendar_service = GoogleCalendarService()
        try:
            tokens = await calendar_service.exchange_code_for_tokens(code)
        except Exception as exc:
            logger.warning(
                "calendar.oauth.callback.exchange_failed user=%s error=%s",
                user.id,
                str(exc),
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    "Failed to exchange Google authorization code for Calendar. "
                    "Use a fresh authorize URL and complete consent immediately."
                ),
            )

        if user.preferences is None:
            user.preferences = {}

        user.preferences["calendar_oauth_tokens"] = {
            "access_token": tokens.get("access_token"),
            "refresh_token": tokens.get("refresh_token"),
            "expires_at": (
                datetime.utcnow() + timedelta(seconds=tokens.get("expires_in", 3600))
            ).isoformat(),
        }
        user.oauth_provider = "google"
        user_repo.update(user)
        db.commit()

        logger.info("Google Calendar connected for user %s", user.id)
        return ApiResponse(
            data={"connected": True, "provider": "calendar", "user_id": user.id},
            message="Google Calendar connected successfully",
        )

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Invalid provider. Use 'email' or 'calendar'.",
    )
