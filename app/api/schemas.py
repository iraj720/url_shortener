"""
API Request and Response Schemas

This module defines all Pydantic models for API requests and responses.
Separated from endpoints to keep concerns separated and enable reuse.

Design Principles:
- Request models: Define input validation
- Response models: Define output structure
- Separation: Can be imported by other modules (services, tests, etc.)
"""

from pydantic import BaseModel, HttpUrl, Field


class ShortenRequest(BaseModel):
    """Request model for URL shortening endpoint."""
    url: HttpUrl = Field(..., description="The long URL to shorten")


class ShortenResponse(BaseModel):
    """Response model for URL shortening endpoint."""
    short_code: str = Field(..., description="The generated short code")
    short_url: str = Field(..., description="The complete short URL")
    original_url: str = Field(..., description="The original long URL")


class StatsResponse(BaseModel):
    """Response model for statistics endpoint."""
    original_url: str
    short_code: str
    created_at: str
    visit_count: int

