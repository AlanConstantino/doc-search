"""
Utility functions for URL normalization and helpers.
"""

import os
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

def _enable_windows_ansi() -> bool:
    """
    Enable ANSI escape code support on Windows 10+.
    
    Windows 10 version 1607+ supports ANSI via Virtual Terminal Processing,
    but it must be explicitly enabled on the console output handle.
    
    Returns:
        True if colors are supported (or not on Windows), False otherwise.
    """
    if sys.platform != 'win32':
        return hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()
    
    if not (hasattr(sys.stdout, 'isatty') and sys.stdout.isatty()):
        return False
    
    try:
        import ctypes
        from ctypes import wintypes
        
        kernel32 = ctypes.windll.kernel32
        
        # STD_OUTPUT_HANDLE = -11
        handle = kernel32.GetStdHandle(wintypes.DWORD(-11))
        if handle == wintypes.HANDLE(-1).value:
            return False
        
        # Get current console mode
        mode = wintypes.DWORD()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        
        # ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004
        ENABLE_VTP = 0x0004
        if not (mode.value & ENABLE_VTP):
            # Try to enable it
            if not kernel32.SetConsoleMode(handle, wintypes.DWORD(mode.value | ENABLE_VTP)):
                return False
        
        return True
    except (AttributeError, ImportError, OSError, ValueError):
        # ctypes or windll not available, or console API failed
        return False



# Emoji fallbacks (DOC_SEARCH_NO_EMOJI=1 → ASCII)
_NO_EMOJI = os.environ.get('DOC_SEARCH_NO_EMOJI', '').lower() in ('1', 'true', 'yes')
_EMOJI_MAP = {
    'search': ('🔍', '[*]'),
    'docs': ('📄', '[-]'),
    'terms': ('🔤', '[#]'),
    'check': ('✓', '+'),
    'cross': ('✗', 'x'),
    'bulb': ('💡', '*'),
    'moon': ('🌙', '[D]'),
    'sun': ('☀️', '[L]'),
    'palette': ('🎨', ''),
    'books': ('📚', '[=]'),
    'chart': ('📊', '#'),
    'globe': ('🌐', '@'),
    'folder': ('📁', '>'),
    'ruler': ('📏', 'A:'),
    'sparkles': ('✨', '*'),
    'skip': ('⏭', '-'),
}


def emoji(name: str) -> str:
    """Get emoji or ASCII fallback based on DOC_SEARCH_NO_EMOJI env var."""
    pair = _EMOJI_MAP.get(name, ('', ''))
    return pair[1] if _NO_EMOJI else pair[0]

class Colors:
    """ANSI escape codes for terminal colors and styles."""
    
    # Check if terminal supports colors (enables VTP on Windows 10+)
    _supports_color = _enable_windows_ansi()
    
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
        if _enable_windows_ansi():
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
            with open(user_path, encoding='utf-8') as f:
                return _json.load(f)
        except (_json.JSONDecodeError, IOError):
            pass
    
    # Bundled defaults
    default_path = Path(__file__).parent / 'data' / 'colors.json'
    if default_path.exists():
        try:
            with open(default_path, encoding='utf-8') as f:
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


def style_info(text: str) -> str:
    """Style info text."""
    return colorize(text, *_resolve_styles('info'))


def style_success(text: str) -> str:
    """Style success text."""
    return colorize(text, *_resolve_styles('success'))


def style_error(text: str) -> str:
    """Style error text."""
    return colorize(text, *_resolve_styles('error'))


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
# Minimal English glue words only.
# Programming / docs keywords are intentionally kept so multi-word queries
# like "async with", "yield from", "for loop", "not implemented" stay multi-term
# at both index and query time (same analyzer).
STOP_WORDS = frozenset([
    # articles / demonstratives
    'a', 'an', 'the', 'this', 'that', 'these', 'those',
    # pure pronouns
    'i', 'me', 'my', 'we', 'our', 'you', 'your', 'he', 'him', 'his',
    'she', 'her', 'it', 'its', 'they', 'them', 'their', 'us',
    # copula / auxiliaries that rarely carry docs intent alone
    'am', 'are', 'was', 'were', 'be', 'been', 'being',
    'have', 'has', 'had', 'having', 'do', 'does', 'did', 'doing',
    'will', 'would', 'could', 'should', 'may', 'might', 'must', 'shall', 'can',
    # wh- / discourse glue
    'what', 'when', 'where', 'who', 'which', 'why', 'how',
    'than', 'then', 'so', 'very', 'just', 'also', 'too', 'now',
    'only', 'own', 'same', 'such', 'some', 'any', 'all', 'each',
    'every', 'both', 'few', 'more', 'most', 'other',
    # prepositions that are weak alone in prose (NOT: with/for/from/in/on/to/as/by/at)
    'of', 'about', 'above', 'after', 'again', 'against', 'below',
    'between', 'during', 'into', 'through', 'under', 'until',
    'once', 'there', 'here', 'but',
])
# Kept searchable (critical for multi-word Python/docs queries):
# and, or, not, if, else, for, from, with, as, in, on, to, by, at, is,
# no, nor, up, out, off, over, down




# Code-aware splits: CamelCase, snake_case, dotted identifiers
_CAMEL_1 = re.compile(r'([a-z0-9])([A-Z])')
_CAMEL_2 = re.compile(r'([A-Z]+)([A-Z][a-z])')
_DOTTED_ID = re.compile(r'\b[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+\b')

# Letter↔digit boundaries inside identifiers (ticket1234, 64bit, html5)
_LETTER_DIGIT = re.compile(r'([A-Za-z])(\d)')
_DIGIT_LETTER = re.compile(r'(\d)([A-Za-z])')

# Keep structured numeric forms as a single token in addition to parts:
# versions (3.12, 2.6.3), thousands (1,234), hex (0x1234).
_VERSION_RE = re.compile(r'(?<![0-9])\d+(?:\.\d+){1,4}\b')
_COMMA_NUM_RE = re.compile(r'\b\d{1,3}(?:,\d{3})+\b')
_HEX_RE = re.compile(r'\b0[xX][0-9A-Fa-f]+\b')


def _keep_token(token: str) -> bool:
    """True if token is worth indexing / querying."""
    if not token or token in STOP_WORDS:
        return False
    return len(token) > 1 or token.isdigit()


def _split_alnum_parts(token: str) -> list:
    """Split letter/digit runs so ticket1234 → ticket + 1234."""
    if not token:
        return []
    s = _LETTER_DIGIT.sub(r'\1\n\2', token)
    s = _DIGIT_LETTER.sub(r'\1\n\2', s)
    return [p for p in s.split('\n') if p]


def _split_code_token(token: str) -> list:
    """Split a single CamelCase / snake_case / alphanum token into parts (lowercased)."""
    if '_' in token:
        chunks = token.split('_')
    else:
        s = _CAMEL_2.sub(r'\1\n\2', token)
        s = _CAMEL_1.sub(r'\1\n\2', s)
        chunks = s.split('\n')
    out = []
    for chunk in chunks:
        for p in _split_alnum_parts(chunk):
            p = p.lower()
            if _keep_token(p):
                out.append(p)
    return out or ([token.lower()] if token else [])


def _add_token(tokens: list, token: str) -> None:
    if _keep_token(token):
        tokens.append(token)


def _raw_tokens(text: str) -> list:
    """Extract raw lowercase tokens with code-aware splitting (no stemming)."""
    if not text:
        return []

    tokens: list = []

    # Structured numeric forms first (before dotted-id rewrite eats the dots).
    # Lookbehind on versions lets v2.6.3 / python3.12 yield the version as one token.
    for m in _HEX_RE.finditer(text):
        whole = m.group(0).lower()
        _add_token(tokens, whole)
        payload = whole[2:]
        if len(payload) >= 2:
            _add_token(tokens, payload)
    for m in _VERSION_RE.finditer(text):
        _add_token(tokens, m.group(0))
    for m in _COMMA_NUM_RE.finditer(text):
        _add_token(tokens, m.group(0).replace(',', ''))

    # Dotted identifiers → spaces (os.path.join → os path join)
    expanded = _DOTTED_ID.sub(lambda m: m.group(0).replace('.', ' '), text)
    for m in re.finditer(r'\b[A-Za-z][A-Za-z0-9_]*\b|\b\d+[A-Za-z][A-Za-z0-9_]*\b|\b\d+\b', expanded):
        raw = m.group(0)
        # Whole hex already emitted (0x1234 + payload); skip 0x… fragments.
        if raw.lower().startswith('0x'):
            continue
        if raw.isdigit():
            _add_token(tokens, raw)
            continue
        mixed = (
            any(c.isupper() for c in raw[1:])
            or '_' in raw
            or any(c.isdigit() for c in raw)
        )
        if mixed:
            for part in _split_code_token(raw):
                _add_token(tokens, part)
            full = raw.lower()
            # Keep full form for CamelCase / snake_case / alphanum (3d, html5)
            if len(full) > 2 or (len(full) >= 2 and any(c.isdigit() for c in full)):
                _add_token(tokens, full)
        else:
            _add_token(tokens, raw.lower())
    return tokens


def _looks_numeric(token: str) -> bool:
    """True for digits, versions, hex, or other tokens Porter stemming would mangle."""
    if not token:
        return False
    if token[0].isdigit() or token.startswith('0x'):
        return True
    return any(c.isdigit() for c in token) and not token.isalpha()


def _maybe_stem(token: str, stem_fn) -> str:
    if _looks_numeric(token):
        return token
    return stem_fn(token)


def tokenize(text: str, apply_stemming: bool = False) -> list:
    """
    Tokenize text into lowercase words for indexing and search.

    Code-aware: splits CamelCase, snake_case, dotted.ids, and glued
    alphanumerics (ticket1234 → ticket + 1234). Keeps versions (3.12),
    hex (0x1234), and digit-leading tokens (3d, 7zip).
    Optional Porter stemming when apply_stemming=True (skipped for numeric tokens).
    """
    tokens = _raw_tokens(text)
    if apply_stemming:
        from .stemmer import stem
        tokens = [_maybe_stem(t, stem) for t in tokens]
    return tokens


def tokenize_with_exact(text: str, apply_stemming: bool = True):
    """
    Return (stemmed_tokens, exact_tokens).

    Stemmed forms power recall; exact (unstemmed) forms power match bonus.
    Numeric / version / hex tokens are never stemmed.
    """
    exact = _raw_tokens(text)
    if not apply_stemming:
        return list(exact), list(exact)
    from .stemmer import stem
    stemmed = [_maybe_stem(t, stem) for t in exact]
    return stemmed, exact


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
