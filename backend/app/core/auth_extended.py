"""
Extended Authentication Module: OAuth, Session, and WebSocket Auth.

Complements core/auth.py with:
- Google OAuth 2.0 flow
- Session management (Redis-backed)
- WebSocket authentication
- Approval-scoped tokens
"""

from typing import Optional
from datetime import datetime, timedelta, timezone
import uuid
import json

from pydantic import BaseModel, Field
import jwt

from app.core.config import settings


# ============================================================================
# OAUTH MODELS
# ============================================================================

class OAuthCallbackRequest(BaseModel):
    """OAuth callback with authorization code."""
    
    code: str = Field(..., description="Authorization code from provider")
    state: str = Field(..., description="State param (CSRF protection)")
    provider: str = Field(..., description="oauth provider (google, github)")


class OAuthTokenRequest(BaseModel):
    """Request to exchange auth code for tokens."""
    
    provider: str
    code: str
    redirect_uri: str = Field(..., description="Must match registered redirect_uri")


class GoogleOAuthTokens(BaseModel):
    """Google OAuth token response."""
    
    access_token: str
    refresh_token: Optional[str] = None
    expires_in: int
    token_type: str = "Bearer"
    scope: str
    id_token: Optional[str] = None


class OAuthUserInfo(BaseModel):
    """User info retrieved from OAuth provider."""
    
    provider: str
    provider_user_id: str
    email: str
    name: str
    picture_url: Optional[str] = None
    verified_email: bool = True


class OAuthToken(BaseModel):
    """Stored OAuth token (encrypted in Redis)."""
    
    provider: str
    access_token: str
    refresh_token: Optional[str] = None
    expires_at: datetime
    scopes: list[str]


# ============================================================================
# SESSION MODELS
# ============================================================================

class SessionData(BaseModel):
    """User session data (stored in Redis)."""
    
    user_id: str
    session_id: str
    email: str
    timezone: str
    oauth_tokens: Optional[dict] = Field(
        None,
        description="Encrypted OAuth tokens {provider: {access_token, refresh_token, expires_at}}"
    )
    last_activity: datetime
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None
    preferences: Optional[dict] = None


class SessionResponse(BaseModel):
    """Session creation response."""
    
    session_id: str
    user_id: str
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int
    user_email: str
    user_timezone: str


# ============================================================================
# WEBSOCKET AUTH
# ============================================================================

class WebSocketAuthPayload(BaseModel):
    """WebSocket authentication payload."""
    
    sub: str  # user_id
    session_id: str
    iat: datetime
    exp: datetime
    websocket_session_id: str = Field(
        default_factory=lambda: str(uuid.uuid4()),
        description="Unique ID for this WebSocket session"
    )


class WebSocketConnectionRequest(BaseModel):
    """Initial WebSocket connection with token."""
    
    token: str = Field(..., description="JWT token")
    client_id: Optional[str] = Field(None, description="Optional client identifier")


# ============================================================================
# APPROVAL TOKEN (TIME-LIMITED APPROVAL USE)
# ============================================================================

class ApprovalToken(BaseModel):
    """Time-limited token for executing approved action (headless)."""
    
    sub: str  # user_id
    approval_id: str
    action_type: str
    iat: datetime
    exp: datetime


class ApprovalTokenRequest(BaseModel):
    """Request to create approval token for API execution."""
    
    approval_id: str
    duration_seconds: int = Field(
        default=900,
        ge=60,
        le=3600,
        description="Token validity (15 min default)"
    )


# ============================================================================
# OAUTH MANAGER
# ============================================================================

class OAuthManager:
    """Handles OAuth flows and token management."""
    
    # For MVP, using placeholder. In production, use google-auth library.
    GOOGLE_OAUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"
    GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
    GOOGLE_USERINFO_ENDPOINT = "https://openidconnect.googleapis.com/v1/userinfo"
    
    @staticmethod
    def get_oauth_authorization_url(
        provider: str,
        state: str,
    ) -> str:
        """
        Generate OAuth authorization URL.
        
        Args:
            provider: "google" or "github"
            state: CSRF protection state
        
        Returns:
            Redirect URL for user authorization
        """
        if provider == "google":
            params = {
                "client_id": settings.google_oauth_client_id,
                "redirect_uri": settings.google_oauth_redirect_uri,
                "response_type": "code",
                "scope": "openid email profile https://www.googleapis.com/auth/gmail.readonly https://www.googleapis.com/auth/calendar",
                "state": state,
                "access_type": "offline",
                "prompt": "consent",
            }
            from urllib.parse import urlencode
            return f"{OAuthManager.GOOGLE_OAUTH_ENDPOINT}?{urlencode(params)}"
        
        raise ValueError(f"Unsupported provider: {provider}")
    
    @staticmethod
    async def exchange_code_for_tokens(
        provider: str,
        code: str,
        redirect_uri: str,
    ) -> GoogleOAuthTokens:
        """
        Exchange authorization code for access tokens.
        
        In production, implement actual OAuth token exchange.
        For now, this is a placeholder that would call Google API.
        
        Args:
            provider: "google"
            code: Authorization code from provider
            redirect_uri: Must match original redirect_uri
        
        Returns:
            OAuth tokens
        """
        # TODO: Implement actual HTTP request to token endpoint
        # For MVP, return mock tokens
        
        raise NotImplementedError("Implement OAuth token exchange")
    
    @staticmethod
    async def get_user_info(
        provider: str,
        access_token: str,
    ) -> OAuthUserInfo:
        """
        Retrieve user info from OAuth provider.
        
        Args:
            provider: "google"
            access_token: OAuth access token
        
        Returns:
            User info from provider
        """
        # TODO: Implement actual HTTP request to userinfo endpoint
        
        raise NotImplementedError("Implement user info retrieval")


# ============================================================================
# SESSION MANAGER
# ============================================================================

class SessionManager:
    """Session storage and retrieval (Redis-backed in production)."""
    
    # In production, use Redis client. For MVP, in-memory store.
    _sessions: dict = {}
    
    @staticmethod
    def create_session(
        user_id: str,
        email: str,
        timezone: str,
        ip_address: Optional[str] = None,
        user_agent: Optional[str] = None,
        preferences: Optional[dict] = None,
    ) -> SessionData:
        """
        Create new user session.
        
        Args:
            user_id: User UUID
            email: User email
            timezone: User timezone
            ip_address: Client IP
            user_agent: Client user agent
            preferences: User preferences
        
        Returns:
            Session object
        """
        session_id = str(uuid.uuid4())
        session = SessionData(
            user_id=user_id,
            session_id=session_id,
            email=email,
            timezone=timezone,
            ip_address=ip_address,
            user_agent=user_agent,
            preferences=preferences,
            last_activity=datetime.now(timezone.utc),
        )
        
        # Store in Redis (MVP: in-memory)
        SessionManager._sessions[session_id] = session.model_dump()
        
        return session
    
    @staticmethod
    def get_session(session_id: str) -> Optional[SessionData]:
        """
        Retrieve session by ID.
        
        Args:
            session_id: Session UUID
        
        Returns:
            Session data or None
        """
        data = SessionManager._sessions.get(session_id)
        return SessionData(**data) if data else None
    
    @staticmethod
    def update_session_activity(session_id: str) -> None:
        """
        Update session's last_activity timestamp.
        
        Args:
            session_id: Session UUID
        """
        if session_id in SessionManager._sessions:
            SessionManager._sessions[session_id]["last_activity"] = \
                datetime.now(timezone.utc).isoformat()
    
    @staticmethod
    def invalidate_session(session_id: str) -> None:
        """
        Invalidate/revoke session.
        
        Args:
            session_id: Session UUID
        """
        if session_id in SessionManager._sessions:
            del SessionManager._sessions[session_id]
    
    @staticmethod
    def store_oauth_tokens(
        session_id: str,
        provider: str,
        tokens: GoogleOAuthTokens,
    ) -> None:
        """
        Store OAuth tokens for a session (encrypted in production).
        
        Args:
            session_id: Session UUID
            provider: OAuth provider
            tokens: OAuth tokens
        """
        if session_id not in SessionManager._sessions:
            raise ValueError("Session not found")
        
        if "oauth_tokens" not in SessionManager._sessions[session_id]:
            SessionManager._sessions[session_id]["oauth_tokens"] = {}
        
        SessionManager._sessions[session_id]["oauth_tokens"][provider] = {
            "access_token": tokens.access_token,
            "refresh_token": tokens.refresh_token,
            "expires_at": (
                datetime.now(timezone.utc) + timedelta(seconds=tokens.expires_in)
            ).isoformat(),
            "scopes": tokens.scope.split(),
        }
    
    @staticmethod
    def get_oauth_tokens(
        session_id: str,
        provider: str,
    ) -> Optional[OAuthToken]:
        """
        Retrieve OAuth tokens for a session.
        
        Args:
            session_id: Session UUID
            provider: OAuth provider
        
        Returns:
            OAuth token or None
        """
        if session_id not in SessionManager._sessions:
            return None
        
        tokens_data = SessionManager._sessions[session_id].get("oauth_tokens", {})
        token_data = tokens_data.get(provider)
        
        if not token_data:
            return None
        
        return OAuthToken(
            provider=provider,
            access_token=token_data["access_token"],
            refresh_token=token_data.get("refresh_token"),
            expires_at=datetime.fromisoformat(token_data["expires_at"]),
            scopes=token_data.get("scopes", []),
        )


# ============================================================================
# WEBSOCKET AUTHENTICATION
# ============================================================================

class WebSocketAuthManager:
    """WebSocket-specific authentication."""
    
    @staticmethod
    def create_websocket_token(
        user_id: str,
        session_id: str,
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        """
        Create WebSocket authentication token.
        
        Args:
            user_id: User UUID
            session_id: Session UUID
            expires_delta: Token lifetime (default: same as JWT)
        
        Returns:
            JWT token for WebSocket auth
        """
        if expires_delta is None:
            expires_delta = timedelta(hours=settings.jwt_expiration_hours)
        
        now = datetime.now(timezone.utc)
        expires = now + expires_delta
        
        payload = {
            "sub": user_id,
            "session_id": session_id,
            "websocket_session_id": str(uuid.uuid4()),
            "iat": now.isoformat(),
            "exp": expires.isoformat(),
            "type": "websocket",
        }
        
        token = jwt.encode(
            payload,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        
        return token
    
    @staticmethod
    def verify_websocket_token(token: str) -> WebSocketAuthPayload:
        """
        Verify WebSocket authentication token.
        
        Args:
            token: JWT token
        
        Returns:
            Decoded payload
        """
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm],
            )
            
            if payload.get("type") != "websocket":
                raise ValueError("Not a WebSocket token")
            
            return WebSocketAuthPayload(
                sub=payload["sub"],
                session_id=payload["session_id"],
                websocket_session_id=payload["websocket_session_id"],
                iat=datetime.fromisoformat(payload["iat"]),
                exp=datetime.fromisoformat(payload["exp"]),
            )
        
        except jwt.ExpiredSignatureError:
            raise ValueError("WebSocket token expired")
        except jwt.JWTError as e:
            raise ValueError(f"Invalid WebSocket token: {e}")


# ============================================================================
# APPROVAL TOKEN MANAGER
# ============================================================================

class ApprovalTokenManager:
    """Manage short-lived approval execution tokens."""
    
    @staticmethod
    def create_approval_token(
        user_id: str,
        approval_id: str,
        action_type: str,
        duration_seconds: int = 900,
    ) -> str:
        """
        Create time-limited approval token for API execution.
        
        Args:
            user_id: User UUID
            approval_id: Approval record UUID
            action_type: Action being approved
            duration_seconds: Token lifetime (default: 15 min)
        
        Returns:
            JWT token
        """
        now = datetime.now(timezone.utc)
        expires = now + timedelta(seconds=duration_seconds)
        
        payload = {
            "sub": user_id,
            "approval_id": approval_id,
            "action_type": action_type,
            "iat": now.isoformat(),
            "exp": expires.isoformat(),
            "type": "approval",
        }
        
        token = jwt.encode(
            payload,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        
        return token
    
    @staticmethod
    def verify_approval_token(token: str) -> ApprovalToken:
        """
        Verify approval token and extract approval details.
        
        Args:
            token: JWT token
        
        Returns:
            Decoded approval payload
        """
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm],
            )
            
            if payload.get("type") != "approval":
                raise ValueError("Not an approval token")
            
            return ApprovalToken(
                sub=payload["sub"],
                approval_id=payload["approval_id"],
                action_type=payload["action_type"],
                iat=datetime.fromisoformat(payload["iat"]),
                exp=datetime.fromisoformat(payload["exp"]),
            )
        
        except jwt.ExpiredSignatureError:
            raise ValueError("Approval token expired")
        except jwt.JWTError as e:
            raise ValueError(f"Invalid approval token: {e}")


# ============================================================================
# COMPLETE AUTH FLOW EXAMPLE
# ============================================================================

"""
COMPLETE OAUTH + SESSION + WEBSOCKET AUTH FLOW:

1. Frontend redirects to: GET /auth/google/login
   Backend generates state, redirects to Google OAuth consent screen
   
2. Google redirects back to: GET /auth/google/callback?code=AUTH_CODE&state=STATE
   Backend:
   - Validates state (CSRF protection)
   - Exchanges code for Google tokens via OAuthManager.exchange_code_for_tokens()
   - Retrieves user info via OAuthManager.get_user_info()
   - Creates/updates User in DB
   - Creates session via SessionManager.create_session()
   - Stores Google tokens in session via SessionManager.store_oauth_tokens()
   - Creates JWT via JWTManager.create_access_token()
   - Creates refresh token via JWTManager.create_refresh_token()
   - Returns SessionResponse with tokens
   
3. Frontend stores tokens:
   - Access token: httpOnly cookie + memory
   - Refresh token: httpOnly cookie
   
4. Frontend connects WebSocket: GET /ws?token=ACCESS_TOKEN
   Backend:
   - Extracts token from query param
   - Verifies via JWTManager.verify_token()
   - Creates WebSocket-scoped token via WebSocketAuthManager.create_websocket_token()
   - Establishes WebSocket connection
   - Sends session:authenticated event
   
5. Frontend makes API requests:
   - Sends JWT in Authorization header
   - Server verifies via JWTManager.verify_token()
   
6. Token refresh on expiry:
   Frontend detects 401, sends refresh_token via POST /auth/refresh
   Backend:
   - Verifies refresh_token
   - Issues new access_token
   - Frontend retries original request
   
7. Approval token for headless execution:
   Frontend: POST /approvals/{id}/decide with user's decision
   Backend creates approval token via ApprovalTokenManager.create_approval_token()
   Returns token + execution URL
   Frontend/external service uses token to execute action
   
8. WebSocket heartbeat (30s):
   Client sends: {"type": "session:heartbeat", "sequence": N}
   Server responds with ack
   Detects connection loss on timeout
   
9. Logout:
   Frontend: POST /auth/logout
   Backend:
   - Revokes access token via JWTManager.revoke_token()
   - Invalidates session via SessionManager.invalidate_session()
   - Returns 200 OK
   Frontend clears stored tokens
"""
