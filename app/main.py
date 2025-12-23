"""
FastAPI Application Entry Point

This module initializes the FastAPI application and configures:
- API routes
- Middleware (logging, CORS, etc.)
- Application metadata

Design Decisions:
- Clean separation: Routes, middleware, and app config are separate
- Easy to extend: Add new routes/middleware without modifying core logic
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address

from app.api import endpoints
from app.middleware.logging import add_logging_middleware
from app.core.rate_limit import limiter
from app.core.pool_manager import initialize_pool, shutdown_pool

# Initialize FastAPI application
# Title and description are used in auto-generated API documentation
app = FastAPI(
    title="URL Shortener Service",
    description="A scalable URL shortening service built with FastAPI",
    version="1.0.0",
    docs_url="/docs",  # Swagger UI documentation
    redoc_url="/redoc",  # ReDoc documentation
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

add_logging_middleware(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Health endpoints defined before router to match before catch-all route
@app.get("/", tags=["Health"])
async def root():
    """
    Root endpoint for health checks.
    
    Returns:
        Simple JSON response indicating service is running
    """
    return {
        "message": "URL Shortener Service",
        "version": "1.0.0",
        "docs": "/docs"
    }


@app.get("/health", tags=["Health"])
async def health_check():
    """
    Health check endpoint for monitoring.
    
    Returns:
        Health status of the service
    
    Future Enhancement:
    - Check database connectivity
    - Check external dependencies (cache, queue, etc.)
    """
    return {"status": "healthy"}


app.include_router(endpoints.router, tags=["URL Shortener"])


@app.on_event("startup")
async def startup_event():
    """Initialize services on startup."""
    await initialize_pool()


@app.on_event("shutdown")
async def shutdown_event():
    """Cleanup on shutdown."""
    await shutdown_pool()
