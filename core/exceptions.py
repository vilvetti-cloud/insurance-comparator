"""Domain exceptions for the insurance comparator.

Every layer has its own exception class so that callers can catch exactly
what went wrong instead of swallowing generic ``Exception``.
"""

from __future__ import annotations


class InsuranceError(Exception):
    """Base exception for all application errors."""

    def __init__(self, message: str = "", detail: dict | None = None) -> None:
        self.detail = detail or {}
        super().__init__(message or self._default_message())

    def _default_message(self) -> str:
        return f"{self.__class__.__name__}: {', '.join(f'{k}={v!r}' for k, v in self.detail.items())}"


# ------------------------------------------------------------------ #
# Collector layer                                                    #
# ------------------------------------------------------------------ #

class CollectorError(InsuranceError):
    """General collection pipeline failure."""


class CollectionConfigError(CollectorError):
    """Misconfigured insurer registry or source URLs."""


class PDFParseError(CollectorError):
    """Failed to extract text from a PDF document."""


class PDFChecksumMismatch(CollectorError):
    """Document checksum does not match the expected value."""


class LLMRequestError(CollectorError):
    """LLM provider returned an error or timed out."""

    def __init__(self, provider: str, message: str = "", detail: dict | None = None) -> None:
        self.provider = provider
        super().__init__(message, {**({"provider": provider}), **(detail or {})})


class LLMProviderUnavailable(LLMRequestError):
    """No LLM provider responded (all keys invalid / rate-limited)."""


class DocumentValidationError(CollectorError):
    """Extracted facts failed validation (quote not found in PDF)."""


# ------------------------------------------------------------------ #
# Database layer                                                     #
# ------------------------------------------------------------------ #

class DatabaseError(InsuranceError):
    """General database error."""


class DatabaseConnectionError(DatabaseError):
    """Could not connect to the database."""


class DatabaseQueryError(DatabaseError):
    """Query execution failed."""


# ------------------------------------------------------------------ #
# Web / API layer                                                    #
# ------------------------------------------------------------------ #

class APIError(InsuranceError):
    """General API error."""


class AuthenticationError(APIError):
    """Invalid credentials or expired session."""


class AuthorizationError(APIError):
    """User lacks permission for the requested action."""


class RateLimitExceeded(APIError):
    """User exceeded the allowed comparison count."""


class ComparisonGateError(APIError):
    """Comparison blocked by the gate (no balance, auth required)."""


# ------------------------------------------------------------------ #
# Service layer                                                      #
# ------------------------------------------------------------------ #

class ServiceError(InsuranceError):
    """General service-layer error."""


class ComparisonServiceError(ServiceError):
    """Error during comparison computation."""


class SalesInsightsError(ServiceError):
    """Error generating sales insights."""


# ------------------------------------------------------------------ #
# HTTP / Network layer                                               #
# ------------------------------------------------------------------ #

class HTTPError(InsuranceError):
    """HTTP request failed."""

    def __init__(self, message: str = "", status_code: int = 0, url: str = "", detail: dict | None = None) -> None:
        self.status_code = status_code
        self.url = url
        super().__init__(message, {**({"status_code": status_code, "url": url}), **(detail or {})})
