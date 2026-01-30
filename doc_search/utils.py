"""
Utility functions for URL normalization and helpers.
"""

import re
import hashlib
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
    
    # Normalize path - preserve trailing slash for directory-like paths
    path = parsed.path or '/'
    # Only remove trailing slash if path ends with a file extension
    # This preserves /3.11/ and /library/ but normalizes /index.html/
    if path != '/' and path.endswith('/'):
        # Check if it looks like a file (common HTML extensions)
        path_without_slash = path.rstrip('/')
        file_extensions = ('.html', '.htm', '.php', '.asp', '.aspx', '.jsp', '.shtml')
        if any(path_without_slash.endswith(ext) for ext in file_extensions):
            path = path_without_slash
    
    return urlunparse((scheme, netloc, path, parsed.params, query, fragment))


def get_domain(url: str) -> str:
    """Extract domain from URL."""
    parsed = urlparse(url)
    return parsed.netloc.lower()


def is_same_domain(url1: str, url2: str) -> bool:
    """Check if two URLs are on the same domain."""
    return get_domain(url1) == get_domain(url2)


def url_to_filename(url: str) -> str:
    """Convert URL to a safe filename using hash."""
    return hashlib.sha256(url.encode()).hexdigest()[:16]


def site_hash(url: str) -> str:
    """Generate a hash for a site's base URL."""
    domain = get_domain(url)
    return hashlib.sha256(domain.encode()).hexdigest()[:12]


def resolve_url(base_url: str, href: str) -> str:
    """Resolve a relative URL against a base URL."""
    return urljoin(base_url, href)


def is_valid_url(url: str) -> bool:
    """Check if URL is valid for crawling."""
    try:
        parsed = urlparse(url)
        return parsed.scheme in ('http', 'https') and bool(parsed.netloc)
    except Exception:
        return False


def is_html_content(content_type: str) -> bool:
    """Check if content type indicates HTML."""
    if not content_type:
        return False
    content_type = content_type.lower()
    return 'text/html' in content_type or 'application/xhtml' in content_type


# Common stop words to exclude from indexing
STOP_WORDS = frozenset([
    'a', 'an', 'and', 'are', 'as', 'at', 'be', 'by', 'for', 'from',
    'has', 'he', 'in', 'is', 'it', 'its', 'of', 'on', 'or', 'that',
    'the', 'to', 'was', 'were', 'will', 'with', 'the', 'this', 'but',
    'they', 'have', 'had', 'what', 'when', 'where', 'who', 'which',
    'why', 'how', 'all', 'each', 'every', 'both', 'few', 'more',
    'most', 'other', 'some', 'such', 'no', 'nor', 'not', 'only',
    'own', 'same', 'so', 'than', 'too', 'very', 'can', 'just', 'should',
    'now', 'your', 'you', 'we', 'our', 'their', 'his', 'her', 'my',
    'me', 'him', 'them', 'us', 'i', 'am', 'been', 'being', 'do', 'does',
    'did', 'doing', 'would', 'could', 'might', 'must', 'shall', 'if',
    'then', 'else', 'there', 'here', 'about', 'above', 'after', 'again',
    'against', 'below', 'between', 'down', 'during', 'into', 'over',
    'through', 'under', 'until', 'up', 'out', 'off', 'once', 'any'
])


def tokenize(text: str) -> list:
    """
    Tokenize text into lowercase words, removing stop words.
    """
    # Convert to lowercase and extract words
    words = re.findall(r'\b[a-z][a-z0-9_]*\b', text.lower())
    # Filter out stop words and very short words
    return [w for w in words if w not in STOP_WORDS and len(w) > 1]


def format_size(size_bytes: int) -> str:
    """Format bytes as human-readable size."""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f} TB"


def format_duration(seconds: float) -> str:
    """Format seconds as human-readable duration."""
    if seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = seconds / 60
        return f"{minutes:.1f}m"
    else:
        hours = seconds / 3600
        return f"{hours:.1f}h"
