"""
HTTP fetching with rate limiting, retry handling, and incremental crawling support.
"""

import gzip
import ssl
from typing import Optional, Dict, Any, Tuple, Callable
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError

from ..core.urls import get_domain
from ..core.http import make_basic_auth_header, create_permissive_ssl_context
from .rate_limiter import RateLimiter
from ..core.constants import DEFAULT_RATE_LIMIT_BACKOFF


class FetchResult:
    """Result of a fetch operation."""
    
    __slots__ = ('content', 'content_type', 'metadata', 'raw_bytes')
    
    def __init__(
        self,
        content: Optional[str] = None,
        content_type: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        raw_bytes: Optional[bytes] = None
    ):
        self.content = content
        self.content_type = content_type
        self.metadata = metadata or {}
        self.raw_bytes = raw_bytes  # Raw bytes for binary content (PDFs, etc.)
    
    @property
    def success(self) -> bool:
        """True if fetch succeeded with content (text or binary)."""
        return self.content is not None or self.raw_bytes is not None
    
    @property
    def not_modified(self) -> bool:
        """True if server returned 304 Not Modified."""
        return self.metadata.get('not_modified', False)
    
    @property
    def error_type(self) -> Optional[str]:
        """Error type if fetch failed."""
        return self.metadata.get('error_type')
    
    @property
    def error_message(self) -> Optional[str]:
        """Error message if fetch failed."""
        return self.metadata.get('error_message')
    
    def as_tuple(self) -> Tuple[Optional[str], Optional[str], Dict[str, Any]]:
        """Return as (content, content_type, metadata) tuple for backward compatibility."""
        return (self.content, self.content_type, self.metadata)


class Fetcher:
    """
    HTTP fetcher with rate limiting, compression handling, and error classification.
    
    Supports:
    - Per-domain rate limiting
    - Gzip decompression
    - Basic authentication
    - Conditional requests (ETag/Last-Modified for incremental crawling)
    - SSL/TLS with permissive certificate handling
    - Detailed error classification
    """
    
    DEFAULT_USER_AGENT = "DocSearchBot/1.2 (+https://github.com/AlanConstantino/doc-search)"
    
    def __init__(
        self,
        user_agent: Optional[str] = None,
        delay: float = 1.0,
        timeout: float = 30.0,
        auth: Optional[Tuple[str, str]] = None,
        auth_token: Optional[str] = None,
        rate_limiter: Optional[RateLimiter] = None,
        ssl_context: Optional[ssl.SSLContext] = None,
        log_func: Optional[Callable[[str], None]] = None,
        stats_callback: Optional[Callable[[str, int], None]] = None
    ):
        """
        Initialize the fetcher.
        
        Args:
            user_agent: User-Agent string for requests
            delay: Default delay between requests to same domain
            timeout: Request timeout in seconds
            auth: Tuple of (username, password) for Basic Auth
            auth_token: Pre-encoded Base64 auth token
            rate_limiter: Custom RateLimiter instance (created if not provided)
            ssl_context: Custom SSL context (permissive context created if not provided)
            log_func: Optional callback for logging messages
            stats_callback: Optional callback for stats updates (stat_name, value)
        """
        self.user_agent = user_agent or self.DEFAULT_USER_AGENT
        self.timeout = timeout
        self.auth = auth
        self.auth_token = auth_token
        self.rate_limiter = rate_limiter or RateLimiter(delay)
        self.ssl_context = ssl_context or create_permissive_ssl_context()
        self._log_func = log_func
        self._stats_callback = stats_callback
    
    def _log(self, message: str):
        """Log a message if logging is enabled."""
        if self._log_func:
            self._log_func(message)
    
    def _update_stat(self, stat_name: str, value: int):
        """Update a stat if stats callback is provided."""
        if self._stats_callback:
            self._stats_callback(stat_name, value)
    
    def _get_auth_header(self) -> Optional[str]:
        """Get Basic Auth header if credentials provided."""
        return make_basic_auth_header(auth=self.auth, auth_token=self.auth_token)
    
    def _build_headers(
        self,
        etag: Optional[str] = None,
        last_modified: Optional[str] = None
    ) -> Dict[str, str]:
        """Build request headers."""
        headers = {
            'User-Agent': self.user_agent,
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Accept-Encoding': 'gzip, deflate',
            'Connection': 'keep-alive',
        }
        
        # Add conditional headers for incremental crawling
        if etag:
            headers['If-None-Match'] = etag
        if last_modified:
            headers['If-Modified-Since'] = last_modified
        
        auth_header = self._get_auth_header()
        if auth_header:
            headers['Authorization'] = auth_header
        
        return headers
    
    def _decode_content(
        self,
        content_bytes: bytes,
        content_type: str,
        content_encoding: str
    ) -> str:
        """Decode response content, handling gzip and charset."""
        # Handle gzip encoding
        if 'gzip' in content_encoding.lower():
            try:
                content_bytes = gzip.decompress(content_bytes)
            except Exception:
                pass  # Fall through to raw decoding
        
        # Determine charset
        charset = 'utf-8'
        if 'charset=' in content_type:
            charset = content_type.split('charset=')[-1].split(';')[0].strip()
        
        # Decode content
        try:
            return content_bytes.decode(charset)
        except (UnicodeDecodeError, LookupError):
            return content_bytes.decode('utf-8', errors='replace')
    
    def _handle_http_error(self, e: HTTPError, domain: str) -> FetchResult:
        """Handle HTTPError and return appropriate FetchResult."""
        if e.code == 304:
            # Not Modified - content unchanged
            return FetchResult(metadata={'not_modified': True})
        
        elif e.code == 429:
            # Rate limited - back off
            retry_after = e.headers.get('Retry-After', str(DEFAULT_RATE_LIMIT_BACKOFF))
            try:
                wait_time = int(retry_after)
            except ValueError:
                wait_time = DEFAULT_RATE_LIMIT_BACKOFF
            self.rate_limiter.set_backoff(domain, wait_time)
            self._log(f"  Rate limited, backing off for {wait_time}s")
            return FetchResult(metadata={
                'error_type': 'http',
                'error_message': f'HTTP {e.code}: Rate limited (retry after {wait_time}s)'
            })
        
        elif e.code >= 500:
            self._log(f"  Server error: {e.code}")
            return FetchResult(metadata={
                'error_type': 'http',
                'error_message': f'HTTP {e.code}: Server error'
            })
        
        else:
            self._log(f"  HTTP error: {e.code}")
            return FetchResult(metadata={
                'error_type': 'http',
                'error_message': f'HTTP {e.code}'
            })
    
    def _handle_url_error(self, e: URLError) -> FetchResult:
        """Handle URLError and return appropriate FetchResult."""
        reason = str(e.reason)
        
        # Check for SSL errors
        if 'ssl' in reason.lower() or 'certificate' in reason.lower():
            self._log(f"  SSL error: {reason}")
            return FetchResult(metadata={
                'error_type': 'ssl',
                'error_message': reason
            })
        
        # Check for timeout
        elif 'timed out' in reason.lower() or 'timeout' in reason.lower():
            self._log(f"  Timeout: {reason}")
            return FetchResult(metadata={
                'error_type': 'timeout',
                'error_message': reason
            })
        
        else:
            self._log(f"  URL error: {reason}")
            return FetchResult(metadata={
                'error_type': 'network',
                'error_message': reason
            })
    
    def fetch(
        self,
        url: str,
        etag: Optional[str] = None,
        last_modified: Optional[str] = None
    ) -> FetchResult:
        """
        Fetch a URL and return a FetchResult.
        
        For incremental crawling, pass etag/last_modified from previous crawl.
        Returns FetchResult with not_modified=True if content is unchanged.
        
        Args:
            url: URL to fetch
            etag: ETag from previous fetch for conditional request
            last_modified: Last-Modified from previous fetch for conditional request
            
        Returns:
            FetchResult with content, content_type, and metadata
        """
        domain = get_domain(url)
        self.rate_limiter.wait_for_domain(domain)
        
        headers = self._build_headers(etag=etag, last_modified=last_modified)
        request = Request(url, headers=headers)
        
        try:
            response = urlopen(request, timeout=self.timeout, context=self.ssl_context)
            
            # Read content
            content_bytes = response.read()
            
            # Get headers for decoding
            content_encoding = response.headers.get('Content-Encoding', '')
            content_type = response.headers.get('Content-Type', '')
            
            # Update stats
            self._update_stat('bytes_downloaded', len(content_bytes))
            
            # Capture metadata for incremental crawling
            metadata = {
                'etag': response.headers.get('ETag'),
                'last_modified': response.headers.get('Last-Modified'),
            }
            
            # Check if binary content (PDF, etc.) - keep raw bytes
            is_binary = 'application/pdf' in content_type.lower() or \
                        'application/octet-stream' in content_type.lower()
            
            if is_binary:
                # For binary content, store raw bytes and skip decoding
                return FetchResult(
                    content=None,
                    content_type=content_type,
                    metadata=metadata,
                    raw_bytes=content_bytes
                )
            
            # Decode text content
            content = self._decode_content(content_bytes, content_type, content_encoding)
            
            return FetchResult(content=content, content_type=content_type, metadata=metadata)
            
        except HTTPError as e:
            return self._handle_http_error(e, domain)
            
        except URLError as e:
            return self._handle_url_error(e)
            
        except ssl.SSLError as e:
            message = str(e)
            self._log(f"  SSL error: {message}")
            return FetchResult(metadata={
                'error_type': 'ssl',
                'error_message': message
            })
            
        except TimeoutError as e:
            message = str(e) or 'Connection timed out'
            self._log(f"  Timeout: {message}")
            return FetchResult(metadata={
                'error_type': 'timeout',
                'error_message': message
            })
            
        except Exception as e:
            message = str(e)
            self._log(f"  Error: {message}")
            return FetchResult(metadata={
                'error_type': 'unknown',
                'error_message': message
            })
