"""
Utility functions for URL normalization and helpers.
"""

import re
import sys
import hashlib
import posixpath
from urllib.parse import urlparse, urlunparse, urljoin, parse_qsl, urlencode


# ============================================================================
# ANSI Terminal Colors & Formatting
# ============================================================================

class Colors:
    """ANSI escape codes for terminal colors and styles."""
    
    # Check if terminal supports colors
    _supports_color = hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()
    
    # Reset
    RESET = '\033[0m' if _supports_color else ''
    
    # Styles
    BOLD = '\033[1m' if _supports_color else ''
    DIM = '\033[2m' if _supports_color else ''
    ITALIC = '\033[3m' if _supports_color else ''
    UNDERLINE = '\033[4m' if _supports_color else ''
    
    # Foreground colors
    BLACK = '\033[30m' if _supports_color else ''
    RED = '\033[31m' if _supports_color else ''
    GREEN = '\033[32m' if _supports_color else ''
    YELLOW = '\033[33m' if _supports_color else ''
    BLUE = '\033[34m' if _supports_color else ''
    MAGENTA = '\033[35m' if _supports_color else ''
    CYAN = '\033[36m' if _supports_color else ''
    WHITE = '\033[37m' if _supports_color else ''
    
    # Bright foreground colors
    BRIGHT_BLACK = '\033[90m' if _supports_color else ''
    BRIGHT_RED = '\033[91m' if _supports_color else ''
    BRIGHT_GREEN = '\033[92m' if _supports_color else ''
    BRIGHT_YELLOW = '\033[93m' if _supports_color else ''
    BRIGHT_BLUE = '\033[94m' if _supports_color else ''
    BRIGHT_MAGENTA = '\033[95m' if _supports_color else ''
    BRIGHT_CYAN = '\033[96m' if _supports_color else ''
    BRIGHT_WHITE = '\033[97m' if _supports_color else ''
    
    @classmethod
    def disable(cls):
        """Disable all colors."""
        for attr in dir(cls):
            if attr.isupper() and not attr.startswith('_'):
                setattr(cls, attr, '')
    
    @classmethod
    def enable(cls):
        """Re-enable colors if terminal supports them."""
        if hasattr(sys.stdout, 'isatty') and sys.stdout.isatty():
            cls._supports_color = True
            # Re-apply colors
            cls.RESET = '\033[0m'
            cls.BOLD = '\033[1m'
            cls.DIM = '\033[2m'
            cls.ITALIC = '\033[3m'
            cls.UNDERLINE = '\033[4m'
            cls.BLACK = '\033[30m'
            cls.RED = '\033[31m'
            cls.GREEN = '\033[32m'
            cls.YELLOW = '\033[33m'
            cls.BLUE = '\033[34m'
            cls.MAGENTA = '\033[35m'
            cls.CYAN = '\033[36m'
            cls.WHITE = '\033[37m'
            cls.BRIGHT_BLACK = '\033[90m'
            cls.BRIGHT_RED = '\033[91m'
            cls.BRIGHT_GREEN = '\033[92m'
            cls.BRIGHT_YELLOW = '\033[93m'
            cls.BRIGHT_BLUE = '\033[94m'
            cls.BRIGHT_MAGENTA = '\033[95m'
            cls.BRIGHT_CYAN = '\033[96m'
            cls.BRIGHT_WHITE = '\033[97m'


def colorize(text: str, *styles) -> str:
    """Apply color/style codes to text."""
    if not styles:
        return text
    return ''.join(styles) + text + Colors.RESET


def highlight_match(text: str) -> str:
    """Highlight a matched term with bold + cyan."""
    return colorize(text, Colors.BOLD, Colors.CYAN)


def style_title(text: str) -> str:
    """Style a title with bold + bright white."""
    return colorize(text, Colors.BOLD, Colors.BRIGHT_WHITE)


def style_url(text: str) -> str:
    """Style a URL with blue + underline."""
    return colorize(text, Colors.BLUE, Colors.UNDERLINE)


def style_score(score: float) -> str:
    """Style a score with yellow."""
    return colorize(f"[{score:.4f}]", Colors.YELLOW)


def style_number(num: int) -> str:
    """Style a result number."""
    return colorize(f"{num}.", Colors.BRIGHT_MAGENTA, Colors.BOLD)


def style_snippet(text: str) -> str:
    """Style snippet text with dim."""
    return colorize(text, Colors.DIM)


def style_info(text: str) -> str:
    """Style info text with bright black (gray)."""
    return colorize(text, Colors.BRIGHT_BLACK)


def style_success(text: str) -> str:
    """Style success text with green."""
    return colorize(text, Colors.GREEN)


def style_error(text: str) -> str:
    """Style error text with red."""
    return colorize(text, Colors.RED)


def style_warning(text: str) -> str:
    """Style warning text with yellow."""
    return colorize(text, Colors.YELLOW)


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


def tokenize(text: str, stem: bool = False) -> list:
    """
    Tokenize text into lowercase words, removing stop words.
    
    Args:
        text: Text to tokenize.
        stem: Whether to apply Porter stemming to tokens.
        
    Returns:
        List of tokens.
    """
    # Convert to lowercase and extract words
    words = re.findall(r'\b[a-z][a-z0-9_]*\b', text.lower())
    # Filter out stop words and very short words
    tokens = [w for w in words if w not in STOP_WORDS and len(w) > 1]
    
    # Apply stemming if requested
    if stem:
        from .stemmer import stem as stem_word
        tokens = [stem_word(t) for t in tokens]
    
    return tokens


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
