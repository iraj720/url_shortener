"""
FastAPI Endpoints for URL Shortener Service

This module defines all REST API endpoints with minimal logic.
Endpoints only handle:
- Request validation (Pydantic models)
- Rate limiting
- Error handling and HTTP responses
- Delegating to service layer

All business logic is in services, enabling microservice architecture.

Design Principles:
- Thin endpoints: Only validation and rate limiting
- Service layer: All business logic
- Separation: Easy to split into microservices later
- Error handling: Proper HTTP status codes
"""

from fastapi import APIRouter, Request, Depends, HTTPException, BackgroundTasks, status
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.schemas import ShortenRequest, ShortenResponse, StatsResponse
from app.db.session import get_session
from app.services.url_service import URLShorteningService
from app.services.redirect_service import RedirectService
from app.services.stats_service import StatsService
from app.services.background_tasks import (
    log_visit_background,
    increment_visit_count_background
)
from app.core.exceptions import InvalidURLError, DatabaseError
from app.core.validators import sanitize_short_code
from app.core.rate_limit import limiter, RATE_LIMITS
from app.core.pool_manager import get_code_pool
from app.core.setting import settings



router = APIRouter()


def get_client_ip(request: Request) -> str:
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


@router.post(
    "/shorten",
    response_model=ShortenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a short URL",
    description="Takes a long URL and returns a shortened version with a unique code"
)
@limiter.limit(RATE_LIMITS["shorten"])
async def create_short_url(
    request: Request,  # Required for rate limiting (slowapi expects parameter named 'request')
    body: ShortenRequest,  # Pydantic model for request body
    session: AsyncSession = Depends(get_session)
) -> ShortenResponse:
    """
    Create a new short URL from a long URL.
    
    Returns:
        ShortenResponse with short_code, short_url, and original_url
    """
    try:
        code_pool = await get_code_pool()

        url_service = URLShorteningService(session, code_pool=code_pool)

        short_url_obj = await url_service.create_short_url(str(body.url))

        complete_short_url = f"{settings.BASE_URL}/{short_url_obj.short_code}"
        
        return ShortenResponse(
            short_code=short_url_obj.short_code,
            short_url=complete_short_url,
            original_url=short_url_obj.original_url
        )
    
    except InvalidURLError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except DatabaseError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to create short URL: {str(e)}"
        )


@router.get(
    "/{short_code}",
    status_code=status.HTTP_302_FOUND,
    summary="Redirect to original URL",
    description="Takes a short code and redirects to the original long URL"
)
@limiter.limit(RATE_LIMITS["redirect"])
async def redirect_to_url(
    short_code: str,
    request: Request,
    background_tasks: BackgroundTasks,
    session: AsyncSession = Depends(get_session)
) -> RedirectResponse:
    """
    Redirect to the original URL for a given short code.
        
    Args:
        short_code: The short code to look up
        request: FastAPI Request object (for IP extraction and rate limiting)
        background_tasks: FastAPI BackgroundTasks for async logging
    
    Returns:
        RedirectResponse (HTTP 302) to original URL
    
    Raises:
        HTTPException 400: If short code format is invalid
        HTTPException 404: If short code not found
        HTTPException 429: If rate limit exceeded
    """
    sanitized_code = sanitize_short_code(short_code)
    if not sanitized_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid short code format: '{short_code}'. Short codes must contain only alphanumeric characters."
        )
    
    short_code = sanitized_code
    
    redirect_service = RedirectService(session)
    original_url = await redirect_service.get_redirect_url(short_code)
    
    if not original_url:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Short code '{short_code}' not found"
        )
    
    client_ip = get_client_ip(request)
    user_agent = request.headers.get("User-Agent")
    
    background_tasks.add_task(
        log_visit_background,
        short_code=short_code,
        ip_address=client_ip,
        user_agent=user_agent
    )
    
    background_tasks.add_task(
        increment_visit_count_background,
        short_code=short_code
    )
    
    return RedirectResponse(
        url=original_url,
        status_code=status.HTTP_302_FOUND
    )


@router.get(
    "/stats/{short_code}",
    response_model=StatsResponse,
    summary="Get URL statistics",
    description="Returns statistics for a short URL including visit count and creation date"
)
@limiter.limit(RATE_LIMITS["stats"])
async def get_url_stats(
    short_code: str,
    request: Request,  # Required for rate limiting
    session: AsyncSession = Depends(get_session)
) -> StatsResponse:
    """
    Get statistics for a short URL.
    
    Args:
        short_code: The short code to get statistics for
        request: FastAPI Request object (for rate limiting)
    
    Returns:
        StatsResponse with URL statistics
    
    Raises:
        HTTPException 400: If short code format is invalid
        HTTPException 404: If short code not found
        HTTPException 429: If rate limit exceeded
    """
    sanitized_code = sanitize_short_code(short_code)
    if not sanitized_code:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid short code format: '{short_code}'. Short codes must contain only alphanumeric characters."
        )
    
    short_code = sanitized_code
    
    stats_service = StatsService(session)
    stats = await stats_service.get_stats(short_code)
    
    if not stats:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Short code '{short_code}' not found"
        )
    
    return StatsResponse(**stats)
