"""
Visit Logging Service

This service handles logging of URL visits for analytics.
Separated from other services to enable microservice architecture.

Design Decisions:
- Separate service for logging to keep concerns separated
- Can be easily replaced with queue-based logging or external service
- Logs IP address, timestamp, and user agent for analytics

Future Microservice Architecture:
- This service can become a separate "Logging Service"
- Can use message queues (Redis/RabbitMQ) for high throughput
- Can use time-series database (InfluxDB/TimescaleDB) for analytics
- Batch inserts for better performance
"""

from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import VisitLog


class VisitLoggerService:
    """
    Service for logging URL visits.
    
    This service is designed to be called asynchronously via background tasks
    to avoid blocking the main request/response cycle.
    """
    
    def __init__(self, session: AsyncSession):
        """
        Initialize the visit logger with a database session.
        
        Args:
            session: Async database session for database operations
        """
        self.session = session
    
    async def log_visit(
        self,
        short_code: str,
        ip_address: str,
        user_agent: Optional[str] = None
    ) -> None:
        """
        Log a visit to a short URL.
        
        Args:
            short_code: The short code that was accessed
            ip_address: IP address of the visitor
            user_agent: User agent string (optional)
        
        Note:
        - This operation is designed to be non-blocking
        - In production, consider using a queue (Redis/RabbitMQ) instead
        - Can be batched for better performance
        """
        visit_log = VisitLog(
            short_code=short_code,
            ip_address=ip_address,
            user_agent=user_agent,
            visited_at=datetime.utcnow()
        )
        
        self.session.add(visit_log)
        
        # Commit the log entry
        # In production, this could be batched or queued
        await self.session.commit()
