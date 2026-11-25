class ServiceError(Exception):
    """Base domain error raised by service layer operations."""


class NotFoundError(ServiceError):
    """Raised when an entity cannot be found (HTTP 404)."""


class ConflictError(ServiceError):
    """Raised when an operation violates a uniqueness or state constraint (HTTP 409)."""


class ValidationError(ServiceError):
    """Raised when input or business-rule validation fails (HTTP 422)."""


class ExternalServiceError(ServiceError):
    """Raised when an upstream Keitaro API call fails (HTTP 502)."""
