"""
Service Registry - Managing Service Instance Registration

This module handles the registration of service instances in a distributed system.
Each service instance registers itself on startup by reserving an available service ID
from a fixed pool of service IDs.

Design:
- Fixed pool of service IDs (configurable, e.g., 1-100)
- Atomic reservation prevents race conditions
- Service ID is used as 'reserver' in batch reservations
- Enables multiple service instances to work without conflicts
"""

import logging
from datetime import datetime
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update, func
from sqlalchemy.exc import IntegrityError

from app.db.models import RegisteredService
from app.core.exceptions import DatabaseError

logger = logging.getLogger(__name__)


class ServiceRegistry:
    """
    Manages service instance registration.
    
    Each service instance must register itself on startup to get a unique service ID.
    This ID is then used for all batch reservations to identify which service
    reserved which batch of URL IDs.
    """
    
    def __init__(self, session: AsyncSession, max_services: int = 100):
        """
        Initialize the service registry.
        
        Args:
            session: Database session for registration operations
            max_services: Maximum number of service IDs in the pool (default: 100)
        """
        self.session = session
        self.max_services = max_services
    
    async def ensure_service_pool_exists(self) -> None:
        """
        Ensure the service ID pool exists in the database.
        
        Creates service IDs from 1 to max_services if they don't exist.
        This is idempotent - safe to call multiple times.
        """
        try:
            # Check how many service IDs exist
            statement = select(func.count(RegisteredService.id))
            result = await self.session.execute(statement)
            count = result.scalar() or 0
            
            if count < self.max_services:
                logger.info(f"Initializing service ID pool: creating {self.max_services - count} service IDs...")
                
                # Find the highest existing ID
                max_id_statement = select(func.max(RegisteredService.id))
                max_id_result = await self.session.execute(max_id_statement)
                max_id = max_id_result.scalar() or 0
                
                # Create missing service IDs
                services_to_create = []
                for service_id in range(max_id + 1, self.max_services + 1):
                    service = RegisteredService(
                        id=service_id,
                        reserved=False,
                        registered_at=datetime.utcnow()
                    )
                    services_to_create.append(service)
                    self.session.add(service)
                
                await self.session.flush()
                await self.session.commit()
                
                logger.info(f"Service ID pool initialized: {len(services_to_create)} service IDs created")
            else:
                logger.debug(f"Service ID pool already exists: {count} service IDs")
        
        except IntegrityError:
            # Race condition: another instance created the pool simultaneously
            await self.session.rollback()
            logger.info("Service ID pool already exists (created by another instance)")
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to initialize service ID pool: {e}", exc_info=True)
            raise DatabaseError(f"Failed to initialize service ID pool: {e}")
    
    async def register_service(self, service_name: Optional[str] = None) -> int:
        """
        Register this service instance and reserve a service ID.
        
        Finds an available service ID (where reserved=False) and atomically
        reserves it for this service instance.
        
        Args:
            service_name: Optional friendly name for this service instance
        
        Returns:
            The reserved service ID (to be used as 'reserver' in batch reservations)
        
        Raises:
            DatabaseError: If no available service IDs or registration fails
        """
        try:
            # First, ensure the pool exists
            await self.ensure_service_pool_exists()
            
            # Find an available service ID (reserved=False, which is 0 in SQLite)
            # Use a subquery with FOR UPDATE to lock the row (prevents race conditions)
            statement = (
                select(RegisteredService)
                .where(RegisteredService.reserved == False)  # False = 0 in SQLite
                .order_by(RegisteredService.id)
                .limit(1)
                .with_for_update()  # Lock the row for atomic update
            )
            
            result = await self.session.execute(statement)
            service = result.scalar_one_or_none()
            
            if not service:
                raise DatabaseError(
                    f"No available service IDs. All {self.max_services} service IDs are reserved. "
                    "Please wait for a service to shut down or increase MAX_SERVICES."
                )
            
            # Atomically reserve this service ID
            service.reserved = True
            service.service_name = service_name
            service.registered_at = datetime.utcnow()
            service.last_heartbeat = datetime.utcnow()
            
            await self.session.flush()
            await self.session.commit()
            
            logger.info(
                f"Service registered successfully: ID={service.id}, name={service_name or 'unnamed'}"
            )
            
            return service.id
        
        except IntegrityError as e:
            await self.session.rollback()
            # Race condition: another instance reserved the same ID
            logger.warning("Service ID reservation conflict, retrying...")
            # Retry once
            return await self.register_service(service_name)
        except Exception as e:
            await self.session.rollback()
            if isinstance(e, DatabaseError):
                raise
            logger.error(f"Failed to register service: {e}", exc_info=True)
            raise DatabaseError(f"Failed to register service: {e}")
    
    async def update_heartbeat(self, service_id: int) -> None:
        """
        Update the heartbeat timestamp for a registered service.
        
        This can be used for health monitoring - services that haven't
        updated their heartbeat in a while might be considered dead.
        
        Args:
            service_id: The service ID to update
        """
        try:
            statement = (
                update(RegisteredService)
                .where(RegisteredService.id == service_id)
                .values(last_heartbeat=datetime.utcnow())
            )
            await self.session.execute(statement)
            await self.session.commit()
        except Exception as e:
            logger.warning(f"Failed to update heartbeat for service {service_id}: {e}")
            await self.session.rollback()
    
    async def release_service(self, service_id: int) -> None:
        """
        Release a service ID when the service shuts down.
        
        Marks the service ID as available (reserved=False) so other
        instances can use it.
        
        Args:
            service_id: The service ID to release
        """
        try:
            statement = (
                update(RegisteredService)
                .where(RegisteredService.id == service_id)
                .values(
                    reserved=False,
                    service_name=None,
                    last_heartbeat=None
                )
            )
            await self.session.execute(statement)
            await self.session.commit()
            
            logger.info(f"Service ID {service_id} released")
        except Exception as e:
            logger.warning(f"Failed to release service {service_id}: {e}")
            await self.session.rollback()

