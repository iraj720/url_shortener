"""
Visit Count Service

This service handles incrementing visit counts for short URLs.
Separated from URL service to enable microservice architecture.

Design Decisions:
- Separate service for visit count operations
- Can be moved to a separate microservice later
- Uses database-level atomic increment for performance
- Non-blocking operations designed for async execution

Future Microservice Architecture:
- This service can become a separate "Analytics Service"
- Handles all visit-related operations
- Can use different database (time-series DB) for scalability
"""

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import update

from app.db.models import ShortURL


class VisitCountService:
    """
    Service for managing visit counts.
    
    This service is designed to be called asynchronously via background tasks
    or can be moved to a separate microservice for analytics.
    """
    
    def __init__(self, session: AsyncSession):
        """
        Initialize the visit count service with a database session.
        
        Args:
            session: Async database session for database operations
        """
        self.session = session
    
    async def increment_visit_count(self, short_code: str) -> None:
        """
        Increment the visit count for a short URL atomically.
        
        Uses database-level UPDATE for atomicity and better performance
        compared to read-modify-write pattern.
        
        Args:
            short_code: The short code to increment count for
        
        Note:
        - Uses database-level UPDATE for atomicity (prevents race conditions)
        - More efficient than read-modify-write pattern
        - Non-blocking operation (doesn't wait for commit in caller)
        - Silently fails if short_code doesn't exist (no exception thrown)
        
        Future Enhancement:
        - Can be moved to a separate analytics microservice
        - Can use Redis for high-frequency increments
        - Can batch increments for better performance
        """
        # Use database-level UPDATE for atomic increment
        # This is more efficient and thread-safe than read-modify-write
        statement = (
            update(ShortURL)
            .where(ShortURL.short_code == short_code)
            .values(visit_count=ShortURL.visit_count + 1)
        )
        
        await self.session.execute(statement)
        # Note: Commit is handled by the caller (background task or service)
    
    async def get_visit_count(self, short_code: str) -> int:
        """
        Get the current visit count for a short URL.
        
        Args:
            short_code: The short code to get count for
        
        Returns:
            Visit count (0 if not found)
        """
        from sqlalchemy import select
        
        statement = select(ShortURL.visit_count).where(ShortURL.short_code == short_code)
        result = await self.session.execute(statement)
        count = result.scalar_one_or_none()
        return count if count is not None else 0

