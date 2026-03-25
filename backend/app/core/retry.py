"""Retry utilities with exponential backoff and optional jitter."""

from __future__ import annotations

import asyncio
import random
import time
from typing import Awaitable, Callable, Iterable, TypeVar


T = TypeVar("T")


class RetryExhaustedError(Exception):
    """Raised when retry attempts are exhausted."""


def _compute_delay(base_delay: float, backoff_factor: float, attempt: int, jitter: bool) -> float:
    delay = base_delay * (backoff_factor ** (attempt - 1))
    if jitter:
        delay *= random.uniform(0.85, 1.15)
    return delay


def retry_sync(
    operation: Callable[[], T],
    exceptions: Iterable[type[Exception]],
    max_attempts: int = 3,
    base_delay: float = 0.3,
    backoff_factor: float = 2.0,
    jitter: bool = True,
) -> tuple[T, int]:
    """Execute a sync operation with retries and return result with attempt count."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    last_error: Exception | None = None
    retry_exceptions = tuple(exceptions)

    for attempt in range(1, max_attempts + 1):
        try:
            return operation(), attempt
        except retry_exceptions as exc:
            last_error = exc
            if attempt == max_attempts:
                break
            time.sleep(_compute_delay(base_delay, backoff_factor, attempt, jitter))

    raise RetryExhaustedError(str(last_error)) from last_error


async def retry_async(
    operation: Callable[[], Awaitable[T]],
    exceptions: Iterable[type[Exception]],
    max_attempts: int = 3,
    base_delay: float = 0.3,
    backoff_factor: float = 2.0,
    jitter: bool = True,
) -> tuple[T, int]:
    """Execute an async operation with retries and return result with attempt count."""
    if max_attempts < 1:
        raise ValueError("max_attempts must be >= 1")

    last_error: Exception | None = None
    retry_exceptions = tuple(exceptions)

    for attempt in range(1, max_attempts + 1):
        try:
            return await operation(), attempt
        except retry_exceptions as exc:
            last_error = exc
            if attempt == max_attempts:
                break
            await asyncio.sleep(_compute_delay(base_delay, backoff_factor, attempt, jitter))

    raise RetryExhaustedError(str(last_error)) from last_error
