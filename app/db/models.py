"""
Database Models for URL Shortener Service

This module defines the SQLModel database schemas for:
- ShortURL: Stores the mapping between short codes and original URLs
- VisitLog: Stores individual visit logs for analytics and statistics

Design Decisions:
- Separate VisitLog table for better scalability (can be partitioned/sharded independently)
- Indexes on short_code for fast lookups (most common operation)
- Indexes on created_at for time-based queries
- visit_count denormalized in ShortURL for quick stats without joins
"""

from sqlmodel import SQLModel, Field, Relationship, Column, Index
from datetime import datetime
from typing import Optional
from sqlalchemy import String, DateTime, Integer, Text


class ShortURL(SQLModel, table=True):
    """
    Main table storing URL shortening mappings.
    
    Fields:
    - id: Auto-incrementing primary key (used for base62 encoding)
    - original_url: The long URL that was shortened
    - short_code: Unique short code (6-7 characters, base62 encoded)
    - created_at: Timestamp when URL was shortened
    - visit_count: Denormalized count for quick stats (updated asynchronously)
    
    Indexes:
    - short_code: Unique index for fast lookups (most critical path)
    - created_at: For time-based analytics queries
    """
    __tablename__ = "short_urls"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    original_url: str = Field(sa_column=Column(Text, nullable=False))
    short_code: str = Field(
        sa_column=Column(String(10), nullable=False, unique=True, index=True),
        max_length=10
    )
    created_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True)
    )
    visit_count: int = Field(default=0, sa_column=Column(Integer, nullable=False, default=0))
    
    # Relationship to visit logs (optional, for detailed analytics)
    # Note: This relationship is optional and can be lazy-loaded when needed
    # visit_logs: list["VisitLog"] = Relationship(back_populates="short_url")


class VisitLog(SQLModel, table=True):
    """
    Visit log table for detailed analytics.
    
    This table stores individual visit records with:
    - IP address for geographic analytics
    - Timestamp for time-series analysis
    - Foreign key to ShortURL
    
    Design Rationale:
    - Separate table allows independent scaling (can be moved to time-series DB)
    - Can be partitioned by date for better performance
    - Enables detailed analytics without impacting main URL lookup performance
    
    Note: In production, this could be moved to a separate analytics database
    or streamed to a time-series database like InfluxDB or TimescaleDB.
    """
    __tablename__ = "visit_logs"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    short_code: str = Field(
        sa_column=Column(String(10), nullable=False, index=True)
    )
    ip_address: str = Field(sa_column=Column(String(45), nullable=False))  # IPv6 max length
    visited_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True)
    )
    user_agent: Optional[str] = Field(
        default=None,
        sa_column=Column(String(500), nullable=True)
    )
    
    # Relationship back to ShortURL (optional, can be queried separately)
    # Note: Relationship is commented out to avoid circular dependencies
    # In production, queries can join these tables when needed
    # short_url: Optional[ShortURL] = Relationship(back_populates="visit_logs")


class RegisteredService(SQLModel, table=True):
    """
    Registered services table for tracking service instances.
    
    This table manages a fixed pool of service IDs that can be reserved by
    running service instances. Each service instance registers itself on startup
    by reserving an available service ID.
    
    Fields:
    - id: Service ID (primary key, used as reserver in batch reservations)
    - service_name: Optional friendly name for the service instance
    - reserved: Whether this service ID is currently reserved by a running instance
    - registered_at: When the service ID was first registered/reserved
    - last_heartbeat: Last time this service checked in (for health monitoring)
    
    Design:
    - Fixed pool of service IDs (e.g., 1-100)
    - Services reserve an ID on startup (atomic operation)
    - ID is used as 'reserver' in url_batch_reserve table
    """
    __tablename__ = "registered_services"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    service_name: Optional[str] = Field(
        default=None,
        sa_column=Column(String(100), nullable=True)
    )
    reserved: bool = Field(
        default=False,
        sa_column=Column(Integer, nullable=False, default=0, index=True)  # SQLite uses 0/1 for boolean
    )
    registered_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True)
    )
    last_heartbeat: Optional[datetime] = Field(
        default=None,
        sa_column=Column(DateTime(timezone=True), nullable=True, index=True)
    )


class URLBatchReserve(SQLModel, table=True):
    """
    Batch reservation table for tracking ID ranges reserved by workers.
    
    This table ensures that multiple service instances can reserve non-overlapping
    ranges of IDs for generating short codes, preventing conflicts.
    
    Fields:
    - id: Auto-incrementing primary key
    - start_id: First ID in the reserved range
    - end_id: Last ID in the reserved range (inclusive)
    - reserver: Service ID (from registered_services) that reserved this range
    - reserved_at: When the reservation was made
    
    Design:
    - Each worker reserves a contiguous range of IDs
    - Workers check the highest end_id and reserve the next range
    - reserver field uses the service ID from registered_services table
    """
    __tablename__ = "url_batch_reserve"
    
    id: Optional[int] = Field(default=None, primary_key=True)
    start_id: int = Field(sa_column=Column(Integer, nullable=False, index=True))
    end_id: int = Field(sa_column=Column(Integer, nullable=False, index=True))
    reserver: int = Field(sa_column=Column(Integer, nullable=False, index=True))  # Changed to int (service ID)
    reserved_at: datetime = Field(
        default_factory=datetime.utcnow,
        sa_column=Column(DateTime(timezone=True), nullable=False, index=True)
    )
