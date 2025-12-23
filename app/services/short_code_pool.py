"""
Short Code Pool

Pre-allocates short codes in memory to eliminate database contention during code generation.
Each service instance maintains its own pool of codes and refills from reserved ID batches.
"""

import asyncio
import logging
import random
from typing import Optional, List
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from app.db.models import URLBatchReserve
from app.services.url_service import encode_base62
from app.core.exceptions import DatabaseError
from app.core.setting import settings
from app.db.sqlite_adapter import get_database_adapter

logger = logging.getLogger(__name__)


class ShortCodePool:
    """
    Manages in-memory pool of pre-allocated short codes.
    
    Maintains a pool of codes generated from reserved ID batches. Codes are selected
    randomly from the pool. When the pool is empty, a new batch is reserved and codes
    are generated in memory.
    """
    
    def __init__(
        self, 
        session: AsyncSession, 
        pool_size: int = 1000, 
        refill_threshold: float = 0.2,
        batch_size: int = 10,
        worker_name: str = "1"  # Default to service ID "1"
    ):
        """
        Initialize the short code pool.
        
        Args:
            session: Database session for batch reservations
            pool_size: Number of codes to maintain in pool (default: 1000)
            refill_threshold: Threshold for refill (default: 0.2, currently unused - refills when empty)
            batch_size: Number of IDs to reserve per batch (default: 10)
            worker_name: Service ID from registered_services (as string)
        """
        self.session = session
        self.pool_size = pool_size
        self.refill_threshold = refill_threshold
        self.batch_size = batch_size
        self.worker_name = worker_name
        self.refill_count = int(pool_size * (1 - refill_threshold))
        
        self._pool: List[str] = []
        self._lock = asyncio.Lock()
        self._refilling = False
        
        self._current_batch_start: Optional[int] = None
        self._current_batch_end: Optional[int] = None
        self._current_batch_next_id: Optional[int] = None
        
        self._total_allocated = 0
        self._total_refills = 0
    
    async def get_short_code(self) -> str:
        """
        Get a random short code from the pool.
        
        Returns a code from the in-memory pool. If pool is empty, triggers refill
        and waits for codes to be generated. Codes are selected randomly to prevent
        predictability.
        
        Returns:
            A short code string
        
        Raises:
            DatabaseError: If pool refill fails or times out
        """
        async with self._lock:
            if self._pool:
                code = random.choice(self._pool)
                self._pool.remove(code)
                self._total_allocated += 1
                return code
        
        async with self._lock:
            if not self._refilling:
                asyncio.create_task(self._refill_pool())
        
        max_wait_time = 100
        attempts = 0
        
        while True:
            async with self._lock:
                if self._pool:
                    code = random.choice(self._pool)
                    self._pool.remove(code)
                    self._total_allocated += 1
                    return code
            
            attempts += 1
            if attempts >= max_wait_time:
                logger.error("Pool refill timeout")
                raise DatabaseError(
                    "Short code pool is empty and refill is taking too long. "
                    "Please check database connectivity and pool initialization."
                )
            
            await asyncio.sleep(0.1)
    
    async def _reserve_batch(self) -> tuple[int, int]:
        """
        Reserve a new batch of IDs from the database with table locking.
        
        Finds the highest end_id across all reservations and reserves the next batch
        sequentially. Uses table-level locking to prevent race conditions.
        
        Returns:
            Tuple of (start_id, end_id) for the reserved batch
        
        Raises:
            DatabaseError: If reservation fails
        """
        try:
            db_adapter = get_database_adapter()
            await db_adapter.lock_table_for_batch_reservation(
                self.session,
                "url_batch_reserve"
            )
            
            statement = select(func.max(URLBatchReserve.end_id))
            result = await self.session.execute(statement)
            max_end_id = result.scalar() or 0
            
            start_id = max_end_id + 1
            end_id = start_id + self.batch_size - 1
            service_id = int(self.worker_name)
            
            reservation = URLBatchReserve(
                start_id=start_id,
                end_id=end_id,
                reserver=service_id
            )
            self.session.add(reservation)
            await self.session.flush()
            await self.session.commit()
            
            logger.info(f"Reserved batch: IDs {start_id} to {end_id} for service {service_id}")
            return start_id, end_id
        
        except Exception as e:
            await self.session.rollback()
            logger.error(f"Failed to reserve batch: {e}", exc_info=True)
            raise DatabaseError(
                f"Failed to reserve batch: {e}. "
                "This may be due to concurrent reservation attempts or database issues."
            )
    
    async def _refill_pool(self) -> None:
        """
        Generate codes from reserved IDs and add them to the pool.
        
        Uses IDs from current batch if available, otherwise reserves a new batch.
        Generates codes in memory only - no database writes until codes are used.
        """
        async with self._lock:
            if self._refilling:
                return
            if len(self._pool) > 0:
                return
            self._refilling = True
        
        try:
            logger.info(f"Refilling pool: generating {self.refill_count} codes")
            
            needs_new_batch = (
                self._current_batch_next_id is None or 
                self._current_batch_next_id > self._current_batch_end
            )
            
            if needs_new_batch:
                start_id, end_id = await self._reserve_batch()
                self._current_batch_start = start_id
                self._current_batch_end = end_id
                self._current_batch_next_id = start_id
            else:
                start_id = self._current_batch_start
                end_id = self._current_batch_end
            
            ids_available = end_id - self._current_batch_next_id + 1
            codes_to_create = min(self.refill_count, ids_available)
            
            if codes_to_create == 0:
                logger.warning("No IDs available in current batch")
                async with self._lock:
                    self._refilling = False
                return
            
            new_codes = []
            for i in range(codes_to_create):
                current_id = self._current_batch_next_id + i
                short_code = encode_base62(current_id, min_length=settings.SHORT_CODE_LENGTH)
                new_codes.append(short_code)
            
            self._current_batch_next_id += codes_to_create
            
            if self._current_batch_next_id > self._current_batch_end:
                logger.info(f"Batch {self._current_batch_start}-{self._current_batch_end} exhausted")
            
            async with self._lock:
                self._pool.extend(new_codes)
            
            self._total_refills += 1
            logger.info(f"Pool refilled: added {len(new_codes)} codes, total: {len(self._pool)}")
        
        except Exception as e:
            logger.error(f"Failed to refill pool: {e}", exc_info=True)
        finally:
            async with self._lock:
                self._refilling = False
    
    async def initialize(self) -> None:
        """
        Initialize the pool by reserving first batch and generating codes.
        """
        logger.info(f"Initializing pool with {self.pool_size} codes")
        start_id, end_id = await self._reserve_batch()
        self._current_batch_start = start_id
        self._current_batch_end = end_id
        self._current_batch_next_id = start_id
        await self._refill_pool()
    
    async def get_stats(self) -> dict:
        """
        Get pool statistics for monitoring.
        
        Returns:
            Dictionary with pool metrics
        """
        async with self._lock:
            codes_in_stash = len(self._pool)
        
        return {
            "pool_size": self.pool_size,
            "current_size": codes_in_stash,
            "total_allocated": self._total_allocated,
            "total_refills": self._total_refills,
            "refill_threshold": self.refill_threshold,
            "is_refilling": self._refilling
        }

