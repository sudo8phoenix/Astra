"""Redis cache configuration and connection."""

import json
import logging
import time
from typing import Any, Optional

import redis
from pydantic_settings import BaseSettings, SettingsConfigDict


logger = logging.getLogger(__name__)


class RedisSettings(BaseSettings):
    """Redis connection configuration from environment variables."""

    model_config = SettingsConfigDict(
        env_prefix="REDIS_",
        env_file=(".env", "../.env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    url: Optional[str] = None
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    ssl: bool = False

    @property
    def redis_url(self) -> str:
        """Construct Redis connection URL."""
        if self.url:
            return self.url
        auth = f":{self.password}@" if self.password else ""
        protocol = "rediss" if self.ssl else "redis"
        return f"{protocol}://{auth}{self.host}:{self.port}/{self.db}"


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

_REDIS_HEALTHCHECK_INTERVAL_SECONDS = 15
_REDIS_RETRY_ATTEMPTS = 2
_REDIS_RETRY_BACKOFF_SECONDS = 0.2
_redis_last_healthcheck = 0.0
_redis_available = True
_redis_last_degraded_log = 0.0


class _NullPubSub:
    """No-op Redis pub/sub used when Redis is unavailable."""

    def subscribe(self, *_channels):
        return None

    def get_message(self, *_args, **_kwargs):
        return None

    def unsubscribe(self, *_channels):
        return None

    def close(self):
        return None


class _NullRedis:
    """No-op Redis client used for graceful degradation."""

    def ping(self):
        return False

    def get(self, *_args, **_kwargs):
        return None

    def setex(self, *_args, **_kwargs):
        return False

    def publish(self, *_args, **_kwargs):
        return 0

    def zrange(self, *_args, **_kwargs):
        return []

    def zadd(self, *_args, **_kwargs):
        return 0

    def expire(self, *_args, **_kwargs):
        return False

    def delete(self, *_args, **_kwargs):
        return 0

    def exists(self, *_args, **_kwargs):
        return 0

    def incrby(self, *_args, **_kwargs):
        return 0

    def decrby(self, *_args, **_kwargs):
        return 0

    def pubsub(self):
        return _NullPubSub()


_null_redis_client = _NullRedis()


def _refresh_redis_health() -> bool:
    """Refresh cached Redis health using bounded retries."""
    global _redis_last_healthcheck, _redis_available

    now = time.time()
    if now - _redis_last_healthcheck < _REDIS_HEALTHCHECK_INTERVAL_SECONDS:
        return _redis_available

    available = False
    for attempt in range(1, _REDIS_RETRY_ATTEMPTS + 1):
        try:
            available = bool(redis_client.ping())
            if available:
                break
        except Exception as exc:
            logger.warning(
                "redis.healthcheck.failed",
                extra={"attempt": attempt, "error": str(exc)},
            )
            if attempt < _REDIS_RETRY_ATTEMPTS:
                time.sleep(_REDIS_RETRY_BACKOFF_SECONDS)

    _redis_available = available
    _redis_last_healthcheck = now
    return _redis_available


def get_redis() -> Any:
    """Get Redis client instance with graceful fallback when unavailable."""
    global _redis_last_degraded_log

    if _refresh_redis_health():
        return redis_client

    now = time.time()
    if now - _redis_last_degraded_log >= _REDIS_HEALTHCHECK_INTERVAL_SECONDS:
        logger.warning(
            "redis.degraded_mode.enabled",
            extra={"mode": "null_redis", "reason": "healthcheck_failed"},
        )
        _redis_last_degraded_log = now

    return _null_redis_client


async def ping_redis() -> bool:
    """Test Redis connection."""
    try:
        result = get_redis().ping()
        return bool(result)
    except Exception as e:
        logger.warning("redis.ping.failed", extra={"error": str(e)})
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
