"""
Short Code Pool Manager

This module manages the global short code pool instance.
The pool is initialized once per application instance and shared across requests.

Design:
- Singleton pattern: One pool per application instance
- Initialized on application startup
- Shared across all requests in the same instance
- Each instance maintains its own pool (enables horizontal scaling)
- Service registration: Each instance registers itself and gets a unique service ID
"""

import logging
from typing import Optional

from app.db.session import async_session_maker
from app.services.short_code_pool import ShortCodePool
from app.services.service_registry import ServiceRegistry
from app.core.setting import settings

logger = logging.getLogger(__name__)

# Global pool instance (initialized on startup)
_pool: Optional[ShortCodePool] = None

# Global service ID (registered on startup)
_service_id: Optional[int] = None


async def get_code_pool() -> Optional[ShortCodePool]:
    """
    Get the global short code pool instance.
    
    Returns:
        ShortCodePool instance if initialized, None otherwise
    
    Note:
    - Returns None if pool is not initialized (fallback to on-demand generation)
    - Pool is initialized on application startup
    """
    return _pool


async def get_service_id() -> Optional[int]:
    """
    Get the registered service ID for this instance.
    
    Returns:
        Service ID if registered, None otherwise
    """
    return _service_id


async def initialize_pool() -> None:
    """
    Initialize the global short code pool.
    
    Registers service instance and warms up pool with pre-allocated codes.
    """
    global _pool, _service_id
    
    if _pool is not None:
        logger.warning("Short code pool already initialized")
        return
    
    try:
        async with async_session_maker() as session:
            registry = ServiceRegistry(session, max_services=settings.MAX_SERVICES)
            _service_id = await registry.register_service(service_name=settings.SERVICE_NAME)
            logger.info(f"Service registered with ID: {_service_id}")
            
            _pool = ShortCodePool(
                session=session,
                pool_size=settings.SHORT_CODE_POOL_SIZE,
                refill_threshold=settings.SHORT_CODE_POOL_REFILL_THRESHOLD,
                batch_size=settings.SHORT_CODE_BATCH_SIZE,
                worker_name=str(_service_id)
            )
            
            await _pool.initialize()
            
            logger.info(
                f"Short code pool initialized: "
                f"service_id={_service_id}, "
                f"pool_size={settings.SHORT_CODE_POOL_SIZE}"
            )
    except Exception as e:
        logger.error(f"Failed to initialize short code pool: {str(e)}", exc_info=True)
        _pool = None
        _service_id = None


async def shutdown_pool() -> None:
    """Shutdown pool and release service registration."""
    global _pool, _service_id
    
    if _service_id is not None:
        try:
            async with async_session_maker() as session:
                from app.services.service_registry import ServiceRegistry
                registry = ServiceRegistry(session, max_services=settings.MAX_SERVICES)
                await registry.release_service(_service_id)
                logger.info(f"Service ID {_service_id} released")
        except Exception as e:
            logger.warning(f"Failed to release service ID {_service_id}: {e}")
    
    if _pool:
        logger.info("Shutting down short code pool")
        _pool = None
        _service_id = None

