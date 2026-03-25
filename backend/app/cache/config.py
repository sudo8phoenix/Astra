"""Redis cache configuration and connection."""

import redis
import json
from typing import Any, Optional
from pydantic_settings import BaseSettings
import os


class RedisSettings(BaseSettings):
    """Redis connection configuration from environment variables."""

    REDIS_URL: Optional[str] = os.getenv("REDIS_URL", None)
    REDIS_HOST: str = os.getenv("REDIS_HOST", "localhost")
    REDIS_PORT: int = int(os.getenv("REDIS_PORT", 6379))
    REDIS_DB: int = int(os.getenv("REDIS_DB", 0))
    REDIS_PASSWORD: Optional[str] = os.getenv("REDIS_PASSWORD", None)
    REDIS_SSL: bool = os.getenv("REDIS_SSL", "false").lower() == "true"
    
    class Config:
        env_file = ".env"

    @property
    def redis_url(self) -> str:
        """Construct Redis connection URL."""
        if self.REDIS_URL:
            return self.REDIS_URL
        auth = f":{self.REDIS_PASSWORD}@" if self.REDIS_PASSWORD else ""
        protocol = "rediss" if self.REDIS_SSL else "redis"
        return f"{protocol}://{auth}{self.REDIS_HOST}:{self.REDIS_PORT}/{self.REDIS_DB}"


# Initialize settings
redis_settings = RedisSettings()

# Create Redis connection pool
redis_pool = redis.ConnectionPool.from_url(
    redis_settings.redis_url,
    decode_responses=True,
    socket_connect_timeout=5,
    socket_keepalive=True,
)

# Create Redis client
redis_client = redis.Redis(connection_pool=redis_pool)


def get_redis() -> redis.Redis:
    """Get Redis client instance."""
    return redis_client


async def ping_redis() -> bool:
    """Test Redis connection."""
    try:
        result = redis_client.ping()
        return bool(result)
    except Exception as e:
        print(f"Redis connection failed: {e}")
        return False


class RedisKeyBuilder:
    """Helper class to build consistent Redis key names."""

    # Session keys
    SESSION_PREFIX = "session"
    USER_SESSION = f"{SESSION_PREFIX}:user:{{user_id}}"  # session:user:{user_id} -> stores JWT or session data
    
    # Cache keys
    CACHE_PREFIX = "cache"
    USER_PROFILE = f"{CACHE_PREFIX}:user:{{user_id}}:profile"
    USER_PREFERENCES = f"{CACHE_PREFIX}:user:{{user_id}}:preferences"
    USER_TIMEZONE = f"{CACHE_PREFIX}:user:{{user_id}}:timezone"
    
    # Queue/Work keys
    QUEUE_PREFIX = "queue"
    AGENT_RUN_QUEUE = f"{QUEUE_PREFIX}:agent:runs"  # List of pending agent runs
    APPROVAL_QUEUE = f"{QUEUE_PREFIX}:approvals:pending"  # Set of pending approvals
    
    # Real-time state keys
    STATE_PREFIX = "state"
    AGENT_RUN_STATE = f"{STATE_PREFIX}:agent:run:{{run_id}}"  # Current state of running agent
    USER_ACTIVE_RUN = f"{STATE_PREFIX}:user:{{user_id}}:active_run"  # Currently executing run
    
    # Temporary cache keys
    TEMP_PREFIX = "temp"
    EMAIL_DRAFT = f"{TEMP_PREFIX}:email:draft:{{user_id}}"  # Temporary email draft
    CALENDAR_FREE_SLOTS = f"{TEMP_PREFIX}:calendar:free_slots:{{user_id}}"  # Cached free slots
    INBOX_SUMMARY = f"{TEMP_PREFIX}:inbox:summary:{{user_id}}"  # Cached summary
    
    # Rate limiting keys
    RATELIMIT_PREFIX = "ratelimit"
    API_CALL_COUNT = f"{RATELIMIT_PREFIX}:api:{{user_id}}:calls"  # API call count per minute
    LLM_TOKEN_COUNT = f"{RATELIMIT_PREFIX}:llm:{{user_id}}:tokens"  # Token count per day
    
    # Lock keys for distributed operations
    LOCK_PREFIX = "lock"
    USER_OPERATION_LOCK = f"{LOCK_PREFIX}:user:{{user_id}}"  # Ensure single operation per user
    APPROVAL_LOCK = f"{LOCK_PREFIX}:approval:{{approval_id}}"  # Lock during approval processing
    
    # Statistics and metrics
    METRICS_PREFIX = "metrics"
    USER_DAILY_STATS = f"{METRICS_PREFIX}:user:{{user_id}}:daily:{{date}}"  # Daily stats
    AGENT_RUN_METRICS = f"{METRICS_PREFIX}:agent:run:{{run_id}}"  # Individual run metrics

    @staticmethod
    def user_session(user_id: str) -> str:
        """Generate user session key."""
        return RedisKeyBuilder.USER_SESSION.format(user_id=user_id)

    @staticmethod
    def user_profile(user_id: str) -> str:
        """Generate user profile cache key."""
        return RedisKeyBuilder.USER_PROFILE.format(user_id=user_id)

    @staticmethod
    def user_preferences(user_id: str) -> str:
        """Generate user preferences cache key."""
        return RedisKeyBuilder.USER_PREFERENCES.format(user_id=user_id)

    @staticmethod
    def agent_run_state(run_id: str) -> str:
        """Generate agent run state key."""
        return RedisKeyBuilder.AGENT_RUN_STATE.format(run_id=run_id)

    @staticmethod
    def user_active_run(user_id: str) -> str:
        """Generate active run key for user."""
        return RedisKeyBuilder.USER_ACTIVE_RUN.format(user_id=user_id)

    @staticmethod
    def email_draft(user_id: str) -> str:
        """Generate email draft key."""
        return RedisKeyBuilder.EMAIL_DRAFT.format(user_id=user_id)

    @staticmethod
    def calendar_free_slots(user_id: str) -> str:
        """Generate calendar free slots key."""
        return RedisKeyBuilder.CALENDAR_FREE_SLOTS.format(user_id=user_id)

    @staticmethod
    def inbox_summary(user_id: str) -> str:
        """Generate inbox summary key."""
        return RedisKeyBuilder.INBOX_SUMMARY.format(user_id=user_id)

    @staticmethod
    def api_call_count(user_id: str) -> str:
        """Generate API call count key."""
        return RedisKeyBuilder.API_CALL_COUNT.format(user_id=user_id)

    @staticmethod
    def llm_token_count(user_id: str) -> str:
        """Generate LLM token count key."""
        return RedisKeyBuilder.LLM_TOKEN_COUNT.format(user_id=user_id)

    @staticmethod
    def user_operation_lock(user_id: str) -> str:
        """Generate user operation lock key."""
        return RedisKeyBuilder.USER_OPERATION_LOCK.format(user_id=user_id)

    @staticmethod
    def approval_lock(approval_id: str) -> str:
        """Generate approval lock key."""
        return RedisKeyBuilder.APPROVAL_LOCK.format(approval_id=approval_id)

    @staticmethod
    def user_daily_stats(user_id: str, date: str) -> str:
        """Generate user daily stats key. Date format: YYYY-MM-DD"""
        return RedisKeyBuilder.USER_DAILY_STATS.format(user_id=user_id, date=date)

    @staticmethod
    def agent_run_metrics(run_id: str) -> str:
        """Generate agent run metrics key."""
        return RedisKeyBuilder.AGENT_RUN_METRICS.format(run_id=run_id)


class CacheManager:
    """Helper class for common cache operations."""

    def __init__(self, redis_client: redis.Redis = None):
        """Initialize cache manager with Redis client."""
        self.redis = redis_client or get_redis()

    def set(self, key: str, value: Any, ttl: int = 3600) -> bool:
        """Set a cache value with TTL (default 1 hour).
        
        Args:
            key: Cache key
            value: Value to cache (will be JSON serialized)
            ttl: Time to live in seconds
            
        Returns:
            True if successful
        """
        try:
            json_value = json.dumps(value) if not isinstance(value, str) else value
            self.redis.setex(key, ttl, json_value)
            return True
        except Exception as e:
            print(f"Cache set error for key {key}: {e}")
            return False

    def get(self, key: str, default: Any = None) -> Any:
        """Get a cached value.
        
        Args:
            key: Cache key
            default: Default value if key not found
            
        Returns:
            Cached value (JSON deserialized) or default
        """
        try:
            value = self.redis.get(key)
            if value is None:
                return default
            try:
                return json.loads(value)
            except json.JSONDecodeError:
                return value
        except Exception as e:
            print(f"Cache get error for key {key}: {e}")
            return default

    def delete(self, *keys: str) -> int:
        """Delete one or more cache keys.
        
        Args:
            keys: Keys to delete
            
        Returns:
            Number of keys deleted
        """
        try:
            return self.redis.delete(*keys)
        except Exception as e:
            print(f"Cache delete error: {e}")
            return 0

    def exists(self, key: str) -> bool:
        """Check if key exists in cache."""
        try:
            return bool(self.redis.exists(key))
        except Exception as e:
            print(f"Cache exists error for key {key}: {e}")
            return False

    def incr(self, key: str, amount: int = 1) -> int:
        """Increment a counter value."""
        try:
            return self.redis.incrby(key, amount)
        except Exception as e:
            print(f"Cache incr error for key {key}: {e}")
            return 0

    def decr(self, key: str, amount: int = 1) -> int:
        """Decrement a counter value."""
        try:
            return self.redis.decrby(key, amount)
        except Exception as e:
            print(f"Cache decr error for key {key}: {e}")
            return 0
