"""Connector error classification.

Sync and credential handling (Phases 3 and 5) branch on these categories:
auth failures distinguish revocation from transient 401/403, and rate
limits carry Retry-After so retries stay bounded.
"""


class ConnectorError(RuntimeError):
    """Unclassified connector failure."""


class AuthError(ConnectorError):
    """401/403 from the provider: token missing, revoked, or forbidden."""


class RateLimitError(ConnectorError):
    def __init__(self, message: str, retry_after: float | None = None) -> None:
        super().__init__(message)
        self.retry_after = retry_after


class ProviderDataError(ConnectorError):
    """The provider response could not be interpreted."""
