"""Bounded retry with exponential backoff and Retry-After support.

A provider rate limit (429 / exhausted quota) or transient error retries a
bounded number of times with exponential backoff — never a tight loop.
`Retry-After` from the provider takes precedence over computed backoff.
"""

import random
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import TypeVar

from app.connectors.errors import AuthError, RateLimitError

T = TypeVar("T")


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 4
    base_delay_seconds: float = 1.0
    max_delay_seconds: float = 30.0
    # Full jitter avoids thundering-herd when many connections retry together.
    jitter: bool = True


def _backoff(policy: RetryPolicy, attempt: int) -> float:
    delay = min(policy.base_delay_seconds * (2 ** attempt), policy.max_delay_seconds)
    return random.uniform(0, delay) if policy.jitter else delay


def run_with_retry(
    fn: Callable[[], T],
    policy: RetryPolicy | None = None,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Run `fn`, retrying transient/rate-limit errors within the budget.

    Auth errors are not retried (they need reconnection, not backoff).
    """
    policy = policy or RetryPolicy()
    last_exc: Exception | None = None
    for attempt in range(policy.max_attempts):
        try:
            return fn()
        except AuthError:
            raise
        except RateLimitError as exc:
            last_exc = exc
            if attempt == policy.max_attempts - 1:
                break
            delay = (
                exc.retry_after
                if exc.retry_after is not None
                else _backoff(policy, attempt)
            )
            sleep(min(delay, policy.max_delay_seconds))
        except Exception as exc:  # transient network/provider errors
            last_exc = exc
            if attempt == policy.max_attempts - 1:
                break
            sleep(_backoff(policy, attempt))
    assert last_exc is not None
    raise last_exc
