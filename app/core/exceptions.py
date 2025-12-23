"""
Custom Exceptions

This module defines custom exceptions for better error handling
and more specific error messages.

Benefits:
- More specific error types for different failure scenarios
- Better error messages for API consumers
- Easier error handling and logging
- Type safety with exception handling
"""


class URLShortenerException(Exception):
    """Base exception for URL shortener service."""
    pass


class InvalidURLError(URLShortenerException):
    """Raised when URL validation fails."""
    
    def __init__(self, url: str, reason: str = "Invalid URL format"):
        self.url = url
        self.reason = reason
        super().__init__(f"{reason}: {url}")


class ShortCodeNotFoundError(URLShortenerException):
    """Raised when a short code is not found in the database."""
    
    def __init__(self, short_code: str):
        self.short_code = short_code
        super().__init__(f"Short code '{short_code}' not found")


class DatabaseError(URLShortenerException):
    """Raised when database operations fail."""
    
    def __init__(self, message: str, original_error: Exception = None):
        self.original_error = original_error
        super().__init__(f"Database error: {message}")


class ServiceUnavailableError(URLShortenerException):
    """Raised when a required service is unavailable."""
    
    def __init__(self, service_name: str):
        self.service_name = service_name
        super().__init__(f"Service '{service_name}' is unavailable")

