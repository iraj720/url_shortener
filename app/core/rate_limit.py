"""
Rate Limiting Configuration

This module provides rate limiting functionality for API endpoints.
Rate limiting prevents abuse and ensures fair usage.

Design Decisions:
- Uses slowapi for rate limiting (lightweight, FastAPI-compatible)
- Different limits for different endpoints
- IP-based limiting (can be extended to user-based)

Future Enhancement:
- Move to Redis-based rate limiting for distributed systems
- Implement token bucket or sliding window algorithms
- Add rate limit headers to responses
"""

from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

# Initialize rate limiter
# Uses IP address for rate limiting
limiter = Limiter(key_func=get_remote_address)

# Rate limit configurations per endpoint
# Format: "count/period" (e.g., "10/minute" means 10 requests per minute)
RATE_LIMITS = {
    "shorten": "10/minute",  # URL creation: 10 per minute per IP
    "redirect": "100/minute",  # Redirects: 100 per minute per IP
    "stats": "30/minute",  # Stats queries: 30 per minute per IP
}

