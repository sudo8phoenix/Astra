"""Calendar OAuth token management utilities."""

import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)


class CalendarOAuthManager:
    """Manages Google Calendar OAuth tokens for users."""

    @staticmethod
    def store_calendar_tokens(
        user_preferences: Dict[str, Any],
        access_token: str,
        refresh_token: Optional[str] = None,
        expires_in: int = 3600,
    ) -> Dict[str, Any]:
        """
        Store Google Calendar OAuth tokens in user preferences.

        Args:
            user_preferences: User's preferences dict
            access_token: Google OAuth access token
            refresh_token: Google OAuth refresh token
            expires_in: Token expiry time in seconds

        Returns:
            Updated preferences dict
        """
        if user_preferences is None:
            user_preferences = {}

        calendar_oauth_tokens = {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "expires_at": (
                datetime.utcnow() + timedelta(seconds=expires_in)
            ).isoformat(),
            "created_at": datetime.utcnow().isoformat(),
        }

        user_preferences["calendar_oauth_tokens"] = calendar_oauth_tokens
        logger.info("Stored Calendar OAuth tokens")

        return user_preferences

    @staticmethod
    def get_calendar_access_token(
        user_preferences: Dict[str, Any],
    ) -> Optional[str]:
        """
        Retrieve valid Google Calendar access token from user preferences.

        Args:
            user_preferences: User's preferences dict

        Returns:
            Valid access token or None
        """
        if not user_preferences:
            return None

        calendar_tokens = user_preferences.get("calendar_oauth_tokens")
        if not calendar_tokens:
            return None

        access_token = calendar_tokens.get("access_token")

        # Check if token is expired
        expires_at_str = calendar_tokens.get("expires_at")
        if expires_at_str:
            expires_at = datetime.fromisoformat(expires_at_str)
            if datetime.utcnow() >= expires_at:
                logger.warning("Calendar access token has expired")
                return None

        return access_token

    @staticmethod
    def get_calendar_refresh_token(
        user_preferences: Dict[str, Any],
    ) -> Optional[str]:
        """
        Retrieve Google Calendar refresh token from user preferences.

        Args:
            user_preferences: User's preferences dict

        Returns:
            Refresh token or None
        """
        if not user_preferences:
            return None

        calendar_tokens = user_preferences.get("calendar_oauth_tokens")
        if not calendar_tokens:
            return None

        return calendar_tokens.get("refresh_token")

    @staticmethod
    def is_calendar_oauth_connected(user_preferences: Dict[str, Any]) -> bool:
        """
        Check if user has connected Google Calendar OAuth.

        Args:
            user_preferences: User's preferences dict

        Returns:
            True if Calendar OAuth is connected and valid
        """
        access_token = CalendarOAuthManager.get_calendar_access_token(
            user_preferences
        )
        return access_token is not None

    @staticmethod
    def update_calendar_access_token(
        user_preferences: Dict[str, Any],
        access_token: str,
        expires_in: int = 3600,
    ) -> Dict[str, Any]:
        """
        Update the access token after refresh.

        Args:
            user_preferences: User's preferences dict
            access_token: New access token
            expires_in: Token expiry time in seconds

        Returns:
            Updated preferences dict
        """
        if user_preferences is None:
            user_preferences = {}

        if "calendar_oauth_tokens" not in user_preferences:
            user_preferences["calendar_oauth_tokens"] = {}

        user_preferences["calendar_oauth_tokens"]["access_token"] = access_token
        user_preferences["calendar_oauth_tokens"]["expires_at"] = (
            datetime.utcnow() + timedelta(seconds=expires_in)
        ).isoformat()

        logger.info("Updated Calendar access token")
        return user_preferences

    @staticmethod
    def disconnect_calendar_oauth(user_preferences: Dict[str, Any]) -> Dict[str, Any]:
        """
        Remove Google Calendar OAuth tokens from user preferences.

        Args:
            user_preferences: User's preferences dict

        Returns:
            Updated preferences dict
        """
        if user_preferences is not None:
            user_preferences.pop("calendar_oauth_tokens", None)
            logger.info("Disconnected Calendar OAuth")

        return user_preferences
