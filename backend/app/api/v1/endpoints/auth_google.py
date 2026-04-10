"""Google OAuth callback bridge endpoints for Gmail and Calendar connections."""

import logging
import uuid
from datetime import datetime, timedelta
from typing import Optional
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy.orm import Session

from app.core.auth import JWTManager
from app.core.config import settings
from app.db.config import get_db
from app.db.models import User
from app.repositories.repositories import UserRepository
from app.schemas.common import ApiResponse
from app.services.calendar import GoogleCalendarService
from app.services.unified_oauth import UnifiedGoogleOAuthService
from app.services.email_service import EmailService

router = APIRouter(prefix="/auth/google", tags=["auth"])
logger = logging.getLogger(__name__)


def _friendly_oauth_error(raw_error: str) -> str:
    """Map low-level OAuth failures to user-facing guidance."""
    text = (raw_error or "").lower()
    if "invalid_grant" in text or "expired" in text:
        return "Google authorization code expired or was already used. Please sign in again."
    if "invalid_client" in text:
        return "Google OAuth client credentials are invalid on the server. Please contact support."
    if "redirect_uri" in text:
        return "Google OAuth redirect URI is misconfigured. Please contact support."
    if "access_denied" in text:
        return "Google sign-in was cancelled. Please try again and approve permissions."
    if "unauthorized_client" in text:
        return "Google OAuth client is not authorized for this flow. Please contact support."
    return "Google OAuth callback failed. Please sign in again."


def _frontend_redirect_html(*, token: Optional[str] = None, error: Optional[str] = None) -> RedirectResponse:
    """Return an HTTP redirect that sends callback results to the frontend app."""
    params = {}
    if token:
        params["token"] = token
    if error:
        params["oauth_error"] = error
    query = urlencode(params)
    destination = f"{settings.frontend_url}/"
    if query:
        destination = f"{destination}?{query}"

    return RedirectResponse(url=destination, status_code=status.HTTP_302_FOUND)


def _extract_bearer_token(request: Request) -> Optional[str]:
    """Return bearer token if present in Authorization header."""
    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return None
    return auth_header.replace("Bearer ", "", 1).strip()


@router.get("/login", response_model=dict)
async def unified_oauth_login() -> dict:
    """
    Generate unified Google OAuth URL for login with Gmail and Calendar.
    
    This combines both Gmail and Calendar scopes so user can login
    and connect both services in one step.
    
    Returns:
        Dictionary with oauth_url for redirection
    """
    try:
        if not settings.google_oauth_client_id or not settings.google_oauth_client_secret:
            logger.error("Google OAuth credentials are not configured")
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Google OAuth is not configured on the server. Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET.",
            )

        state = str(uuid.uuid4())
        
        # Combine Gmail and Calendar scopes
        scopes = [
            "openid",
            "email",
            "profile",
            "https://www.googleapis.com/auth/gmail.readonly",
            "https://www.googleapis.com/auth/gmail.send",
            "https://www.googleapis.com/auth/gmail.modify",
            "https://www.googleapis.com/auth/calendar.readonly",
            "https://www.googleapis.com/auth/calendar.events",
        ]
        
        params = {
            "client_id": settings.google_oauth_client_id,
            "redirect_uri": settings.google_oauth_redirect_uri,
            "response_type": "code",
            "scope": " ".join(scopes),
            "state": state,
            "access_type": "offline",
            "prompt": "consent",
            "include_granted_scopes": "true",
        }
        
        oauth_url = f"https://accounts.google.com/o/oauth2/v2/auth?{urlencode(params)}"
        
        logger.info("Unified OAuth login URL generated with both Gmail and Calendar scopes")
        return {"oauth_url": oauth_url, "state": state}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to generate unified OAuth URL: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to generate login URL",
        )


@router.post("/unified-callback", response_model=dict)
async def unified_oauth_callback(
    code: str = Query(..., description="Google OAuth authorization code"),
    state: Optional[str] = Query(None, description="OAuth state"),
    db: Session = Depends(get_db),
) -> dict:
    """
    Handle unified Google OAuth callback for login with Gmail and Calendar connected.
    
    This endpoint creates a new user (or gets existing one) and connects
    both Gmail and Calendar tokens in one step using a single authorization code.
    
    IMPORTANT: Google OAuth codes are single-use. We exchange once and store
    the token for both services.
    
    Args:
        code: Authorization code from Google
        state: State parameter for CSRF protection
        db: Database session
        
    Returns:
        Dictionary with JWT token and user info
    """
    if not code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing authorization code",
        )
    
    try:
        # For unified login, we'll create/get user and connect both services
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
        
        gmail_connected = False
        calendar_connected = False
        
        # Exchange code ONCE using UnifiedGoogleOAuthService
        # Google OAuth codes are single-use. The returned token works for all requested scopes (Gmail + Calendar)
        tokens = None
        try:
            unified_service = UnifiedGoogleOAuthService()
            tokens = await unified_service.exchange_code_for_tokens(code)
            logger.info(f"Successfully exchanged OAuth code for unified tokens")
        except Exception as e:
            logger.warning(f"Failed to exchange OAuth code: {str(e)}")
            err_text = str(e).lower()
            if (
                "invalid_grant" in err_text
                or "expired" in err_text
                or "scope has changed" in err_text
            ):
                return _frontend_redirect_html(
                    error="Google authorization code expired or was already used. Please sign in again."
                )
            raise
        
        if not tokens:
            raise ValueError("No tokens returned from OAuth code exchange")
        
        # Store Gmail tokens from the exchange
        if tokens.get("access_token"):
            preferences = dict(user.preferences or {})
            preferences["gmail_access_token"] = tokens.get("access_token")
            if tokens.get("refresh_token"):
                preferences["gmail_refresh_token"] = tokens.get("refresh_token")
            preferences["gmail_expires_at"] = (
                datetime.utcnow() + timedelta(seconds=tokens.get("expires_in", 3600))
            ).isoformat()
            preferences["gmail_connected"] = True
            user.preferences = preferences
            user.oauth_provider = "google"
            db.add(user)
            db.commit()
            gmail_connected = True
            logger.info(f"Gmail connected for user {user.id}")
        
        # Store Calendar tokens from same exchange
        if tokens.get("access_token"):
            preferences = dict(user.preferences or {})
            existing_tokens = dict(preferences.get("calendar_oauth_tokens") or {})
            preferences["calendar_oauth_tokens"] = {
                "access_token": tokens.get("access_token"),
                "refresh_token": tokens.get("refresh_token") or existing_tokens.get("refresh_token"),
                "expires_at": (
                    datetime.utcnow() + timedelta(seconds=tokens.get("expires_in", 3600))
                ).isoformat(),
            }
            preferences["calendar_connected"] = True
            user.preferences = preferences
            user.oauth_provider = "google"
            db.add(user)
            db.commit()
            calendar_connected = True
            logger.info(f"Calendar connected for user {user.id} using shared OAuth token")
        
        # Generate JWT token
        access_token = JWTManager.create_access_token(
            user_id=user.id,
            email=user.email,
            scopes=["read", "write"],
        )
        
        return {
            "success": True,
            "token": access_token,
            "user_id": user.id,
            "email": user.email,
            "services_connected": {
                "gmail": gmail_connected,
                "calendar": calendar_connected,
            },
            "message": f"Login successful. Gmail: {gmail_connected}, Calendar: {calendar_connected}",
        }
    
    except ValueError as e:
        logger.warning(f"Unified OAuth callback validation failed: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Google authorization failed. Please sign in again.",
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unified OAuth callback failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to process OAuth callback",
        )


@router.get("/callback", response_model=ApiResponse)
async def google_oauth_callback_bridge(
    request: Request,
    code: str = Query(..., description="Google OAuth authorization code"),
    state: Optional[str] = Query(None, description="OAuth state (can carry JWT token)"),
    token: Optional[str] = Query(None, description="JWT token for user identification"),
    provider: Optional[str] = Query(None, description="Target integration: email or calendar"),
    scope: Optional[str] = Query(None, description="OAuth scopes returned by Google"),
    error: Optional[str] = Query(None, description="OAuth error returned by Google"),
    error_description: Optional[str] = Query(None, description="OAuth error description returned by Google"),
    db: Session = Depends(get_db),
) -> ApiResponse:
    """
    Complete Google OAuth callback and link Gmail/Calendar services.
    
    Handles both authenticated (linking service to existing user) and 
    unauthenticated (new unified login with both services) flows.
    """
    if error:
        description = (error_description or error).replace("+", " ").strip()
        return _frontend_redirect_html(error=_friendly_oauth_error(description))

    # If no token and no provider, this is a unified login attempt
    if not token and not provider:
        try:
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
            
            gmail_connected = False
            calendar_connected = False
            
            # Exchange code ONCE using UnifiedGoogleOAuthService
            tokens = None
            try:
                unified_service = UnifiedGoogleOAuthService()
                tokens = await unified_service.exchange_code_for_tokens(code)
                logger.info(f"Successfully exchanged OAuth code for unified tokens in callback")
            except Exception as e:
                logger.warning(f"Failed to exchange OAuth code in unified callback: {str(e)}")
                err_text = str(e).lower()
                if (
                    "invalid_grant" in err_text
                    or "expired" in err_text
                    or "scope has changed" in err_text
                ):
                    return _frontend_redirect_html(
                        error="Google authorization code expired or was already used. Please sign in again."
                    )
                raise
            
            if tokens and tokens.get("access_token"):
                # Store Gmail tokens from shared OAuth exchange
                preferences = dict(user.preferences or {})
                preferences["gmail_access_token"] = tokens.get("access_token")
                if tokens.get("refresh_token"):
                    preferences["gmail_refresh_token"] = tokens.get("refresh_token")
                preferences["gmail_expires_at"] = (
                    datetime.utcnow() + timedelta(seconds=tokens.get("expires_in", 3600))
                ).isoformat()
                preferences["gmail_connected"] = True
                user.preferences = preferences
                user.oauth_provider = "google"
                db.add(user)
                db.commit()
                gmail_connected = True
                logger.info(f"Gmail connected for user {user.id} via unified callback")
                
                # Store Calendar tokens from same OAuth exchange
                preferences = dict(user.preferences or {})
                existing_tokens = dict(preferences.get("calendar_oauth_tokens") or {})
                preferences["calendar_oauth_tokens"] = {
                    "access_token": tokens.get("access_token"),
                    "refresh_token": tokens.get("refresh_token") or existing_tokens.get("refresh_token"),
                    "expires_at": (
                        datetime.utcnow() + timedelta(seconds=tokens.get("expires_in", 3600))
                    ).isoformat(),
                }
                preferences["calendar_connected"] = True
                user.preferences = preferences
                user.oauth_provider = "google"
                db.add(user)
                db.commit()
                calendar_connected = True
                logger.info(f"Calendar connected for user {user.id} via unified callback using shared token")
            
            # Generate JWT token
            access_token = JWTManager.create_access_token(
                user_id=user.id,
                email=user.email,
                scopes=["read", "write"],
            )
            
            # Redirect to frontend and let frontend persist token in its own origin.
            return _frontend_redirect_html(token=access_token)
        
        except ValueError as e:
            logger.warning(f"Unified oauth callback validation failed: {str(e)}")
            return _frontend_redirect_html(
                error="Google authorization failed. Please sign in again."
            )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Unified oauth callback failed: {str(e)}", exc_info=True)
            return _frontend_redirect_html(error=_friendly_oauth_error(str(e)))
    
    # Existing authenticated provider-specific flow
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

        preferences = dict(user.preferences or {})
        existing_tokens = dict(preferences.get("calendar_oauth_tokens") or {})
        preferences["calendar_oauth_tokens"] = {
            "access_token": tokens.get("access_token"),
            "refresh_token": tokens.get("refresh_token") or existing_tokens.get("refresh_token"),
            "expires_at": (
                datetime.utcnow() + timedelta(seconds=tokens.get("expires_in", 3600))
            ).isoformat(),
        }
        preferences["calendar_connected"] = True
        user.preferences = preferences
        user.oauth_provider = "google"
        db.add(user)
        db.commit()

        logger.info("Google Calendar connected for user %s", user.id)
        return ApiResponse(
            data={"connected": True, "provider": "calendar", "user_id": user.id},
            message="Calendar account connected successfully",
        )

    return ApiResponse(
        data={},
        message="No provider selected",
    )
