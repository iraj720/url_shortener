"""
Background Task Helpers

Provides helper functions for background tasks that create their own database sessions.
Background tasks cannot use the endpoint's session as it's closed after the endpoint returns.
"""

import logging
from typing import Optional

from app.db.session import async_session_maker
from app.services.visit_logger import VisitLoggerService
from app.services.visit_count_service import VisitCountService

logger = logging.getLogger(__name__)


async def log_visit_background(
    short_code: str,
    ip_address: str,
    user_agent: Optional[str] = None
) -> None:
    """
    Background task to log a visit.
    
    Creates its own database session as endpoint session is closed.
    
    Args:
        short_code: The short code that was accessed
        ip_address: IP address of the visitor
        user_agent: User agent string (optional)
    """
    try:
        async with async_session_maker() as session:
            visit_logger = VisitLoggerService(session)
            await visit_logger.log_visit(
                short_code=short_code,
                ip_address=ip_address,
                user_agent=user_agent
            )
            await session.commit()
    except Exception as e:
        logger.error(
            f"Failed to log visit for {short_code}: {str(e)}",
            exc_info=True
        )


async def increment_visit_count_background(short_code: str) -> None:
    """
    Background task to increment visit count.
    
    Uses database-level increment for atomicity.
    
    Args:
        short_code: The short code to increment count for
    """
    try:
        async with async_session_maker() as session:
            visit_count_service = VisitCountService(session)
            await visit_count_service.increment_visit_count(short_code)
            await session.commit()
    except Exception as e:
        logger.error(
            f"Failed to increment visit count for {short_code}: {str(e)}",
            exc_info=True
        )

