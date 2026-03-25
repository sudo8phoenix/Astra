"""
Authentication & Authorization Module

Implements JWT token management and OAuth 2.0 flows for Google and GitHub.
"""

from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from app.core.config import settings

# ============================================================================
# TOKEN MODELS
# ============================================================================


class TokenPayload(BaseModel):
    """JWT token payload structure."""
    
    sub: str  # Subject (user ID)
    email: str
    scopes: list[str] = []
    exp: datetime
    iat: datetime
    jti: Optional[str] = None  # JWT ID for token revocation


class TokenResponse(BaseModel):
    """Token response structure."""
    
    access_token: str
    refresh_token: Optional[str] = None
    token_type: str = "bearer"
    expires_in: int
    user_id: str


class TokenBlacklist:
    """
    In-memory token blacklist for revocation.
    In production, use Redis for distributed token blacklist.
    """
    
    _blacklist: set[str] = set()
    
    @classmethod
    def add(cls, jti: str) -> None:
        """Add token JTI to blacklist."""
        cls._blacklist.add(jti)
    
    @classmethod
    def is_blacklisted(cls, jti: str) -> bool:
        """Check if token is blacklisted."""
        return jti in cls._blacklist
    
    @classmethod
    def clear(cls) -> None:
        """Clear blacklist (for testing)."""
        cls._blacklist.clear()


# ============================================================================
# JWT TOKEN MANAGEMENT
# ============================================================================


class JWTManager:
    """JWT token creation, validation, and management."""
    
    @staticmethod
    def create_access_token(
        user_id: str,
        email: str,
        scopes: list[str] | None = None,
        expires_delta: Optional[timedelta] = None,
    ) -> str:
        """
        Create JWT access token.
        
        Args:
            user_id: User identifier
            email: User email
            scopes: List of permission scopes
            expires_delta: Custom expiration time delta
        
        Returns:
            Encoded JWT token
        """
        if expires_delta is None:
            expires_delta = timedelta(hours=settings.jwt_expiration_hours)
        
        now = datetime.now(timezone.utc)
        expires = now + expires_delta

        # PyJWT validates iat/exp as NumericDate values (unix timestamps).
        payload = {
            "sub": user_id,
            "email": email,
            "scopes": scopes or [],
            "iat": int(now.timestamp()),
            "exp": int(expires.timestamp()),
            "jti": f"{user_id}_{now.timestamp()}",
        }
        
        encoded_jwt = jwt.encode(
            payload,
            settings.jwt_secret_key,
            algorithm=settings.jwt_algorithm,
        )
        
        return encoded_jwt
    
    @staticmethod
    def create_refresh_token(
        user_id: str,
        email: str,
    ) -> str:
        """
        Create JWT refresh token (longer expiration).
        
        Args:
            user_id: User identifier
            email: User email
        
        Returns:
            Encoded JWT token
        """
        expires_delta = timedelta(days=settings.jwt_refresh_expiration_days)
        
        return JWTManager.create_access_token(
            user_id=user_id,
            email=email,
            scopes=["refresh"],
            expires_delta=expires_delta,
        )
    
    @staticmethod
    def verify_token(token: str) -> TokenPayload:
        """
        Verify and decode JWT token.
        
        Args:
            token: JWT token string
        
        Returns:
            Decoded token payload
        
        Raises:
            HTTPException: If token is invalid or expired
        """
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm],
            )
            
            # Check if token is blacklisted
            jti = payload.get("jti")
            if jti and TokenBlacklist.is_blacklisted(jti):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Token has been revoked",
                )
            
            return TokenPayload(**payload)
        
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Token has expired",
            )
        except jwt.PyJWTError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token",
            )
    
    @staticmethod
    def revoke_token(token: str) -> None:
        """
        Revoke a token by adding it to blacklist.
        
        Args:
            token: JWT token string
        """
        try:
            payload = jwt.decode(
                token,
                settings.jwt_secret_key,
                algorithms=[settings.jwt_algorithm],
            )
            jti = payload.get("jti")
            if jti:
                TokenBlacklist.add(jti)
        except jwt.PyJWTError:
            pass  # Ignore invalid tokens during revocation


# ============================================================================
# DEPENDENCY INJECTION
# ============================================================================

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> TokenPayload:
    """
    Dependency for protected routes - validates JWT token.
    
    Usage:
        @router.get("/protected")
        async def protected_route(current_user: TokenPayload = Depends(get_current_user)):
            return {"user_id": current_user.sub}
    """
    return JWTManager.verify_token(credentials.credentials)


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[TokenPayload]:
    """
    Optional authentication dependency.
    Returns None if token is not provided or invalid.
    """
    if credentials is None:
        return None
    
    try:
        return JWTManager.verify_token(credentials.credentials)
    except HTTPException:
        return None


# ============================================================================
# OAUTH 2.0 FLOWS
# ============================================================================


class OAuth2Manager:
    """
    OAuth 2.0 authentication flow manager.
    Supports Google and GitHub.
    """
    
    @staticmethod
    def get_google_auth_url(state: str) -> str:
        """Generate Google OAuth authorization URL."""
        params = {
            "client_id": settings.google_oauth_client_id,
            "redirect_uri": settings.google_oauth_redirect_uri,
            "response_type": "code",
            "scope": "openid profile email",
            "state": state,
            "access_type": "offline",
        }
        
        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        return f"https://accounts.google.com/o/oauth2/v2/auth?{query_string}"
    
    @staticmethod
    def get_github_auth_url(state: str) -> str:
        """Generate GitHub OAuth authorization URL."""
        params = {
            "client_id": settings.github_oauth_client_id,
            "redirect_uri": settings.github_oauth_redirect_uri,
            "scope": "user:email",
            "state": state,
            "allow_signup": "true",
        }
        
        query_string = "&".join(f"{k}={v}" for k, v in params.items())
        return f"https://github.com/login/oauth/authorize?{query_string}"


# ============================================================================
# SECURITY UTILITIES
# ============================================================================


def create_authorization_header(token: str) -> dict[str, str]:
    """Create HTTP Authorization header for bearer token."""
    return {"Authorization": f"Bearer {token}"}
