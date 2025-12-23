"""
Redirect Service

This service handles URL redirection logic.
Separated from URL service to enable microservice architecture.

Design Decisions:
- Separate service for redirect operations
- Can be moved to a separate microservice later
- Handles URL lookup and redirection logic
"""

from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.url_service import URLShorteningService


class RedirectService:
    """
    Service for handling URL redirections.
    
    This service encapsulates redirect logic, making it easy to
    move to a separate microservice if needed.
    """
    
    def __init__(self, session: AsyncSession):
        """
        Initialize the redirect service with a database session.
        
        Args:
            session: Async database session for database operations
        """
        self.session = session
        self.url_service = URLShorteningService(session)
    
    async def get_redirect_url(self, short_code: str) -> Optional[str]:
        """
        Get the original URL for redirection.
        """
        short_url = await self.url_service.get_original_url(short_code)
        if short_url:
            return short_url.original_url
        return None

