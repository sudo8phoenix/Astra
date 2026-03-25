"""LLM token/cost monitoring with threshold checks."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict

from app.cache.config import CacheManager, RedisKeyBuilder, get_redis
from app.core.config import settings
from app.core.metrics import metrics_collector

logger = logging.getLogger(__name__)


class LLMUsageMonitor:
    """Tracks per-user daily LLM usage and raises alerts on thresholds."""

    _in_memory_daily: Dict[str, Dict[str, float]] = {}

    def __init__(self) -> None:
        self.cache = CacheManager(get_redis())

    def _date_key(self) -> str:
        return datetime.utcnow().strftime("%Y-%m-%d")

    def _redis_key(self, user_id: str) -> str:
        return RedisKeyBuilder.user_daily_stats(user_id, self._date_key())

    def _load_daily(self, user_id: str) -> Dict[str, float]:
        cache_key = self._redis_key(user_id)
        cached = self.cache.get(cache_key)
        if isinstance(cached, dict):
            return {
                "tokens": float(cached.get("tokens", 0)),
                "cost_usd": float(cached.get("cost_usd", 0.0)),
            }

        mem_key = f"{user_id}:{self._date_key()}"
        if mem_key not in self._in_memory_daily:
            self._in_memory_daily[mem_key] = {"tokens": 0.0, "cost_usd": 0.0}
        return self._in_memory_daily[mem_key]

    def _save_daily(self, user_id: str, data: Dict[str, float]) -> None:
        cache_key = self._redis_key(user_id)
        # Keep daily stats for 2 days to bridge timezone/date boundaries.
        if not self.cache.set(cache_key, data, ttl=172800):
            mem_key = f"{user_id}:{self._date_key()}"
            self._in_memory_daily[mem_key] = data

    def record_usage(
        self,
        user_id: str,
        model: str,
        prompt_tokens: int,
        completion_tokens: int,
        cost_usd: float,
    ) -> Dict[str, float | bool]:
        """Record usage and return updated totals with threshold status."""
        tokens = max(0, int(prompt_tokens) + int(completion_tokens))
        usage = self._load_daily(user_id)

        usage["tokens"] = float(usage["tokens"] + tokens)
        usage["cost_usd"] = float(usage["cost_usd"] + max(cost_usd, 0.0))
        self._save_daily(user_id, usage)

        token_exceeded = usage["tokens"] >= settings.llm_daily_token_limit
        cost_threshold_usd = settings.llm_cost_threshold_cents / 100.0
        cost_exceeded = usage["cost_usd"] >= cost_threshold_usd
        threshold_exceeded = token_exceeded or cost_exceeded

        metrics_collector.record_llm_usage(
            model=model,
            tokens=tokens,
            cost_usd=cost_usd,
            threshold_exceeded=threshold_exceeded,
        )

        if threshold_exceeded:
            logger.warning(
                "LLM usage threshold exceeded",
                extra={
                    "user_id": user_id,
                    "model": model,
                    "daily_tokens": int(usage["tokens"]),
                    "daily_cost_usd": round(usage["cost_usd"], 6),
                    "token_limit": settings.llm_daily_token_limit,
                    "cost_limit_usd": round(cost_threshold_usd, 2),
                },
            )

        return {
            "daily_tokens": int(usage["tokens"]),
            "daily_cost_usd": round(usage["cost_usd"], 6),
            "token_exceeded": token_exceeded,
            "cost_exceeded": cost_exceeded,
            "threshold_exceeded": threshold_exceeded,
        }


llm_usage_monitor = LLMUsageMonitor()
