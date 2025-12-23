"""
Example Test File for URL Shortening Service

This file demonstrates how to write tests for the URL shortening service.
In a production environment, you would have comprehensive test coverage.

Note: These are example tests. For full implementation, you would need:
- Test database setup/teardown
- Async test fixtures
- Mock external dependencies
"""

import pytest
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.url_service import URLShorteningService, encode_base62, decode_base62, is_valid_url


class TestBase62Encoding:
    """Test base62 encoding/decoding functions."""
    
    def test_encode_base62(self):
        """Test encoding decimal numbers to base62 with fixed 7-character length."""
        # All codes are now padded to 7 characters for consistency
        assert encode_base62(0) == "0000000"
        assert encode_base62(1) == "0000001"
        assert encode_base62(62) == "0000010"  # 62 in base62 is "10", padded to 7 chars
        assert encode_base62(100000000000) == "1L9zO9O"  # Already 7+ chars, no padding needed
    
    def test_decode_base62(self):
        """Test decoding base62 strings to decimal."""
        # Decode works with both padded and unpadded codes
        assert decode_base62("0000000") == 0
        assert decode_base62("0000001") == 1
        assert decode_base62("0000010") == 62
        assert decode_base62("1L9zO9O") == 100000000000
        # Also test that it works with shorter codes (backward compatibility)
        assert decode_base62("0") == 0
        assert decode_base62("1") == 1
        assert decode_base62("10") == 62
    
    def test_encode_decode_roundtrip(self):
        """Test that encoding and decoding are inverse operations."""
        test_numbers = [0, 1, 62, 100, 1000, 1000000, 100000000000]
        for num in test_numbers:
            encoded = encode_base62(num)
            decoded = decode_base62(encoded)
            assert decoded == num, f"Roundtrip failed for {num}: encoded={encoded}, decoded={decoded}"
    
    def test_fixed_length_encoding(self):
        """Test that all encoded codes have the same length (7 characters)."""
        test_numbers = [0, 1, 10, 100, 1000, 10000, 100000]
        for num in test_numbers:
            encoded = encode_base62(num)
            assert len(encoded) == 7, f"Code for {num} should be 7 chars, got {len(encoded)}: {encoded}"


class TestURLValidation:
    """Test URL validation function."""
    
    def test_valid_urls(self):
        """Test that valid URLs are accepted."""
        valid_urls = [
            "http://example.com",
            "https://example.com",
            "https://www.example.com/path/to/page",
            "http://subdomain.example.com:8080/path?query=value",
        ]
        for url in valid_urls:
            assert is_valid_url(url), f"Should be valid: {url}"
    
    def test_invalid_urls(self):
        """Test that invalid URLs are rejected."""
        invalid_urls = [
            "not-a-url",
            "ftp://example.com",  # FTP not supported
            "example.com",  # Missing scheme
            "",
            "http://",  # Missing domain
        ]
        for url in invalid_urls:
            assert not is_valid_url(url), f"Should be invalid: {url}"


# Example integration test (would need proper async fixtures)
@pytest.mark.asyncio
async def test_create_short_url_integration():
    """
    Example integration test for creating short URLs.
    
    Note: This test would require:
    - Test database setup
    - Async session fixture
    - Proper cleanup
    """
    # This is a placeholder - actual implementation would require:
    # - Test database connection
    # - AsyncSession fixture
    # - Transaction rollback after test
    
    # Example structure:
    # async with get_test_session() as session:
    #     service = URLShorteningService(session)
    #     short_url = await service.create_short_url("https://example.com")
    #     assert short_url.short_code is not None
    #     assert short_url.original_url == "https://example.com"
    pass


# Example API endpoint test (would need TestClient)
def test_shorten_endpoint():
    """
    Example test for POST /shorten endpoint.
    
    Note: This would require:
    - FastAPI TestClient
    - Mock database or test database
    """
    # Example structure:
    # from fastapi.testclient import TestClient
    # from app.main import app
    # 
    # client = TestClient(app)
    # response = client.post("/shorten", json={"url": "https://example.com"})
    # assert response.status_code == 201
    # assert "short_code" in response.json()
    pass

