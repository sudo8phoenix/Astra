"""Unified Google OAuth service for both Gmail and Calendar in a single flow."""

import os
import logging
from datetime import datetime, timedelta
from time import perf_counter
from typing import Dict, Any, Optional
import uuid

from google_auth_oauthlib.flow import Flow
from app.core.config import settings
from app.core.logging_config import get_trace_id
from app.core.metrics import metrics_collector
from app.core.retry import RetryExhaustedError, retry_sync

logger = logging.getLogger(__name__)


class UnifiedGoogleOAuthService:
    """
    Unified Google OAuth service for login that combines both Gmail and Calendar.
    
    This service handles OAuth flows where users authenticate once and get
    tokens for both Gmail and Calendar services.
    """
    
    # Unified scopes for both Gmail and Calendar
    SCOPES = [
        "openid",
        "email",
        "profile",
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/calendar.readonly",
        "https://www.googleapis.com/auth/calendar.events",
    ]
    
    def __init__(self):
        """Initialize unified OAuth service."""
        self.client_id = settings.google_oauth_client_id
        self.client_secret = settings.google_oauth_client_secret
        self.redirect_uri = settings.google_oauth_redirect_uri
    
    def get_oauth_flow(self) -> Flow:
        """Create OAuth 2.0 flow for unified Gmail + Calendar authorization."""
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
    
    async def exchange_code_for_tokens(self, code: str) -> Dict[str, Any]:
        """
        Exchange authorization code for access and refresh tokens.
        
        Returns tokens that work for both Gmail and Calendar APIs.
        
        Args:
            code: Authorization code from OAuth callback
            
        Returns:
            Dict with access_token, refresh_token, expires_in, etc.
        """
        trace_id = get_trace_id() or "N/A"
        start = perf_counter()
        attempts = 1
        
        try:
            # Google can return semantically equivalent scope aliases (for example
            # userinfo scopes for email/profile). Allow token exchange to proceed.
            os.environ.setdefault("OAUTHLIB_RELAX_TOKEN_SCOPE", "1")
            flow = self.get_oauth_flow()
            
            # Exchange code for tokens using retry logic
            _, attempts = retry_sync(
                operation=lambda: flow.fetch_token(code=code),
                exceptions=(Exception,),
                # OAuth authorization codes are single-use. Retrying can only
                # cause repeated invalid_grant responses for the same code.
                max_attempts=1,
                base_delay=0.4,
                backoff_factor=2.0,
            )
            
            token = flow.credentials.token
            refresh_token = flow.credentials.refresh_token
            expires_in = 3600  # Default Google token expiry
            
            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_external_call(
                service="unified_oauth",
                operation="exchange_code_for_tokens",
                status="success",
                duration_ms=duration_ms,
                attempts=attempts,
            )
            
            logger.info(
                "unified.oauth.exchange.success",
                extra={
                    "trace_id": trace_id,
                    "duration_ms": round(duration_ms, 2),
                    "attempts": attempts,
                },
            )
            
            return {
                "access_token": token,
                "refresh_token": refresh_token,
                "expires_in": expires_in,
                "token_type": "Bearer",
                "scope": " ".join(self.SCOPES),
            }
        
        except RetryExhaustedError as e:
            if "invalid_grant" in str(e).lower():
                raise ValueError(
                    "Google authorization code is invalid or expired. Please start sign-in again."
                ) from e
            duration_ms = (perf_counter() - start) * 1000
            metrics_collector.record_external_call(
                service="unified_oauth",
                operation="exchange_code_for_tokens",
                status="error",
                duration_ms=duration_ms,
                attempts=attempts,
            )
            logger.error(
                "unified.oauth.exchange.failed",
                extra={"trace_id": trace_id, "duration_ms": round(duration_ms, 2)},
                exc_info=True,
            )
            raise
        except Exception as e:
            duration_ms = (perf_counter() - start) * 1000
            logger.error(
                "unified.oauth.unexpected_error",
                extra={"trace_id": trace_id, "error": str(e)},
                exc_info=True,
            )
            raise
