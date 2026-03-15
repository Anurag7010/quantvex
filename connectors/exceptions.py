"""Shared exceptions for data connectors."""


class RateLimitError(Exception):
    """Raised when an upstream data provider rate-limits the request."""
