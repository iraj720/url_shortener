"""
Statistics Service

This service handles retrieving statistics for short URLs.
Separated from URL service to enable microservice architecture.

Design Decisions:
- Separate service for statistics operations
- Can be moved to a separate microservice later
- Aggregates data from multiple sources (URL service, visit count service)

Future Microservice Architecture:
- This service can become a separate "Analytics Service"
- Can aggregate data from multiple sources
- Can use caching for frequently accessed stats
"""

from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.url_service import URLShorteningService
from app.services.visit_count_service import VisitCountService


class StatsService:
    """
    Service for retrieving URL statistics.
    
    This service aggregates data from multiple sources to provide
    comprehensive statistics for a short URL.
    """
    
    def __init__(self, session: AsyncSession):
        """
        Initialize the stats service with a database session.
        
        Args:
            session: Async database session for database operations
        """
        self.session = session
        self.url_service = URLShorteningService(session)
        self.visit_count_service = VisitCountService(session)
    
    async def get_stats(self, short_code: str) -> Optional[dict]:
        """
        Get comprehensive statistics for a short URL.
        
        Aggregates data from:
        - URL service: URL information
        - Visit count service: Visit count
        
        Returns:
            Dictionary with statistics:
            - original_url: The original long URL
            - short_code: The short code
            - created_at: When the URL was created
            - visit_count: Total number of visits
        
        Returns None if short code not found.
        
        Note:
        - visit_count is denormalized for fast queries
        - For detailed analytics, query VisitLog table separately
        - Can be cached for frequently accessed stats
        
        Future Enhancement:
        - Can query from separate analytics microservice
        - Can include additional metrics (unique visitors, geographic data, etc.)
        """
        # Get URL information
        short_url = await self.url_service.get_original_url(short_code)
        
        if not short_url:
            return None
        
        # Get visit count (can be from separate service in microservice architecture)
        visit_count = await self.visit_count_service.get_visit_count(short_code)
        
        return {
            "original_url": short_url.original_url,
            "short_code": short_url.short_code,
            "created_at": short_url.created_at.isoformat(),
            "visit_count": visit_count,
        }

