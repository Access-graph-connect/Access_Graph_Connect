import pytest

from app.connectors.errors import AuthError, RateLimitError
from app.sync.retry import RetryPolicy, run_with_retry


def _no_sleep(_: float) -> None:
    pass


def test_succeeds_first_try() -> None:
    calls = []
    result = run_with_retry(lambda: calls.append(1) or "ok", sleep=_no_sleep)
    assert result == "ok"
    assert len(calls) == 1


def test_retries_rate_limit_then_succeeds() -> None:
    attempts = []

    def flaky():
        attempts.append(1)
        if len(attempts) < 3:
            raise RateLimitError("limited", retry_after=0)
        return "ok"

    result = run_with_retry(flaky, sleep=_no_sleep)
    assert result == "ok"
    assert len(attempts) == 3


def test_rate_limit_respects_retry_after() -> None:
    delays = []

    def limited():
        raise RateLimitError("limited", retry_after=5.0)

    policy = RetryPolicy(max_attempts=2)
    with pytest.raises(RateLimitError):
        run_with_retry(limited, policy=policy, sleep=delays.append)
    assert delays == [5.0]


def test_bounded_retries_never_tight_loop() -> None:
    attempts = []

    def always_limited():
        attempts.append(1)
        raise RateLimitError("limited", retry_after=0)

    policy = RetryPolicy(max_attempts=4)
    with pytest.raises(RateLimitError):
        run_with_retry(always_limited, policy=policy, sleep=_no_sleep)
    # Exactly max_attempts, then gives up — no infinite loop.
    assert len(attempts) == 4


def test_auth_error_not_retried() -> None:
    attempts = []

    def unauthorized():
        attempts.append(1)
        raise AuthError("revoked")

    with pytest.raises(AuthError):
        run_with_retry(unauthorized, sleep=_no_sleep)
    assert len(attempts) == 1


def test_backoff_is_bounded() -> None:
    policy = RetryPolicy(max_attempts=10, base_delay_seconds=1.0, max_delay_seconds=30.0)
    from app.sync.retry import _backoff

    for attempt in range(10):
        assert _backoff(policy, attempt) <= 30.0
