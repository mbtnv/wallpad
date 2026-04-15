from __future__ import annotations


class AppError(Exception):
    """Base application error."""


class ConfigurationError(AppError):
    """Raised when the app or provider is not configured correctly."""


class ActionError(AppError):
    """Raised when a user action cannot be completed."""


class UpstreamError(AppError):
    """Raised when an upstream provider or API request fails."""


class ProviderNotRegisteredError(AppError):
    """Raised when an expected provider is missing from the orchestrator."""


class ConflictError(AppError):
    """Raised when a resource changed while a user was editing it."""
