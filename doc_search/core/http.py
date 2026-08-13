"""HTTP helpers used by crawl and extract (no CLI / terminal deps)."""

import base64
import ssl
from typing import Optional, Tuple


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

