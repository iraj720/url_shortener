"""
URL Shortening Service

This service handles the core business logic for URL shortening:
- Generating unique short codes using base62 encoding
- Encoding/decoding between numeric IDs and short codes
- Validating URLs

Design Decisions:
- Base62 encoding: Uses [0-9a-zA-Z] for maximum URL compatibility
- Counter-based: Uses auto-incrementing ID converted to base62 (ensures uniqueness)
- Short code length: 6-7 characters (supports billions of URLs)
- URL validation: Basic validation to ensure URL format is correct

Why Base62?
- More compact than base10 (fewer characters needed)
- URL-safe (no special characters)
- Case-sensitive (more combinations per character)
- Standard approach used by bit.ly, tinyurl.com, etc.
"""

from typing import Optional, TYPE_CHECKING
from urllib.parse import urlparse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.db.models import ShortURL
from app.core.exceptions import InvalidURLError, DatabaseError

if TYPE_CHECKING:
    from app.services.short_code_pool import ShortCodePool


BASE62_CHARS = "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"
BASE62_LENGTH = len(BASE62_CHARS)


def encode_base62(number: int, min_length: int = 7) -> str:
    """
    Encode a number to base62 string with fixed length.
    
    Args:
        number: The number to convert
        min_length: Minimum length of the code (default: 7)
    
    Returns:
        Base62 encoded string, padded to min_length
    
    Example:
        encode_base62(0) -> "0000000"
        encode_base62(1) -> "0000001"
        encode_base62(62) -> "0000010"
    """
    if number == 0:
        return BASE62_CHARS[0] * min_length
    
    digits = []
    while number > 0:
        remainder = number % BASE62_LENGTH
        digits.append(BASE62_CHARS[remainder])
        number //= BASE62_LENGTH
    
    code = ''.join(reversed(digits))
    
    if len(code) < min_length:
        code = BASE62_CHARS[0] * (min_length - len(code)) + code
    
    return code


def decode_base62(encoded: str) -> int:
    """
    Decode a base62 string back to a number.
    
    Args:
        encoded: The base62 encoded string
    
    Returns:
        The decoded number
    
    Example:
        decode_base62("1L9zO9O") -> 100000000000
    """
    number = 0
    for char in encoded:
        number = number * BASE62_LENGTH + BASE62_CHARS.index(char)
    return number


def is_valid_url(url: str) -> bool:
    """
    Validate URL format and security.
    
    Checks that URL uses http/https, has valid domain, and doesn't contain
    malicious patterns. Prevents javascript:, file:, and other dangerous schemes.
    
    Args:
        url: The URL string to validate
    
    Returns:
        True if valid and safe, False otherwise
    """
    if not url or not isinstance(url, str):
        return False
    
    MAX_URL_LENGTH = 2048
    if len(url) > MAX_URL_LENGTH:
        return False
    
    try:
        result = urlparse(url)
        
        if not result.scheme or not result.netloc:
            return False
        
        allowed_schemes = {'http', 'https'}
        if result.scheme.lower() not in allowed_schemes:
            return False
        
        domain = result.netloc.split(':')[0]
        if domain != 'localhost' and '.' not in domain:
            return False
        
        malicious_patterns = ['javascript:', 'data:', 'file:', 'vbscript:']
        url_lower = url.lower()
        if any(pattern in url_lower for pattern in malicious_patterns):
            return False
        
        return True
    except Exception:
        return False


class URLShorteningService:
    """
    Core business logic for URL shortening.
    
    Handles URL validation, code generation via pool, and database operations.
    Separated from API layer for testability and maintainability.
    """
    
    def __init__(self, session: AsyncSession, code_pool: Optional['ShortCodePool'] = None):
        """
        Initialize the URL shortening service.
        
        Args:
            session: Database session
            code_pool: Short code pool instance (required for code generation)
        """
        self.session = session
        self.code_pool = code_pool
    
    async def get_existing_short_url(self, original_url: str) -> Optional[ShortURL]:
        """
        Check if a short URL already exists for the given original URL.
        
        Args:
            original_url: The long URL to check
        
        Returns:
            ShortURL object if found, None otherwise
        """
        try:
            statement = select(ShortURL).where(ShortURL.original_url == original_url).limit(1)
            result = await self.session.execute(statement)
            return result.scalars().first()
        except Exception:
            return None
    
    async def create_short_url(self, original_url: str) -> ShortURL:
        """
        Create a new short URL or return existing one if URL was already shortened.
        
        Args:
            original_url: The long URL to shorten
        
        Returns:
            ShortURL object with short_code populated
        
        Raises:
            InvalidURLError: If URL format is invalid
            DatabaseError: If database operation fails
        """
        if not is_valid_url(original_url):
            raise InvalidURLError(
                original_url,
                reason="Invalid URL format. URL must use http:// or https:// and have a valid domain"
            )
        
        existing_short_url = await self.get_existing_short_url(original_url)
        if existing_short_url:
            return existing_short_url
        
        try:
            if not self.code_pool:
                raise DatabaseError(
                    "Short code pool is not available. Service must be initialized with a code pool."
                )
            
            short_code = await self.code_pool.get_short_code()
            code_id = decode_base62(short_code)
            
            short_url = ShortURL(
                id=code_id,
                original_url=original_url,
                short_code=short_code,
                visit_count=0
            )
            
            self.session.add(short_url)
            await self.session.flush()
            await self.session.commit()
            await self.session.refresh(short_url)
            
            return short_url
        
        except IntegrityError as e:
            await self.session.rollback()
            existing_short_url = await self.get_existing_short_url(original_url)
            if existing_short_url:
                return existing_short_url
            raise DatabaseError(
                f"Failed to create short URL: database constraint violation",
                original_error=e
            )
        except Exception as e:
            await self.session.rollback()
            if isinstance(e, (InvalidURLError, DatabaseError)):
                raise
            raise DatabaseError(
                f"Failed to create short URL: {str(e)}",
                original_error=e
            )
    
    async def get_original_url(self, short_code: str) -> Optional[ShortURL]:
        """
        Retrieve the original URL for a given short code.
        
        Args:
            short_code: The short code to look up
        
        Returns:
            ShortURL object if found, None otherwise
        """
        statement = select(ShortURL).where(ShortURL.short_code == short_code)
        result = await self.session.execute(statement)
        return result.scalar_one_or_none()
