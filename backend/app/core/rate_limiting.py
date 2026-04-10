"""Rate limiting middleware using Redis."""

import logging
from datetime import datetime
from fastapi import Request, HTTPException, status
from app.cache.config import get_redis
from app.core.config import settings

logger = logging.getLogger(__name__)


class RateLimiter:
    """Rate limiter using Redis for distributed rate limiting."""
    
    # Default rate limits (requests per minute)
    DEFAULT_LIMITS = {
        "/api/v1/chat": 10,
        "/api/v1/auth/refresh": 5,
        "default": 100,
    }
    
    @staticmethod
    def get_limit_for_path(path: str) -> int:
        """Get rate limit for a given path."""
        for route, limit in RateLimiter.DEFAULT_LIMITS.items():
            if path.startswith(route):
                return limit
        return RateLimiter.DEFAULT_LIMITS["default"]
    
    @staticmethod
    def get_client_identifier(request: Request) -> str:
        """Get unique identifier for client (user_id or IP)."""
        # Prefer authenticated user_id from JWT
        if hasattr(request.state, "user_id"):
            return f"user:{request.state.user_id}"
        
        # Fall back to IP address
        client_ip = request.client.host if request.client else "unknown"
        return f"ip:{client_ip}"
    
    @staticmethod
    async def check_rate_limit(request: Request) -> bool:
        """
        Check if request is within rate limit.
        
        Returns True if allowed, False if rate limited.
        
        Uses sliding window approach:
        - Key: f"ratelimit:{identifier}:{path}"
        - Value: last N request timestamps
        """
        redis_client = get_redis()
        identifier = RateLimiter.get_client_identifier(request)
        path = request.url.path
        limit = RateLimiter.get_limit_for_path(path)
        
        limit_key = f"ratelimit:{identifier}:{path}"
        current_time = datetime.utcnow().timestamp()
        window_start = current_time - 60  # 1 minute window
        
        try:
            # Get all request times in the window
            request_times = redis_client.zrange(limit_key, 0, -1, byscore=(window_start, current_time))

            # Check if limit exceeded
            if len(request_times) >= limit:
                logger.warning(
                    f"Rate limit exceeded",
                    extra={
                        "identifier": identifier,
                        "path": path,
                        "limit": limit,
                        "requests_in_window": len(request_times),
                    },
                )
                return False

            # Add current request to window
            redis_client.zadd(limit_key, {str(current_time): current_time})

            # Set expiry to 2 minutes (cleanup after window passes)
            redis_client.expire(limit_key, 120)

            return True
        except Exception as exc:
            logger.warning(
                "rate_limit.redis_unavailable",
                extra={"path": path, "identifier": identifier, "error": str(exc)},
            )
            # Fail-open to keep API available when cache is degraded.
            return True


async def rate_limit_middleware(request: Request, call_next):
    """
    Middleware to enforce rate limiting.
    
    Returns 429 Too Many Requests if limit exceeded.
    """
    # Skip rate limiting for certain paths
    skip_paths = ["/health", "/openapi", "/docs", "/redoc", "/swagger"]
    if any(request.url.path.startswith(path) for path in skip_paths):
        return await call_next(request)
    
    # Check rate limit
    allowed = await RateLimiter.check_rate_limit(request)
    
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Rate limit exceeded. Please try again later.",
        )
    
    return await call_next(request)
