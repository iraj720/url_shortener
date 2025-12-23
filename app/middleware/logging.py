"""
Logging Middleware for Request/Response Logging

This middleware logs all HTTP requests and responses for observability.
It captures:
- Request method and path
- Response status code
- Request processing time
- Client IP address

Design Decisions:
- Uses Starlette's BaseHTTPMiddleware for compatibility
- Logs to standard Python logging (can be configured to send to external services)
- Non-blocking: Doesn't impact request processing time significantly

Future Enhancements:
- Structured logging (JSON format) for better parsing
- Integration with observability platforms (Datadog, New Relic, etc.)
- Request ID tracking for distributed tracing
"""

import time
import logging
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import Response

# Configure logger
# In production, configure this to send logs to centralized logging service
logger = logging.getLogger("url_shortener")


class LoggingMiddleware(BaseHTTPMiddleware):
    """
    Middleware for logging HTTP requests and responses.
    
    This middleware logs:
    - Request method and path
    - Response status code
    - Processing time
    - Client IP address
    
    It wraps the request/response cycle to add logging without
    modifying endpoint code.
    """
    
    async def dispatch(self, request: Request, call_next):
        """
        Process request and log details.
        
        Args:
            request: The incoming HTTP request
            call_next: The next middleware/endpoint in the chain
        
        Returns:
            Response object
        """
        # Extract client IP (handles proxies/load balancers)
        client_ip = self._get_client_ip(request)
        
        # Record start time for performance measurement
        start_time = time.time()
        
        # Process the request
        response = await call_next(request)
        
        # Calculate processing time
        process_time = time.time() - start_time
        
        # Log request details
        # Format: METHOD PATH STATUS_CODE PROCESS_TIME_MS CLIENT_IP
        logger.info(
            f"{request.method} {request.url.path} "
            f"{response.status_code} {process_time*1000:.2f}ms "
            f"IP:{client_ip}"
        )
        
        # Add custom headers for observability (optional)
        response.headers["X-Process-Time"] = str(process_time)
        
        return response
    
    def _get_client_ip(self, request: Request) -> str:
        """
        Extract client IP address from request.
        
        Handles proxies and load balancers by checking X-Forwarded-For header.
        
        Args:
            request: FastAPI Request object
        
        Returns:
            IP address as string
        """
        # Check for forwarded IP (from proxy/load balancer)
        forwarded_for = request.headers.get("X-Forwarded-For")
        if forwarded_for:
            # X-Forwarded-For can contain multiple IPs, take the first one
            return forwarded_for.split(",")[0].strip()
        
        # Fallback to direct client IP
        return request.client.host if request.client else "unknown"


def add_logging_middleware(app):
    """
    Add logging middleware to FastAPI app.
    
    Args:
        app: FastAPI application instance
    """
    app.add_middleware(LoggingMiddleware)
