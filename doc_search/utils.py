"""
Utility functions for URL normalization and helpers.
"""

import re
import ssl
import sys
import base64
import hashlib
import posixpath
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse, urlunparse, urljoin, parse_qsl, urlencode


def create_permissive_ssl_context() -> ssl.SSLContext:
    """
    Create SSL context that skips certificate verification.
    
    This is useful for crawling documentation sites with self-signed
    certificates or internal sites where SSL verification is not needed.
    
    Warning:
        This disables SSL certificate verification, which makes connections
        vulnerable to man-in-the-middle attacks. Only use for trusted sources.
    
    Returns:
        An SSLContext configured to skip certificate verification.
    
    Example:
        >>> ctx = create_permissive_ssl_context()
        >>> urlopen(url, context=ctx)
    """
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    return ctx


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
    
    # Extended colors (256-color)
    ORANGE = '\033[38;5;208m' if _supports_color else ''
    
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


def _hex_to_ansi(hex_color: str) -> str:
    """Convert a hex color like '#FF5733' to an ANSI true color escape code."""
    hex_color = hex_color.lstrip('#')
    if len(hex_color) != 6:
        return ''
    try:
        r, g, b = int(hex_color[0:2], 16), int(hex_color[2:4], 16), int(hex_color[4:6], 16)
        return f'\033[38;2;{r};{g};{b}m'
    except ValueError:
        return ''


_STYLE_MAP = {
    'bold': '\033[1m',
    'dim': '\033[2m',
    'italic': '\033[3m',
    'underline': '\033[4m',
}


def _parse_color_value(value: str) -> tuple:
    """
    Parse a color value like '#FF5733+bold+underline' into ANSI codes.
    
    Returns:
        Tuple of ANSI escape code strings
    """
    if not value or not Colors._supports_color:
        return ()
    
    parts = value.split('+')
    codes = []
    
    # First part is the hex color
    hex_part = parts[0].strip()
    if hex_part.startswith('#'):
        ansi = _hex_to_ansi(hex_part)
        if ansi:
            codes.append(ansi)
    
    # Remaining parts are style modifiers
    for part in parts[1:]:
        style = _STYLE_MAP.get(part.strip().lower(), '')
        if style:
            codes.append(style)
    
    return tuple(codes)


def _load_color_theme() -> dict:
    """
    Load CLI color theme from colors.json.
    
    Searches in order:
    1. ~/.doc_search/colors.json (user override)
    2. Bundled data/colors.json (defaults)
    
    Returns:
        Dict mapping role names to hex color strings
    """
    import json as _json
    
    # User override
    user_path = Path.home() / '.doc_search' / 'colors.json'
    if user_path.exists():
        try:
            with open(user_path) as f:
                return _json.load(f)
        except (_json.JSONDecodeError, IOError):
            pass
    
    # Bundled defaults
    default_path = Path(__file__).parent / 'data' / 'colors.json'
    if default_path.exists():
        try:
            with open(default_path) as f:
                return _json.load(f)
        except (_json.JSONDecodeError, IOError):
            pass
    
    return {}


def _resolve_styles(role: str) -> tuple:
    """Resolve a role name to ANSI escape codes from the color theme."""
    value = _COLOR_THEME.get(role, '')
    if not value or isinstance(value, list):
        # Fallback for old list format or empty
        return ()
    return _parse_color_value(value)


# Load theme once at import time
_COLOR_THEME = _load_color_theme()


def highlight_match(text: str) -> str:
    """Highlight a matched term."""
    return colorize(text, *_resolve_styles('highlight'))


def style_title(text: str) -> str:
    """Style a title."""
    return colorize(text, *_resolve_styles('title'))


def style_url(text: str) -> str:
    """Style a URL."""
    return colorize(text, *_resolve_styles('url'))


def style_score(score: float) -> str:
    """Style a score."""
    return colorize(f"[{score:.4f}]", *_resolve_styles('score'))


def style_number(num: int) -> str:
    """Style a result number."""
    return colorize(f"{num}.", *_resolve_styles('number'))


def style_snippet(text: str) -> str:
    """Style snippet text."""
    return colorize(text, *_resolve_styles('snippet'))


def style_info(text: str) -> str:
    """Style info text."""
    return colorize(text, *_resolve_styles('info'))


def style_success(text: str) -> str:
    """Style success text."""
    return colorize(text, *_resolve_styles('success'))


def style_error(text: str) -> str:
    """Style error text."""
    return colorize(text, *_resolve_styles('error'))


def style_warning(text: str) -> str:
    """Style warning text."""
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


# Common stop words to exclude from indexing.
# These are high-frequency words that appear in almost every document and
# provide little discriminative value for search. Filtering them reduces
# index size and improves search relevance.
#
# Categories:
#   - Articles: a, an, the
#   - Prepositions: at, by, for, from, in, of, on, to, with, etc.
#   - Conjunctions: and, but, or, nor, so, etc.
#   - Pronouns: i, you, he, she, it, we, they, etc.
#   - Auxiliary verbs: am, is, are, was, were, be, been, being, etc.
#   - Modal verbs: can, could, may, might, must, shall, should, will, would
#   - Common adverbs: how, when, where, why, very, just, now, etc.
#   - Quantifiers: all, any, both, each, every, few, more, most, some, etc.
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


# Pre-compiled regex pattern for tokenization (avoids repeated compilation)
_WORD_PATTERN = re.compile(r'\b[a-z][a-z0-9_]*\b')


def tokenize(text: str, apply_stemming: bool = False) -> list:
    """
    Tokenize text into lowercase words for indexing and search.
    
    This function performs the following transformations:
    
    1. **Case normalization**: All text is converted to lowercase.
    
    2. **Word extraction**: Uses regex pattern ``[a-z][a-z0-9_]*`` to extract
       words that start with a letter and contain only letters, digits, or
       underscores. This means:
       - Words must start with a-z (not numbers or symbols)
       - Words can contain digits after the first letter (e.g., "python3")
       - Underscores are allowed (e.g., "my_function")
       - Punctuation and special characters are stripped
    
    3. **Stop word removal**: Common English words (articles, prepositions,
       pronouns, etc.) are filtered out. See ``STOP_WORDS`` for the full list.
       These words appear in nearly every document and don't help distinguish
       between documents.
    
    4. **Short word filtering**: Single-character tokens are removed since
       they're typically not meaningful for search (e.g., "a", "I" are already
       stop words, and other single letters are usually noise).
    
    5. **Optional stemming**: When ``apply_stemming=True``, words are reduced
       to their root form using the Porter Stemming algorithm (e.g.,
       "running" → "run", "files" → "file").
    
    Args:
        text: The input text to tokenize.
        apply_stemming: If True, apply Porter stemming to each token.
            Default is False.
    
    Returns:
        A list of processed tokens (lowercase strings).
    
    Examples:
        >>> tokenize("The quick brown fox")
        ['quick', 'brown', 'fox']
        
        >>> tokenize("Python3 programming is fun!")
        ['python3', 'programming', 'fun']
        
        >>> tokenize("running files", apply_stemming=True)
        ['run', 'file']
        
        >>> tokenize("A B C test")  # Single letters filtered
        ['test']
    
    Note:
        - Numbers alone are not tokenized (must start with a letter)
        - Email addresses and URLs are split at punctuation
        - Non-ASCII characters are ignored (English-only tokenization)
    """
    # Convert to lowercase and extract words using pre-compiled pattern
    words = _WORD_PATTERN.findall(text.lower())
    
    # Filter out stop words and single-character words
    # Using set membership check (STOP_WORDS is already a frozenset)
    tokens = [w for w in words if len(w) > 1 and w not in STOP_WORDS]
    
    # Apply stemming if requested
    if apply_stemming:
        from .stemmer import stem
        tokens = [stem(t) for t in tokens]
    
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


def make_basic_auth_header(
    auth: Optional[Tuple[str, str]] = None,
    auth_token: Optional[str] = None
) -> Optional[str]:
    """
    Generate Basic Auth header from credentials or token.
    
    This function creates the value for an HTTP Authorization header using
    Basic authentication. It supports two modes:
    
    1. Pre-encoded token: If ``auth_token`` is provided, it's used directly
       (after stripping any "Basic " prefix the user may have included).
    
    2. Username/password: If ``auth`` tuple is provided, the credentials are
       Base64-encoded in the standard "username:password" format.
    
    The token takes priority over username/password if both are provided.
    
    Args:
        auth: Optional tuple of (username, password) for Basic authentication.
        auth_token: Optional pre-encoded Base64 token. May optionally include
                    the "Basic " prefix (it will be normalized).
    
    Returns:
        The full Authorization header value (e.g., "Basic dXNlcjpwYXNz") or
        None if no credentials are provided.
    
    Examples:
        >>> make_basic_auth_header(auth=("user", "pass"))
        'Basic dXNlcjpwYXNz'
        
        >>> make_basic_auth_header(auth_token="dXNlcjpwYXNz")
        'Basic dXNlcjpwYXNz'
        
        >>> make_basic_auth_header(auth_token="Basic dXNlcjpwYXNz")
        'Basic dXNlcjpwYXNz'
        
        >>> make_basic_auth_header()
        None
    """
    # Pre-encoded token takes priority
    if auth_token:
        # Remove 'Basic ' prefix if user included it
        token = auth_token
        if token.lower().startswith('basic '):
            token = token[6:]
        return f"Basic {token}"
    
    # Otherwise encode from username/password
    if auth:
        username, password = auth
        credentials = f"{username}:{password}"
        encoded = base64.b64encode(credentials.encode()).decode()
        return f"Basic {encoded}"
    
    return None
