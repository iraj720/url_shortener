"""
Configuration Settings

This module defines application configuration using Pydantic Settings.
All configuration is loaded from environment variables or .env file.

Design Decisions:
- Uses pydantic-settings for type-safe configuration
- Supports multiple environments (production, staging, dev)
- Defaults to SQLite (file-based) for easy local development
- Can be switched to PostgreSQL for production via DATABASE_URL
"""

from __future__ import annotations

from enum import Enum
from pathlib import Path
from typing import Optional

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

__all__ = ["Settings", "settings"]

BASE_DIR = Path(__file__).resolve().parent.parent.parent


class EnvSettingsOptions(Enum):
    """Environment options for deployment."""
    production = "production"
    staging = "staging"
    development = "dev"


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.
    
    All settings can be overridden via environment variables or .env file.
    """
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore"
    )

    # Project Configuration
    ENV_SETTING: EnvSettingsOptions = Field(
        default=EnvSettingsOptions.development,
        description="Environment setting (production, staging, dev)"
    )
    
    # Database Configuration
    # Defaults to SQLite (file-based) for local development
    # For PostgreSQL: postgresql+asyncpg://user:password@host:port/dbname
    # For SQLite: sqlite+aiosqlite:///./urlshortener.db (default)
    DATABASE_URL: str = Field(
        default="sqlite+aiosqlite:///./urlshortener.db",
        description="Database connection string (SQLite by default, PostgreSQL for production)"
    )
    
    # Application Configuration
    BASE_URL: str = Field(
        default="http://localhost:8000",
        description="Base URL for generating short URLs"
    )
    
    # Short Code Pool Configuration
    SHORT_CODE_POOL_SIZE: int = Field(
        default=1000,
        description="Number of pre-allocated short codes to maintain in memory pool"
    )
    SHORT_CODE_POOL_REFILL_THRESHOLD: float = Field(
        default=0.2,
        description="Refill pool when it drops below this fraction (0.2 = 20%)"
    )
    SHORT_CODE_BATCH_SIZE: int = Field(
        default=10,
        description="Number of codes to reserve in each batch reservation"
    )
    SHORT_CODE_LENGTH: int = Field(
        default=7,
        description="Fixed length for all short codes (e.g., 7 = '0000000' to 'zzzzzzz')"
    )
    MAX_SERVICES: int = Field(
        default=100,
        description="Maximum number of service instances that can register (service ID pool size)"
    )
    SERVICE_NAME: Optional[str] = Field(
        default=None,
        description="Optional friendly name for this service instance (for identification)"
    )


settings = Settings()
