"""
Input Validators and Sanitizers

This module provides validation and sanitization functions for user inputs.
These functions help prevent security issues and ensure data integrity.

Security Considerations:
- Input validation prevents injection attacks
- Sanitization prevents XSS and other attacks
- Length limits prevent DoS attacks
"""

import re
from typing import Optional


def sanitize_short_code(short_code: str) -> Optional[str]:
    """
    Sanitize and validate short code format.
    
    Short codes should only contain base62 characters: [0-9a-zA-Z]
    This prevents injection attacks and ensures consistency.
    
    Args:
        short_code: The short code to sanitize
    
    Returns:
        Sanitized short code if valid, None otherwise
    
    Security:
    - Only allows alphanumeric characters
    - Prevents SQL injection (short_code is used in queries)
    - Prevents path traversal attacks
    """
    if not short_code or not isinstance(short_code, str):
        return None
    
    # Remove any whitespace
    short_code = short_code.strip()
    
    # Check length (reasonable limit)
    if len(short_code) > 20:  # Base62 codes are typically 6-7 chars
        return None
    
    # Only allow base62 characters: [0-9a-zA-Z]
    # This is the same character set used for encoding
    if not re.match(r'^[0-9a-zA-Z]+$', short_code):
        return None
    
    return short_code


def validate_url_length(url: str, max_length: int = 2048) -> bool:
    """
    Validate URL length to prevent DoS attacks.
    
    Args:
        url: The URL to validate
        max_length: Maximum allowed length (default: 2048 per RFC 7230)
    
    Returns:
        True if URL length is valid, False otherwise
    """
    return url and len(url) <= max_length

