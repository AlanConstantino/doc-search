"""URL normalization and site-identity helpers."""

import hashlib
import posixpath
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse, urlunparse, urljoin, parse_qsl, urlencode


def normalize_url(url: str) -> str:
    """
    Normalize a URL to avoid duplicate crawls.
    
    - Lowercase scheme and host
    - Remove default ports (80, 443)
    - Remove fragments
    - Sort query parameters
    - Remove trailing slash (except for root)
    """
    parsed = urlparse(url)
    
    # Lowercase scheme and netloc
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()
    
    # Remove default ports
    if netloc.endswith(':80') and scheme == 'http':
        netloc = netloc[:-3]
    elif netloc.endswith(':443') and scheme == 'https':
        netloc = netloc[:-4]
    
    # Sort query parameters
    query_params = parse_qsl(parsed.query, keep_blank_values=True)
    query_params.sort()
    query = urlencode(query_params)
    
    # Remove fragment
    fragment = ''
    
    # Normalize path - resolve .. and . sequences, preserve trailing slash for directories
    path = parsed.path or '/'
    
    # Resolve .. and . in path (e.g., /a/../b -> /b, /./a -> /a)
    had_trailing_slash = path.endswith('/') and len(path) > 1
    path = posixpath.normpath(path)
    if path == '.':
        path = '/'
    
    # Restore trailing slash for directory-like paths (not files)
    if had_trailing_slash and not path.endswith('/'):
        # Check if it looks like a file (common HTML extensions)
        file_extensions = ('.html', '.htm', '.php', '.asp', '.aspx', '.jsp', '.shtml')
        if not any(path.endswith(ext) for ext in file_extensions):
            path = path + '/'
    
    return urlunparse((scheme, netloc, path, parsed.params, query, fragment))


def get_domain(url: str) -> str:
    """Extract domain from URL."""
    parsed = urlparse(url)
    return parsed.netloc.lower()


def is_same_domain(url1: str, url2: str) -> bool:
    """Check if two URLs are on the same domain."""
    return get_domain(url1) == get_domain(url2)


def hash_string(s: str, length: int = 16) -> str:
    """
    Generate a truncated SHA256 hash of a string.
    
    Args:
        s: String to hash
        length: Number of hex characters to return (max 64)
        
    Returns:
        Truncated hex digest string
    """
    return hashlib.sha256(s.encode()).hexdigest()[:length]


def url_to_filename(url: str) -> str:
    """Convert URL to a safe filename using hash."""
    return hash_string(url, length=16)


def site_hash(url: str, include_path: bool = False) -> str:
    """
    Generate a hash for a site's base URL.
    
    Args:
        url: The site URL
        include_path: If True, include the URL path in the hash (allows
                      separate storage for different paths on same domain)
    
    Returns:
        12-character hash string
    """
    if include_path:
        # Hash domain + path for separate storage per path
        parsed = urlparse(url)
        key = parsed.netloc.lower() + parsed.path.rstrip('/')
    else:
        # Hash domain only (default - one folder per domain)
        key = get_domain(url)
    return hash_string(key, length=12)


def resolve_url(base_url: str, href: str) -> str:
    """Resolve a relative URL against a base URL."""
    # Sanitize href before resolving
    href = sanitize_url(href)
    return urljoin(base_url, href)


def sanitize_url(url: str) -> str:
    """Remove control characters and clean up a URL.
    
    Strips control chars (except common whitespace), collapses whitespace,
    and encodes any remaining invalid characters.
    """
    import re as _re
    import urllib.parse as _up
    # Remove control characters (0x00-0x1F, 0x7F) except tab/newline
    url = _re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', url)
    # Strip and collapse whitespace
    url = url.strip()
    # Encode spaces that snuck in
    url = url.replace(' ', '%20')
    return url


def is_valid_url(url: str) -> bool:
    """Check if URL is valid for crawling."""
    try:
        parsed = urlparse(url)
        if not (parsed.scheme in ('http', 'https') and bool(parsed.netloc)):
            return False
        # Reject URLs with remaining control characters
        import re as _re
        if _re.search(r'[\x00-\x1f\x7f]', url):
            return False
        return True
    except Exception:
        return False


def is_html_content(content_type: str) -> bool:
    """Check if content type indicates HTML."""
    if not content_type:
        return False
    content_type = content_type.lower()
    return 'text/html' in content_type or 'application/xhtml' in content_type

